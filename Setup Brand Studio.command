#!/bin/bash
# One-time setup for Brand Studio on a Mac. Double-click to run. Safe to run again.
set -e
cd "$(dirname "$0")"
echo ""
echo "=========================================="
echo "   Brand Studio setup (about 10-20 min)"
echo "=========================================="

# 1. uv: installs a modern Python just for this app, no admin password needed
export PATH="$HOME/.local/bin:$PATH"
if ! command -v uv >/dev/null 2>&1; then
  echo "→ Installing uv (Python manager)…"
  curl -LsSf https://astral.sh/uv/install.sh | sh
  export PATH="$HOME/.local/bin:$PATH"
fi

# 2. Ollama: the local text AI
if [ ! -d "/Applications/Ollama.app" ] && [ ! -d "$HOME/Applications/Ollama.app" ]; then
  echo "→ Downloading Ollama…"
  curl -L --progress-bar -o /tmp/Ollama-darwin.zip https://ollama.com/download/Ollama-darwin.zip
  unzip -q -o /tmp/Ollama-darwin.zip -d /Applications 2>/dev/null || { mkdir -p "$HOME/Applications"; unzip -q -o /tmp/Ollama-darwin.zip -d "$HOME/Applications"; }
fi
open -a Ollama 2>/dev/null || open "$HOME/Applications/Ollama.app"
echo "→ Waiting for Ollama to start (approve any pop-up it shows)…"
for i in $(seq 1 60); do curl -s http://localhost:11434/api/tags >/dev/null && break; sleep 2; done

# 3. Pick models that suit this Mac's memory
MEM=$(( $(sysctl -n hw.memsize) / 1073741824 ))
if [ "$MEM" -le 8 ]; then TEXT=llama3.2:3b; IMG=sdxl-turbo
elif [ "$MEM" -le 16 ]; then TEXT=llama3.1:8b; IMG=sdxl-turbo
else TEXT=llama3.1:8b; IMG=sdxl-base; fi
echo "→ This Mac has ${MEM} GB memory: text model $TEXT, image model $IMG"

# 4. Python environment + app packages + image engine (Apple GPU)
echo "→ Installing app packages…"
uv venv --python 3.12 --allow-existing .venv
uv pip install --python .venv/bin/python -r requirements.txt
echo "→ Installing the image engine (about 1 GB)…"
OSMAJOR=$(sw_vers -productVersion | cut -d. -f1)
if [ "$OSMAJOR" -lt 15 ]; then TORCH='torch>=2.14,<2.15'; else TORCH='torch'; fi  # PyTorch 2.15+ needs macOS 15
uv pip install --python .venv/bin/python "$TORCH" torchvision -r requirements-images.txt

# 5. Save model choice
.venv/bin/python - "$TEXT" "$IMG" <<'PY'
import sys
from studio.config import load_settings, save_settings
s = load_settings(); s["text_model"], s["image_model"] = sys.argv[1], sys.argv[2]; save_settings(s)
PY

# 6. Download the text model (a few GB, one time)
echo "→ Downloading $TEXT (one time, a few GB)…"
.venv/bin/python - "$TEXT" <<'PY'
import json, sys, requests
last = ""
with requests.post("http://localhost:11434/api/pull", json={"model": sys.argv[1]}, stream=True, timeout=None) as r:
    for line in r.iter_lines():
        if not line: continue
        d = json.loads(line)
        if "error" in d: sys.exit("Ollama error: " + d["error"])
        msg = d.get("status", "")
        if d.get("total"): msg += f" {100*d.get('completed',0)//d['total']}%"
        if msg != last: print("\r   " + msg + " " * 20, end="", flush=True); last = msg
print("\n   done")
PY

chmod +x "Start Brand Studio.command" start.sh install-images.sh 2>/dev/null || true
echo ""
echo "✅ Setup complete. Opening Brand Studio in your browser…"
echo "   (Next time, just double-click 'Start Brand Studio.command'.)"
echo "   The first AI image downloads the image model (~7 GB) once."
.venv/bin/python app.py
