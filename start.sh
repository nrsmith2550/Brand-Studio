#!/usr/bin/env bash
# Mac / Linux launcher: sets up a private Python environment on first run, then opens the app.
set -e
cd "$(dirname "$0")"
if [ ! -d .venv ]; then
  echo "First run: creating environment…"
  python3 -m venv .venv
  ./.venv/bin/pip install --upgrade pip
  ./.venv/bin/pip install -r requirements.txt
fi
./.venv/bin/python app.py
