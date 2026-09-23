"""Append-only annotation store (``data/metadata/annotations/annotations.jsonl``).

* Records are only ever appended. A revision is a new record with ``supersedes``.
* Nothing in ``records.jsonl`` or the acquisition provenance is touched.
* Every append validates the new record **together with** the existing store, so
  cross-record rules (N11 supersession, N12 id uniqueness) see the whole picture.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from src.dataset.convert import read_jsonl
from src.dataset.schema import RESEARCH_RECORDS_PATH

from .model import ANNOTATIONS_PATH
from .validate import AnnotationValidation, validate_annotations


class AnnotationRejected(ValueError):
    def __init__(self, validation: AnnotationValidation) -> None:
        self.validation = validation
        super().__init__("annotation rejected:\n  - " + "\n  - ".join(map(str, validation.problems)))


def artifact_images(records_path: Path | None = None) -> dict[str, set[str]]:
    """artifact_id -> image_ids, from the research records."""
    path = records_path or RESEARCH_RECORDS_PATH
    out: dict[str, set[str]] = {}
    if path.exists():
        for r in read_jsonl(path):
            out.setdefault(r["artifact_id"], set()).add(r["image_id"])
    return out


@dataclass
class AnnotationStore:
    path: Path = ANNOTATIONS_PATH
    records_path: Path = RESEARCH_RECORDS_PATH

    def all(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        return [json.loads(line) for line in self.path.read_text(encoding="utf-8").splitlines()
                if line.strip()]

    def for_artifact(self, artifact_id: str) -> list[dict[str, Any]]:
        return [a for a in self.all() if a.get("artifact_id") == artifact_id]

    def current(self, artifact_id: str | None = None) -> list[dict[str, Any]]:
        """Latest record of each revision chain (annotations nobody supersedes)."""
        anns = self.all() if artifact_id is None else self.for_artifact(artifact_id)
        superseded = {a["supersedes"] for a in anns if a.get("supersedes")}
        return [a for a in anns if a["annotation_id"] not in superseded]

    def validate(self, extra: list[dict[str, Any]] | None = None,
                 knowledge_ref_ids: set[str] | None = None,
                 verified_ref_ids: set[str] | None = None) -> AnnotationValidation:
        return validate_annotations(self.all() + list(extra or []),
                                    artifact_images=artifact_images(self.records_path),
                                    knowledge_ref_ids=knowledge_ref_ids,
                                    verified_ref_ids=verified_ref_ids)

    def append(self, annotation: dict[str, Any], *, knowledge_ref_ids: set[str] | None = None,
               verified_ref_ids: set[str] | None = None) -> dict[str, Any]:
        """Validate against the whole store, then append. Raises AnnotationRejected.

        Knowledge-base ids (N10) and registry-verified ids (N14) default to the live ones."""
        if knowledge_ref_ids is None:
            from src.knowledge.base import reference_ids

            knowledge_ref_ids = reference_ids()
        if verified_ref_ids is None:
            from src.knowledge.verification import verified_ref_ids as _verified

            verified_ref_ids = _verified()
        result = self.validate([annotation], knowledge_ref_ids, verified_ref_ids)
        mine = [p for p in result.problems
                if p.annotation_id in (annotation.get("annotation_id"), annotation.get("supersedes"))]
        if mine:
            raise AnnotationRejected(AnnotationValidation(mine, 1))
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8", newline="\n") as fh:
            fh.write(json.dumps(annotation, ensure_ascii=False, sort_keys=True) + "\n")
        return annotation


__all__ = ["AnnotationRejected", "AnnotationStore", "artifact_images"]
