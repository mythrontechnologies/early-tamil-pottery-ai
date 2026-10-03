"""Design-system building blocks. Every function returns HTML with ALL data values escaped.

Status is never conveyed by colour alone: every badge carries a text label and a glyph.
"""

from __future__ import annotations

import html
from functools import lru_cache
from pathlib import Path
from typing import Any

import streamlit as st

CSS_PATH = Path(__file__).with_name("theme.css")

#: status -> (css class, glyph, label). Glyphs differ by shape, not only colour.
BADGES = {
    "verified": ("b-verified", "✓", "Verified"),
    "unverified": ("b-unverified", "○", "Unverified"),
    "transcribed": ("b-unverified", "○", "Transcribed · unverified"),
    "bibliographic": ("b-unverified", "○", "Bibliographic only"),
    "unresolved": ("b-unresolved", "?", "Unresolved"),
    "ai": ("b-ai", "◇", "AI observation"),
    "pass": ("b-pass", "✓", "Pass"),
    "waiting": ("b-waiting", "…", "Waiting"),
    "blocked": ("b-blocked", "■", "Blocked"),
    "human": ("b-human", "●", "Human action"),
    "expert": ("b-human", "●", "Expert"),
    "project": ("b-neutral", "●", "Project"),
    "insufficient": ("b-insufficient", "∅", "Insufficient evidence"),
    "future": ("b-future", "◌", "Not yet reached"),
    "research_data": ("b-real", "■", "Real research data"),
    "synthetic": ("b-synthetic", "◆", "Synthetic demonstration"),
    "unregistered": ("b-unresolved", "?", "Unregistered image"),
    "neutral": ("b-neutral", "·", ""),
}


def e(value: Any) -> str:
    """Escape any value for HTML (None -> em dash)."""
    return "—" if value is None or value == "" else html.escape(str(value), quote=True)


@lru_cache(maxsize=1)
def _css() -> str:
    return CSS_PATH.read_text(encoding="utf-8") + "\n" + CSS_PATH.with_name("theme_v3.css").read_text(encoding="utf-8")


def inject_theme() -> None:
    """Load the design system once per script run."""
    # st.html drops a style-only block; markdown keeps it. The CSS is a static project file.
    st.markdown(f"<style>{_css()}</style>", unsafe_allow_html=True)


def badge(kind: str, label: str | None = None) -> str:
    cls, glyph, default = BADGES.get(kind, BADGES["neutral"])
    text = label if label is not None else default
    return f'<span class="etp-badge {cls}"><span class="g" aria-hidden="true">{glyph}</span>{e(text)}</span>'


def reference_badge(effective_status: str, resolution: str | None = None) -> str:
    """Map an EFFECTIVE (registry-backed) status to a badge. Unresolved always wins."""
    if resolution == "unresolved":
        return badge("unresolved")
    return {"verified_against_source": badge("verified"),
            "transcribed_unverified": badge("transcribed"),
            "bibliographic_only": badge("bibliographic")}.get(effective_status, badge("unverified"))


def nav_link(page: str, label: str, icon: str | None = None) -> None:
    """A link to another page of the app; plain text when the page runs on its own (no navigation)."""
    from streamlit.errors import StreamlitAPIException

    try:
        st.page_link(page, label=label, icon=icon)
    except StreamlitAPIException:
        st.caption(label)


def mode_switch() -> None:
    """Research / Presentation view switch (presentation only; never changes data)."""
    with st.container(key="etp_mode_switch"):
        st.segmented_control("View mode", ["Research", "Presentation"], key="ui_mode", label_visibility="collapsed",
                             help="Research shows provenance, hashes and verification detail; Presentation keeps the "
                                  "findings, the AI warning and every limitation but collapses implementation detail.")


def page_header(eyebrow: str, title: str, subtitle: str = "") -> None:
    left, right = st.columns([5, 1.6], vertical_alignment="top")
    with left:
        st.html(f'<header class="etp-rise"><div class="etp-pill">{e(eyebrow)}</div>'
                f'<h1 class="etp-page-title">{e(title)}</h1>'
                + (f'<p class="etp-page-sub">{e(subtitle)}</p>' if subtitle else "") + "</header>")
    with right:
        mode_switch()


def section(title: str, kicker: str = "") -> None:
    st.html(f'<h2 class="etp-section">{e(title)}' + (f"<small>{e(kicker)}</small>" if kicker else "") + "</h2>")


