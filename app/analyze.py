"""Analysis page: upload a photograph (or pick a registered research photograph) and see
everything the project can honestly say about it.

    streamlit run app/main.py           (this page + the annotation tool)
    streamlit run app/analyze.py        (this page alone)

Layout follows ``src.inference.analyze``: image preview, image quality, regions,
classification, transcription, translation, estimated age, period, reasoning, evidence,
confidence, warnings. Four evidence layers are drawn DIFFERENTLY and never mixed:

* AI observation            amber warning box, "not archaeological evidence"
* Project annotation        neutral panel, "not expert-reviewed"
* Expert annotation         neutral panel, annotator and qualification shown
* Verified evidence         neutral panel; says "None" until a human verifies a source

Nothing on this page writes anything.
"""

from __future__ import annotations

import hashlib
import io
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import streamlit as st
from PIL import Image, ImageDraw

from src.dataset.convert import read_jsonl
from src.dataset.schema import RESEARCH_DATA_ROOT, RESEARCH_RECORDS_PATH
from src.detection import Region, RegionError, crop, parse_region
from src.inference import InferenceError, analyze
from src.ocr import enhance

COLOURS = {"human_annotation": (0, 170, 60), "user_supplied": (40, 110, 255), "ai_prediction": (255, 150, 0)}
AI_BANNER = "AI OBSERVATION: not archaeological evidence. Do not copy it into an annotation without independent verification."


@st.cache_data(show_spinner="Analysing...", max_entries=16)
def _analyse(data: bytes, artifact_id: str | None, regions: tuple[str, ...]) -> dict:
    return analyze(data, artifact_id=artifact_id or None,
                   regions=[parse_region(r) for r in regions]).to_dict()


