"""Agent-CLI providers: drive the user's own logged-in CLIs, so their subscriptions are used.

Policy (docs/SPEC.md §4.1): the user signs in to the unmodified Claude Code binary with their own
subscription; this app is single-user and local. Never offer this login to other users.

Every call runs in a fresh, empty job folder inside the workspace (``claude -p`` would run a
project's hooks and MCP servers from its cwd), with built-in tools disabled unless the job needs
web research, and with learner/web text passed as data inside tags.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Callable


class ProviderError(RuntimeError):
    pass


class ProviderUnavailable(ProviderError):
    pass


@dataclass
class Call:
    prompt: str
    schema: dict | None = None
    model: str = "sonnet"
    system: str = ""
    tools: tuple[str, ...] = ()       # e.g. ("WebSearch", "WebFetch") for research jobs
    timeout: int = 600
    max_turns: int | None = None
    on_event: Callable[[str], None] | None = None  # live progress (web searches/fetches), where supported


class Provider:
    name = "base"
    binary = ""

    def available(self) -> bool:
        return bool(self.binary and shutil.which(self.binary))

    def run(self, call: Call, cwd: Path) -> dict | str:
        raise NotImplementedError


class ClaudeCLI(Provider):
    name, binary = "claude", "claude"

    def command(self, call: Call) -> list[str]:
        fmt = ["stream-json", "--verbose"] if call.on_event else ["json"]
        cmd = [shutil.which(self.binary) or self.binary, "-p",
               "--output-format", *fmt, "--model", call.model,
               "--tools", ",".join(call.tools),
               "--strict-mcp-config", "--setting-sources", "user",
               "--no-session-persistence", "--permission-prompts", "none"]
        if call.tools:
            cmd += ["--allowedTools", ",".join(call.tools)]
        if call.schema:
            cmd += ["--json-schema", json.dumps(call.schema)]
        if call.system:
            cmd += ["--append-system-prompt", call.system]
        if call.max_turns:
            cmd += ["--max-turns", str(call.max_turns)]
        return cmd

    def run(self, call: Call, cwd: Path) -> dict | str:
        if not self.available():
            raise ProviderUnavailable("claude CLI not found on PATH")
        cwd.mkdir(parents=True, exist_ok=True)
        env = {k: v for k, v in os.environ.items() if k != "ANTHROPIC_API_KEY"}  # use the subscription login
        if call.on_event:
            return self._run_streaming(call, cwd, env)
        try:
            proc = subprocess.run(self.command(call), input=call.prompt, capture_output=True, text=True,
                                  encoding="utf-8", cwd=cwd, timeout=call.timeout, env=env)
        except subprocess.TimeoutExpired as e:
            raise ProviderError(f"claude timed out after {call.timeout}s") from e
        return parse_claude_output(proc.stdout, proc.stderr, proc.returncode, structured=call.schema is not None)

    def _run_streaming(self, call: Call, cwd: Path, env: dict) -> dict | str:
        """stream-json: report each web search / page fetch as it happens, then parse the `result` event."""
        proc = subprocess.Popen(self.command(call), stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                text=True, encoding="utf-8", errors="replace", cwd=cwd, env=env)
        killed = threading.Event()
        timer = threading.Timer(call.timeout, lambda: (killed.set(), proc.kill()))
        timer.start()
        last, stderr = "", ""
        try:
            proc.stdin.write(call.prompt)
            proc.stdin.close()
            for line in proc.stdout:
                line = line.strip()
                if not line:
                    continue
                try:
                    if json.loads(line).get("type") == "result":
                        last = line  # other events (e.g. task_summary) can follow the result
                except (json.JSONDecodeError, AttributeError):
                    continue
                for msg in describe_event(line):
                    call.on_event(msg)
            stderr = proc.stderr.read()
            proc.wait()
        finally:
            timer.cancel()
        if killed.is_set():
            raise ProviderError(f"claude timed out after {call.timeout}s")
        return parse_claude_output(last, stderr, proc.returncode or 0, structured=call.schema is not None)


def describe_event(line: str) -> list[str]:
    """Human-readable progress from one stream-json line (web searches and fetches only)."""
    try:
        d = json.loads(line)
    except json.JSONDecodeError:
        return []
    if d.get("type") != "assistant":
        return []
    out = []
    for c in (d.get("message") or {}).get("content") or []:
        if c.get("type") != "tool_use":
            continue
        inp = c.get("input") or {}
        if c.get("name") == "WebSearch" and inp.get("query"):
            out.append(f'searching: {inp["query"]}'[:160])
        elif c.get("name") == "WebFetch" and inp.get("url"):
            out.append(f'reading: {inp["url"]}'[:160])
    return out


def parse_claude_output(stdout: str, stderr: str, code: int, structured: bool) -> dict | str:
    try:
        data = json.loads(stdout.strip().splitlines()[-1]) if stdout.strip() else None
    except (json.JSONDecodeError, IndexError):
        data = None
    if not isinstance(data, dict):
        raise ProviderError(f"claude exited {code}: {(stderr or stdout).strip()[:400]}")
    if data.get("is_error") or data.get("subtype") not in (None, "success"):
        msg = str(data.get("result") or data.get("subtype") or "unknown error")
        if "limit" in msg.lower():
            raise ProviderUnavailable(f"rate limited: {msg[:200]}")
        raise ProviderError(msg[:400])
    if structured:
        out = data.get("structured_output")
        if out is None:  # some versions only put it in result as JSON text
            try:
                out = json.loads(data.get("result") or "")
            except json.JSONDecodeError as e:
                raise ProviderError("no structured output in claude result") from e
        return out
    return str(data.get("result", ""))


class CodexCLI(Provider):
    """ChatGPT subscription via `codex exec` (non-interactive mode).

    Prompt on stdin (`-`), read-only sandbox, final message via `-o <file>`, structured output via
    `--output-schema <file>`. Docs: learn.chatgpt.com/docs/non-interactive-mode.
    """
    name, binary = "codex", "codex"

    def command(self, call: Call, cwd: Path, out_file: Path, schema_file: Path | None) -> list[str]:
        cmd = [shutil.which(self.binary) or self.binary]
        if "WebSearch" in call.tools:
            cmd += ["--search"]  # a top-level option: `codex exec --search` is rejected (codex-cli 0.163)
        cmd += ["exec", "--skip-git-repo-check", "--ephemeral",
                "--sandbox", "read-only", "--cd", str(cwd), "--output-last-message", str(out_file)]
        if call.model and call.model != "default":
            cmd += ["--model", call.model]
        if schema_file:
            cmd += ["--output-schema", str(schema_file)]
        return cmd + ["-"]

    def run(self, call: Call, cwd: Path) -> dict | str:
        if not self.available():
            raise ProviderUnavailable("codex CLI not found on PATH")
        cwd.mkdir(parents=True, exist_ok=True)
        out_file, schema_file = cwd / "codex-last-message.txt", None
        if call.schema:
            schema_file = cwd / "codex-schema.json"
            schema_file.write_text(json.dumps(strict_schema(call.schema)), encoding="utf-8")
        prompt = call.prompt if not call.system else f"{call.system}\n\n{call.prompt}"
        env = {k: v for k, v in os.environ.items() if k not in ("CODEX_API_KEY", "OPENAI_API_KEY")}  # stay on the plan
        try:
            proc = subprocess.run(self.command(call, cwd, out_file, schema_file), input=prompt, capture_output=True,
                                  text=True, encoding="utf-8", cwd=cwd, timeout=call.timeout, env=env)
        except subprocess.TimeoutExpired as e:
            raise ProviderError(f"codex timed out after {call.timeout}s") from e
        if proc.returncode != 0:
            _raise_cli_error("codex", proc.returncode, proc.stderr or proc.stdout)
        text = out_file.read_text(encoding="utf-8") if out_file.exists() else proc.stdout
        return _finish(text, structured=call.schema is not None)


class CursorCLI(Provider):
    """Cursor subscription via the Cursor CLI (`cursor-agent`; newer installs call it `agent`) in print mode.

    There is no structured-output flag, so the schema goes into the prompt and the JSON is parsed
    from `result`. Runs in `ask` mode (read-only). Docs: cursor.com/docs/cli/reference.
    """
    name, binary = "cursor", "cursor-agent"
    binaries = ("cursor-agent", "agent")

    def resolve(self) -> str | None:
        for b in self.binaries:
            path = shutil.which(b)
            if path:
                return path
        return None

    def available(self) -> bool:
        return self.resolve() is not None

    def command(self, call: Call, cwd: Path, prompt: str) -> list[str]:
        cmd = [self.resolve() or self.binary, "-p", "--output-format", "json", "--trust", "--mode", "ask",
               "--workspace", str(cwd)]
        if call.model and call.model != "default":
            cmd += ["--model", call.model]
        return cmd + [prompt]

    def run(self, call: Call, cwd: Path) -> dict | str:
        if not self.available():
            raise ProviderUnavailable("Cursor CLI (cursor-agent / agent) not found on PATH")
        cwd.mkdir(parents=True, exist_ok=True)
        prompt = call.prompt if not call.system else f"{call.system}\n\n{call.prompt}"
        if call.schema:
            prompt += ("\n\nReturn only a JSON object (no prose, no code fence) that matches this JSON Schema:\n"
                       + json.dumps(call.schema))
        env = {k: v for k, v in os.environ.items() if k != "CURSOR_API_KEY"}  # stay on the plan
        try:
            proc = subprocess.run(self.command(call, cwd, prompt), capture_output=True, text=True, encoding="utf-8",
                                  cwd=cwd, timeout=call.timeout, env=env)
        except subprocess.TimeoutExpired as e:
            raise ProviderError(f"cursor timed out after {call.timeout}s") from e
        if proc.returncode != 0:
            _raise_cli_error("cursor", proc.returncode, proc.stderr or proc.stdout)
        try:
            data = json.loads(proc.stdout.strip().splitlines()[-1])
        except (json.JSONDecodeError, IndexError) as e:
            raise ProviderError(f"cursor returned no JSON: {proc.stdout[:300]}") from e
        if data.get("is_error"):
            raise ProviderError(str(data.get("result"))[:400])
        return _finish(str(data.get("result", "")), structured=call.schema is not None)


def _raise_cli_error(name: str, code: int, message: str) -> None:
    msg = (message or "").strip()[-400:]
    if any(w in msg.lower() for w in ("rate limit", "usage limit", "limit reached", "quota", "not logged in", "login")):
        raise ProviderUnavailable(f"{name}: {msg}")
    raise ProviderError(f"{name} exited {code}: {msg}")


def _finish(text: str, structured: bool) -> dict | str:
    return drop_nulls(extract_json(text)) if structured else text.strip()


def extract_json(text: str) -> dict:
    """Parse a JSON object from model text, tolerating a code fence or surrounding prose."""
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    start, end = text.find("{"), text.rfind("}")
    if start >= 0 and end > start:
        try:
            return json.loads(text[start:end + 1])
        except json.JSONDecodeError:
            pass
    raise ProviderError("the model did not return valid JSON")


def strict_schema(schema: dict) -> dict:
    """OpenAI strict mode: every object lists all its properties as required and forbids extras.
    Optional properties become nullable; `drop_nulls` removes those nulls afterwards."""
    out = dict(schema)
    if isinstance(schema.get("items"), dict):
        out["items"] = strict_schema(schema["items"])
    if "properties" in schema:
        required = set(schema.get("required", []))
        props = {}
        for k, v in schema["properties"].items():
            sub = strict_schema(v)
            props[k] = sub if k in required else {"anyOf": [sub, {"type": "null"}]}
        out.update(properties=props, required=list(schema["properties"]), additionalProperties=False)
    return out


def drop_nulls(v):
    if isinstance(v, dict):
        return {k: drop_nulls(x) for k, x in v.items() if x is not None}
    if isinstance(v, list):
        return [drop_nulls(x) for x in v]
    return v


class AnthropicAPI(Provider):
    """The Claude API with the learner's own API key (SPEC §25), for people without the agent CLIs (the desktop app).

    Uses the official SDK: streaming, adaptive thinking (always on for these models), server-side web search and
    web fetch for research jobs, structured JSON output, and server-side refusal fallbacks. Billed to the key's
    account, not to a subscription.
    """
    name, binary = "anthropic", ""
    MODEL_IDS = {"opus": "claude-opus-5-5", "sonnet": "claude-sonnet-5-5", "haiku": "claude-haiku-5-5",
                 "default": "claude-sonnet-5-5"}
    WEB_TOOLS = [{"type": "web_search_20260209", "name": "web_search", "max_uses": 20},
                 {"type": "web_fetch_20260209", "name": "web_fetch", "max_uses": 20}]
    MAX_CONTINUATIONS = 6

    def available(self) -> bool:
        from . import apikey
        return apikey.get() is not None

    def run(self, call: Call, cwd: Path) -> dict | str:
        import anthropic

        from . import apikey
        key = apikey.get()
        if not key:
            raise ProviderUnavailable("no Anthropic API key (Settings → Anthropic API key)")
        client = anthropic.Anthropic(api_key=key, timeout=float(call.timeout), max_retries=2)
        model = self.MODEL_IDS.get(call.model, call.model)
        web = bool({"WebSearch", "WebFetch"} & set(call.tools))
        prompt = call.prompt
        params: dict = {"model": model, "max_tokens": 64000, "betas": ["server-side-fallback-2026-07-01"],
                        "fallbacks": "default"}
        if call.system:
            params["system"] = call.system
        output_config: dict = {"effort": "high"} if call.model == "opus" else {}
        if call.schema and web:
            # Web results carry citations, which do not mix with a JSON output format: ask for JSON in the prompt.
            prompt += ("\n\nWhen you are done, reply with only a JSON object (no prose, no code fence) that matches "
                       "this JSON Schema:\n" + json.dumps(call.schema))
        elif call.schema:
            output_config["format"] = {"type": "json_schema", "schema": api_schema(call.schema)}
        if output_config:
            params["output_config"] = output_config
        if web:
            params["tools"] = self.WEB_TOOLS
        messages: list = [{"role": "user", "content": prompt}]
        try:
            for _ in range(self.MAX_CONTINUATIONS):
                with client.beta.messages.stream(messages=messages, **params) as stream:
                    msg = stream.get_final_message()
                if call.on_event:
                    for b in msg.content:
                        if b.type == "server_tool_use":
                            what = (b.input or {}).get("query") or (b.input or {}).get("url") or ""
                            call.on_event(f"{'searching' if b.name == 'web_search' else 'reading'}: {what}"[:160])
                if msg.stop_reason != "pause_turn":
                    break
                messages = [messages[0], {"role": "assistant", "content": msg.content}]  # the server resumes the turn
        except anthropic.AuthenticationError as e:
            raise ProviderUnavailable("the Anthropic API key was rejected") from e
        except anthropic.PermissionDeniedError as e:
            raise ProviderUnavailable(f"the API key may not use {model}") from e
        except anthropic.RateLimitError as e:
            raise ProviderUnavailable("Anthropic API rate limit; try again later") from e
        except anthropic.APIStatusError as e:
            raise ProviderError(f"Anthropic API error {e.status_code}: {e.message}"[:500]) from e
        except anthropic.APIConnectionError as e:
            raise ProviderUnavailable("cannot reach the Anthropic API (network)") from e
        if msg.stop_reason == "refusal":
            raise ProviderError("the model declined this request")
        if msg.stop_reason == "max_tokens":
            raise ProviderError("the answer was cut off (max_tokens)")
        text = "".join(b.text for b in msg.content if b.type == "text")
        return _finish(text, structured=call.schema is not None)


_UNSUPPORTED = ("minimum", "maximum", "exclusiveMinimum", "exclusiveMaximum", "multipleOf", "minLength", "maxLength",
                "maxItems", "pattern")


def api_schema(schema: dict) -> dict:
    """A JSON schema the Claude API accepts for structured output: strict objects, no numeric or length limits
    (those are checked by the code that reads the answer), minItems only 0 or 1."""
    def clean(v):
        if isinstance(v, dict):
            out = {k: clean(x) for k, x in v.items() if k not in _UNSUPPORTED}
            if isinstance(out.get("minItems"), int) and out["minItems"] > 1:
                out["minItems"] = 1
            return out
        if isinstance(v, list):
            return [clean(x) for x in v]
        return v
    return clean(strict_schema(schema))


PROVIDERS: dict[str, Provider] = {p.name: p for p in (ClaudeCLI(), CodexCLI(), CursorCLI(), AnthropicAPI())}

# "default" lets a CLI use its own configured model (set it in that CLI's config); other values go to --model.
MODELS = {"claude": ["opus", "sonnet", "haiku"], "codex": ["default"], "cursor": ["default"],
          "anthropic": ["opus", "sonnet", "haiku"]}

# Recommended provider and model per job, with the reason shown in Settings. Opus where a mistake is expensive or
# repeats in every lesson (research, roadmap, facts, the lesson plan); Sonnet where the output is long or must be fast
# (lesson text, tutor, grading); Codex for the fact-check, so a second model family checks what Claude wrote.
RECOMMENDED: dict[str, tuple[str, str, str]] = {
    "Research": ("claude", "opus", "Deep web research and choosing the best sources needs the strongest reasoning."),
    "Source curation": ("claude", "opus", "Choosing the canonical source among many needs careful judgment."),
    "Curriculum": ("claude", "opus", "The roadmap shapes months of study; a weak plan costs the most."),
    "Source cards": ("claude", "opus", "Cards are the facts every lesson is written from."),
    "Fact-check": ("codex", "default", "A different model family checks the cards, so it does not share their blind spots. "
                                       "Without Codex, use Claude Opus."),
    "Renditions": ("claude", "sonnet", "Long lesson text: Sonnet writes it well and fast. Opus is better but much slower."),
    "Tutor chat": ("claude", "sonnet", "Answers must come fast."),
    "Grading": ("claude", "sonnet", "A rubric check: Sonnet is accurate enough and fast."),
    "Code review": ("claude", "sonnet", "Reading short code against tests."),
    "Roadmap review": ("claude", "opus", "Changes to the roadmap need judgment about the whole goal."),
    "Placement": ("claude", "sonnet", "Short quiz questions over the outline."),
    "Study plan": ("claude", "opus", "Plans a study session and writes what you learned into your graph: needs judgment."),
    "Study tutor": ("claude", "sonnet", "Each step of a study session must come fast."),
    "Practice": ("claude", "sonnet", "Writes practice problems and reads your thinking: must answer fast."),
    "Reflection": ("claude", "opus", "Finding patterns over weeks of feedback needs careful reasoning."),
    "Card refresh": ("claude", "opus", "Finds errors in facts: the strongest model."),
    "Feedback": ("claude", "sonnet", "Rewrites one lesson from your feedback; Sonnet is good and fast."),
    "Lesson planner": ("claude", "opus", "The plan decides every section of the lesson; its answer is short, so Opus costs little."),
    "Lesson assets": ("claude", "sonnet", "Small graphs and questions from the card."),
    "Lesson review": ("claude", "sonnet", "Checks every lesson; Opus finds more problems but costs more for each lesson."),
}


def status() -> list[dict]:
    return [{"id": p.name, "cli": p.binary or "API key", "detected": p.available(), "implemented": True,
             "models": MODELS[p.name]} for p in PROVIDERS.values()]


def run_with_fallback(route: dict, call: Call, cwd: Path) -> tuple[dict | str, str]:
    """Run on the routed provider; if it is unavailable or rate-limited, fall back to the Claude CLI, then to the
    Claude API when an API key is set.

    Returns (output, provider name used).
    """
    order = [route["provider"]] + [n for n in ("claude", "anthropic") if n != route["provider"]]
    last: Exception | None = None
    for name in order:
        p = PROVIDERS[name]
        model = route["model"] if name == route["provider"] else call.model
        if name in ("claude", "anthropic") and model == "default":
            model = call.model
        try:
            return p.run(Call(**{**call.__dict__, "model": model}), cwd), name
        except ProviderUnavailable as e:
            last = e
    raise ProviderUnavailable(str(last))
