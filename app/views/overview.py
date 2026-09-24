"""Overview: what the system is, what it knows today, and how it reasons."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ui.boot import boot

boot("Overview")

import streamlit as st
from ui import data
from ui.components import badge, card, e, footer, grid, nav_link, section, stat
from ui.sherd3d import render_sherd

o = data.overview()

left, right = st.columns([1.05, 1], gap="large", vertical_alignment="center")
with left:
    st.html(
        '<div class="etp-rise"><div class="etp-eyebrow">Early Historic Tamil Nadu · pottery &amp; inscriptions</div>'
        '<h1 class="etp-h1">Reading the <em>archaeological</em> record</h1>'
        '<p class="etp-lede">A research assistant for early Tamil pottery. It looks at photographs with computer '
        "vision, then reasons only from recorded evidence: expert annotations, published sources and their "
        "verification. Where the evidence is thin, it says <b>insufficient evidence</b> and shows why.</p></div>")
    with st.container(horizontal=True, gap="medium"):
        nav_link("analyze.py", "Analyse a photograph")
        nav_link("views/workflow.py", "Project workflow")
with right:
    render_sherd(460)

section("What the project holds today", "live, from the records and stores")
training = "BLOCKED" if not o["training_ready"] else "READY"
grid([
    stat(o["artifacts"], "research artifacts", "openly licensed photographs"),
    stat(o["images"], "photographs", "each with a recorded SHA-256"),
    stat(o["project_annotations"], "project annotations", "not expert-reviewed"),
    stat(o["expert_annotations"], "expert annotations", "the only route to a label"),
    stat(f'{o["verified_references"]}/{o["references"]}', "references verified", "checked by a named human"),
    stat(training, "training", badge("blocked" if not o["training_ready"] else "pass",
                                     "gate G1–G11" if not o["training_ready"] else "gate passed"), word=True),
], "cols-6")
if not o["training_ready"]:
    st.html('<div class="etp-note" style="margin-top:.9rem">Training becomes available only after sufficient '
            "<b>expert-labelled archaeological data</b> exists: at least 5 artifacts in every class for "
            "grouped cross-validation, 20 for a hold-out split. No model is trained, and none is implied.</div>")

section("How it reasons", "four layers, never mixed")
grid([
    card("Expert annotation", "A qualified epigraphist's or archaeologist's judgement, with qualification and "
         "review state. The only source that can become a training label, through a reviewed, reversible step.",
         extra=badge("expert")),
    card("Project annotation", "Careful observation by a project annotator. Useful and recorded, but provisional: "
         "it is never promoted on its own.", extra=badge("project")),
    card("Verified evidence", "A published claim a named person checked in the source itself. Unverified and "
         "unresolved references are shown as such and cap confidence.", extra=badge("verified")),
    card("AI observation", "What a model or measurement suggests: image quality, regions, OCR, classifier "
         "probabilities. Reported for inspection only; never evidence.", extra=badge("ai")),
], "cols-4")

section("From the research set", "real photographs · Wikimedia Commons")
# Representative images: pilot photographs NOT suspected of being reproductions.
arts = [a for a in data.artifacts() if a["pilot"] and "possible_reproduction" not in a["flag_kinds"]][:3]     or data.artifacts()[:3]
tiles = []
for a in arts:
    im = a["images"][0]
    uri = data.thumbnail_b64(im["path"], 640)
    if not uri:
        continue
    flag = f" · {a['flags'][0]}" if a["flags"] else ""
    tiles.append(f'<figure class="etp-thumb" style="margin:0"><img src="{uri}" loading="lazy" '
                 f'alt="Research photograph {e(im["image_id"])} of artifact {e(a["artifact_id"])}">'
                 f'<figcaption class="cap"><b>{e(a["artifact_id"])}</b><span>{e(im["license"])} · '
                 f'{e(data.short_attribution(im["attribution"]))}{e(flag)}</span></figcaption></figure>')
if tiles:
    grid(tiles, "cols-3")
else:
    st.html('<div class="etp-note">Image files are not present on this machine. The records exist; the '
            "photographs are kept out of the repository and must be obtained under their licences.</div>")

section("Principles")
grid([
    card("An honest answer first", "“Insufficient evidence” is a valid result. The tool never fills a gap with "
         "a guess, a caption, a site date or a model probability.", tilt=False),
    card("Provenance on everything", "Every photograph has a licence, a source and a hash; every annotation says "
         "who made it; every append is chained in a tamper-evident ledger.", tilt=False),
    card("Disagreement is data", "Annotators work independently. Differences are listed item by item and "
         "resolved by an expert, never averaged away.", tilt=False),
], "asym")
footer()
