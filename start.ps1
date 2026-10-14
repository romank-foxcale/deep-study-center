# Deep Study Center: one command to set up (first time) and start. Usage: .\start.ps1
# Needs Python 3.11+, Node.js 20+, and the Claude Code CLI logged in with your subscription.
$ErrorActionPreference = 'Stop'
$backend = Join-Path $PSScriptRoot 'backend'
$py = Join-Path $backend '.venv\Scripts\python.exe'
if (-not (Test-Path $py)) {
    Write-Host 'First run: creating the Python environment...'
    python -m venv (Join-Path $backend '.venv')
    & $py -m pip install --disable-pip-version-check -q -e $backend
}
& $py -m dsc.cli start @args
