"""About: purpose, what the tool is not, and where the limits are."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ui.boot import boot

boot("About")

import streamlit as st
from ui.components import card, e, footer, grid, page_header, section

page_header("About", "An assistive research tool, not an archaeologist",
            "Early Tamil Pottery AI supports the study of Early Historic Tamil Nadu pottery and its Tamil-Brahmi "
            "(Tamiḻi) inscriptions and graffiti, by keeping observation, interpretation, published evidence and "
            "conclusions apart and traceable.")

section("What it does")
grid([
    card("Looks carefully", "Guarded image loading, technical quality measures, region inspection, contrast "
         "enhancement for the eye. None of it is evidence.", tilt=False),
    card("Records people's judgement", "Independent project and expert annotation in an append-only, tamper-evident "
         "store; agreement measured item by item.", tilt=False),
    card("Reasons from evidence", "Script, reading, translation and date only from human sources; conflicts shown, "
         "never averaged; unverified sources cap confidence.", tilt=False),
], "asym")

section("What it is not")
st.html('<ul class="etp-lede" style="max-width:75ch">'
        "<li>Not a trained classifier. Training is blocked until enough expert-labelled artifacts exist in every class.</li>"
        "<li>Not an OCR for Tamil-Brahmi. No validated model exists; the answer is “No reliable transcription established.”</li>"
        "<li>Not a dating service. A site date or caption is never an object date.</li>"
        "<li>Not a substitute for an epigraphist or archaeologist.</li></ul>")

section("Visual language")
grid([
    card("Photographs are authoritative", "Every photograph shown is a real, openly licensed research image, "
         "credited to its photographer.", tilt=False),
    card("Illustrations are labelled", "The 3D sherd on the Overview is an illustrative visualization drawn by the "
         "interface: not a model of any real object; its surface is abstract texture and carries no inscription.", tilt=False),
    card("Colour never stands alone", "Every status carries a word and a shape as well as a colour; AI output always "
         "carries the words “AI observation”.", tilt=False),
], "cols-3")

section("Using the workstation", "keyboard, modes and 2D alternatives")
KEYS = [("Ctrl + K  /  ⌘ K", "Command palette: pages, artifact search, mode switch, reduce motion, reset"),
        ("Tab  ·  Shift + Tab", "Move between controls; the first Tab reaches “Skip to main content”"),
        ("← → ↑ ↓", "Orbit the 3D view, or pan a zoomed photograph"),
        ("+  ·  −  ·  0", "Zoom in, zoom out, reset the view"),
        ("Space", "Pause or resume auto-rotation (3D)"),
        ("C", "Focus mode: frame the sherd (3D)"),
        ("G  ·  R", "Show or hide the grid, or the marked regions (photograph)"),
        ("F", "Fullscreen for the focused viewer"),
        ("M", "Measure on the photograph (distance in pixels of the original)"),
        ("Esc", "Close the palette, leave fullscreen or cancel a measurement")]
st.html('<table class="etp-keys"><caption class="sr-only">Keyboard shortcuts</caption><thead><tr><th scope="col">Keys</th>'
        '<th scope="col">Action</th></tr></thead><tbody>'
        + "".join(f"<tr><td><kbd>{e(k)}</kbd></td><td>{e(v)}</td></tr>" for k, v in KEYS) + "</tbody></table>")
grid([
    card("Research and Presentation", "Research mode shows hashes, paths, gate detail and verification tables. Presentation "
         "hides that detail for a demonstration. The AI warning, the labels and every limitation stay in both.", tilt=False),
    card("Every 3D view has a 2D equivalent", "Each 3D view has a 2D button. Without WebGL, or with reduced motion requested, "
         "the page switches to an accessible 2D view and says so. Adding ?no3d to the address forces 2D everywhere.", tilt=False),
    card("Derived displays are marked", "Exposure, contrast, edge emphasis and the 2.5D surface are computed in your browser "
         "for the eye only. They are labelled “Derived display — original source preserved.” The stored file is never changed.", tilt=False),
], "cols-3")
st.caption("3D rendering: three.js r170 (MIT licence), bundled with the app and served locally from app/static/vendor/three. "
           "No external network request is needed.")

section("Documentation")
st.markdown("`docs/USER_GUIDE.md` · `docs/ARCHITECTURE.md` · `docs/ANNOTATION_GUIDE.md` · `docs/DATASET_POLICY.md` · "
            "`docs/MODEL_CARD.md` · `docs/LIMITATIONS.md` · `docs/DEPLOYMENT.md` · `docs/FINAL_ENGINEERING_STATUS.md`")
footer()
