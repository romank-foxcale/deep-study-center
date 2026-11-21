# PyInstaller spec for the desktop app's backend (SPEC §25).
# Build (from the repository root):  backend/.venv/Scripts/pyinstaller desktop/backend/dsc-backend.spec --noconfirm
#   --distpath desktop/backend/dist --workpath desktop/backend/build
# The result is a folder (onedir, so the app starts fast): desktop/backend/dist/dsc-backend/dsc-backend.exe
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

ROOT = Path(SPECPATH).resolve().parents[1]
WEB_DIST = ROOT / "web" / "dist"
if not (WEB_DIST / "index.html").exists():
    raise SystemExit("Build the UI first: npm --prefix web run build")

datas = collect_data_files("dsc")  # prompts, demo seed, roadmap data
datas += [(str(WEB_DIST), "web/dist")]
hidden = collect_submodules("uvicorn") + collect_submodules("keyring") + collect_submodules("dsc")

a = Analysis(
    [str(Path(SPECPATH) / "dsc_backend.py")],
    pathex=[str(ROOT / "backend")],
    datas=datas,
    hiddenimports=hidden,
    excludes=["tkinter", "pytest"],
)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="dsc-backend", console=True, upx=False)
coll = COLLECT(exe, a.binaries, a.datas, name="dsc-backend", upx=False)
