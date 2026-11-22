"""Local dictation with Whisper (SPEC §27, TODO C2).

Why: the browser's speech API sends the learner's voice to Google, and desktop webviews may not have it at all. Local
dictation keeps the audio on this computer: the page records one phrase at a time (``MediaRecorder``) and posts it to
``POST /api/transcribe``; a faster-whisper model on the CPU turns it into text.

- Mode (meta ``dictation_mode``): "browser" (the Web Speech API) or "local". The page also uses local dictation when
  the browser has no speech API and a model is installed.
- Models (meta ``dictation_model``): "base" (default, about 140 MB, about 2 s for a short phrase on a laptop CPU) or
  "small" (about 460 MB, more accurate, about 3x slower). They are downloaded once, by the job ``dictation_model``,
  into ``<workspace>/models/whisper``; after that, dictation works with no network.
- The model is loaded on the first phrase and kept in memory. Audio is never stored.
"""

from __future__ import annotations

import os
import tempfile
import threading
import time
from pathlib import Path
from typing import TYPE_CHECKING

from .db import DB, workspace

if TYPE_CHECKING:
    from .jobs import Jobs

MODES = ("browser", "local")
MODELS = {
    "base": {"repo": "Systran/faster-whisper-base", "mb": 142, "label": "Base: fast, about 140 MB"},
    "small": {"repo": "Systran/faster-whisper-small", "mb": 464, "label": "Small: more accurate, slower, about 460 MB"},
}
DEFAULT_MODEL = "base"
MAX_AUDIO = 8 * 1024 * 1024  # one phrase; a minute of opus audio is far below this

_lock = threading.Lock()
_loaded: dict[str, object] = {}


class DictationError(Exception):
    pass


def models_dir() -> Path:
    return workspace() / "models" / "whisper"


def available() -> bool:
    """faster-whisper is installed (it is a normal dependency; this guards a broken install)."""
    try:
        import faster_whisper  # noqa: F401
    except Exception:
        return False
    return True


def _snapshot(size: str) -> Path | None:
    """The folder of a fully downloaded model, or None."""
    repo = MODELS[size]["repo"].replace("/", "--")
    snaps = models_dir() / f"models--{repo}" / "snapshots"
    for d in sorted(snaps.glob("*")) if snaps.exists() else []:
        if (d / "model.bin").exists() and (d / "config.json").exists():
            return d
    return None


def installed(size: str) -> bool:
    return size in MODELS and _snapshot(size) is not None


def mode(db: DB) -> str:
    m = db.meta("dictation_mode") or "browser"
    return m if m in MODES else "browser"


def model(db: DB) -> str:
    m = db.meta("dictation_model") or DEFAULT_MODEL
    return m if m in MODELS else DEFAULT_MODEL


def status(db: DB) -> dict:
    return {"mode": mode(db), "model": model(db), "available": available(),
            "models": [{"id": k, "label": v["label"], "mb": v["mb"], "installed": installed(k)} for k, v in MODELS.items()],
            "ready": available() and installed(model(db))}


def set_settings(db: DB, mode_: str | None = None, model_: str | None = None) -> None:
    if mode_ is not None:
        if mode_ not in MODES:
            raise DictationError(f"unknown dictation mode {mode_!r}")
        db.set_meta("dictation_mode", mode_)
    if model_ is not None:
        if model_ not in MODELS:
            raise DictationError(f"unknown model {model_!r}")
        db.set_meta("dictation_model", model_)


# ---------------------------------------------------------------- download (job "dictation_model")

_LONG = "\\\\?\\"  # the Windows prefix for paths longer than 260 characters


def _size_mb(path: Path) -> float:
    total = 0
    top = str(Path(path).resolve())
    if os.name == "nt" and not top.startswith(_LONG):
        top = _LONG + top  # long paths: the partial download's name can pass the 260-character limit
    for root, _, files in os.walk(top):
        for f in files:
            try:
                total += os.path.getsize(os.path.join(root, f))
            except OSError:
                pass
    return total / 1e6


