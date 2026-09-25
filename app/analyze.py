"""Analysis workstation: inspect a photograph and see everything the project can honestly say.

    streamlit run app/main.py           (all pages)
    streamlit run app/analyze.py        (this page alone)

Layout: title bar (artifact + status) · stage (2D photograph viewer, or 2.5D inspection) ·
evidence panel (script, reading, dating, evidence) · evidence chain (observation → reference) ·
evidence layers · AI observation (separate) · warnings.

The real photograph is always the authoritative source; every processed view is marked
derived. AI output appears only inside the panel "AI observation — not archaeological
evidence." Nothing on this page writes anything.
"""

from __future__ import annotations

import hashlib
import io
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ui.boot import boot, research

boot("Analysis")

import streamlit as st
from PIL import Image
from ui import data
from ui.chain import evidence_chain, render_chain
from ui.components import ai_panel, badge, e, footer, kv, note, page_header, reference_badge, section
from ui.inspect3d import render_inspection
from ui.viewer import render_viewer

from src.dataset.schema import RESEARCH_DATA_ROOT
from src.detection import RegionError, parse_region
from src.inference import InferenceError, analyze
from src.ocr import enhance


@st.cache_data(show_spinner="Analysing the photograph…", max_entries=16)
def _analyse(blob: bytes, artifact_id: str | None, regions: tuple[str, ...]) -> dict:
    return analyze(blob, artifact_id=artifact_id or None, regions=[parse_region(r) for r in regions]).to_dict()


@st.cache_data(show_spinner=False, max_entries=8)
def _images(blob: bytes) -> tuple[Image.Image, Image.Image]:
    img = Image.open(io.BytesIO(blob))
    img.load()
    img = img.convert("RGB")
    small = img.copy()
    small.thumbnail((1800, 1800))
    return img, enhance(small).convert("RGB")


def _v(x: object) -> str:
    return "—" if x in (None, "", "not_available", "not_applicable", "unknown") else str(x)


page_header("Analysis", "Artifact inspection workstation",
            "Choose a photograph. The photograph is the authoritative source; the panel reports only what recorded human "
            "evidence supports, and keeps AI observations apart.")

records = data.records()
with st.container(border=True):
    c1, c2 = st.columns([1, 2], vertical_alignment="bottom")
    source = c1.radio("Image", ["Upload a photograph", "A registered research photograph"], key="mode")
    blob: bytes | None = None
    with c2:
        if source == "Upload a photograph":
            up = st.file_uploader("JPEG, PNG, TIFF, WebP or BMP (max 50 MB)",
                                  type=["jpg", "jpeg", "png", "tif", "tiff", "webp", "bmp"])
            if up is not None:
                blob = up.getvalue()
        elif records:
            ids = sorted(r["image_id"] for r in records)
            by_id = {r["image_id"]: r for r in records}
            image_id = st.selectbox("Research photograph", ids, key="image_id",
                                    format_func=lambda i: f"{by_id[i]['artifact_id']}  ·  {i}")
            path = RESEARCH_DATA_ROOT / by_id[image_id]["image_path"]
            if path.is_file():
                blob = path.read_bytes()
            else:
                st.warning(f"The image file is not present on this machine: {by_id[image_id]['image_path']}")
        else:
            st.info("No research records.")
    with st.expander("Options: expected artifact, your regions"):
        o1, o2 = st.columns(2)
        artifact_id = o1.text_input("Expected artifact id (optional)", key="artifact_id",
                                    help="Annotations apply only if the photograph is registered (SHA-256 match).")
        region_text = o2.text_area("Your regions (one normalised 'x,y,w,h' per line)", key="regions",
                                   help="A viewing aid only. Your regions are never evidence.")

if blob is None:
    note("<b>No photograph selected.</b> Upload one, or choose a registered research photograph above. An uploaded image "
         "that is not in the research set has no provenance, so the honest answer will usually be “Insufficient evidence”.")
    footer()
    st.stop()

regions = tuple(line.strip() for line in region_text.splitlines() if line.strip())
try:
    for r in regions:
        parse_region(r)
except RegionError as exc:
    st.error(f"Region not accepted: {exc}")
    st.stop()
