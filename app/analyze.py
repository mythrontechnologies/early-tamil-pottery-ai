"""Analysis: inspect a photograph and see everything the project can honestly say about it.

    streamlit run app/main.py           (all pages)
    streamlit run app/analyze.py        (this page alone)

The real photograph is the centrepiece (inspection viewer: zoom, pan, fullscreen, graticule,
coordinates, region overlays, original/enhanced comparison). The analysis panel follows
``src.inference.analyze``: artifact, provenance, visual observations, inscription detection,
script, dating, reasoning, confidence, references.

Evidence layers are drawn apart and never mixed. AI output appears only inside the panel
marked "AI observation — not archaeological evidence." Nothing on this page writes anything.
"""

from __future__ import annotations

import hashlib
import io
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ui.boot import boot

boot("Analysis")

import streamlit as st
from PIL import Image
from ui import data
from ui.components import ai_panel, badge, e, footer, kv, note, page_header, reference_badge, section
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


page_header("Analysis", "Inspect a photograph",
            "Upload a photograph or choose one from the research set. The photograph is the authoritative source; "
            "the panel reports only what recorded human evidence supports, and keeps AI observations apart.")

records = data.records()
with st.container(border=True):
    c1, c2 = st.columns([1, 2], vertical_alignment="bottom")
    mode = c1.radio("Image", ["Upload a photograph", "A registered research photograph"], key="mode",
                    horizontal=False)
    blob: bytes | None = None
    with c2:
        if mode == "Upload a photograph":
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
    note("<b>No photograph selected.</b> Upload one, or choose a registered research photograph above. "
         "An uploaded image that is not in the research set has no provenance, so the honest answer will "
         "usually be “Insufficient evidence”.")
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

# -- verdict ---------------------------------------------------------------------------------
reg_badge = badge("pass", "registered photograph") if info["registered"] else badge("unresolved", "unregistered image")
st.html(f'<section aria-label="Summary" style="margin:1.2rem 0 .6rem"><div class="etp-eyebrow">Summary</div>'
        f'<h2 class="etp-verdict">{e(res["summary"])}</h2><div style="display:flex;gap:.45rem;flex-wrap:wrap">'
        f'{reg_badge}{badge("neutral", "archaeological confidence: " + res["confidence"]["archaeological"])}'
        + "".join(badge("unresolved", "review flag") for w in res["warnings"] if w.startswith("REVIEW REQUIRED"))
        + "</div></section>")

left, right = st.columns([1.35, 1], gap="large")
with left:
    alt = (f"Photograph {info.get('image_id') or 'uploaded'} of {info.get('artifact_id') or 'an unregistered object'}")
    meta = f"{info['width_px']}×{info['height_px']} px · {info['format']} · sha256 {info['sha256']}"
    render_viewer(img, res["regions"], alt=alt, meta=meta, enhanced=enhanced, height=560)
    st.caption("Display copy of the real photograph (the stored file is only read). The enhanced view is a "
               "contrast aid for the eye, not evidence.")

