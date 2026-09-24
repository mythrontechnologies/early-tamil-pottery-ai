"""Annotation records: constants, the blank template, and helpers.

An annotation is a plain dict validated against
``data/metadata/schema/annotation.schema.json`` plus the cross-field rules in
``validate.py``. The template starts every field at the honest default: nothing known,
nothing asserted.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from functools import lru_cache
from typing import Any

from src.dataset.schema import ROOT

ANNOTATION_SCHEMA_PATH = ROOT / "data" / "metadata" / "schema" / "annotation.schema.json"
ANNOTATIONS_PATH = ROOT / "data" / "metadata" / "annotations" / "annotations.jsonl"
ANNOTATION_SCHEMA_VERSION = "1.1.0"
#: Schema 1.1.0: is the photographed object original or a reproduction (optional field).
OBJECT_STATUSES = ("original", "reproduction", "uncertain", "unknown")

SENTINELS = frozenset({"unknown", "not_available", "not_applicable"})
#: Values of source_reference that are not reference ids.
SELF_REFERENCES = frozenset({"annotator_observation", "this_annotator"})

PROVENANCE_ROLE = {
    "source_information": "project_annotator",
    "project_annotation": "project_annotator",
    "expert_annotation": "expert",
    "ai_prediction": "ai_model",
}

#: Ordering of provenance strength, used when choosing what to report. Never merged.
PROVENANCE_RANK = {
    "expert_annotation": 0,
    "source_information": 1,
    "project_annotation": 2,
    "ai_prediction": 3,
}

EVIDENCE_TYPES = ("palaeography", "linguistics", "pottery_typology", "archaeological_context",
                  "stratigraphy", "absolute_dating", "associated_material", "historical_reference",
                  "comparative_inscription")


@lru_cache(maxsize=1)
def load_annotation_schema() -> dict[str, Any]:
    return json.loads(ANNOTATION_SCHEMA_PATH.read_text(encoding="utf-8"))


def new_annotation_id() -> str:
    return "ann_" + uuid.uuid4().hex[:16]


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def is_real(value: Any) -> bool:
    """True when a value carries information (not None, empty, or a sentinel)."""
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip()) and value not in SENTINELS
    if isinstance(value, (list, tuple, dict)):
        return bool(value)
    return True


def blank_annotation(
    artifact_id: str,
    image_ids: list[str],
    *,
    annotator_id: str,
    provenance_type: str = "project_annotation",
    qualification: str | None = None,
    supersedes: str | None = None,
) -> dict[str, Any]:
    """A new annotation asserting nothing. Every field starts unknown/not_available."""
    if provenance_type not in PROVENANCE_ROLE:
        raise ValueError(f"unknown provenance_type {provenance_type!r}")
    annotator: dict[str, Any] = {"annotator_id": annotator_id, "role": PROVENANCE_ROLE[provenance_type]}
    if qualification:
        annotator["qualification"] = qualification
    return {
        "annotation_schema_version": ANNOTATION_SCHEMA_VERSION,
        "annotation_id": new_annotation_id(),
        "artifact_id": artifact_id,
        "image_ids": list(image_ids),
        "provenance_type": provenance_type,
        "annotator": annotator,
        "created_utc": utc_now(),
        "supersedes": supersedes,
        "review_state": "unreviewed",
        "object": {"object_type": "unknown", "pottery_type": "unknown", "fabric": "unknown",
                   "surface": "unknown", "manufacturing_characteristics": "unknown",
                   "colour": "unknown", "decoration": "unknown", "condition": "unknown",
                   "object_status": "unknown"},
        "inscription": {"inscription_present": "unknown", "inscription_type": "unknown",
                        "script_type": "unknown", "script_confidence": "unknown", "regions": [],
                        "characters_visible": None, "reading": "not_available",
                        "transliteration": "not_available", "transliteration_scheme": "not_available",
                        "alternative_readings": [], "reading_confidence": "not_applicable",
                        "reading_source": "not_available"},
        "interpretation": {"interpretation_type": "not_applicable", "translation": "not_available",
                           "meaning": "not_available", "translation_confidence": "not_applicable",
                           "translation_source": "not_available"},
        "linguistic_features": [],
        "dating": {"estimated_start_year": None, "estimated_end_year": None,
                   "dating_confidence": "unknown", "dating_basis": ["not_available"],
                   "dating_evidence": []},
        "image_usability": [],
        "references": [],
    }


def region_to_pixels(region: dict[str, Any], width: int, height: int) -> dict[str, int]:
    """Convert a normalised region to the pixel ``xywh`` of image_record.inscription_regions."""
    x = round(region["x"] * width)
    y = round(region["y"] * height)
    w = max(1, round(region["width"] * width))
    h = max(1, round(region["height"] * height))
    return {"x": x, "y": y, "w": min(w, width - x), "h": min(h, height - y)}


def pixels_to_region(x: int, y: int, w: int, h: int, width: int, height: int) -> dict[str, float]:
    return {"x": round(x / width, 6), "y": round(y / height, 6),
            "width": round(w / width, 6), "height": round(h / height, 6)}


__all__ = [
    "ANNOTATIONS_PATH", "ANNOTATION_SCHEMA_PATH", "ANNOTATION_SCHEMA_VERSION", "EVIDENCE_TYPES",
    "OBJECT_STATUSES",
    "PROVENANCE_RANK", "PROVENANCE_ROLE", "SELF_REFERENCES", "SENTINELS", "blank_annotation",
    "is_real", "load_annotation_schema", "new_annotation_id", "pixels_to_region",
    "region_to_pixels", "utc_now",
]
