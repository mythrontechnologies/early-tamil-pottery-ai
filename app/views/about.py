"""About: purpose, what the tool is not, and where the limits are."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ui.boot import boot

boot("About")

import streamlit as st
from ui.components import card, footer, grid, page_header, section

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
    card("Illustrations are labelled", "The rotating sherd on the Overview is an illustrative visualization drawn "
         "by the interface: not a model of any real object, and its marks are not an inscription.", tilt=False),
    card("Colour never stands alone", "Every status carries a word and a shape as well as a colour; AI output always "
         "carries the words “AI observation”.", tilt=False),
], "cols-3")

section("Documentation")
st.markdown("`docs/USER_GUIDE.md` · `docs/ARCHITECTURE.md` · `docs/ANNOTATION_GUIDE.md` · `docs/DATASET_POLICY.md` · "
            "`docs/MODEL_CARD.md` · `docs/LIMITATIONS.md` · `docs/DEPLOYMENT.md` · `docs/FINAL_ENGINEERING_STATUS.md`")
footer()
