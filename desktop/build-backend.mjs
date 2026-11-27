// Build the bundled backend with PyInstaller on Windows, macOS and Linux (npm run build:backend).
// Uses backend/.venv when it exists (a local build), else the `python` on PATH (CI, after `pip install -e backend[dev]`).
import { spawnSync } from 'node:child_process'
import { existsSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

const root = join(dirname(fileURLToPath(import.meta.url)), '..')
const win = process.platform === 'win32'
const venv = join(root, 'backend', '.venv', win ? 'Scripts/python.exe' : 'bin/python')
const python = existsSync(venv) ? venv : (win ? 'python' : 'python3')

const r = spawnSync(python, ['-m', 'PyInstaller', 'desktop/backend/dsc-backend.spec', '--noconfirm',
  '--distpath', 'desktop/backend/dist', '--workpath', 'desktop/backend/build', '--log-level', 'WARN'],
{ cwd: root, stdio: 'inherit' })
if (r.error) { console.error(`Could not run ${python}: ${r.error.message}`); process.exit(1) }
process.exit(r.status ?? 1)
