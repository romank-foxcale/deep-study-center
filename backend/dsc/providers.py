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
from dataclasses import dataclass
from pathlib import Path


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
        cmd = [shutil.which(self.binary) or self.binary, "-p",
               "--output-format", "json", "--model", call.model,
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
        try:
            proc = subprocess.run(self.command(call), input=call.prompt, capture_output=True, text=True,
                                  encoding="utf-8", cwd=cwd, timeout=call.timeout, env=env)
        except subprocess.TimeoutExpired as e:
            raise ProviderError(f"claude timed out after {call.timeout}s") from e
        return parse_claude_output(proc.stdout, proc.stderr, proc.returncode, structured=call.schema is not None)


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
        cmd = [shutil.which(self.binary) or self.binary, "exec", "--skip-git-repo-check", "--ephemeral",
               "--sandbox", "read-only", "--cd", str(cwd), "--output-last-message", str(out_file)]
        if call.model and call.model != "default":
            cmd += ["--model", call.model]
        if "WebSearch" in call.tools:
            cmd += ["--search"]
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


PROVIDERS: dict[str, Provider] = {p.name: p for p in (ClaudeCLI(), CodexCLI(), CursorCLI())}

# "default" lets a CLI use its own configured model (set it in that CLI's config); other values go to --model.
MODELS = {"claude": ["opus", "sonnet", "haiku"], "codex": ["default"], "cursor": ["default"]}


def status() -> list[dict]:
    return [{"id": p.name, "cli": p.binary, "detected": p.available(), "implemented": True,
             "models": MODELS[p.name]} for p in PROVIDERS.values()]


def run_with_fallback(route: dict, call: Call, cwd: Path) -> tuple[dict | str, str]:
    """Run on the routed provider; if it is unavailable or rate-limited, fall back to Claude.

    Returns (output, provider name used).
    """
    order = [route["provider"]] + ([] if route["provider"] == "claude" else ["claude"])
    last: Exception | None = None
    for name in order:
        p = PROVIDERS[name]
        model = route["model"] if name == route["provider"] else call.model
        if name == "claude" and model == "default":
            model = call.model
        try:
            return p.run(Call(**{**call.__dict__, "model": model}), cwd), name
        except ProviderUnavailable as e:
            last = e
    raise ProviderUnavailable(str(last))