try:
    res = _analyse(blob, artifact_id.strip() or None, regions)
except InferenceError as exc:
    st.error(f"The image could not be analysed: {exc}")
    st.stop()

info, q = res["image"], res["image_quality"]
img, enhanced = _images(blob)
title = info.get("artifact_id") or "Unregistered photograph"
flags = [w for w in res["warnings"] if w.startswith("REVIEW REQUIRED")]

# -- title bar ---------------------------------------------------------------------------------
st.html(f'<div class="etp-title-bar" role="region" aria-label="Artifact status"><h2>{e(title)}</h2>'
        + (badge("pass", "registered photograph") if info["registered"] else badge("unresolved", "unregistered image"))
        + badge("neutral", "archaeological confidence: " + res["confidence"]["archaeological"])
        + "".join(badge("unresolved", "review flag") for _ in flags[:1]) + "</div>"
        f'<p class="etp-verdict" style="font-size:clamp(1.3rem,2vw,1.8rem);margin:0 0 .8rem">{e(res["summary"])}</p>')

# -- stage + evidence panel ---------------------------------------------------------------------
stage_col, panel_col = st.columns([1.55, 1], gap="large")
with stage_col:
    view = st.segmented_control("Stage view", ["Photograph · 2D", "2.5D inspection"], default="Photograph · 2D",
                                key="stage_view", help="2D is the authoritative photograph. 2.5D maps the same photograph onto "
                                                      "an illustrative curved surface for raking-light inspection.")
    alt = f"Photograph {info.get('image_id') or 'uploaded'} of {info.get('artifact_id') or 'an unregistered object'}"
    if view == "2.5D inspection":
        disp = img.copy()
        disp.thumbnail((1600, 1600))
        render_inspection(disp, res["regions"], alt=alt, height=560)
    else:
        meta = (f"{info['width_px']}×{info['height_px']} px · {info['format']} · sha256 {info['sha256']}" if research()
                else f"{info['width_px']}×{info['height_px']} px")
        render_viewer(img, res["regions"], alt=alt, meta=meta, enhanced=enhanced, height=560)
    st.caption("The real photograph is the authoritative source; the stored file is only read. Any adjusted or "
               "2.5D view is derived and is labelled as such.")

with panel_col:
    hr, tr = res["transcription"]["human_reading"], res["translation"]
    ds = res["age"].get("dating_summary", {})
    refs = res["evidence"]["references"]
    ver = sum(v["verification_status"] == "verified_against_source" for v in refs.values())
    translation = tr["translation"] if tr["state"] == "translated" else tr["meaning"]
    alts = "".join(f'<div class="who">Alternative reading: {e(a.get("reading"))} ({e(a.get("source"))})</div>'
                   for a in hr.get("alternative_readings", []))
    rows = [("Artifact", info.get("artifact_id") or "unregistered", True), ("Image", info.get("image_id") or "uploaded file", True),
            ("Source", _v(info.get("source")), False), ("Licence", _v(info.get("license")), False),
            ("Attribution", data.short_attribution(info.get("attribution")) if info.get("attribution") else "—", False)]
    if research():
        rows.append(("SHA-256", info["sha256"], True))
    st.html(
        '<section class="etp-shell" aria-label="Analysis panel"><div class="etp-core">'
        f'<div class="etp-finding"><div class="k">Script</div><div class="v">{e(res["script"]["statement"])}</div>'
        f'<div class="who">Asserted by: {e(res["script"]["provenance_label"])}</div></div>'
        f'<div class="etp-finding"><div class="k">Reading</div><div class="v">{e(res["transcription"]["statement"])}</div>{alts}</div>'
        f'<div class="etp-finding"><div class="k">Translation</div><div class="v">{e(translation)}</div></div>'
        f'<div class="etp-finding"><div class="k">Dating</div><div class="v">{e(res["age"]["display"])}</div>'
        f'<div class="who">Period: {e(res["period"])}</div><div class="who">Basis: {e("; ".join(ds.get("basis", [])) or "none")}</div></div>'
        f'<div class="etp-finding"><div class="k">Evidence</div><div class="v">{ver} verified reference(s) · {len(refs)} cited</div>'
        f'<div class="who">Confidence (archaeological): {e(res["confidence"]["archaeological"])}. A model probability is never an archaeological confidence.</div></div>'
        f'<div class="etp-finding"><div class="k">Artifact &amp; provenance</div>{kv(rows)}</div>'
        "</div></section>")

