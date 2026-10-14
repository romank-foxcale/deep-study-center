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
    """ChatGPT subscription via `codex exec`. Detected but not wired yet (milestone 3)."""
    name, binary = "codex", "codex"

    def run(self, call: Call, cwd: Path) -> dict | str:
        raise ProviderUnavailable("the codex adapter is not implemented yet")


class CursorCLI(Provider):
    """Cursor subscription via `cursor-agent -p`. Detected but not wired yet (milestone 3)."""
    name, binary = "cursor", "cursor-agent"

    def run(self, call: Call, cwd: Path) -> dict | str:
        raise ProviderUnavailable("the cursor adapter is not implemented yet")


PROVIDERS: dict[str, Provider] = {p.name: p for p in (ClaudeCLI(), CodexCLI(), CursorCLI())}

MODELS = {"claude": ["opus", "sonnet", "haiku"], "codex": ["default"], "cursor": ["default"]}


def status() -> list[dict]:
    return [{"id": p.name, "cli": p.binary, "detected": p.available(),
             "implemented": isinstance(p, ClaudeCLI), "models": MODELS[p.name]} for p in PROVIDERS.values()]


def run_with_fallback(route: dict, call: Call, cwd: Path) -> tuple[dict | str, str]:
    """Run on the routed provider; if it is unavailable or rate-limited, fall back to Claude.

    Returns (output, provider name used).
    """
    order = [route["provider"]] + ([] if route["provider"] == "claude" else ["claude"])
    last: Exception | None = None
    for name in order:
        p = PROVIDERS[name]
        model = route["model"] if name == route["provider"] else "sonnet"
        try:
            return p.run(Call(**{**call.__dict__, "model": model if model != "default" else call.model}), cwd), name
        except ProviderUnavailable as e:
            last = e
    raise ProviderUnavailable(str(last))
