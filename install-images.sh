#!/usr/bin/env bash
# Adds local image generation. Run once after start.sh has created .venv.
set -e
cd "$(dirname "$0")"
if [[ "$(uname)" == "Darwin" ]]; then
  # Apple Silicon uses the GPU (MPS) automatically. PyTorch 2.15+ needs macOS 15, so pin older on macOS 14.
  if [ "$(sw_vers -productVersion | cut -d. -f1)" -lt 15 ]; then
    ./.venv/bin/pip install "torch>=2.14,<2.15" torchvision
  else
    ./.venv/bin/pip install torch torchvision
  fi
elif command -v nvidia-smi >/dev/null 2>&1; then
  ./.venv/bin/pip install torch torchvision --index-url https://download.pytorch.org/whl/cu128
else
  ./.venv/bin/pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu
fi
./.venv/bin/pip install -r requirements-images.txt
echo "Done. Restart the app."
