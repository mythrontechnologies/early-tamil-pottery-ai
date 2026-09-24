# Start the HTTP API on http://127.0.0.1:8765  (GET /health, POST /analyze with image bytes)
Set-Location (Split-Path -Parent $PSScriptRoot)
& .\.venv\Scripts\python.exe -m src.inference serve --host 127.0.0.1 --port 8765 --max-mb 25
