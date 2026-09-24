#!/usr/bin/env bash
# Early Tamil Pottery AI - Linux / macOS set-up.
#   scripts/setup.sh          # CUDA 12.6 wheels (NVIDIA GPU, Linux)
#   scripts/setup.sh --cpu    # CPU-only wheels
set -euo pipefail
cd "$(dirname "$0")/.."

[ -d .venv ] || python3 -m venv .venv
PY=.venv/bin/python
"$PY" -m pip install --upgrade pip
INDEX=https://download.pytorch.org/whl/cu126
[ "${1:-}" = "--cpu" ] && INDEX=https://download.pytorch.org/whl/cpu
"$PY" -m pip install torch torchvision --index-url "$INDEX"
"$PY" -m pip install -r requirements.txt -r requirements-dev.txt
"$PY" scripts/check_env.py