def run_download(jobs: Jobs, jid: int, d: dict) -> dict:
    size = d["model"]
    if size not in MODELS:
        raise ValueError(f"unknown model {size!r}")
    if installed(size):
        return {"model": size, "already": True}
    from huggingface_hub import snapshot_download

    target = models_dir()
    target.mkdir(parents=True, exist_ok=True)
    repo, total = MODELS[size]["repo"], MODELS[size]["mb"]
    before = _size_mb(target)
    done = threading.Event()

    def report() -> None:
        # The download library has no progress hook we can use from a job, so watch the models folder grow (the
        # partial file is not inside the model's own folder while it downloads).
        last = -1
        while not done.wait(1.0):
            pct = max(0, min(99, int((_size_mb(target) - before) / total * 100)))
            if pct != last:
                jobs.progress(jid, f"downloaded {pct}%")
                last = pct

    # Plain HTTP instead of the "xet" transfer: xet assembles the file elsewhere and moves it in at the end, so the
    # folder would show no progress (and it keeps logs in the home folder).
    from huggingface_hub import constants as hf_constants
    xet_before = hf_constants.HF_HUB_DISABLE_XET
    hf_constants.HF_HUB_DISABLE_XET = True
    watcher = threading.Thread(target=report, daemon=True)
    watcher.start()
    try:
        snapshot_download(repo, cache_dir=str(target),
                          allow_patterns=["config.json", "model.bin", "tokenizer.json", "vocabulary.*", "preprocessor_config.json"])
    finally:
        hf_constants.HF_HUB_DISABLE_XET = xet_before
        done.set()
        watcher.join(timeout=3)
    if not installed(size):
        raise RuntimeError("the download finished but the model files are incomplete; try again")
    jobs.progress(jid, "downloaded 100%")
    return {"model": size}


def start_download(db: DB, jobs: Jobs, size: str) -> None:
    if size not in MODELS:
        raise DictationError(f"unknown model {size!r}")
    if not available():
        raise DictationError("local dictation is not installed (the faster-whisper package is missing)")
    if installed(size) or jobs.active("dictation_model", model=size):
        return
    jobs.enqueue("dictation_model", f"Download the dictation model ({size})", {"model": size})


def remove(size: str) -> None:
    import shutil
    if size not in MODELS:
        raise DictationError(f"unknown model {size!r}")
    with _lock:
        _loaded.pop(size, None)
    shutil.rmtree(models_dir() / f"models--{MODELS[size]['repo'].replace('/', '--')}", ignore_errors=True)


# ---------------------------------------------------------------- transcription

def _model(size: str):
    with _lock:
        m = _loaded.get(size)
        if m is None:
            snap = _snapshot(size)
            if snap is None:
                raise DictationError(f"the {size} dictation model is not downloaded yet (Settings → Dictation)")
            from faster_whisper import WhisperModel
            m = WhisperModel(str(snap), device="cpu", compute_type="int8")  # a local folder: no network
            _loaded.clear()  # keep one model in memory
            _loaded[size] = m
        return m


def transcribe(db: DB, audio: bytes, language: str | None = None) -> dict:
    """One recorded phrase (webm/opus, ogg, wav, …) → its text. The audio goes to a temporary file and is deleted."""
    if not audio:
        return {"text": "", "seconds": 0.0}
    if len(audio) > MAX_AUDIO:
        raise DictationError("the recording is too long; dictate in shorter phrases")
    if not available():
        raise DictationError("local dictation is not installed (the faster-whisper package is missing)")
    m = _model(model(db))
    lang = (language or "").split("-")[0].lower() or None
    t = time.time()
    fd, path = tempfile.mkstemp(suffix=".audio")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(audio)
        try:
            segments, info = m.transcribe(path, beam_size=1, vad_filter=True, language=lang,
                                          condition_on_previous_text=False)
            text = " ".join(s.text.strip() for s in segments).strip()
        except Exception as e:  # undecodable audio, or a language Whisper does not know
            if lang:  # retry once with language detection
                segments, info = m.transcribe(path, beam_size=1, vad_filter=True, condition_on_previous_text=False)
                text = " ".join(s.text.strip() for s in segments).strip()
            else:
                raise DictationError(f"could not read the recording: {e}") from e
    finally:
        try:
            os.remove(path)
        except OSError:
            pass
    return {"text": text, "language": getattr(info, "language", None), "seconds": round(time.time() - t, 2)}
