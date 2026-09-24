"""Read-only data for the UI, cached briefly. Every value comes from the project's own
functions; nothing here computes a status of its own or writes anything."""

from __future__ import annotations

import base64
import io
import os
from collections import Counter
from pathlib import Path
from typing import Any

import streamlit as st
from PIL import Image, ImageOps

from src.annotation.model import ANNOTATIONS_PATH
from src.annotation.store import AnnotationStore
from src.dataset.convert import read_jsonl
from src.dataset.schema import RESEARCH_DATA_ROOT, RESEARCH_RECORDS_PATH


def store() -> AnnotationStore:
    return AnnotationStore(Path(os.environ.get("ETPAI_ANNOTATIONS_PATH", ANNOTATIONS_PATH)))


@st.cache_data(ttl=30, show_spinner=False)
def records() -> list[dict[str, Any]]:
    return read_jsonl(RESEARCH_RECORDS_PATH) if RESEARCH_RECORDS_PATH.exists() else []


@st.cache_data(ttl=30, show_spinner=False)
def overview() -> dict[str, Any]:
    """Honest headline numbers. Zeros are reported as zeros."""
    from src.dataset.readiness import evaluate
    from src.knowledge.verification import effective_statuses

    recs = records()
    current = store().current()
    by_tier = Counter(a["provenance_type"] for a in current)
    rep = evaluate()
    eff = effective_statuses()
    return {
        "artifacts": len({r["artifact_id"] for r in recs}),
        "images": len(recs),
        "labelled_images": sum(r.get("label_source") == "expert_annotation" for r in recs),
        "project_annotations": by_tier.get("project_annotation", 0),
        "expert_annotations": by_tier.get("expert_annotation", 0),
        "ai_predictions": by_tier.get("ai_prediction", 0),
        "references": len(eff),
        "verified_references": sum(1 for s in eff.values() if s.verified),
        "training_ready": rep.training_ready,
        "readiness_reason": rep.reason,
        "artifacts_by_class": dict(rep.artifacts_by_class or {}),
        "min_per_class": rep.min_artifacts_per_class_required,
        "gates": rep.gates,
    }


@st.cache_data(ttl=30, show_spinner=False)
def artifacts() -> list[dict[str, Any]]:
    from src.annotation.pilot import load_pilot, load_review_flags

    recs = records()
    current = store().current()
    flags = load_review_flags()
    try:
        pilot = set(load_pilot().artifacts)
    except ValueError:
        pilot = set()
    out: dict[str, dict[str, Any]] = {}
    for r in sorted(recs, key=lambda r: r["image_id"]):
        a = out.setdefault(r["artifact_id"], {"artifact_id": r["artifact_id"], "images": [], "site": r.get("site"),
                                              "pilot": r["artifact_id"] in pilot,
                                              "flags": [f.label for f in flags.get(r["artifact_id"], [])],
                                              "flag_kinds": [f.kind for f in flags.get(r["artifact_id"], [])]})
        a["images"].append({"image_id": r["image_id"], "path": r["image_path"], "sha256": r.get("image_sha256"),
                            "license": r.get("license"), "attribution": r.get("rights_notes"),
                            "source": r.get("source_reference"), "script_type": r.get("script_type"),
                            "label_source": r.get("label_source")})
    for a in out.values():
        mine = [x for x in current if x["artifact_id"] == a["artifact_id"]]
        a["annotations"] = dict(Counter(x["provenance_type"] for x in mine))
    return list(out.values())


@st.cache_data(ttl=600, show_spinner="Checking every workflow stage (decoding each photograph once)…")
def workflow() -> dict[str, Any]:
    """The FULL check, including decoding every image: a skipped check must never read as PASS."""
    from src.workflow import workflow_status

    return workflow_status(decode_images=True).to_dict()


@st.cache_data(ttl=60, show_spinner=False)
def knowledge() -> dict[str, Any]:
    from src.knowledge.base import default_kb, describe
    from src.knowledge.verification import claim_report, effective_statuses

    kb = default_kb()
    eff = effective_statuses()
    refs = [{"ref_id": rid, "citation": r.get("citation"), "kb_status": r.get("verification_status"),
             "effective_status": eff[rid].effective_status if rid in eff else r.get("verification_status"),
             "resolution": r.get("resolution"), "candidate_works": r.get("candidate_works", []),
             "notes": r.get("project_notes", ""), "verified_claims": list(eff[rid].verified_claims) if rid in eff else []}
            for rid, r in sorted(kb.references.items())]
    return {"references": refs, "claims": describe(), "claim_report": claim_report()}


def short_attribution(rights_notes: str | None) -> str:
    """'Attribution required: "X" by Y, CC-BY-SA-4.0 (url), via ...' -> '"X" by Y, CC-BY-SA-4.0'."""
    text = (rights_notes or "").removeprefix("Attribution required:").strip()
    return text.split(" (http")[0].strip() or "attribution not recorded"


@st.cache_data(max_entries=64, show_spinner=False)
def thumbnail_b64(image_path: str, size: int = 520) -> str | None:
    """A small JPEG data URI of a research photograph (the stored file is only read)."""
    p = RESEARCH_DATA_ROOT / image_path
    if not p.is_file():
        return None
    with Image.open(p) as im:
        im.draft("RGB", (size * 2, size * 2))
        im = ImageOps.exif_transpose(im).convert("RGB")
        im.thumbnail((size, size))
        buf = io.BytesIO()
        im.save(buf, format="JPEG", quality=82, optimize=True)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode("ascii")


__all__ = ["artifacts", "knowledge", "overview", "records", "short_attribution", "store", "thumbnail_b64", "workflow"]
