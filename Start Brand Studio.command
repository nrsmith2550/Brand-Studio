#!/bin/bash
# Daily launcher: starts Ollama if needed, then opens Brand Studio. Close this window to stop it.
# Everything printed here is also saved to logs/last_run.log so problems can be diagnosed.
cd "$(dirname "$0")"
mkdir -p logs
exec > >(tee logs/last_run.log) 2>&1
echo "Brand Studio launcher · $(date)"
echo "macOS $(sw_vers -productVersion 2>/dev/null) · $(( $(sysctl -n hw.memsize 2>/dev/null || echo 0) / 1073741824 )) GB memory"
echo "Free disk: $(df -h . | awk 'NR==2 {print $4}')"

open -g -a Ollama 2>/dev/null || open -g "$HOME/Applications/Ollama.app" 2>/dev/null || echo "⚠️ Couldn't open the Ollama app"
for i in $(seq 1 20); do curl -s http://localhost:11434/api/tags >/dev/null && break; sleep 1; done
curl -s http://localhost:11434/api/tags >/dev/null && echo "Ollama: running" || echo "⚠️ Ollama isn't responding yet (the app still opens; AI features need it)"

if [ ! -x .venv/bin/python ]; then
  echo "❌ The app's Python environment is missing. Run 'Setup Brand Studio.command' first."
  read -n 1 -p "Press any key to close."; exit 1
fi

# If an old copy is still holding the app's port, stop it
OLD=$(lsof -ti tcp:7860 2>/dev/null)
if [ -n "$OLD" ]; then echo "Stopping an old copy of Brand Studio (pid $OLD)…"; kill $OLD 2>/dev/null; sleep 2; fi

PYTHONUNBUFFERED=1 .venv/bin/python -X faulthandler app.py
CODE=$?
echo ""
echo "Brand Studio stopped (exit code $CODE)."
if [ $CODE -ne 0 ]; then
  echo "❌ Something went wrong. The details above are saved in logs/last_run.log, so Claude can read them."
  read -n 1 -p "Press any key to close."
fi
