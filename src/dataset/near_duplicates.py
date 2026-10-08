"""Near-duplicate photographs across artifacts (Milestone 11): leakage the SHA-256 cannot see.

Gate G6 and ``verify_partitions`` catch the SAME BYTES in two places. They cannot catch a
resized, re-encoded or lightly cropped copy of one photograph, or one inscription photographed
twice and filed under two artifact ids (a suspected reproduction is exactly that case: pilot
artifacts 107/109). If such a pair lands in train and test, the test score measures memory.

This module computes a 64-bit difference hash (dHash) of every research photograph and lists
pairs across DIFFERENT artifacts whose hashes differ in at most ``max_distance`` bits. It never
decides that two photographs show the same object: it reports the pair, and the split refuses
until a human either merges the two artifacts or records them as distinct in
``split.near_duplicate_exceptions`` (configs/project.yaml) with a reason.

The hash describes pixels, not archaeology; it is computed on a 9x8 greyscale thumbnail of the
EXIF-oriented image. Raw files are opened read-only. A thumbnail with almost no tonal range
(``MIN_TONAL_RANGE``) carries no comparable structure, so its hash bits are noise: such images are
reported as "too featureless to compare", never matched (or cleared) by accident.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from itertools import combinations
from pathlib import Path
from typing import Any

from PIL import Image, ImageOps

from .schema import load_config

DEFAULT_MAX_DISTANCE = 6
MIN_TONAL_RANGE = 12          # grey levels across the 9x8 thumbnail


def _thumbnail(path: Path | str, size: int = 8) -> list[int]:
    with Image.open(path) as im:
        im.draft("L", (size * 16, size * 16))
        g = ImageOps.exif_transpose(im).convert("L").resize((size + 1, size), Image.Resampling.LANCZOS)
        return list(g.tobytes())


def dhash(path: Path | str, size: int = 8) -> int:
    """64-bit difference hash: each bit says whether a pixel is brighter than its right neighbour."""
    px = _thumbnail(path, size)
    bits = 0
    for row in range(size):
        for col in range(size):
            bits = (bits << 1) | (px[row * (size + 1) + col] > px[row * (size + 1) + col + 1])
    return bits


def informative(path: Path | str) -> bool:
    """False when the image is too featureless for its hash to mean anything."""
    px = _thumbnail(path)
    return max(px) - min(px) >= MIN_TONAL_RANGE


def hamming(a: int, b: int) -> int:
    return (a ^ b).bit_count()


@dataclass(frozen=True)
class NearDuplicate:
    image_a: str
    artifact_a: str
    image_b: str
    artifact_b: str
    distance: int

    def __str__(self) -> str:
        return (f"{self.image_a} ({self.artifact_a}) ~ {self.image_b} ({self.artifact_b}): "
                f"dHash distance {self.distance}/64")


def exceptions(config: dict[str, Any] | None = None) -> set[frozenset[str]]:
    """Artifact pairs a human has recorded as distinct objects despite similar photographs."""
    rows = (config or load_config()).get("split", {}).get("near_duplicate_exceptions") or []
    return {frozenset((r["artifact_a"], r["artifact_b"])) for r in rows if r.get("reason")}


def find_near_duplicates(items: Iterable[tuple[str, str, Path]], *, max_distance: int = DEFAULT_MAX_DISTANCE,
                         allowed: set[frozenset[str]] | None = None) -> tuple[list[NearDuplicate], list[str]]:
    """``items`` = (image_id, artifact_id, path). Returns (pairs across artifacts, images not compared
    with the reason: unreadable, or too featureless for a hash to mean anything)."""
    hashed: list[tuple[str, str, int]] = []
    unreadable: list[str] = []
    for image_id, artifact_id, path in items:
        try:
            if not informative(path):
                unreadable.append(f"{image_id}: too featureless to compare (tonal range < {MIN_TONAL_RANGE})")
                continue
            hashed.append((image_id, artifact_id, dhash(path)))
        except (OSError, ValueError, Image.DecompressionBombError) as exc:
            unreadable.append(f"{image_id}: {exc}")
    allowed = allowed or set()
    pairs = []
    for (ia, aa, ha), (ib, ab, hb) in combinations(hashed, 2):
        if aa == ab or frozenset((aa, ab)) in allowed:
            continue
        d = hamming(ha, hb)
        if d <= max_distance:
            (i1, a1), (i2, a2) = sorted([(ia, aa), (ib, ab)])
            pairs.append(NearDuplicate(i1, a1, i2, a2, d))
    return sorted(pairs, key=lambda p: (p.distance, p.image_a, p.image_b)), unreadable


def dataset_near_duplicates(records: Iterable[Any], *, max_distance: int | None = None,
                            config: dict[str, Any] | None = None) -> tuple[list[NearDuplicate], list[str]]:
    """Near-duplicates among ``DatasetRecord``s (anything with image_id, artifact_id, image_path)."""
    cfg = config or load_config()
    md = max_distance if max_distance is not None else int(
        cfg.get("split", {}).get("near_duplicate_max_distance", DEFAULT_MAX_DISTANCE))
    items = [(r.image_id, r.artifact_id, Path(r.image_path)) for r in records if Path(r.image_path).is_file()]
    return find_near_duplicates(items, max_distance=md, allowed=exceptions(cfg))


__all__ = ["DEFAULT_MAX_DISTANCE", "MIN_TONAL_RANGE", "NearDuplicate", "dataset_near_duplicates", "dhash",
           "exceptions", "find_near_duplicates", "hamming", "informative"]
