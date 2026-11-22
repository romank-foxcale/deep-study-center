"""Local dictation with Whisper (SPEC §27): settings, the one-time model download, and transcription."""

import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from dsc import actions, dictation, state
from dsc.api import create_app


def act(db, jobs, **a):
    actions.dispatch(db, jobs, a)
    return state.snapshot(db)


def fake_model_files(size="base"):
    repo = dictation.MODELS[size]["repo"].replace("/", "--")
    snap = dictation.models_dir() / f"models--{repo}" / "snapshots" / "abc123"
    snap.mkdir(parents=True, exist_ok=True)
    for name in ("config.json", "model.bin", "tokenizer.json"):
        (snap / name).write_text("x")
    return snap


class FakeSegment:
    def __init__(self, text):
        self.text = text


class FakeInfo:
    language = "en"


class FakeWhisper:
    def __init__(self):
        self.paths = []

    def transcribe(self, path, **kw):
        self.paths.append(path)
        assert Path(path).read_bytes() == b"opus-audio"
        return iter([FakeSegment(" I think the projection "), FakeSegment(" is a shadow. ")]), FakeInfo()


def test_settings_default_to_the_browser_and_validate(env):
    db, jobs, _ = env
    d = act(db, jobs, type="setDictation")["dictation"]
    assert d["mode"] == "browser" and d["model"] == "base" and not d["ready"]
    assert [m["id"] for m in d["models"]] == ["base", "small"] and not any(m["installed"] for m in d["models"])
    d = act(db, jobs, type="setDictation", mode="local", model="small")["dictation"]
    assert d["mode"] == "local" and d["model"] == "small"
    with pytest.raises(actions.ActionError):
        actions.dispatch(db, jobs, {"type": "setDictation", "mode": "cloud"})
    with pytest.raises(actions.ActionError):
        actions.dispatch(db, jobs, {"type": "downloadDictationModel", "model": "huge"})


def test_the_download_job_installs_the_model_and_reports_progress(env, monkeypatch):
    db, jobs, _ = env
    import huggingface_hub

    def fake_download(repo, cache_dir, allow_patterns):
        assert repo == "Systran/faster-whisper-base" and "model.bin" in allow_patterns
        assert Path(cache_dir) == dictation.models_dir()
        fake_model_files("base")
        return cache_dir
    monkeypatch.setattr(huggingface_hub, "snapshot_download", fake_download)
    s = act(db, jobs, type="downloadDictationModel", model="base")
    job = next(j for j in s["jobs"] if j["kind"] == "dictation_model")
    assert job["status"] == "done" and job["progress"][-1] == "downloaded 100%"
    assert s["dictation"]["models"][0]["installed"]
    s = act(db, jobs, type="setDictation", mode="local")
    assert s["dictation"]["ready"]
    act(db, jobs, type="downloadDictationModel", model="base")  # already there: no second job
    assert len([j for j in state.snapshot(db)["jobs"] if j["kind"] == "dictation_model"]) == 1
    s = act(db, jobs, type="removeDictationModel", model="base")
    assert not s["dictation"]["models"][0]["installed"] and not s["dictation"]["ready"]


def test_an_incomplete_download_fails_the_job(env, monkeypatch):
    db, jobs, _ = env
    import huggingface_hub
    monkeypatch.setattr(huggingface_hub, "snapshot_download", lambda repo, cache_dir, allow_patterns: cache_dir)
    s = act(db, jobs, type="downloadDictationModel", model="small")
    job = next(j for j in s["jobs"] if j["kind"] == "dictation_model")
    assert job["status"] == "failed" and "incomplete" in job["error"]


def test_transcribe_returns_the_text_and_deletes_the_audio(env, monkeypatch):
    db, jobs, _ = env
    fake = FakeWhisper()
    monkeypatch.setattr(dictation, "_model", lambda size: fake)
    client = TestClient(dictation_app(db, jobs))
    r = client.post("/api/transcribe", content=b"opus-audio", headers={"Content-Type": "audio/webm"})
    assert r.status_code == 200 and r.json()["text"] == "I think the projection is a shadow."
    assert fake.paths and not os.path.exists(fake.paths[0])  # the audio is not kept
    assert client.post("/api/transcribe", content=b"").json()["text"] == ""


def test_transcribe_without_a_model_is_a_clear_error(env):
    db, jobs, _ = env
    client = TestClient(dictation_app(db, jobs))
    r = client.post("/api/transcribe", content=b"opus-audio")
    assert r.status_code == 400 and "not downloaded" in r.json()["detail"]
    r = client.post("/api/transcribe", content=b"x" * (dictation.MAX_AUDIO + 1))
    assert r.status_code == 400 and "too long" in r.json()["detail"]


def dictation_app(db, jobs):
    return create_app(db=db, jobs=jobs)
