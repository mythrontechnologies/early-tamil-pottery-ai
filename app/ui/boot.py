"""Page bootstrap: import paths, page config (when a page runs on its own), theme, view mode,
command palette + skip link.

View modes (presentation only; they never change data):

* Research (default): provenance, hashes, licensing detail, verification tables, gate detail.
* Presentation: the same findings with implementation detail collapsed. The AI warning, the
  limitations and every blocked state stay visible.

The view mode is plain session state (``MODE_KEY``) owned by this module, never a widget value.
Streamlit gives a widget on each page its own identity (the page's script hash is part of the
widget id), so a switch keyed directly on the mode is a different widget on every page: changing
pages dropped the chosen mode and a return visit could set it to ``None`` (as did clicking the
selected option of a non-required switch). The switch (``ui.components.mode_switch``) therefore
has its own key: it is seeded from the mode before it renders and writes back through ``keep_mode``.
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
DEFAULT_MODE = MODES[0]           # first load: the full research view
MODE_KEY = "ui_mode"              # the view mode (session state)
SWITCH_KEY = "ui_mode_switch"     # the View-mode switch widget, a view of MODE_KEY


def mode() -> str:
    """The view mode: always one of ``MODES`` (``DEFAULT_MODE`` until one has been chosen)."""
    import streamlit as st

    value: object = st.session_state.get(MODE_KEY, DEFAULT_MODE)
    if not isinstance(value, str) or value not in MODES:
        raise ValueError(f"invalid view mode {value!r} in session state; expected one of {MODES}")
    return value


def research() -> bool:
    return mode() == "Research"


def keep_mode() -> None:
    """``on_change`` of the switch: copy its value into the view mode (before the page runs)."""
    import streamlit as st

    st.session_state[MODE_KEY] = st.session_state[SWITCH_KEY]


def boot(title: str) -> str:
    import streamlit as st

    from ui import data
    from ui.components import inject_theme
    from ui.palette import render_palette

    with contextlib.suppress(Exception):          # already configured by app/main.py
        st.set_page_config(page_title=f"{title} · Early Tamil Pottery AI", layout="wide")
    qp = str(st.query_params.get("mode", "")).capitalize()
    if qp in MODES and st.session_state.get("_mode_qp") != qp:     # palette link -> session (once per value)
        st.session_state[MODE_KEY] = qp
        st.session_state["_mode_qp"] = qp
    st.session_state.setdefault(MODE_KEY, DEFAULT_MODE)
    inject_theme()
    render_palette(sorted({r["artifact_id"] for r in data.records()}), mode().lower())
    return mode()


__all__ = ["APP", "DEFAULT_MODE", "MODES", "MODE_KEY", "ROOT", "SWITCH_KEY", "boot", "keep_mode", "mode", "research"]
