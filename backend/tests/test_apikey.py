"""The Claude API provider with the learner's own key (SPEC §25). A fake SDK client: no network, no real keychain."""

from types import SimpleNamespace as NS

import anthropic
import pytest

from dsc import actions, apikey, providers, state


@pytest.fixture
def keychain(monkeypatch):
    store: dict = {}
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setattr(apikey, "_read", lambda: store.get("k"))
    monkeypatch.setattr(apikey, "_write", lambda v: store.pop("k", None) if v is None else store.__setitem__("k", v))
    apikey._cache.clear()
    yield store
    apikey._cache.clear()


KEY = "sk-ant-api03-" + "x" * 40


class FakeStream:
    def __init__(self, msg):
        self.msg = msg

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def get_final_message(self):
        return self.msg


def fake_client(monkeypatch, replies, calls):
    class Client:
        def __init__(self, **kw):
            calls.append(("client", kw))
            self.beta = NS(messages=NS(stream=self.stream))
            self.models = NS(list=lambda **kw: [])

        def stream(self, **kw):
            calls.append(("stream", kw))
            return FakeStream(replies.pop(0))
    monkeypatch.setattr(anthropic, "Anthropic", Client)


def msg(text, stop="end_turn", extra=()):
    return NS(content=[*extra, NS(type="text", text=text)], stop_reason=stop)


def test_key_lives_in_the_keychain_and_never_in_the_snapshot(env, keychain, monkeypatch):
    db, jobs, _ = env
    fake_client(monkeypatch, [], [])
    assert state.snapshot(db)["apiKey"] == {"set": False, "source": None}
    with pytest.raises(actions.ActionError):
        actions.dispatch(db, jobs, {"type": "setApiKey", "key": "not-a-key"})
    actions.dispatch(db, jobs, {"type": "setApiKey", "key": KEY})
    s = state.snapshot(db)
    assert keychain["k"] == KEY and s["apiKey"] == {"set": True, "source": "keychain"}
    assert KEY not in str(s) and not db.one("SELECT 1 FROM meta WHERE value LIKE 'sk-ant-%'")
    assert next(p for p in s["providers"] if p["id"] == "anthropic")["detected"]
    actions.dispatch(db, jobs, {"type": "useApiForAll"})
    routes = {r["role"]: (r["provider"], r["model"]) for r in state.snapshot(db)["routes"]}
    assert routes["Research"] == ("anthropic", "opus") and routes["Fact-check"] == ("anthropic", "opus")
    assert routes["Tutor chat"] == ("anthropic", "sonnet")
    actions.dispatch(db, jobs, {"type": "clearApiKey"})
    assert "k" not in keychain and not state.snapshot(db)["apiKey"]["set"]


def test_rejected_key_is_not_stored(env, keychain, monkeypatch):
    db, jobs, _ = env

    class Client:
        def __init__(self, **kw):
            def deny(**kw):
                raise anthropic.AuthenticationError("bad key", response=NS(status_code=401, headers={}, request=None), body=None)
            self.models = NS(list=deny)
    monkeypatch.setattr(anthropic, "Anthropic", Client)
    with pytest.raises(actions.ActionError, match="rejected"):
        actions.dispatch(db, jobs, {"type": "setApiKey", "key": KEY})
    assert "k" not in keychain


def test_structured_call(keychain, monkeypatch, tmp_path):
    keychain["k"] = KEY
    calls = []
    fake_client(monkeypatch, [msg('{"n": 4}', extra=[NS(type="thinking", thinking="")])], calls)
    schema = {"type": "object", "required": ["n"], "properties": {"n": {"type": "integer", "minimum": 0},
                                                                    "items": {"type": "array", "minItems": 3, "items": {"type": "string"}}}}
    out = providers.AnthropicAPI().run(providers.Call(prompt="count", schema=schema, model="opus"), tmp_path)
    assert out == {"n": 4}
    kw = calls[1][1]
    assert kw["model"] == "claude-opus-5-5" and kw["fallbacks"] == "default" and kw["betas"] == ["server-side-fallback-2026-07-01"]
    fmt = kw["output_config"]["format"]["schema"]
    assert kw["output_config"]["effort"] == "high" and fmt["additionalProperties"] is False
    assert "minimum" not in str(fmt) and "'minItems': 1" in str(fmt) and "tools" not in kw
    assert calls[0][1]["api_key"] == KEY


def test_web_research_resumes_paused_turns_and_asks_json_in_the_prompt(keychain, monkeypatch, tmp_path):
    keychain["k"] = KEY
    calls, events = [], []
    search = NS(type="server_tool_use", name="web_search", input={"query": "chain rule"})
    fake_client(monkeypatch, [msg("", stop="pause_turn", extra=[search]), msg('Done. {"ok": true}')], calls)
    out = providers.AnthropicAPI().run(providers.Call(prompt="research", schema={"type": "object", "properties": {"ok": {"type": "boolean"}}},
                                                      model="sonnet", tools=("WebSearch", "WebFetch"), on_event=events.append), tmp_path)
    assert out == {"ok": True} and events == ["searching: chain rule"]
    first, second = calls[1][1], calls[2][1]
    assert first["model"] == "claude-sonnet-5-5" and [t["type"] for t in first["tools"]] == ["web_search_20260209", "web_fetch_20260209"]
    assert "output_config" not in first and "JSON Schema" in first["messages"][0]["content"]
    assert second["messages"][1]["role"] == "assistant" and len(second["messages"]) == 2


def test_refusal_and_missing_key(keychain, monkeypatch, tmp_path):
    with pytest.raises(providers.ProviderUnavailable):
        providers.AnthropicAPI().run(providers.Call(prompt="x"), tmp_path)
    keychain["k"] = KEY
    apikey._cache.clear()
    fake_client(monkeypatch, [msg("", stop="refusal")], [])
    with pytest.raises(providers.ProviderError, match="declined"):
        providers.AnthropicAPI().run(providers.Call(prompt="x"), tmp_path)


def test_fallback_order_ends_with_the_api(keychain, monkeypatch, tmp_path):
    keychain["k"] = KEY
    seen = []
    for name in ("codex", "claude"):
        monkeypatch.setattr(providers.PROVIDERS[name], "run",
                            lambda call, cwd, n=name: (seen.append(n), (_ for _ in ()).throw(providers.ProviderUnavailable(n)))[1])
    monkeypatch.setattr(providers.PROVIDERS["anthropic"], "run", lambda call, cwd: (seen.append(("anthropic", call.model)), "ok")[1])
    out, used = providers.run_with_fallback({"provider": "codex", "model": "default"}, providers.Call(prompt="x", model="opus"), tmp_path)
    assert out == "ok" and used == "anthropic" and seen == ["codex", "claude", ("anthropic", "opus")]