def stat(value: Any, label: str, foot: str = "", *, word: bool = False) -> str:
    return (f'<div class="etp-card etp-stat tilt" role="group" aria-label="{e(label)}: {e(value)}">'
            f'<div class="n{" word" if word else ""}">{e(value)}</div><div class="l">{e(label)}</div>'
            + (f'<div class="foot">{foot}</div>' if foot else "") + "</div>")


def grid(items: list[str], cols: str = "cols-4") -> None:
    st.html(f'<div class="etp-grid {cols}">{"".join(items)}</div>')


def card(title: str, body_html: str, *, tilt: bool = True, extra: str = "") -> str:
    return (f'<div class="etp-card{" tilt" if tilt else ""}">{extra}<h4>{e(title)}</h4>'
            f"<p>{body_html}</p></div>")


def blocked_state(kind: str, title: str, message: str, reasons: list[str], *, why: str = "Why is this blocked?") -> str:
    """An intentional, honest blocked/waiting state: what, why (expandable), never hidden."""
    items = "".join(f"<li>{e(r)}</li>" for r in reasons)
    return (f'<section class="etp-blocked" aria-label="{e(title)}">{badge(kind)}<h4>{e(title)}</h4><p>{e(message)}</p>'
            + (f"<details><summary>{e(why)}</summary><ul>{items}</ul></details>" if reasons else "") + "</section>")


def note(html_text: str) -> None:
    st.html(f'<div class="etp-note">{html_text}</div>')


def kv(rows: list[tuple[str, Any, bool]]) -> str:
    """(label, value, monospace) rows -> <dl>."""
    return '<dl class="etp-kv">' + "".join(
        f'<dt>{e(k)}</dt><dd class="{"mono" if mono else ""}">{e(v)}</dd>' for k, v, mono in rows) + "</dl>"


AI_LABEL = "AI observation — not archaeological evidence."

#: dataset_type (src.inference result) -> badge kind of the dataset indicator
DATASET_BADGE = {"research": "research_data", "synthetic": "synthetic", "unregistered": "unregistered"}


def dataset_badge(dataset_type: str) -> str:
    """The small dataset indicator: REAL RESEARCH DATA / SYNTHETIC DEMONSTRATION / UNREGISTERED IMAGE."""
    return badge(DATASET_BADGE.get(dataset_type, "unregistered"))


def synthetic_banner(block: dict[str, Any], prediction: dict[str, Any] | None = None) -> str:
    """The unmistakable notice shown whenever a synthetic image is analysed."""
    gt = block.get("ground_truth") or {}
    rows = [("Synthetic image", block.get("image_id"), True), ("Synthetic object", block.get("artifact_id"), True),
            ("Generator", f'v{block.get("generator_version")} · seed {block.get("generation_seed")}', True),
            ("Generator ground truth", f'{gt.get("label")} (task label, not evidence)', True)]
    if prediction and prediction.get("status") == "predicted":
        rows.append(("Synthetic model prediction", f'{prediction.get("label")} · AI observation', True))
    return (f'<section class="etp-synthetic" role="note" aria-label="{e(block.get("statement"))}">'
            f'{badge("synthetic")}<h3>{e(block.get("statement"))}</h3>'
            f'<p>{e(block.get("marker"))}. {e(block.get("purpose"))}</p>'
            f'<p>{e(block.get("label_warning"))}</p>{kv(rows)}</section>')


def ai_panel(body_html: str, title: str = AI_LABEL) -> None:
    st.html(f'<section class="etp-ai" aria-label="{e(title)}"><div class="etp-ai-head">'
            f'{badge("ai")}<span>{e(title)}</span></div>{body_html}</section>')


def footer() -> None:
    st.html('<div class="etp-foot">Early Tamil Pottery AI is an assistive research tool, not an '
            "archaeologist. No model is trained: training stays blocked until enough expert-labelled "
            "archaeological data exists. Photographs: Wikimedia Commons contributors, CC BY / CC BY-SA "
            "(attribution on each image). Illustrative visualizations are labelled as such.</div>")


__all__ = ["AI_LABEL", "BADGES", "DATASET_BADGE", "ai_panel", "badge", "card", "dataset_badge", "e", "footer", "grid",
           "inject_theme", "kv", "mode_switch", "nav_link", "note", "page_header", "reference_badge", "section", "stat",
           "synthetic_banner"]
