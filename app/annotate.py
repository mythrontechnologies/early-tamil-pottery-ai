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

Pilot completion (2026-09-24): a provenance panel (ids, Commons page, licence, attribution,
technical quality flags), review flags such as "REVIEW REQUIRED — possible reproduction /
duplicate inscription", a count of existing annotations (collapsed, so independent work
stays independent), the form grouped as OBJECT / INSCRIPTION / MEANING / DATING with
'unknown' / 'uncertain' one click away, the object's original/reproduction status, and an
OPTIONAL read-only AI-draft layer (off by default, always shown under its warning; it is
never saved, and rule N15 refuses it under a human provenance tier).

Milestone 11: a "Queue" tab (every research artifact, its state and the next human step), glyph
(character) regions with their sign index and reading, reading completeness, expert ADJUDICATION
of disagreeing annotations (the resolved annotations stay; rule N18), a field-level disagreement
table, and a legend that keeps the five kinds of statement apart: source metadata, project
annotation, expert annotation, AI draft, promoted ground truth.

The annotation store path can be overridden with ETPAI_ANNOTATIONS_PATH (used by tests).
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import cast

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ui.boot import boot

boot("Annotation")

import streamlit as st
from PIL import Image, ImageOps
from ui.components import badge, e, page_header
from ui.inspect3d import render_inspection
from ui.viewer import render_viewer

from src.annotation.agreement import compute_agreement, render_agreement
from src.annotation.ai_draft import AI_DRAFT_BANNER, AI_DRAFT_WARNING, load_ai_draft
from src.annotation.form import build_annotation, crop_view
from src.annotation.model import ANNOTATIONS_PATH, load_annotation_schema
from src.annotation.pilot import Pilot, load_pilot, load_review_flags, pilot_status, render_pilot
from src.annotation.quality import quality_report
from src.annotation.resolve import resolve_artifact
from src.annotation.store import AnnotationRejected, AnnotationStore
from src.annotation.worksheet import annotation_queue, disagreement_report
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


store = AnnotationStore(Path(os.environ.get("ETPAI_ANNOTATIONS_PATH", ANNOTATIONS_PATH)))
records = read_jsonl(RESEARCH_RECORDS_PATH) if RESEARCH_RECORDS_PATH.exists() else []
by_artifact: dict[str, list[dict]] = {}
for r in sorted(records, key=lambda r: r["image_id"]):
    by_artifact.setdefault(r["artifact_id"], []).append(r)

page_header("Annotation", "Digital archaeology workstation",
            "Annotations are appended, never overwritten. Leave anything you cannot determine as 'unknown' or "
            "'uncertain'. Do not label from a guess, a file name, a caption or an AI suggestion. Your identity and "
            "role are set in the sidebar.")

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
    adjudicating = False
    if provenance_type == "expert_annotation":
        qualification = st.text_input("Qualification and affiliation (required for experts)")
        adjudicating = st.checkbox("I am ADJUDICATING disagreeing annotations", value=False,
                                   help="Read the other annotations of this artifact, then record your own "
                                        "decision. The annotations you resolve are kept and stay visible.")
    pilot: Pilot | None
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
    st.divider()
    show_ai = st.checkbox("Show AI draft (optional reference layer)", value=False, help=AI_DRAFT_WARNING)

recs = by_artifact[artifact_id]
image_ids = [r["image_id"] for r in recs]
st.session_state.setdefault("regions", {})
regions: list[dict] = st.session_state["regions"].setdefault(artifact_id, [])

tab_annotate, tab_review, tab_pilot, tab_queue = st.tabs(["Annotate", "Review", "Pilot & agreement", "Queue"])

review_flags = load_review_flags().get(artifact_id, [])

TIER = {"project_annotation": ("project", "Project annotation"),
        "source_information": ("transcribed", "Published source · unverified"),
        "expert_annotation": ("expert", "Expert review")}


def lab_section(n: int, title: str, hint: str) -> None:
    st.html(f'<div class="etp-lab-sec"><span class="num" aria-hidden="true">{n:02d}</span>'
            f'<h3>{e(title)}</h3><span class="hint">{e(hint)}</span></div>')


