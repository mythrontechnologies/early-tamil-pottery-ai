# Start the Streamlit application (analysis page + annotation tool) on http://localhost:8501
# --logger.hideWelcomeMessage also withholds Streamlit's in-app "Install the official Streamlit skills" popup, which
# covers the Research / Presentation switch (client.toolbarMode does not); it hides Streamlit's URL banner, so the URL is printed here.
Set-Location (Split-Path -Parent $PSScriptRoot)
Write-Host "Early Tamil Pottery AI: http://127.0.0.1:8501  (opens in your browser; Ctrl+C stops it)"
& .\.venv\Scripts\python.exe -m streamlit run app\main.py --server.address 127.0.0.1 --server.port 8501 --browser.gatherUsageStats false `
    --logger.hideWelcomeMessage true
