"""Dataset fingerprints: tell, from a short string, whether the training data changed.

Two fingerprints, for two different questions:

* :func:`dataset_fingerprint` covers **every field of every record**. Any change at all,
  whether a new photograph, a relabelled sherd or a corrected note, gives a new
  fingerprint. A split manifest and an experiment report are both tied to this value,
  so a model can never be silently evaluated against a dataset it was not split from.
* :func:`image_set_fingerprint` covers only ``(image_id, artifact_id, image_sha256)``.
  It changes when the *pixels* or the grouping change, and not when metadata is edited.

Both are order-independent: records are sorted by ``image_id`` before hashing, so
reordering the JSONL file does not change either value.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable
from typing import Any

FINGERPRINT_VERSION = "1"


def _canonical(obj: Any) -> bytes:
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode(
        "utf-8"
    )


def _sort_key(rec: Any) -> str:
    if isinstance(rec, dict):
        return str(rec.get("image_id", ""))
    return ""


def dataset_fingerprint(records: Iterable[Any]) -> str:
    """SHA-256 over the canonical JSON of all records, sorted by ``image_id``."""
    ordered = sorted(records, key=lambda r: (_sort_key(r), _canonical(r)))
    h = hashlib.sha256()
    h.update(f"dataset-fingerprint-v{FINGERPRINT_VERSION}\n".encode())
    for rec in ordered:
        h.update(_canonical(rec))
        h.update(b"\n")
    return h.hexdigest()


def image_set_fingerprint(records: Iterable[Any]) -> str:
    """SHA-256 over ``(image_id, artifact_id, image_sha256)`` triples only."""
    triples = sorted(
        (
            str(r.get("image_id", "")),
            str(r.get("artifact_id", "")),
            str(r.get("image_sha256", "")),
        )
        for r in records
        if isinstance(r, dict)
    )
    h = hashlib.sha256()
    h.update(f"image-set-fingerprint-v{FINGERPRINT_VERSION}\n".encode())
    for t in triples:
        h.update(_canonical(list(t)))
        h.update(b"\n")
    return h.hexdigest()


__all__ = ["FINGERPRINT_VERSION", "dataset_fingerprint", "image_set_fingerprint"]
