"""Early Tamil Pottery AI - application entry point.

    streamlit run app/main.py

Two pages: analyse a photograph (read-only) and the annotation tool (append-only store).
"""

from __future__ import annotations

import streamlit as st

pages = st.navigation([
    st.Page("analyze.py", title="Analyse a photograph", default=True),
    st.Page("annotate.py", title="Annotate (project annotator / expert)"),
])
pages.run()
