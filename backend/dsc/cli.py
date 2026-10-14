"""`dsc serve` runs the API (and the built frontend, if present); `dsc seed` resets to the demo."""

from __future__ import annotations

import argparse
from pathlib import Path

from .db import DB, workspace


def main() -> None:
    p = argparse.ArgumentParser(prog="dsc", description="Deep Study Center backend")
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("serve", help="run the local server")
    s.add_argument("--port", type=int, default=8000)
    sub.add_parser("seed", help="reset the workspace database to the demo roadmap")
    sub.add_parser("where", help="print the workspace folder")
    args = p.parse_args()

    if args.cmd == "where":
        print(workspace())
    elif args.cmd == "seed":
        from .seed import seed_demo
        seed_demo(DB(workspace() / "study.db"))
        print(f"Seeded demo data in {workspace() / 'study.db'}")
    elif args.cmd == "serve":
        import uvicorn
        from .api import create_app
        dist = Path(__file__).resolve().parents[2] / "web" / "dist"
        print(f"Workspace: {workspace()}")
        uvicorn.run(create_app(static_dir=dist), host="127.0.0.1", port=args.port)


if __name__ == "__main__":
    main()