def _draw(image: Image.Image, regions: list[dict]) -> Image.Image:
    out = image.copy()
    out.thumbnail((1400, 1400))
    d = ImageDraw.Draw(out)
    w, h = out.size
    for r in regions:
        box = (r["x"] * w, r["y"] * h, (r["x"] + r["width"]) * w, (r["y"] + r["height"]) * h)
        d.rectangle(box, outline=COLOURS.get(r["source"], (255, 0, 0)), width=max(2, w // 250))
    return out


def _v(x: object) -> str:
    return "—" if x in (None, "", "not_available", "not_applicable", "unknown") else str(x)


st.set_page_config(page_title="Analyse a photograph", layout="wide")
st.title("Early Tamil Pottery - analyse a photograph")
st.caption("An assistive research tool, not an archaeologist. \"Insufficient evidence\" is a valid, "
           "often correct, answer. AI output is shown separately and is never evidence.")

records = read_jsonl(RESEARCH_RECORDS_PATH) if RESEARCH_RECORDS_PATH.exists() else []
with st.sidebar:
    st.header("Input")
    mode = st.radio("Image", ["Upload a photograph", "A registered research photograph"], key="mode")
    data: bytes | None = None
    if mode == "Upload a photograph":
        up = st.file_uploader("JPEG, PNG, TIFF, WebP or BMP", type=["jpg", "jpeg", "png", "tif", "tiff", "webp", "bmp"])
        if up is not None:
            data = up.getvalue()
    elif records:
        ids = sorted(r["image_id"] for r in records)
        image_id = st.selectbox("Research photograph", ids, key="image_id",
                                format_func=lambda i: f"{i}  ({next(r['artifact_id'] for r in records if r['image_id'] == i)})")
        rec = next(r for r in records if r["image_id"] == image_id)
        path = RESEARCH_DATA_ROOT / rec["image_path"]
        if path.is_file():
            data = path.read_bytes()
        else:
            st.warning(f"Image file not present: {rec['image_path']}")
    else:
        st.info("No research records.")
    artifact_id = st.text_input("Expected artifact id (optional)",
                                help="Annotations apply only if the photograph is registered (SHA-256 match).")
    region_text = st.text_area("Your regions (optional, one 'x,y,w,h' per line, normalised 0-1)",
                               help="A viewing aid. User regions are never evidence.")
    show_enhanced = st.checkbox("Show enhanced crops of regions (contrast aid)", value=False)

if data is None:
    st.info("Upload a photograph or choose a registered research photograph in the sidebar.")
    st.stop()

regions = tuple(line.strip() for line in region_text.splitlines() if line.strip())
try:
    for r in regions:
        parse_region(r)
except RegionError as exc:
    st.error(f"Region not accepted: {exc}")
    st.stop()
try:
    res = _analyse(data, artifact_id.strip() or None, regions)
except InferenceError as exc:
    st.error(f"The image could not be analysed: {exc}")
    st.stop()

img = Image.open(io.BytesIO(data))
img.load()
img = img.convert("RGB")
info = res["image"]

# -- summary ------------------------------------------------------------------------------
st.subheader("Summary")
st.markdown(f"### {res['summary']}")
c1, c2, c3 = st.columns(3)
c1.metric("Registered photograph", "yes" if info["registered"] else "no")
c2.metric("Archaeological confidence", res["confidence"]["archaeological"])
c3.metric("Estimated age", res["age"]["display"])
if info["registered"]:
    st.caption(f"{info['artifact_id']} / {info['image_id']} - {_v(info.get('license'))} - {_v(info.get('attribution'))[:300]}"
               f" - source: {_v(info.get('source'))}")
else:
    st.caption(f"Unregistered image (sha256 {info['sha256'][:16]}...): no provenance, no annotations applied.")

# -- 1-4 image, quality, regions -------------------------------------------------------------
left, right = st.columns([3, 2])
with left:
    st.subheader("Image and inscription regions")
    st.image(_draw(img, res["regions"]), caption="green = human annotation, blue = yours, amber = AI")
    if not res["regions"]:
        st.caption("No region is marked. No validated automatic detector exists.")
    if show_enhanced and res["regions"]:
        cols = st.columns(min(4, len(res["regions"])))
        for i, r in enumerate(res["regions"]):
            reg = Region(r["x"], r["y"], r["width"], r["height"], r["source"])
            cols[i % len(cols)].image(enhance(crop(img, reg)), caption=f"{r['source']} (enhanced; viewing aid)")
with right:
    st.subheader("Image quality (technical)")
    q = res["image_quality"]
    st.dataframe([{"measure": k, "value": q[k]} for k in ("width_px", "height_px", "sharpness_laplacian_var",
                  "brightness_mean", "contrast_std", "dynamic_range", "highlight_clip_fraction")],
                 hide_index=True)
    st.caption("Flags: " + (", ".join(q["flags"]) or "none") + ". " + q["note"])

# -- 5-9 findings -----------------------------------------------------------------------------
st.subheader("Findings (from human evidence only)")
f1, f2 = st.columns(2)
with f1:
    st.markdown("**Classification / script**")
    st.write(res["script"]["statement"])
    st.caption(f"Asserted by: {res['script']['provenance_label']}")
    st.markdown("**Transcription**")
    st.write(res["transcription"]["statement"])
    for alt in res["transcription"]["human_reading"].get("alternative_readings", []):
        st.caption(f"Alternative reading: {alt.get('reading')} ({alt.get('source')})")
    st.markdown("**Translation**")
    tr = res["translation"]
    st.write(tr["translation"] if tr["state"] == "translated" else tr["meaning"])
with f2:
    st.markdown("**Estimated age**")
    st.write(res["age"]["display"] + (f" ({res['age']['centuries']})" if res["age"].get("centuries") else ""))
    st.markdown("**Period**")
    st.write(res["period"])
    st.markdown("**Confidence (archaeological)**")
    st.write(res["confidence"]["archaeological"])
    st.caption(res["confidence"]["note"])
    for s in res["status_statements"]:
        st.markdown(f"- {s}")

st.subheader("Reasoning")
for line in res["reasoning"]:
    st.markdown(f"- {line}")

# -- evidence layers ------------------------------------------------------------------------
st.subheader("Evidence layers (kept apart)")
L = res["layers"]
with st.container(border=True):
    st.markdown(f"**{L['expert_annotation']['label']}**")
    ex = L["expert_annotation"]["annotations"]
    st.dataframe(ex, hide_index=True) if ex else st.caption("No expert annotation of this artifact.")
with st.container(border=True):
    st.markdown(f"**{L['project_annotation']['label']}**")
    pr = L["project_annotation"]["annotations"]
    st.dataframe(pr, hide_index=True) if pr else st.caption("No project annotation of this artifact.")
with st.container(border=True):
    st.markdown(f"**{L['verified_evidence']['label']}**")
    ve = L["verified_evidence"]["references"]
    st.dataframe(ve, hide_index=True) if ve else st.caption(L["verified_evidence"]["statement"])
    refs = res["evidence"]["references"]
    if refs:
        st.caption("References cited by the evidence (effective status from the verification registry):")
        st.dataframe([{"ref_id": k, "status": v["verification_status"], "citation": v["citation"]}
                      for k, v in refs.items()], hide_index=True)
    if res["evidence"]["dating_evidence"]:
        st.dataframe(res["evidence"]["dating_evidence"], hide_index=True)
st.warning(f"**{AI_BANNER}**")
ai = L["ai_observation"]
with st.expander("AI observation details (classifier, detector, mark analysis, OCR)"):
    st.write("Classifier: " + ai["classification"]["statement"])
    if ai["classification"]["probabilities"]:
        st.dataframe([{"class": k, "model probability": v} for k, v in ai["classification"]["probabilities"].items()],
                     hide_index=True)
    st.write("Region detector: " + ai["region_detection"]["statement"])
    for row in ai["ocr"]:
        st.write(f"OCR [{row['status']}]: {row['statement']}")
    for row in ai["mark_analysis"]:
        st.write(f"Mark analysis [{row['status']}]: {row['statement']}")

# -- warnings ----------------------------------------------------------------------------------
st.subheader("Warnings and limitations")
for w in res["warnings"]:
    st.markdown(f"- {w}")
st.caption(res["disclaimer"])
st.caption(f"analysis digest {res['analysis_digest'][:16]} - input sha256 "
           f"{hashlib.sha256(data).hexdigest()[:16]} - result schema {res['schema_version']}")