with right, st.container(border=True):
    hr = res["transcription"]["human_reading"]
    tr = res["translation"]
    ds = res["age"].get("dating_summary", {})
    prov = kv([("Artifact", info.get("artifact_id") or "unregistered", True),
               ("Image", info.get("image_id") or "uploaded file", True),
               ("Licence", _v(info.get("license")), False),
               ("Attribution", data.short_attribution(info.get("attribution")) if info.get("attribution") else "—", False),
               ("Source", _v(info.get("source")), False),
               ("SHA-256", info["sha256"], True)])
    n_by = {}
    for r in res["regions"]:
        n_by[r["source"]] = n_by.get(r["source"], 0) + 1
    regions_txt = (", ".join(f"{n} {k.replace('_', ' ')}" for k, n in n_by.items())
                   if n_by else "No region is marked. No validated automatic detector exists.")
    alts = "".join(f'<div class="who">Alternative reading: {e(a.get("reading"))} ({e(a.get("source"))})</div>'
                   for a in hr.get("alternative_readings", []))
    translation = tr["translation"] if tr["state"] == "translated" else tr["meaning"]
    st.html(
        '<div aria-label="Analysis panel">'
        f'<div class="etp-finding"><div class="k">Artifact &amp; provenance</div>{prov}</div>'
        f'<div class="etp-finding"><div class="k">Visual observations · technical</div><div class="v etp-mono" '
        f'style="font-size:.86rem">sharpness {e(q["sharpness_laplacian_var"])} · brightness {e(q["brightness_mean"])} · '
        f'contrast {e(q["contrast_std"])} · range {e(q["dynamic_range"])}</div><div class="who">Flags: '
        f'{e(", ".join(q["flags"]) or "none")} — uncalibrated; they describe the photograph, not the object.</div></div>'
        f'<div class="etp-finding"><div class="k">Inscription detection</div><div class="v">{e(regions_txt)}</div></div>'
        f'<div class="etp-finding"><div class="k">Script assessment</div><div class="v">{e(res["script"]["statement"])}</div>'
        f'<div class="who">Asserted by: {e(res["script"]["provenance_label"])}</div></div>'
        f'<div class="etp-finding"><div class="k">Transcription</div><div class="v">{e(res["transcription"]["statement"])}</div>{alts}</div>'
        f'<div class="etp-finding"><div class="k">Translation</div><div class="v">{e(translation)}</div></div>'
        f'<div class="etp-finding"><div class="k">Dating evidence</div><div class="v">{e(res["age"]["display"])}'
        + (f' <span class="who">({e(res["age"]["centuries"])})</span>' if res["age"].get("centuries") else "")
        + f'</div><div class="who">Period: {e(res["period"])}</div>'
        f'<div class="who">Basis: {e("; ".join(ds.get("basis", [])) or "none")}</div></div>'
        f'<div class="etp-finding"><div class="k">Confidence · archaeological</div><div class="v">{e(res["confidence"]["archaeological"])}</div>'
        f'<div class="who">{e(res["confidence"]["note"])}</div></div></div>')

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
    f'<div class="etp-layer expert"><h5>{badge("expert")} {e(L["expert_annotation"]["label"])}</h5>'
    + (_ann_rows(ex) or "<p>No expert annotation of this artifact.</p>") + "</div>"
    f'<div class="etp-layer project"><h5>{badge("project")} {e(L["project_annotation"]["label"])}</h5>'
    + (_ann_rows(pr) or "<p>No project annotation of this artifact.</p>") + "</div>"
    f'<div class="etp-layer verified"><h5>{badge("verified") if ve else badge("neutral", "verified layer · empty")} '
    f'{e(L["verified_evidence"]["label"])}</h5>'
    + ("".join(f'<p>{e(v["ref_id"])}: {e(v["citation"])}</p>' for v in ve) or f'<p>{e(L["verified_evidence"]["statement"])}</p>')
    + "</div>")
refs = res["evidence"]["references"]
if refs:
    st.html('<div class="etp-card" style="padding:.9rem 1.1rem"><div class="etp-eyebrow">References cited by the evidence</div>'
            + "".join(f'<div style="display:flex;gap:.6rem;align-items:center;margin-top:.5rem">'
                      f'{reference_badge(v["verification_status"])}<span class="etp-mono">{e(k)}</span>'
                      f'<span style="color:var(--text-2);font-size:.88rem">{e(v["citation"])}</span></div>'
                      for k, v in refs.items()) + "</div>")
if res["evidence"]["dating_evidence"]:
    st.dataframe(res["evidence"]["dating_evidence"], hide_index=True)

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
st.caption(f"analysis digest {res['analysis_digest'][:16]} · input sha256 {hashlib.sha256(blob).hexdigest()[:16]} · "
           f"result schema {res['schema_version']}")
footer()