with tab_annotate:
    # -- title bar: who is recording what, stated in words ------------------------------
    tk, tl = TIER[provenance_type]
    st.html(f'<div class="etp-title-bar"><h2>Artifact {e(artifact_id)}</h2>{badge(tk, "recording as " + tl)}'
            f'{badge("neutral", f"{len(recs)} photograph(s)")}'
            + (badge("unresolved", "review flag") if review_flags else "")
            + (badge("ai", "AI draft shown — not evidence") if show_ai else "") + "</div>")
    for f in review_flags:
        state = "Confirmed." if f.confirmed else "NOT confirmed: record your own judgement under Object status."
        st.warning(f"**{f.label}** ({f.kind}; related artifact: {f.related_artifact or '-'}). "
                   f"{f.observation} Raised: {f.raised}. {state}")
    if show_ai:
        st.error(f"**{AI_DRAFT_BANNER}.** {AI_DRAFT_WARNING}")
        try:
            drafts = load_ai_draft().get(artifact_id, [])
        except ValueError as exc:
            drafts = []
            st.error(f"AI draft refused: {exc}")
        for d in drafts:
            st.json({"provenance": d["provenance_type"], "annotator": d["annotator"]["annotator_id"],
                     "object_type": d["object"]["object_type"],
                     "inscription_present": d["inscription"]["inscription_present"],
                     "script_type": d["inscription"]["script_type"], "regions": d["inscription"]["regions"],
                     "reading": d["inscription"]["reading"], "notes": d.get("notes", ""),
                     "uncertainty_notes": d.get("uncertainty_notes", "")}, expanded=False)
        if not drafts:
            st.caption("No AI draft for this artifact.")

    stage, desk = st.columns([1.25, 1], gap="large")
    # -- inspection stage: photograph, overlays, region marking -------------------------
    with stage:
        lab_section(0, "Inspection stage", "the photograph is the authoritative source")
        image_id = st.selectbox("Photograph", image_ids)
        rec = next(r for r in recs if r["image_id"] == image_id)
        loaded = load_image(RESEARCH_DATA_ROOT / rec["image_path"], compute_hash=False)
        if not loaded.ok:
            st.error("Image could not be loaded: " + "; ".join(str(i) for i in loaded.errors))
            st.stop()
        image = to_rgb(apply_exif_orientation(cast(Image.Image, loaded.image)))   # st.stop() above if absent
        display = image.copy()
        display.thumbnail((1600, 1600))
        pending = [{**r, "source": "user_supplied"} for r in regions if r["image_id"] == image_id]
        view = st.segmented_control("Stage view", ["Photograph · 2D", "2.5D inspection"], default="Photograph · 2D",
                                    key="lab_view", label_visibility="collapsed",
                                    help="2.5D maps the photograph onto an illustrative curved surface; "
                                         "the curvature is not measured. Marking always uses the flat photograph.")
        if view == "2.5D inspection":
            render_inspection(display, pending, alt=f"Photograph {image_id} of artifact {artifact_id}", height=440)
        else:
            render_viewer(display, pending, alt=f"Photograph {image_id} of artifact {artifact_id}", height=440,
                          meta=f"{image_id} · regions you have marked but not yet saved are shown dashed",
                          max_side=1600)
        with st.container(border=True):
            st.markdown("**Mark a region** (the current zoom window becomes the region)")
            z1, z2 = st.columns([1, 1])
            with z1:
                zx = st.slider("x range", 0.0, 1.0, (0.0, 1.0), 0.01, key="zx")
                zy = st.slider("y range", 0.0, 1.0, (0.0, 1.0), 0.01, key="zy")
                rlabel = st.selectbox("Region label", D["region"]["properties"]["label"]["enum"],
                                      help="'character' marks ONE sign inside an inscription.")
                sign_index, sign_reading = None, ""
                if rlabel == "character":
                    sign_index = st.number_input("Sign position in the reading (1 = first)", 1, 200, 1)
                    sign_reading = st.text_input("Sign as read ('?' if it cannot be read; never guess)")
                rnote = st.text_input("Region note (optional)")
            with z2:
                st.image(crop_view(image, zx[0], zx[1], zy[0], zy[1]), caption="zoom window (full resolution)")
            if st.button("Add region from zoom window"):
                region = {"image_id": image_id, "x": round(zx[0], 4), "y": round(zy[0], 4),
                          "width": round(max(zx[1] - zx[0], 0.0001), 4),
                          "height": round(max(zy[1] - zy[0], 0.0001), 4), "label": rlabel}
                if rnote.strip():
                    region["note"] = rnote.strip()
                if rlabel == "character":
                    region["sign_index"] = int(sign_index or 1)
                    if sign_reading.strip():
                        region["sign_reading"] = sign_reading.strip()
                regions.append(region)
            if regions:
                st.dataframe([{"region": f"R{i}", **r} for i, r in enumerate(regions, 1)], hide_index=True)
                if st.button("Clear regions"):
                    regions.clear()
        with st.expander(f"All {len(recs)} photograph(s) of this artifact", expanded=False):
            cols = st.columns(min(len(recs), 4))
            for i, r in enumerate(recs):
                try:
                    cols[i % len(cols)].image(thumbnail(str(RESEARCH_DATA_ROOT / r["image_path"])),
                                              caption=r["image_id"])
                except OSError as exc:
                    cols[i % len(cols)].warning(f"{r['image_id']}: {exc}")
        st.caption("Source label (what the uploader said): " + " | ".join(sorted({r["notes"].split(
            "Source label (verbatim): ")[-1].split(". Artifact grouping")[0] for r in recs}))[:500])

    # -- annotation desk: the unchanged form ---------------------------------------------
    with desk:
        with st.form("annotation"):
            st.caption("An uncertain answer is preferable to an unsupported positive identification. "
                       "'uncertain' = examined, cannot decide; 'unknown' = not assessed.")
            lab_section(1, "Object", "what the object is, and whether it is original")
            OS = enum("object", "object_status")
            object_status = st.radio("Original archaeological object or reproduction?", OS,
                                     index=OS.index("unknown"), horizontal=True)
            o1, o2 = st.columns(2)
            object_type = o1.selectbox("Object type", enum("object", "object_type"), index=enum("object", "object_type").index("unknown"))
            pottery_type = o2.selectbox("Pottery type (ware), only if known", enum("object", "pottery_type"), index=enum("object", "pottery_type").index("unknown"))
            object_notes = st.text_input("Object comments / basis for the original-reproduction judgement",
                                         placeholder="e.g. museum label, catalogue no., painted surface")
            with st.expander("More object detail (optional)"):
                text_fields = {k: st.text_input(k.replace("_", " ").capitalize(), placeholder="unknown")
                               for k in ("fabric", "surface", "manufacturing_characteristics", "colour",
                                         "decoration", "condition")}

            lab_section(2, "Inscription", "presence, script, reading")
            IP, ST = enum("inscription", "inscription_present"), enum("inscription", "script_type")
            inscription_present = st.radio("Inscription / graffiti present", IP, index=IP.index("unknown"), horizontal=True,
                                           help="'uncertain' = you examined it and cannot tell; 'unknown' = not examined")
            script_type = st.radio("Script type", ST, index=ST.index("unknown"), horizontal=True,
                                   help="The site name is not evidence of script.")
            i3, _ = st.columns(2)
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
            RC = enum("inscription", "reading_completeness")
            reading_completeness = st.radio(
                "Reading completeness", RC, index=RC.index("unknown"), horizontal=True,
                help="partial = some signs read, others lost or doubtful (mark them in the reading); illegible = "
                     "marks present but nothing can be read (give no reading). Unreadable signs are never invented.")
            st.caption("Alternative readings: one row each, with who proposed it (ref_id or 'this_annotator'). "
                       "For a published reading, cite its ref_id as the source.")
            alt = st.data_editor([{"reading": "", "source": "", "note": ""}], num_rows="dynamic", key="alt")

            lab_section(3, "Meaning", "only what a source establishes")
            st.caption("Leave the translation empty unless a source establishes it; the record then says "
                       "no translation is established. A personal name gets no literal translation.")
            t1, t2 = st.columns(2)
            interpretation_type = t1.selectbox("Interpretation type (project category)", enum("interpretation", "interpretation_type"),
                                               index=enum("interpretation", "interpretation_type").index("not_applicable"))
            translation_confidence = t2.selectbox("Translation confidence", CONF, index=CONF.index("not_applicable"))
            translation = st.text_input("Translation (leave empty if none is established)")
            meaning = st.text_input("Meaning / explanation", placeholder="e.g. Proper name; no literal translation established.")
            translation_source = st.text_input("Translation source (ref_id or 'this_annotator')", placeholder="not_available")

            st.markdown("**Linguistic features**")
            ling = st.data_editor([{"feature_type": "word_form", "observation": "", "confidence": "unknown",
                                    "source_reference": "annotator_observation", "significance": ""}],
                                  num_rows="dynamic", key="ling",
                                  column_config={"feature_type": st.column_config.SelectboxColumn(
                                      options=D["linguistic_feature"]["properties"]["feature_type"]["enum"]),
                                      "confidence": st.column_config.SelectboxColumn(options=CONF)})

            lab_section(4, "Dating", "evidence rows, never a site or caption date")
            st.caption("One row per piece of evidence: palaeographic, linguistic, archaeological context, "
                       "stratigraphy, absolute dating, typology. Years: negative = BCE, positive = CE, no year 0. "
                       "Leave bounds empty if the evidence does not bound the date. 'association' says whether "
                       "the evidence dates THIS object or only its context. A site or caption date is not an "
                       "object date. The dating basis is derived from these rows.")
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
            unresolved_conflict = st.text_input("Unresolved dating conflict (recorded, never averaged)")

            lab_section(5, "Evidence", "references and per-photograph usability")
            st.markdown("**References**")
            st.caption("A reference is 'verified_against_source' only when the verification registry says "
                       "so (python -m src.knowledge status); a self-declared status is rejected (rule N14). "
                       "Cite knowledge-base ids (R1, S01, S03, ...) where they apply.")
            refs = st.data_editor([{"ref_id": "", "citation": "", "locator": "", "verification_status": "unverified"}],
                                  num_rows="dynamic", key="refs",
                                  column_config={"verification_status": st.column_config.SelectboxColumn(
                                      options=D["reference"]["properties"]["verification_status"]["enum"])})

            st.markdown("**Archaeological usability (per photograph)**")
            usability = []
            for iid in image_ids:
                st.markdown(f"`{iid}`")
                cols = st.columns(3)
                u = {"image_id": iid}
                for col, fname in zip(cols * 2, ("sherd_visible", "inscription_visible", "characters_readable",
                                                 "morphology_visible", "usable_for_annotation")):
                    u[fname] = col.selectbox(fname.replace("_", " "), YNU, index=YNU.index("unknown"),
                                             key=f"{iid}-{fname}")
                usability.append(u)

            lab_section(6, "Review", "uncertainty, notes, review state")
            adjudication = None
            if adjudicating:
                others = [a for a in store.current(artifact_id)
                          if a["provenance_type"] != "ai_prediction" and a["annotator"]["annotator_id"] != annotator_id.strip()]
                st.warning("ADJUDICATION: you are resolving the annotations selected below. They are kept; your "
                           "record states your decision and why. AI predictions can never be selected.")
                picked = st.multiselect(
                    "Annotations you have read and are resolving (at least two)",
                    [a["annotation_id"] for a in others],
                    default=[a["annotation_id"] for a in others],
                    format_func=lambda i: next(f"{i} · {a['annotator']['annotator_id']} · {a['provenance_type']} · "
                                               f"script {a['inscription']['script_type']}" for a in others
                                               if a["annotation_id"] == i))
                AO = P["adjudication"]["properties"]["outcome"]["enum"]
                outcome = st.radio("Outcome", AO, horizontal=True,
                                   help="insufficient_evidence: the photographs cannot settle it; the script is then "
                                        "'uncertain' (or 'unknown'), never a guess.")
                FD = P["adjudication"]["properties"]["fields_decided"]["items"]["enum"]
                fields_decided = st.multiselect("Fields you decided", FD, default=["script_type"])
                basis = st.text_area("Basis: what you examined and why you prefer one view (required)")
                adjudication = {"resolves": picked, "outcome": outcome, "basis": basis,
                                "fields_decided": fields_decided}
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
                    object_status=object_status, object_notes=object_notes,
                    unresolved_conflict=unresolved_conflict,
                    inscription_present=inscription_present, script_type=script_type,
                    script_confidence=script_confidence, inscription_type=inscription_type,
                    regions=list(regions), characters_visible=int(characters_visible) or None,
                    reading=reading, transliteration=transliteration,
                    transliteration_scheme=transliteration_scheme, reading_confidence=reading_confidence,
                    reading_source=reading_source, alternative_readings=[r for r in alt if r.get("reading")],
                    reading_completeness=reading_completeness, adjudication=adjudication,
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

    # -- provenance and revision history ---------------------------------------------------
    lab_section(7, "Provenance and revision history", "objective facts; append-only records")
    quality = {q.image_id: q for q in quality_report(recs, [])}

    def _flags(iid: str) -> str:
        q = quality[iid]
        return ", ".join(q.technical_flags) or ("not preprocessed" if "status" in q.technical else "none")

    st.dataframe([{"image_id": r["image_id"], "source": r.get("source_reference", "not_available"),
                   "licence": r.get("license", "unknown"), "attribution": r.get("rights_notes", "not_available"),
                   "quality flags (technical, uncalibrated)": _flags(r["image_id"])} for r in recs],
                 hide_index=True)
    existing = store.current(artifact_id)
    history = store.for_artifact(artifact_id)
    with st.expander(f"Existing annotations: {len(existing)} current, {len(history)} record(s) in the revision "
                     "history (open only AFTER saving your own)"):
        st.caption("Pilot annotators work independently. The other annotator's answers are data "
                   "about disagreement; do not read them before you have saved. Records are appended, never "
                   "edited: a revision supersedes the earlier record, which stays in the store.")
        current_ids = {a["annotation_id"] for a in existing}
        st.dataframe([{"annotation_id": a["annotation_id"], "annotator": a["annotator"]["annotator_id"],
                       "provenance": a["provenance_type"], "review_state": a["review_state"],
                       "created (UTC)": a.get("created_utc", ""), "supersedes": a.get("supersedes") or "",
                       "state": "current" if a["annotation_id"] in current_ids else "superseded"}
                      for a in history], hide_index=True)