# -- evidence chain -----------------------------------------------------------------------------
section("Evidence chain", "observation → reference · select a step for detail")
st.html(render_chain(evidence_chain(res)))

section("Reasoning", "every line traces to a recorded input")
st.html('<ol style="margin:0;padding-left:1.2rem;color:var(--text-2);line-height:1.7;max-width:100ch">'
        + "".join(f"<li>{e(x)}</li>" for x in res["reasoning"]) + "</ol>")

section("Evidence layers", "kept apart")
L = res["layers"]
ex, pr, ve = L["expert_annotation"]["annotations"], L["project_annotation"]["annotations"], L["verified_evidence"]["references"]


def _ann_rows(items: list[dict]) -> str:
    return "".join(f'<p><span class="etp-mono">{e(a["annotator"])}</span> · {e(a["review_state"])} · script '
                   f'{e(a["script_type"])} · presence {e(a["inscription_present"])} · object {e(a["object_status"])}</p>'
                   for a in items)


st.html(
    f'<div class="etp-layer expert"><h5>{badge("expert", "Expert review")} {e(L["expert_annotation"]["label"])}</h5>'
    + (_ann_rows(ex) or "<p>No expert annotation of this artifact.</p>") + "</div>"
    f'<div class="etp-layer project"><h5>{badge("project", "Project annotation")} {e(L["project_annotation"]["label"])}</h5>'
    + (_ann_rows(pr) or "<p>No project annotation of this artifact.</p>") + "</div>"
    f'<div class="etp-layer verified"><h5>{badge("verified") if ve else badge("neutral", "verified layer · empty")} '
    f'{e(L["verified_evidence"]["label"])}</h5>'
    + ("".join(f'<p>{e(v["ref_id"])}: {e(v["citation"])}</p>' for v in ve) or f'<p>{e(L["verified_evidence"]["statement"])}</p>')
    + "</div>")
if refs and research():
    st.html('<div class="etp-card" style="padding:.9rem 1.1rem"><div class="etp-eyebrow">References cited by the evidence</div>'
            + "".join(f'<div style="display:flex;gap:.6rem;align-items:center;margin-top:.5rem">'
                      f'{reference_badge(v["verification_status"])}<span class="etp-mono">{e(k)}</span>'
                      f'<span style="color:var(--text-2);font-size:.88rem">{e(v["citation"])}</span></div>'
                      for k, v in refs.items()) + "</div>")

section("AI observation", "for inspection only")
ai = L["ai_observation"]
ocr = "".join(f"<li>OCR [{e(o['status'])}]: {e(o['statement'])}</li>" for o in ai["ocr"])
marks = "".join(f"<li>Mark analysis [{e(m['status'])}]: {e(m['statement'])}</li>" for m in ai["mark_analysis"])
probs = ai["classification"]["probabilities"]
prob_html = ("<p>Model probabilities (not archaeological confidence): " + ", ".join(
    f'{e(k)} {v:.2f}' for k, v in probs.items()) + "</p>") if probs else ""
ai_panel(f'<ul style="margin:.2rem 0 0 1.1rem;padding:0;line-height:1.6"><li>Classifier: {e(ai["classification"]["statement"])}</li>'
         f'<li>Region detector: {e(ai["region_detection"]["statement"])}</li>{marks}{ocr}</ul>{prob_html}'
         "<p style='margin-top:.5rem'>Do not copy an AI observation into an annotation without independent verification.</p>")

section("Warnings and limitations")
st.html('<ul style="margin:0;padding-left:1.2rem;color:var(--text-2);line-height:1.7">'
        + "".join(f"<li>{e(w)}</li>" for w in res["warnings"]) + "</ul>")
st.caption(res["disclaimer"])
if research():
    st.caption(f"analysis digest {res['analysis_digest'][:16]} · input sha256 {hashlib.sha256(blob).hexdigest()[:16]} · "
               f"result schema {res['schema_version']}")
footer()
