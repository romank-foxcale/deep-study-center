"""`dsc start` builds the frontend if needed, serves the app and opens the browser.
`dsc serve` only serves; `dsc seed` resets to the demo; `dsc backup` writes a backup now; `dsc roadmap` is the daily
study roadmap (see dsc/roadmap/cli.py)."""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import threading
import webbrowser
from pathlib import Path

from .db import DB, workspace

ROOT = Path(__file__).resolve().parents[2]
WEB = ROOT / "web"


def frontend_stale() -> bool:
    """True when web/dist is missing or older than any source file."""
    index = WEB / "dist" / "index.html"
    if not index.exists():
        return True
    built = index.stat().st_mtime
    sources = [p for p in (WEB / "src").rglob("*") if p.is_file()] + [WEB / "index.html", WEB / "package.json"]
    return any(p.stat().st_mtime > built for p in sources if p.exists())


def build_frontend() -> None:
    npm = shutil.which("npm")
    if not npm:
        raise SystemExit("The frontend needs building, but npm isn't on PATH. Install Node.js 20+ and run again.")
    if not (WEB / "node_modules").exists():
        print("Installing frontend dependencies (first run)…")
        subprocess.run([npm, "ci"], cwd=WEB, check=True)
    print("Building the frontend…")
    subprocess.run([npm, "run", "build"], cwd=WEB, check=True)


def serve(port: int, open_browser: bool) -> None:
    import uvicorn
    from .api import create_app
    url = f"http://127.0.0.1:{port}"
    print(f"Workspace: {workspace()}")
    print(f"Deep Study Center: {url}  (Ctrl+C to stop)")
    if open_browser:
        threading.Timer(1.5, lambda: webbrowser.open(url)).start()
    uvicorn.run(create_app(static_dir=WEB / "dist"), host="127.0.0.1", port=port, log_level="warning")


def main() -> None:
    p = argparse.ArgumentParser(prog="dsc", description="Deep Study Center")
    sub = p.add_subparsers(dest="cmd", required=True)
    for name, help_ in (("start", "build the frontend if needed, serve, and open the browser"), ("serve", "run the local server")):
        s = sub.add_parser(name, help=help_)
        s.add_argument("--port", type=int, default=8000)
    sub.add_parser("seed", help="reset the workspace database to the demo roadmap (erases everything)")
    sub.add_parser("backup", help="write a backup of the workspace database now")
    sub.add_parser("where", help="print the workspace folder")
    sub.add_parser("roadmap", help="daily study roadmap: plan and progress (`dsc roadmap --help`)")
    if len(sys.argv) > 1 and sys.argv[1] == "roadmap":
        from .roadmap.cli import main as roadmap_main
        roadmap_main(sys.argv[2:])
        return
    args = p.parse_args()

    if args.cmd == "where":
        print(workspace())
    elif args.cmd == "seed":
        from .seed import seed_demo
        seed_demo(DB(workspace() / "study.db"))
        print(f"Seeded demo data in {workspace() / 'study.db'}")
    elif args.cmd == "backup":
        from .backup import backup_now
        print(f"Backup written: {backup_now(DB(workspace() / 'study.db'))}")
    elif args.cmd == "start":
        if frontend_stale():
            build_frontend()
        serve(args.port, open_browser=True)
    elif args.cmd == "serve":
        serve(args.port, open_browser=False)


if __name__ == "__main__":
    main()
