#!/usr/bin/env bash
# Start the Streamlit application (analysis page + annotation tool) on http://localhost:8501
set -euo pipefail
cd "$(dirname "$0")/.."
exec .venv/bin/python -m streamlit run app/main.py --server.address 127.0.0.1 --server.port 8501 --browser.gatherUsageStats false
