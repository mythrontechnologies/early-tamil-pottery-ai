"""Build reasoning inputs for a real artifact from the project's data layers.

Layers, never merged, each value keeping its provenance:

    A. source information   records.jsonl (site as stated by source) + acquisition provenance
                            (source_label); and source_information annotations
    B. project annotation   annotations by project annotators
    C. expert annotation    annotations by experts
    D. AI inference         ai_prediction annotations -> reported separately, never evidence

The reasoning basis is ONE human annotation, chosen by strength of provenance:
expert_reviewed expert > other expert > source_information > project. Other annotators'
views are not averaged in; disagreement is reported via ``annotation_status``, and every
human annotator's own dating range is passed through side by side (Milestone 8).

Reference status is the EFFECTIVE status from the verification registry
(``src.knowledge.verification``). An annotation cannot upgrade a reference by declaring it
verified: a self-declared ``verified_against_source`` without a registry record is reported
as ``unverified``.
"""

from __future__ import annotations

from typing import Any

from src.annotation.model import PROVENANCE_RANK
from src.annotation.resolve import resolve_artifact
from src.annotation.store import AnnotationStore
from src.dataset.convert import read_jsonl
from src.dataset.schema import RESEARCH_RECORDS_PATH
from src.knowledge.base import default_kb
from src.knowledge.verification import VERIFIED, effective_statuses

from .types import (
    ArchaeologicalContext,
    Attributed,
    EvidenceItem,
    InscriptionInput,
    LinguisticFeature,
    ReasoningInputs,
    ReferenceInfo,
    VisualFeatures,
)


def _basis(current: list[dict[str, Any]]) -> dict[str, Any] | None:
    humans = [a for a in current if a["provenance_type"] != "ai_prediction"]
    if not humans:
        return None
    return min(humans, key=lambda a: (a["review_state"] != "expert_reviewed",
                                      PROVENANCE_RANK[a["provenance_type"]],
                                      a["created_utc"], a["annotation_id"]))


def dating_positions(current: list[dict[str, Any]]) -> tuple[dict[str, Any], ...]:
    """Each current human annotation's own dating range (or evidence), for side-by-side display."""
    out = []
    for a in sorted(current, key=lambda a: (a["annotator"]["annotator_id"], a["annotation_id"])):
        d = a["dating"]
        if a["provenance_type"] == "ai_prediction":
            continue
        if d["estimated_start_year"] is None and d["estimated_end_year"] is None and not d["dating_evidence"]:
            continue
        out.append({"annotation_id": a["annotation_id"], "annotator_id": a["annotator"]["annotator_id"],
                    "provenance": a["provenance_type"], "start_year": d["estimated_start_year"],
                    "end_year": d["estimated_end_year"],
                    "basis": [b for b in d["dating_basis"] if b not in ("not_available", "unknown")],
                    "confidence": d["dating_confidence"]})
    return tuple(out)


def _reference_infos(annotation: dict[str, Any] | None) -> dict[str, ReferenceInfo]:
    kb = default_kb()
    eff = effective_statuses(kb=kb)
    refs = {rid: ReferenceInfo(rid, e["citation"], eff[rid].effective_status,
                               tuple(v["claim"] for v in eff[rid].verified_claims))
            for rid, e in kb.references.items()}
    for r in (annotation or {}).get("references", []):
        if r["ref_id"] in refs:                  # the registry, not the annotator, decides
            continue
        status = r["verification_status"]
        refs[r["ref_id"]] = ReferenceInfo(r["ref_id"], r["citation"],
                                          "unverified" if status == VERIFIED else status)
    return refs


def build_inputs(artifact_id: str, *, store: AnnotationStore | None = None,
                 records: list[dict[str, Any]] | None = None,
                 provenance: dict[str, dict[str, Any]] | None = None) -> ReasoningInputs:
    store = store or AnnotationStore()
    if records is None:
        records = read_jsonl(RESEARCH_RECORDS_PATH) if RESEARCH_RECORDS_PATH.exists() else []
    if provenance is None:
        from src.acquisition.provenance import read_registry

        provenance = {p["image_id"]: p for p in read_registry()}
    recs = [r for r in records if r["artifact_id"] == artifact_id]
    if not recs:
        raise KeyError(f"artifact {artifact_id!r} is not in the research records")

    first = min(recs, key=lambda r: r["image_id"])
    site = Attributed(first.get("site", "not_available"), "source_information" if
                      first.get("site", "not_available") != "not_available" else "none",
                      source_reference=first.get("source_reference", "not_available"))
    labels = sorted({provenance[r["image_id"]]["source_label"] for r in recs if r["image_id"] in provenance})
    ctx_rel = Attributed(first.get("context_reliability", "unknown"), "source_information")

    current = store.current(artifact_id)
    res = resolve_artifact(artifact_id, current)
    a = _basis(current)
    ai = tuple({"annotation_id": x["annotation_id"], "annotator": x["annotator"]["annotator_id"],
                "script_type": x["inscription"]["script_type"],
                "reading": x["inscription"]["reading"]}
               for x in current if x["provenance_type"] == "ai_prediction")

    if a is None:
        return ReasoningInputs(artifact_id, VisualFeatures(source_label=" || ".join(labels) or "not_available"),
                               archaeological_context=ArchaeologicalContext(site, ctx_rel),
                               references={}, ai_predictions=ai, annotation_status=res.status)

    refs = _reference_infos(a)
    pt = a["provenance_type"]
    o, ins, it, d = a["object"], a["inscription"], a["interpretation"], a["dating"]

    def at(value: Any, conf: str = "unknown", src: str = "annotator_observation") -> Attributed:
        return Attributed(value, pt, conf, src, a["annotation_id"])

    cited = {ins["reading_source"], it["translation_source"]}
    cited |= {e["source_reference"] for e in d["dating_evidence"]}
    cited |= {f["source_reference"] for f in a.get("linguistic_features", [])}
    used_refs = {k: v for k, v in refs.items() if k in cited}

    return ReasoningInputs(
        artifact_id=artifact_id,
        visual_features=VisualFeatures(at(o["object_type"]), at(o["pottery_type"]),
                                       " || ".join(labels) or "not_available"),
        inscription=InscriptionInput(
            inscription_present=at(ins["inscription_present"]),
            script_type=at(ins["script_type"], ins["script_confidence"]),
            reading=at(ins["reading"], ins["reading_confidence"], ins["reading_source"]),
            transliteration=ins.get("transliteration", "not_available"),
            alternative_readings=tuple(ins.get("alternative_readings", [])),
            interpretation_type=at(it["interpretation_type"], it["translation_confidence"], it["translation_source"]),
            translation=at(it["translation"], it["translation_confidence"], it["translation_source"]),
            meaning=it["meaning"],
        ),
        linguistic_features=tuple(LinguisticFeature(f["feature_type"], f["observation"], pt,
                                                     f["confidence"], f["source_reference"],
                                                     f.get("significance", ""))
                                  for f in a.get("linguistic_features", [])),
        archaeological_context=ArchaeologicalContext(site, ctx_rel),
        dating_evidence=tuple(EvidenceItem(e["evidence_id"], e["evidence_type"], e["observation"], pt,
                                           e["confidence"], e["source_reference"],
                                           e.get("supports_start_year"), e.get("supports_end_year"),
                                           e.get("supports", ""), e.get("association", "not_applicable"))
                              for e in d["dating_evidence"]),
        references=used_refs,
        ai_predictions=ai,
        annotation_status=res.status,
        disagreements=res.disagreements,
        annotator_dating_positions=dating_positions(current),
    )


__all__ = ["build_inputs", "dating_positions"]
