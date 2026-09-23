"""Technical quality vs archaeological usability: two separate questions, never merged.

* **Technical quality** comes from the Milestone 3 preprocessing sidecars under
  ``data/processed/``: resolution, blur, exposure, contrast, compression. These are
  uncalibrated heuristics. They describe the photograph and never reject it.
* **Archaeological usability** comes only from annotators (``image_usability``): whether
  the sherd, the inscription, the characters and the morphology are visible. It stays
  ``unknown`` until someone looks.

A technically "blurry" photograph can still be archaeologically usable, and vice versa.
Thresholds are not changed to make images pass. Calibration is future work.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from src.dataset.schema import ROOT

PROCESSED_ROOT = ROOT / "data" / "processed"
USABILITY_FIELDS = ("sherd_visible", "inscription_visible", "characters_readable",
                    "morphology_visible", "usable_for_annotation")


@dataclass
class ImageQuality:
    image_id: str
    artifact_id: str
    technical: dict[str, Any] = field(default_factory=dict)
    technical_flags: list[str] = field(default_factory=list)
    usability: dict[str, dict[str, str]] = field(default_factory=dict)   # annotator -> field -> value

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _sidecars(root: Path) -> dict[str, dict[str, Any]]:
    """source sha256 -> quality block, from every preprocessing sidecar."""
    out: dict[str, dict[str, Any]] = {}
    for p in root.rglob("*.json"):
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        sha = (d.get("source") or {}).get("source_sha256")
        if sha and isinstance(d.get("quality"), dict):
            out[sha] = d["quality"]
    return out


def quality_report(records: list[dict[str, Any]], current_annotations: list[dict[str, Any]],
                   processed_root: Path | None = None) -> list[ImageQuality]:
    side = _sidecars(processed_root or PROCESSED_ROOT)
    rows: dict[str, ImageQuality] = {}
    for r in sorted(records, key=lambda r: r["image_id"]):
        q = side.get(r["image_sha256"], {})
        rows[r["image_id"]] = ImageQuality(
            r["image_id"], r["artifact_id"],
            technical={k: q.get(k) for k in ("width_px", "height_px", "sharpness_laplacian_var",
                                             "brightness_mean", "contrast_std", "file_size_bytes")
                       if k in q} or {"status": "not preprocessed"},
            technical_flags=list(q.get("flags", [])))
    for a in current_annotations:
        who = f"{a['annotator']['annotator_id']} ({a['provenance_type']})"
        for u in a.get("image_usability", []):
            if u["image_id"] in rows:
                rows[u["image_id"]].usability[who] = {f: u.get(f, "unknown") for f in USABILITY_FIELDS}
    return list(rows.values())


__all__ = ["PROCESSED_ROOT", "USABILITY_FIELDS", "ImageQuality", "quality_report"]