with tab_annotate, st.expander("Reference verification status (read-only)"):
        keys = set(key_references())
        st.dataframe([{"ref_id": rid, "key": rid in keys, "effective_status": s.effective_status,
                       "verified_claims": len(s.verified_claims), "citation": s.citation}
                      for rid, s in effective_statuses().items()])

with tab_queue:
    st.caption("Every research artifact, its annotation state and the next HUMAN step. Nothing here is a label. "
               "Worksheets for offline work: python -m src.annotation handoff --all; import with "
               "python -m src.annotation import-worksheet FILE --role project|expert (dry run first).")
    q = annotation_queue(records, store.current(), pilot.artifacts if pilot else (),
                         pilot.required_tiers if pilot else ("project_annotation", "expert_annotation"),
                         load_review_flags())
    st.dataframe([{"artifact": r.artifact_id, "pilot": r.in_pilot, "photos": len(r.image_ids), "status": r.status,
                   "annotations": ", ".join(f"{k}={v}" for k, v in sorted(r.tiers.items())) or "none",
                   "review flags": len(r.review_flags), "next step": r.next_step} for r in q], hide_index=True)

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
    promoted = any(r.get("label_source") == "expert_annotation" for r in recs)
    st.html('<div class="etp-title-bar">'
            + badge("neutral", "Source metadata: what the uploader / publisher said")
            + badge("project", "Project annotation: provisional")
            + badge("expert", "Expert annotation")
            + badge("ai", "AI draft: never evidence")
            + badge("expert" if promoted else "waiting",
                    "Promoted ground truth" if promoted else "Not promoted: no ground truth yet")
            + "</div>")
    st.metric("Status", res.status)
    st.write(f"Ground-truth eligible: **{res.ground_truth_eligible}**"
             + (f" · adjudication {res.adjudication_id}" if res.adjudication_id else ""))
    for n in res.notes:
        st.info(n)
    if res.disagreements:
        st.warning("Annotators disagree (kept, never averaged; an expert may adjudicate):")
        rep = disagreement_report([artifact_id], current)
        if rep:
            st.dataframe([{"field": k, "state": f["state"], **{who: str(v) for who, v in f["values"].items()}}
                          for k, f in rep[0]["fields"].items() if f["state"] in ("agree", "disagree")],
                         hide_index=True)
    TIER_TEXT = {"project_annotation": "PROJECT ANNOTATION (provisional)", "expert_annotation": "EXPERT ANNOTATION",
                 "source_information": "SOURCE INFORMATION (transcribed, unverified)",
                 "ai_prediction": "AI PREDICTION — NOT EVIDENCE"}
    for a in store.for_artifact(artifact_id):
        superseded = a["annotation_id"] not in {c["annotation_id"] for c in current}
        kind = "ADJUDICATION · " if a.get("adjudication") else ""
        with st.expander(f"{kind}{TIER_TEXT.get(a['provenance_type'], a['provenance_type'])} · {a['annotation_id']} - "
                         f"{a['annotator']['annotator_id']} ({a['review_state']})" + (" [superseded]" if superseded else "")):
            st.json(a)
    st.subheader("Reasoning output")
    st.text(render_text(analyze_artifact(build_inputs(artifact_id, store=store, records=records))))
