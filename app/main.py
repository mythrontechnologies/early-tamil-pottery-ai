"""Early Tamil Pottery AI - application entry point.

    streamlit run app/main.py

Seven pages in a top navigation: Overview, Analysis, Annotation, Dataset, Evidence, Workflow,
About. Analysis and the annotation tool keep their own files (and can run alone); the other
pages live in app/views/. Everything is read-only except the annotation tool, which appends to
the annotation store through its validated, ledger-chained API.
"""

from __future__ import annotations

import sys
from pathlib import Path

APP = Path(__file__).resolve().parent
for p in (str(APP.parent), str(APP)):
    if p not in sys.path:
        sys.path.insert(0, p)

import streamlit as st

st.set_page_config(page_title="Early Tamil Pottery AI", layout="wide")

pages = st.navigation([
    st.Page("views/overview.py", title="Overview", default=True),
    st.Page("analyze.py", title="Analysis", url_path="analysis"),
    st.Page("annotate.py", title="Annotation", url_path="annotation"),
    st.Page("views/dataset.py", title="Dataset", url_path="dataset"),
    st.Page("views/evidence.py", title="Evidence", url_path="evidence"),
    st.Page("views/workflow.py", title="Workflow", url_path="workflow"),
    st.Page("views/about.py", title="About", url_path="about"),
], position="top")
# No icons in the navigation: Streamlit renders Material icons as ligature text, which screen
# readers would announce as part of every link name ("center_focus_strong Analysis").
pages.run()
