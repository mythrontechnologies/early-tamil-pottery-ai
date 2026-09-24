# Start the Streamlit application (analysis page + annotation tool) on http://localhost:8501
Set-Location (Split-Path -Parent $PSScriptRoot)
& .\.venv\Scripts\python.exe -m streamlit run app\main.py --server.address 127.0.0.1 --server.port 8501 --browser.gatherUsageStats false
