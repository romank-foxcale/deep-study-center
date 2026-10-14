"""Local Python runner for exercises that need more than Pyodide (e.g. PyTorch).

This is NOT a sandbox: Python on the learner's machine can do anything the learner can. The
safeguards are about not running agent-written code unseen:

1. Exercise tests are written by agents that read the web. Before an exercise first runs, the
   learner sees its full test code and approves it; the approval is tied to a hash of the tests,
   so a changed test needs a new approval.
2. A static check rejects code that imports networking, process, file-system or introspection
   modules, or calls open/exec/eval/__import__, or touches dunder attributes.
3. Runs happen in a separate virtual environment in the workspace, in an empty folder, with a
   minimal environment (no API keys or tokens), Python's isolated mode, and a timeout.
"""

from __future__ import annotations

import ast
import hashlib
import os
import subprocess
import sys
from pathlib import Path

from .db import DB, now, workspace

PACKAGES = ("numpy", "torch")
TIMEOUT = 90

BLOCKED_MODULES = {
    "os", "sys", "subprocess", "socket", "shutil", "pathlib", "glob", "tempfile", "io", "builtins",
    "importlib", "ctypes", "cffi", "multiprocessing", "threading", "asyncio", "signal", "pickle", "marshal",
    "shelve", "urllib", "http", "requests", "httpx", "ftplib", "smtplib", "telnetlib", "ssl", "webbrowser",
    "inspect", "gc", "code", "codeop", "pty", "fcntl", "winreg", "msvcrt", "_winapi", "zipfile", "tarfile",
}
BLOCKED_CALLS = {"open", "exec", "eval", "compile", "__import__", "globals", "locals", "vars", "getattr",
                 "setattr", "delattr", "breakpoint", "input"}
ALLOWED_DUNDERS = {"__init__", "__call__", "__repr__", "__str__", "__len__", "__getitem__", "__name__",
                   "__main__", "__add__", "__mul__", "__sub__", "__neg__", "__eq__", "__iter__", "__next__"}


def venv_dir() -> Path:
    return workspace() / "runner-venv"


def python_path() -> Path:
    return venv_dir() / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def is_set_up() -> bool:
    return python_path().exists() and (venv_dir() / "ready").exists()


def setup(progress=lambda msg: None) -> dict:
    """Create the runner environment and install numpy + torch (CPU). Large download (~1 GB for torch)."""
    vd = venv_dir()
    if not python_path().exists():
        progress("creating a Python environment for exercises")
        subprocess.run([sys.executable, "-m", "venv", str(vd)], check=True, capture_output=True, timeout=300)
    progress(f"installing {', '.join(PACKAGES)} (torch is a large download; this can take several minutes)")
    proc = subprocess.run([str(python_path()), "-m", "pip", "install", "--disable-pip-version-check", "-q", *PACKAGES],
                          capture_output=True, text=True, timeout=3600)
    if proc.returncode != 0:
        raise RuntimeError(f"pip install failed: {proc.stderr.strip()[-400:]}")
    versions = subprocess.run([str(python_path()), "-c", "import numpy, torch; print(numpy.__version__, torch.__version__)"],
                              capture_output=True, text=True, timeout=120).stdout.strip()
    (vd / "ready").write_text(versions or "ok", encoding="utf-8")
    progress(f"ready: numpy/torch {versions}")
    return {"versions": versions}


def tests_hash(tests: str) -> str:
    return hashlib.sha256(tests.encode("utf-8")).hexdigest()[:16]


def is_approved(db: DB, concept_id: str, item_id: str, tests: str) -> bool:
    return bool(db.one("SELECT 1 FROM runner_approvals WHERE concept_id=? AND item_id=? AND tests_hash=?",
                       (concept_id, item_id, tests_hash(tests))))


def approve(db: DB, concept_id: str, item_id: str, tests: str) -> None:
    db.x("INSERT OR REPLACE INTO runner_approvals VALUES(?,?,?,?)", (concept_id, item_id, tests_hash(tests), now()))


def static_check(source: str) -> list[str]:
    """Reasons to refuse running ``source``; empty if it passes."""
    try:
        tree = ast.parse(source)
    except SyntaxError as e:
        return [f"syntax error on line {e.lineno}: {e.msg}"]
    problems: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                if a.name.split(".")[0] in BLOCKED_MODULES:
                    problems.append(f"line {node.lineno}: import of '{a.name}' is not allowed in exercises")
        elif isinstance(node, ast.ImportFrom):
            if (node.module or "").split(".")[0] in BLOCKED_MODULES or node.level:
                problems.append(f"line {node.lineno}: import from '{node.module}' is not allowed in exercises")
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in BLOCKED_CALLS:
            problems.append(f"line {node.lineno}: calling '{node.func.id}' is not allowed in exercises")
        elif isinstance(node, ast.Attribute) and node.attr.startswith("__") and node.attr not in ALLOWED_DUNDERS:
            problems.append(f"line {node.lineno}: access to '{node.attr}' is not allowed in exercises")
        elif isinstance(node, ast.Name) and node.id in ("__builtins__", "__loader__", "__spec__"):
            problems.append(f"line {node.lineno}: '{node.id}' is not allowed in exercises")
    return sorted(set(problems))


def run(code: str, tests: str, run_id: str) -> dict:
    """Run learner code + tests in the runner environment. Passed = exit 0 and 'All tests passed'."""
    folder = workspace() / "runs" / run_id
    folder.mkdir(parents=True, exist_ok=True)
    script = folder / "exercise.py"
    script.write_text(f"{code}\n\n# ---- tests ----\n{tests}\n", encoding="utf-8")
    keep = ("SYSTEMROOT", "WINDIR", "TEMP", "TMP", "PATH", "HOME", "USERPROFILE", "LANG")
    env = {k: v for k, v in os.environ.items() if k in keep}
    try:  # -I: isolated mode (ignores PYTHON* env and user site); -X utf8: UTF-8 stdio despite -I
        proc = subprocess.run([str(python_path()), "-I", "-X", "utf8", "-B", str(script)], cwd=folder, env=env,
                              capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=TIMEOUT)
    except subprocess.TimeoutExpired:
        return {"passed": False, "output": f"Stopped after {TIMEOUT}s (infinite loop or very slow code?)"}
    out = (proc.stdout + ("\n" + proc.stderr if proc.stderr else "")).strip().replace(str(script), "exercise.py")
    lines = out.splitlines()
    if proc.returncode != 0 and lines:
        # Show the error line and the traceback frames from the exercise only.
        out = "\n".join(l for l in lines if "exercise.py" in l or not l.startswith(" ") or l.strip().startswith("assert"))
    return {"passed": proc.returncode == 0 and "All tests passed" in proc.stdout, "output": out[-4000:] or "(no output)"}
