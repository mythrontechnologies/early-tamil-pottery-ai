"""Inscription regions: where on a photograph the marks are.

Three sources of a region, never merged and always labelled:

* ``human_annotation``  marked by a project annotator or an expert in the annotation store
                        (the only regions that are *evidence* of where an inscription is);
* ``user_supplied``     typed in by whoever runs an analysis (a viewing aid, not evidence);
* ``ai_prediction``     proposed by a detector model (reported, never evidence).

No validated inscription detector exists in this project, so the default ``NoDetector``
proposes nothing and says why. A trained detector plugs in through ``RegionDetector``.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Protocol

from PIL import Image

REGION_SOURCES = ("human_annotation", "user_supplied", "ai_prediction")
NO_DETECTOR = ("No validated inscription-region detector exists in this project; no region was "
               "proposed automatically.")


class RegionError(ValueError):
    """A region is malformed or lies outside the image."""


@dataclass(frozen=True)
class Region:
    """A rectangle NORMALISED to the image (x, y, width, height in [0, 1])."""

    x: float
    y: float
    width: float
    height: float
    source: str
    label: str = "possible_inscription"
    annotator: str | None = None
    annotation_id: str | None = None
    provenance_type: str | None = None
    note: str = ""

    def __post_init__(self) -> None:
        if self.source not in REGION_SOURCES:
            raise RegionError(f"unknown region source {self.source!r}")
        vals = (self.x, self.y, self.width, self.height)
        if any(not isinstance(v, (int, float)) or v != v for v in vals):       # v != v: NaN
            raise RegionError(f"region coordinates must be numbers: {vals}")
        if self.x < 0 or self.y < 0 or self.width <= 0 or self.height <= 0:
            raise RegionError(f"region must have x, y >= 0 and positive size: {vals}")
        if self.x + self.width > 1 + 1e-9 or self.y + self.height > 1 + 1e-9:
            raise RegionError(f"region extends beyond the image (normalised coordinates exceed 1): {vals}")

    @property
    def is_evidence(self) -> bool:
        return self.source == "human_annotation"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self) | {"is_evidence": self.is_evidence}

    def pixel_box(self, width: int, height: int) -> tuple[int, int, int, int]:
        left, top = round(self.x * width), round(self.y * height)
        right = max(left + 1, min(width, round((self.x + self.width) * width)))
        bottom = max(top + 1, min(height, round((self.y + self.height) * height)))
        return left, top, right, bottom


def parse_region(text: str, source: str = "user_supplied") -> Region:
    """``"x,y,w,h"`` (normalised) -> Region. Raises RegionError on anything else."""
    parts = [p.strip() for p in str(text).split(",")]
    if len(parts) != 4:
        raise RegionError(f"a region is 'x,y,width,height' (normalised), got {text!r}")
    try:
        x, y, w, h = (float(p) for p in parts)
    except ValueError as exc:
        raise RegionError(f"region values must be numbers: {text!r}") from exc
    return Region(x, y, w, h, source=source)


def crop(image: Image.Image, region: Region) -> Image.Image:
    """A COPY of the region at full resolution. The image is not modified."""
    return image.crop(region.pixel_box(*image.size))


def regions_from_annotations(annotations: list[dict[str, Any]], image_id: str) -> list[Region]:
    """Human-marked regions on one photograph, from CURRENT human annotations only."""
    out: list[Region] = []
    for a in sorted(annotations, key=lambda a: a["annotation_id"]):
        if a.get("provenance_type") == "ai_prediction":
            continue
        for r in a["inscription"].get("regions", []):
            if r["image_id"] != image_id:
                continue
            out.append(Region(r["x"], r["y"], r["width"], r["height"], "human_annotation",
                              label=r.get("label", "possible_inscription"),
                              annotator=a["annotator"]["annotator_id"], annotation_id=a["annotation_id"],
                              provenance_type=a["provenance_type"], note=r.get("note", "")))
    return out


class RegionDetector(Protocol):
    name: str

    def detect(self, image: Image.Image) -> list[Region]: ...


class NoDetector:
    """The honest default: no model, no proposals."""

    name = "none"
    statement = NO_DETECTOR

    def detect(self, image: Image.Image) -> list[Region]:
        return []


__all__ = ["NO_DETECTOR", "REGION_SOURCES", "NoDetector", "Region", "RegionDetector", "RegionError",
           "crop", "parse_region", "regions_from_annotations"]
