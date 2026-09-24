# Early Tamil Pottery AI - Windows set-up (PowerShell).
#   .\scripts\setup.ps1            # CUDA 12.6 wheels (NVIDIA GPU)
#   .\scripts\setup.ps1 -Cpu       # CPU-only wheels
# Creates .venv in the repository, installs dependencies, then runs the environment check.
param([switch]$Cpu)
$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot)

if (-not (Test-Path ".venv")) { python -m venv .venv }
$py = ".\.venv\Scripts\python.exe"
& $py -m pip install --upgrade pip
$index = if ($Cpu) { "https://download.pytorch.org/whl/cpu" } else { "https://download.pytorch.org/whl/cu126" }
& $py -m pip install torch torchvision --index-url $index
& $py -m pip install -r requirements.txt -r requirements-dev.txt
& $py scripts\check_env.py
