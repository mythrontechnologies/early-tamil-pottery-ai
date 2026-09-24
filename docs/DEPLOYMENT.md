# Deployment

## Windows (PowerShell)

```powershell
cd <repository>
.\scripts\setup.ps1            # NVIDIA GPU (CUDA 12.6 wheels)
.\scripts\setup.ps1 -Cpu       # or CPU only
.\scripts\start_app.ps1        # UI  -> http://localhost:8501
.\scripts\start_api.ps1        # API -> http://127.0.0.1:8765
```
If script execution is disabled: `powershell -ExecutionPolicy Bypass -File .\scripts\setup.ps1`.

## Linux / macOS

```bash
scripts/setup.sh [--cpu]
scripts/start_app.sh
scripts/start_api.sh
```

## GPU and CPU

* `python scripts/check_env.py` and `python -m src.training device` report CUDA, the GPU and AMP.
* CUDA wheels: `pip install torch torchvision --index-url https://download.pytorch.org/whl/cu126`
  (check the tag for your driver at pytorch.org). CPU: `.../whl/cpu`.
* Everything except training runs comfortably on CPU. `runtime.device: auto` in
  `configs/training.yaml` falls back to CPU (AMP is disabled on CPU).

## Docker

```bash
docker compose up --build        # UI on 127.0.0.1:8501, API on 127.0.0.1:8765
# GPU image:
docker build --build-arg TORCH_INDEX=https://download.pytorch.org/whl/cu126 -t etpai:gpu .
docker run --gpus all -p 127.0.0.1:8501:8501 -v "$PWD/data:/app/data" etpai:gpu
```
* The image contains **no data, models or secrets** (`.dockerignore`). `data/` and
  `knowledge/verification/` are bind-mounted so the annotation store, the registry and their
  ledgers persist on the host.
* It runs as a non-root user and has a health check.
* Status: `docker compose config` validates; the image build was not run on the development
  machine (Docker engine not running at the time).

## API

```
GET  /health                    -> {"status": "ok", "training_ready": false, ...}
POST /analyze[?artifact_id=ID]  body: raw image bytes, Content-Type image/* -> InferenceResult JSON
```
```powershell
curl.exe -X POST --data-binary "@photo.jpg" -H "Content-Type: image/jpeg" http://127.0.0.1:8765/analyze
```
Only image bytes are accepted (never a path or URL); `Content-Length` is required and capped
(`--max-mb`, default 25); decoding uses the guarded loader.

## Exposing it beyond localhost

There is **no authentication**. Before binding to anything but localhost, put it behind a
reverse proxy with authentication and TLS, keep the upload cap, and keep the API's data
mount read-only. The annotation tool writes to the shared store: restrict it to named
annotators.

## Paths

Production code contains no absolute machine paths (a test enforces it). Everything is
resolved from the repository root.
