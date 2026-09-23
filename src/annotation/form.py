"""Form helpers for the annotation UI: pure functions, tested without Streamlit.

The UI collects flat values; ``build_annotation`` turns them into a schema-shaped record,
starting from ``blank_annotation`` so every field not touched stays at its honest default.
Empty inputs never become values: an empty text box stays ``unknown`` / ``not_available``.
"""

from __future__ import annotations

from typing import Any

from PIL import Image, ImageDraw

from .model import blank_annotation

TEXT_DEFAULTS = {"fabric": "unknown", "surface": "unknown", "manufacturing_characteristics": "unknown",
                 "colour": "unknown", "decoration": "unknown", "condition": "unknown"}


def _text(value: Any, default: str) -> str:
    if value is None:
        return default
    s = str(value).strip()
    return s if s else default


def _year(value: Any) -> int | None:
    if value in (None, "", "None"):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def clean_evidence(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Rows from the evidence table -> dating_evidence items. Blank rows are dropped;
    evidence ids are assigned E1, E2, ... in order."""
    out = []
    for row in rows:
        if not _text(row.get("observation"), ""):
            continue
        item = {
            "evidence_id": f"E{len(out) + 1}",
            "evidence_type": row.get("evidence_type") or "palaeography",
            "observation": _text(row.get("observation"), "not_available"),
            "confidence": row.get("confidence") or "unknown",
            "source_reference": _text(row.get("source_reference"), "annotator_observation"),
            "supports_start_year": _year(row.get("supports_start_year")),
            "supports_end_year": _year(row.get("supports_end_year")),
        }
        if _text(row.get("supports"), ""):
            item["supports"] = row["supports"].strip()
        if item["evidence_type"] in ("stratigraphy", "absolute_dating"):
            item["association"] = row.get("association") or "not_established"
        out.append(item)
    return out


def clean_references(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for row in rows:
        rid, cit = _text(row.get("ref_id"), ""), _text(row.get("citation"), "")
        if not rid or not cit:
            continue
        ref = {"ref_id": rid, "citation": cit,
               "verification_status": row.get("verification_status") or "unverified"}
        if _text(row.get("locator"), ""):
            ref["locator"] = row["locator"].strip()
        out.append(ref)
    return out


def build_annotation(values: dict[str, Any]) -> dict[str, Any]:
    """Assemble an annotation from UI values. Validation happens in the store, not here."""
    a = blank_annotation(values["artifact_id"], values["image_ids"],
                         annotator_id=values["annotator_id"],
                         provenance_type=values.get("provenance_type", "project_annotation"),
                         qualification=values.get("qualification") or None,
                         supersedes=values.get("supersedes") or None)
    if values.get("review_state"):
        a["review_state"] = values["review_state"]
    o = a["object"]
    o["object_type"] = values.get("object_type", "unknown")
    o["pottery_type"] = values.get("pottery_type", "unknown")
    for k, d in TEXT_DEFAULTS.items():
        o[k] = _text(values.get(k), d)

    ins = a["inscription"]
    for k in ("inscription_present", "inscription_type", "script_type", "script_confidence",
              "reading_confidence", "transliteration_scheme"):
        if values.get(k):
            ins[k] = values[k]
    ins["regions"] = list(values.get("regions", []))
    ins["characters_visible"] = values.get("characters_visible")
    ins["reading"] = _text(values.get("reading"), "not_available")
    ins["transliteration"] = _text(values.get("transliteration"), "not_available")
    ins["reading_source"] = _text(values.get("reading_source"), "not_available")
    ins["alternative_readings"] = [r for r in values.get("alternative_readings", []) if r.get("reading")]
    if ins["inscription_present"] == "no":
        ins.update({"script_type": "none", "inscription_type": "not_applicable",
                    "reading": "not_applicable", "transliteration": "not_applicable",
                    "reading_source": "not_applicable", "reading_confidence": "not_applicable",
                    "script_confidence": values.get("script_confidence") or "unknown"})

    it = a["interpretation"]
    for k in ("interpretation_type", "translation_confidence"):
        if values.get(k):
            it[k] = values[k]
    it["translation"] = _text(values.get("translation"), "not_available")
    it["meaning"] = _text(values.get("meaning"), "not_available")
    it["translation_source"] = _text(values.get("translation_source"), "not_available")
    if it["interpretation_type"] == "personal_name":
        it["translation"] = "not_applicable"

    ev = clean_evidence(values.get("dating_evidence", []))
    d = a["dating"]
    d["dating_evidence"] = ev
    d["estimated_start_year"] = _year(values.get("estimated_start_year"))
    d["estimated_end_year"] = _year(values.get("estimated_end_year"))
    d["dating_basis"] = sorted({e["evidence_type"] for e in ev}) or ["not_available"]
    d["dating_confidence"] = values.get("dating_confidence") or "unknown"

    a["linguistic_features"] = [f for f in values.get("linguistic_features", []) if f.get("observation")]
    a["image_usability"] = list(values.get("image_usability", []))
    a["references"] = clean_references(values.get("references", []))
    for k in ("uncertainty_notes", "notes"):
        if _text(values.get(k), ""):
            a[k] = values[k].strip()
    return a


def draw_regions(image: Image.Image, regions: list[dict[str, Any]], image_id: str) -> Image.Image:
    """A COPY of the image with normalised regions outlined. The original is untouched."""
    out = image.convert("RGB").copy()
    draw = ImageDraw.Draw(out)
    w, h = out.size
    width = max(2, w // 300)
    for r in regions:
        if r["image_id"] != image_id:
            continue
        box = (r["x"] * w, r["y"] * h, (r["x"] + r["width"]) * w, (r["y"] + r["height"]) * h)
        draw.rectangle(box, outline=(255, 0, 0), width=width)
    return out


def crop_view(image: Image.Image, x0: float, x1: float, y0: float, y1: float) -> Image.Image:
    """Zoom: a copy of the normalised window [x0,x1] x [y0,y1]."""
    w, h = image.size
    x0, x1 = sorted((max(0.0, x0), min(1.0, x1)))
    y0, y1 = sorted((max(0.0, y0), min(1.0, y1)))
    return image.crop((round(x0 * w), round(y0 * h), max(round(x1 * w), round(x0 * w) + 1),
                       max(round(y1 * h), round(y0 * h) + 1)))


__all__ = ["build_annotation", "clean_evidence", "clean_references", "crop_view", "draw_regions"]
