"""Entry point of the desktop app's bundled backend: the same `dsc` command line (the app runs `dsc-backend serve`)."""

import os
import subprocess
import sys
from pathlib import Path

from dsc.cli import main


def full_path() -> None:
    """macOS and Linux: an app opened from Finder or a desktop menu gets a short PATH (/usr/bin:/bin:...), so the
    model CLIs (claude, codex, cursor-agent) are not found. Add the PATH of the user's login shell and the usual
    install folders. Windows apps get the full PATH, so nothing changes there."""
    if os.name == "nt":
        return
    parts = os.environ.get("PATH", "").split(os.pathsep)
    shell = os.environ.get("SHELL") or ("/bin/zsh" if sys.platform == "darwin" else "/bin/bash")
    try:
        out = subprocess.run([shell, "-ilc", 'printf "%s" "$PATH"'], capture_output=True, text=True, timeout=10,
                             stdin=subprocess.DEVNULL).stdout.strip().splitlines()
        if out:
            parts += out[-1].split(os.pathsep)  # the last line: a shell start file can print text of its own
    except (OSError, subprocess.SubprocessError):
        pass
    home = Path.home()
    parts += [str(home / ".local" / "bin"), str(home / ".claude" / "local"), str(home / ".npm-global" / "bin"),
              str(home / ".volta" / "bin"), str(home / ".bun" / "bin"),
              "/opt/homebrew/bin", "/usr/local/bin", "/usr/bin", "/bin"]
    seen: list[str] = []
    for p in parts:
        if p and p not in seen:
            seen.append(p)
    os.environ["PATH"] = os.pathsep.join(seen)


if __name__ == "__main__":
    # The app sends output to a log file; write each line at once, so the log is complete when the app stops us.
    for stream in (sys.stdout, sys.stderr):
        if stream is not None and hasattr(stream, "reconfigure"):
            stream.reconfigure(line_buffering=True)
    full_path()
    main()
