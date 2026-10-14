#!/usr/bin/env sh
# Deep Study Center: one command to set up (first time) and start. Usage: ./start.sh
# Needs Python 3.11+, Node.js 20+, and the Claude Code CLI logged in with your subscription.
set -e
cd "$(dirname "$0")/backend"
if [ ! -x .venv/bin/python ]; then
  echo "First run: creating the Python environment..."
  python3 -m venv .venv
  .venv/bin/python -m pip install --disable-pip-version-check -q -e .
fi
exec .venv/bin/python -m dsc.cli start "$@"
