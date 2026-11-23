"""Make the files for a GitHub release after `npm run build` (SPEC §39).

The installed app reads `latest.json` from the newest GitHub release. This script copies the signed installer under
the name GitHub gives it (spaces become dots) and writes `latest.json` next to it, in `desktop/release/<version>/`.

    python release.py                       # for the GitHub release of the version in tauri.conf.json
    python release.py --base-url http://127.0.0.1:8765/   # for a local update test

Then: gh release create v<version> release/<version>/* --title "Deep Study Center <version>" --notes-file ...
"""
import argparse
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = "romank-foxcale/deep-study-center"


def main() -> None:
    conf = json.loads((HERE / "src-tauri" / "tauri.conf.json").read_text(encoding="utf-8"))
    version = conf["version"]
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--base-url", default=f"https://github.com/{REPO}/releases/download/v{version}/",
                    help="where the installer is downloaded from (default: the GitHub release of this version)")
    ap.add_argument("--notes", default=f"See https://github.com/{REPO}/releases/tag/v{version}")
    args = ap.parse_args()

    nsis = HERE / "src-tauri" / "target" / "release" / "bundle" / "nsis"
    exe = nsis / f"{conf['productName']}_{version}_x64-setup.exe"
    sig = exe.with_name(exe.name + ".sig")
    for f in (exe, sig):
        if not f.exists():
            raise SystemExit(f"Missing {f}. Run `npm run build` with TAURI_SIGNING_PRIVATE_KEY set (docs/RELEASING.md).")
    out = HERE / "release" / version
    out.mkdir(parents=True, exist_ok=True)
    name = exe.name.replace(" ", ".")  # the asset name that GitHub shows and serves
    shutil.copyfile(exe, out / name)
    latest = {
        "version": version,
        "notes": args.notes,
        "pub_date": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "platforms": {"windows-x86_64": {"signature": sig.read_text(encoding="utf-8").strip(),
                                         "url": args.base_url.rstrip("/") + "/" + name}},
    }
    (out / "latest.json").write_text(json.dumps(latest, indent=2) + "\n", encoding="utf-8")
    print(f"{out / name}\n{out / 'latest.json'}")


if __name__ == "__main__":
    main()
