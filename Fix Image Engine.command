#!/bin/bash
# Installs the last PyTorch version that supports macOS 14 (2.14). PyTorch 2.15+ needs macOS 15.
cd "$(dirname "$0")"
mkdir -p logs
export PATH="$HOME/.local/bin:$PATH"
echo "Stopping Brand Studio if it's running…"
OLD=$(lsof -ti tcp:7860 2>/dev/null); [ -n "$OLD" ] && kill $OLD 2>/dev/null && sleep 2
echo "Installing the macOS 14 compatible image engine (about 100 MB)…"
uv pip install --python .venv/bin/python "torch>=2.14,<2.15" torchvision 2>&1 | tee logs/fix_image_engine.log
echo ""
.venv/bin/python -c "import torch; x=torch.ones(3, device='mps'); print('✅ Image engine OK · PyTorch', torch.__version__, '· test:', (x*2).cpu().tolist())" 2>&1 | tee -a logs/fix_image_engine.log
echo ""
echo "Done. Now double-click 'Start Brand Studio.command'."
read -n 1 -p "Press any key to close."
