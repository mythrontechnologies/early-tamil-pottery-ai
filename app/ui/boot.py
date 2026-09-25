"""Page bootstrap: import paths, page config (when a page runs on its own), theme, view mode,
command palette + skip link.

View modes (presentation only; they never change data):

* Research (default): provenance, hashes, licensing detail, verification tables, gate detail.
* Presentation: the same findings with implementation detail collapsed. The AI warning, the
  limitations and every blocked state stay visible.
"""

from __future__ import annotations

import contextlib
import sys
from pathlib import Path

APP = Path(__file__).resolve().parents[1]
ROOT = APP.parent
for p in (str(ROOT), str(APP)):
    if p not in sys.path:
        sys.path.insert(0, p)

MODES = ("Research", "Presentation")


def mode() -> str:
    import streamlit as st

    return st.session_state.get("ui_mode", "Research")


def research() -> bool:
    return mode() == "Research"


def boot(title: str) -> str:
    import streamlit as st

    from ui import data
    from ui.components import inject_theme
    from ui.palette import render_palette

    with contextlib.suppress(Exception):          # already configured by app/main.py
        st.set_page_config(page_title=f"{title} · Early Tamil Pottery AI", layout="wide")
    qp = str(st.query_params.get("mode", "")).capitalize()
    if qp in MODES and st.session_state.get("_mode_qp") != qp:     # palette link -> session (once per value)
        st.session_state["ui_mode"] = qp
        st.session_state["_mode_qp"] = qp
    st.session_state.setdefault("ui_mode", "Research")
    inject_theme()
    render_palette(sorted({r["artifact_id"] for r in data.records()}), mode().lower())
    return mode()


__all__ = ["APP", "MODES", "ROOT", "boot", "mode", "research"]
