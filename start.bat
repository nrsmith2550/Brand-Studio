@echo off
REM Windows launcher: sets up a private Python environment on first run, then opens the app.
cd /d "%~dp0"
if not exist .venv (
  echo First run: creating environment...
  py -3 -m venv .venv || python -m venv .venv
  .venv\Scripts\python -m pip install --upgrade pip
  .venv\Scripts\pip install -r requirements.txt
)
.venv\Scripts\python app.py
pause
