@echo off
REM Adds local image generation. Run once after start.bat has created .venv.
cd /d "%~dp0"
where nvidia-smi >nul 2>nul
if %errorlevel%==0 (
  .venv\Scripts\pip install torch torchvision --index-url https://download.pytorch.org/whl/cu128
) else (
  .venv\Scripts\pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu
)
.venv\Scripts\pip install -r requirements-images.txt
echo Done. Restart the app.
pause
