"""Overview: what the system is, what it knows today, and how it reasons."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ui.boot import boot, research

boot("Overview")

import streamlit as st
from ui import data
from ui.components import badge, blocked_state, card, e, footer, grid, mode_switch, nav_link, section, stat
from ui.scene3d import render_scene

o = data.overview()

_, top = st.columns([5, 1.6])
with top:
    mode_switch()
left, right = st.columns([1, 1.12], gap="large", vertical_alignment="center")
with left:
    st.html(
        '<div class="etp-rise"><div class="etp-pill">Digital archaeology laboratory · Early Historic Tamil Nadu</div>'
        '<h1 class="etp-h1">Reading the <em>archaeological</em> record</h1>'
        '<p class="etp-lede">A research workstation for early Tamil pottery and its inscriptions. It inspects '
        "photographs with computer vision, then reasons only from recorded evidence: expert annotations, "
        "published sources and their verification. Where the evidence is thin it says <b>insufficient "
        "evidence</b>, and shows you why.</p></div>")
    with st.container(horizontal=True, gap="medium"):
        nav_link("analyze.py", "Inspect a photograph")
        nav_link("views/dataset.py", "Open the collection")
        nav_link("views/workflow.py", "Project workflow")
        nav_link("analyze.py", "Run synthetic demonstration", query_params={"data": "synthetic"})
    st.caption("Press Ctrl + K (⌘ K) for commands. The synthetic demonstration runs the complete AI pipeline on "
               "generated images only: synthetic model output, not archaeological evidence.")
with right:
    render_scene(540)

section("What the project holds today", "live, from the records and stores")
ready = o["training_ready"]
grid([
    stat(o["artifacts"], "research artifacts", "openly licensed photographs"),
    stat(o["images"], "photographs", "each with a recorded SHA-256"),
    stat(o["project_annotations"], "project annotations", "not expert-reviewed"),
    stat(o["expert_annotations"], "expert annotations", "the only route to a label"),
    stat(f'{o["verified_references"]}/{o["references"]}', "references verified", "checked by a named person"),
    stat("READY" if ready else "BLOCKED", "training",
         badge("pass", "gate passed") if ready else badge("blocked", "gate G1–G11"), word=True),
], "cols-6")
if not ready:
    failing = [f'{g["id"]} {g.get("title", "")}: {g.get("detail", "")}' for g in o["gates"] if not g.get("passed")]
    st.html('<div style="margin-top:.9rem">' + blocked_state(
        "blocked", "Training — awaiting expert-labelled archaeological data",
        "No model is trained, and none is implied. Training becomes available only after sufficient expert-labelled "
        "archaeological data exists: at least 5 artifacts in every class for grouped cross-validation, 20 for a hold-out split.",
        failing) + "</div>")

section("How it reasons", "four layers, never mixed")
grid([
    card("Expert annotation", "A qualified epigraphist's or archaeologist's judgement, with qualification and review "
         "state. The only source that can become a training label, through a reviewed, reversible step.", extra=badge("expert", "Expert review")),
    card("Project annotation", "Careful observation by a project annotator. Recorded and useful, but provisional: never "
         "promoted on its own.", extra=badge("project", "Project annotation")),
    card("Verified evidence", "A published claim a named person checked in the source itself. Unverified and unresolved "
         "references are shown as such and cap confidence.", extra=badge("verified")),
    card("AI observation", "What a model or measurement suggests: image quality, regions, OCR, classifier probabilities. "
         "Shown for inspection only; never evidence.", extra=badge("ai", "AI observation — not evidence")),
], "cols-4")

section("From the collection", "real photographs · Wikimedia Commons")
arts = [a for a in data.artifacts() if a["pilot"] and "possible_reproduction" not in a["flag_kinds"]][:3] or data.artifacts()[:3]
tiles = []
for a in arts:
    im = a["images"][0]
    uri = data.thumbnail_b64(im["path"], 640)
    if not uri:
        continue
    flag = f" · {a['flags'][0]}" if a["flags"] else ""
    tiles.append(f'<figure class="etp-plinth" style="margin:0"><div class="plate"><div class="vit"><img src="{uri}" loading="lazy" '
                 f'alt="Research photograph {e(im["image_id"])} of artifact {e(a["artifact_id"])}"></div>'
                 f'<figcaption class="base"><div class="id">{e(a["artifact_id"])}</div><div class="meta">{e(im["license"])} · '
                 f'{e(data.short_attribution(im["attribution"]))}{e(flag)}</div></figcaption></div></figure>')
if tiles:
    grid(tiles, "cols-3")
else:
    st.html('<div class="etp-note">Image files are not present on this machine. The records exist; the photographs are '
            "kept out of the repository and must be obtained under their licences.</div>")

section("Principles")
grid([
    card("An honest answer first", "“Insufficient evidence” is a valid result. The tool never fills a gap with a guess, a "
         "caption, a site date or a model probability.", tilt=False),
    card("Provenance on everything", "Every photograph has a licence, a source and a hash; every annotation says who made it; "
         "every append is chained in a tamper-evident ledger.", tilt=False),
    card("Illustration is labelled", "The sherd above is drawn by the interface. It is not an artifact, carries no inscription, "
         "and has a 2D alternative; photographs remain the authoritative source.", tilt=False),
], "asym")
if research():
    st.caption("Research mode: every page shows provenance, hashes and verification detail. Switch to Presentation for a "
               "cleaner demonstration view; the AI warning and all limitations stay visible in both.")
footer()
