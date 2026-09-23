"""Annotation interface (Milestones 7-8).

    streamlit run app/annotate.py

Select an artifact, view its photographs, zoom, mark inscription regions, record object,
inscription, reading, interpretation, linguistic features, dating evidence, references,
image usability and uncertainty, then save. Saving APPENDS a new annotation record; it never
edits source metadata or another annotator's record. Review previous annotations,
disagreements and the reasoning output in the "Review" tab.

Milestone 8 additions, and nothing more: a "pilot artifacts only" filter (the six Keezhadi
close-ups by default), a gallery of every photograph of the selected artifact, a read-only
table of the references' EFFECTIVE verification status, and a "Pilot & agreement" tab.

The annotation store path can be overridden with ETPAI_ANNOTATIONS_PATH (used by tests).
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import streamlit as st
from PIL import Image, ImageOps

from src.annotation.agreement import compute_agreement, render_agreement
from src.annotation.form import build_annotation, crop_view, draw_regions
from src.annotation.model import ANNOTATIONS_PATH, load_annotation_schema
from src.annotation.pilot import load_pilot, pilot_status, render_pilot
from src.annotation.resolve import resolve_artifact
from src.annotation.store import AnnotationRejected, AnnotationStore
from src.dataset.convert import read_jsonl
from src.dataset.schema import RESEARCH_DATA_ROOT, RESEARCH_RECORDS_PATH
from src.knowledge.verification import effective_statuses, key_references
from src.preprocessing.loader import load_image
from src.preprocessing.transforms import apply_exif_orientation, to_rgb
from src.reasoning.engine import analyze_artifact, render_text
from src.reasoning.from_annotations import build_inputs

SCHEMA = load_annotation_schema()
P = SCHEMA["properties"]
D = SCHEMA["$defs"]
CONF = D["confidence"]["enum"]
YNU = D["yes_no_uncertain_unknown"]["enum"]


def enum(section: str, field: str) -> list[str]:
    return P[section]["properties"][field]["enum"]


@st.cache_data(show_spinner=False)
def thumbnail(path: str, size: int = 360) -> Image.Image:
    """A small copy for the gallery; the stored image is only read."""
    with Image.open(path) as im:
        im.draft("RGB", (size * 2, size * 2))
        out = ImageOps.exif_transpose(im).convert("RGB")
    out.thumbnail((size, size))
    return out


st.set_page_config(page_title="Pottery annotation", layout="wide")
store = AnnotationStore(Path(os.environ.get("ETPAI_ANNOTATIONS_PATH", ANNOTATIONS_PATH)))
records = read_jsonl(RESEARCH_RECORDS_PATH) if RESEARCH_RECORDS_PATH.exists() else []
by_artifact: dict[str, list[dict]] = {}
for r in sorted(records, key=lambda r: r["image_id"]):
    by_artifact.setdefault(r["artifact_id"], []).append(r)

st.title("Early Tamil Pottery - annotation")
st.caption("Annotations are appended, never overwritten. Leave anything you cannot determine "
           "as 'unknown'. Do not label from a guess, from the file name, or from an AI suggestion.")

if not by_artifact:
    st.warning("No research records found. Nothing to annotate.")
    st.stop()

# -- annotator ---------------------------------------------------------------------------
with st.sidebar:
    st.header("Annotator")
    annotator_id = st.text_input("Annotator id", key="annotator_id",
                                 help="A stable id, e.g. initials. Required to save.")
    prov_labels = {"project_annotation": "Project annotator (my own examination)",
                   "source_information": "Transcribing a published source (cite it)",
                   "expert_annotation": "Expert (qualified archaeologist / epigraphist)"}
    provenance_type = st.radio("I am recording", list(prov_labels), format_func=prov_labels.get)
    qualification = ""
    if provenance_type == "expert_annotation":
        qualification = st.text_input("Qualification and affiliation (required for experts)")
    try:
        pilot = load_pilot()
    except ValueError:
        pilot = None
    pilot_ids = [a for a in (pilot.artifacts if pilot else ()) if a in by_artifact]
    pilot_only = st.checkbox("Pilot artifacts only", value=bool(pilot_ids), disabled=not pilot_ids,
                             help="The Milestone 8 pilot: six Keezhadi incised-sherd close-ups. "
                                  "Not assumed to be Tamil-Brahmi.")
    choices = pilot_ids if pilot_only and pilot_ids else sorted(by_artifact)
    artifact_id = st.selectbox("Artifact", choices,
                               format_func=lambda a: f"{a}  ({len(by_artifact[a])} photo(s))")

recs = by_artifact[artifact_id]
image_ids = [r["image_id"] for r in recs]
st.session_state.setdefault("regions", {})
regions: list[dict] = st.session_state["regions"].setdefault(artifact_id, [])

tab_annotate, tab_review, tab_pilot = st.tabs(["Annotate", "Review", "Pilot & agreement"])

with tab_annotate:
    # -- photographs, zoom, regions ---------------------------------------------------
    st.subheader("Photographs")
    with st.expander(f"All {len(recs)} photograph(s) of this artifact", expanded=len(recs) > 1):
        cols = st.columns(min(len(recs), 4))
        for i, r in enumerate(recs):
            try:
                cols[i % len(cols)].image(thumbnail(str(RESEARCH_DATA_ROOT / r["image_path"])),
                                          caption=r["image_id"])
            except OSError as exc:
                cols[i % len(cols)].warning(f"{r['image_id']}: {exc}")
    st.caption("Source label (what the uploader said): " + " | ".join(sorted({r["notes"].split(
        "Source label (verbatim): ")[-1].split(". Artifact grouping")[0] for r in recs}))[:500])
    image_id = st.selectbox("Photograph", image_ids)
    rec = next(r for r in recs if r["image_id"] == image_id)
    loaded = load_image(RESEARCH_DATA_ROOT / rec["image_path"], compute_hash=False)
    if not loaded.ok:
        st.error("Image could not be loaded: " + "; ".join(str(i) for i in loaded.errors))
        st.stop()
    image = to_rgb(apply_exif_orientation(loaded.image))
    display = image.copy()
    display.thumbnail((1600, 1600))
    c1, c2 = st.columns(2)
    with c1:
        st.image(draw_regions(display, regions, image_id), caption=f"{image_id} (regions in red)")
    with c2:
        st.markdown("**Zoom** (normalised window)")
        zx = st.slider("x range", 0.0, 1.0, (0.0, 1.0), 0.01, key="zx")
        zy = st.slider("y range", 0.0, 1.0, (0.0, 1.0), 0.01, key="zy")
        st.image(crop_view(image, zx[0], zx[1], zy[0], zy[1]), caption="zoomed (full resolution)")
        st.markdown("**Mark a region** (the current zoom window becomes the region)")
        rlabel = st.selectbox("Region label", D["region"]["properties"]["label"]["enum"])
        rnote = st.text_input("Region note (optional)")
        if st.button("Add region from zoom window"):
            region = {"image_id": image_id, "x": round(zx[0], 4), "y": round(zy[0], 4),
                      "width": round(max(zx[1] - zx[0], 0.0001), 4),
                      "height": round(max(zy[1] - zy[0], 0.0001), 4), "label": rlabel}
            if rnote.strip():
                region["note"] = rnote.strip()
            regions.append(region)
        if regions:
            st.dataframe(regions)
            if st.button("Clear regions"):
                regions.clear()

    # -- annotation form --------------------------------------------------------------
    with st.form("annotation"):
        st.subheader("Object")
        o1, o2 = st.columns(2)
        object_type = o1.selectbox("Object type", enum("object", "object_type"), index=enum("object", "object_type").index("unknown"))
        pottery_type = o2.selectbox("Pottery type (ware)", enum("object", "pottery_type"), index=enum("object", "pottery_type").index("unknown"))
        text_fields = {k: st.text_input(k.replace("_", " ").capitalize(), placeholder="unknown")
                       for k in ("fabric", "surface", "manufacturing_characteristics", "colour",
                                 "decoration", "condition")}

        st.subheader("Inscription")
        i1, i2, i3 = st.columns(3)
        inscription_present = i1.selectbox("Inscription present", enum("inscription", "inscription_present"), index=3,
                                           help="'uncertain' = you examined it and cannot tell; 'unknown' = not examined")
        script_type = i2.selectbox("Script type", enum("inscription", "script_type"),
                                   index=enum("inscription", "script_type").index("unknown"))
        script_confidence = i3.selectbox("Script confidence", CONF, index=CONF.index("unknown"))
        i4, i5 = st.columns(2)
        inscription_type = i4.selectbox("Inscription type (project category)", enum("inscription", "inscription_type"),
                                         index=enum("inscription", "inscription_type").index("unknown"))
        characters_visible = i5.number_input("Characters visible (0 = not counted)", 0, 200, 0)
        reading = st.text_input("Reading (as read; keep editorial marks)", placeholder="not_available")
        transliteration = st.text_input("Transliteration", placeholder="not_available")
        r1, r2, r3 = st.columns(3)
        transliteration_scheme = r1.selectbox("Transliteration scheme", enum("inscription", "transliteration_scheme"),
                                              index=enum("inscription", "transliteration_scheme").index("not_available"))
        reading_confidence = r2.selectbox("Reading confidence", CONF, index=CONF.index("not_applicable"))
        reading_source = r3.text_input("Reading source (ref_id or 'this_annotator')", placeholder="not_available")
        alt = st.data_editor([{"reading": "", "source": "", "note": ""}], num_rows="dynamic", key="alt")

        st.subheader("Translation / meaning")
        t1, t2 = st.columns(2)
        interpretation_type = t1.selectbox("Interpretation type (project category)", enum("interpretation", "interpretation_type"),
                                           index=enum("interpretation", "interpretation_type").index("not_applicable"))
        translation_confidence = t2.selectbox("Translation confidence", CONF, index=CONF.index("not_applicable"))
        translation = st.text_input("Translation (leave empty if none is established)")
        meaning = st.text_input("Meaning / explanation", placeholder="e.g. Proper name; no literal translation established.")
        translation_source = st.text_input("Translation source (ref_id or 'this_annotator')", placeholder="not_available")

        st.subheader("Linguistic features")
        ling = st.data_editor([{"feature_type": "word_form", "observation": "", "confidence": "unknown",
                                "source_reference": "annotator_observation", "significance": ""}],
                              num_rows="dynamic", key="ling",
                              column_config={"feature_type": st.column_config.SelectboxColumn(
                                  options=D["linguistic_feature"]["properties"]["feature_type"]["enum"]),
                                  "confidence": st.column_config.SelectboxColumn(options=CONF)})

        st.subheader("Dating evidence")
        st.caption("One row per piece of evidence. Years: negative = BCE, positive = CE, no year 0. "
                   "Leave bounds empty if the evidence does not bound the date.")
        ev = st.data_editor([{"evidence_type": "palaeography", "observation": "", "supports_start_year": None,
                              "supports_end_year": None, "supports": "", "association": "not_applicable",
                              "confidence": "unknown", "source_reference": "annotator_observation"}],
                            num_rows="dynamic", key="ev",
                            column_config={"evidence_type": st.column_config.SelectboxColumn(
                                options=D["dating_evidence"]["properties"]["evidence_type"]["enum"]),
                                "association": st.column_config.SelectboxColumn(
                                    options=D["dating_evidence"]["properties"]["association"]["enum"]),
                                "confidence": st.column_config.SelectboxColumn(options=CONF),
                                "supports_start_year": st.column_config.NumberColumn(step=1),
                                "supports_end_year": st.column_config.NumberColumn(step=1)})
        dd1, dd2, dd3 = st.columns(3)
        est_start = dd1.text_input("Estimated start year (optional)")
        est_end = dd2.text_input("Estimated end year (optional)")
        dating_confidence = dd3.selectbox("Dating confidence", CONF, index=CONF.index("unknown"))

        st.subheader("References")
        st.caption("A reference is 'verified_against_source' only when the verification registry says "
                   "so (python -m src.knowledge status); a self-declared status is rejected (rule N14). "
                   "Cite knowledge-base ids (R1, S01, S03, ...) where they apply.")
        refs = st.data_editor([{"ref_id": "", "citation": "", "locator": "", "verification_status": "unverified"}],
                              num_rows="dynamic", key="refs",
                              column_config={"verification_status": st.column_config.SelectboxColumn(
                                  options=D["reference"]["properties"]["verification_status"]["enum"])})

        st.subheader("Archaeological usability (per photograph)")
        usability = []
        for iid in image_ids:
            cols = st.columns(6)
            cols[0].markdown(f"`{iid}`")
            u = {"image_id": iid}
            for col, f in zip(cols[1:], ("sherd_visible", "inscription_visible", "characters_readable",
                                         "morphology_visible", "usable_for_annotation")):
                u[f] = col.selectbox(f.replace("_", " "), YNU, index=YNU.index("unknown"), key=f"{iid}-{f}")
            usability.append(u)

        uncertainty_notes = st.text_area("Uncertainty notes")
        notes = st.text_area("Other notes")
        review_state = st.selectbox("Review state", P["review_state"]["enum"],
                                    help="'expert_reviewed' is only valid for expert annotations")
        submitted = st.form_submit_button("Save annotation (append)")

    if submitted:
        if not annotator_id.strip():
            st.error("Annotator id is required.")
        else:
            values = dict(
                artifact_id=artifact_id, image_ids=image_ids, annotator_id=annotator_id.strip(),
                provenance_type=provenance_type, qualification=qualification, review_state=review_state,
                object_type=object_type, pottery_type=pottery_type, **text_fields,
                inscription_present=inscription_present, script_type=script_type,
                script_confidence=script_confidence, inscription_type=inscription_type,
                regions=list(regions), characters_visible=int(characters_visible) or None,
                reading=reading, transliteration=transliteration,
                transliteration_scheme=transliteration_scheme, reading_confidence=reading_confidence,
                reading_source=reading_source, alternative_readings=[r for r in alt if r.get("reading")],
                interpretation_type=interpretation_type, translation=translation, meaning=meaning,
                translation_confidence=translation_confidence, translation_source=translation_source,
                linguistic_features=[r for r in ling if r.get("observation")],
                dating_evidence=ev, estimated_start_year=est_start, estimated_end_year=est_end,
                dating_confidence=dating_confidence, references=refs, image_usability=usability,
                uncertainty_notes=uncertainty_notes, notes=notes,
            )
            mine = [a for a in store.current(artifact_id)
                    if a["annotator"]["annotator_id"] == annotator_id.strip()]
            if mine:
                values["supersedes"] = mine[-1]["annotation_id"]
            try:
                saved = store.append(build_annotation(values))
                st.success(f"Saved {saved['annotation_id']}"
                           + (f" (supersedes {saved['supersedes']})" if saved["supersedes"] else ""))
            except AnnotationRejected as exc:
                st.error("Not saved. Fix these problems:")
                for p in exc.validation.problems:
                    st.write(f"- {p}")

with tab_annotate, st.expander("Reference verification status (read-only)"):
        keys = set(key_references())
        st.dataframe([{"ref_id": rid, "key": rid in keys, "effective_status": s.effective_status,
                       "verified_claims": len(s.verified_claims), "citation": s.citation}
                      for rid, s in effective_statuses().items()])

with tab_pilot:
    if pilot is None:
        st.info("No annotation pilot is configured (configs/project.yaml annotation_pilot).")
    else:
        all_current = store.current()
        st.text(render_pilot(pilot_status(all_current, set(by_artifact), pilot)))
        st.subheader("Agreement: project annotator vs expert")
        st.caption("Agreement measures the annotators. It never resolves a disagreement.")
        st.text(render_agreement(compute_agreement(all_current, pilot.artifacts)))

with tab_review:
    current = store.current(artifact_id)
    res = resolve_artifact(artifact_id, current)
    st.metric("Status", res.status)
    st.write(f"Ground-truth eligible: **{res.ground_truth_eligible}**")
    if res.disagreements:
        st.warning("Annotators disagree:")
        st.json(res.disagreements)
    for a in store.for_artifact(artifact_id):
        superseded = a["annotation_id"] not in {c["annotation_id"] for c in current}
        with st.expander(f"{a['annotation_id']} - {a['annotator']['annotator_id']} "
                         f"({a['provenance_type']}, {a['review_state']})" + (" [superseded]" if superseded else "")):
            st.json(a)
    st.subheader("Reasoning output")
    st.text(render_text(analyze_artifact(build_inputs(artifact_id, store=store, records=records))))
