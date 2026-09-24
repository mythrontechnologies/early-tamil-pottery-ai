"""Page bootstrap: import paths, page config (only when a page runs on its own) and theme."""

from __future__ import annotations

import contextlib
import sys
from pathlib import Path

APP = Path(__file__).resolve().parents[1]
ROOT = APP.parent
for p in (str(ROOT), str(APP)):
    if p not in sys.path:
        sys.path.insert(0, p)


def boot(title: str) -> None:
    import streamlit as st

    from ui.components import inject_theme

    with contextlib.suppress(Exception):          # already configured by app/main.py
        st.set_page_config(page_title=f"{title} · Early Tamil Pottery AI", layout="wide")
    inject_theme()


__all__ = ["APP", "ROOT", "boot"]
