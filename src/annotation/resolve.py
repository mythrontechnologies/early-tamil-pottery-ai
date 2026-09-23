"""Label resolution and disagreement analysis across annotators.

Resolution never merges provenance tiers. For each artifact it reports:

* ``expert_label``      - every current expert annotation marked ``expert_reviewed`` agrees
                          on a script_type other than unknown. The ONLY status that can ever
                          become ground truth (``ground_truth_eligible``).
* ``disputed``          - experts disagree, or any current annotation is marked disputed.
* ``provisional``       - project / source-information annotations agree; no expert yet.
                          Explicitly NOT ground truth.
* ``project_disagreement`` - project annotators disagree; no expert yet.
* ``unannotated``       - no human annotation (AI predictions do not count).

AI predictions are listed separately and never contribute to a status.

Nothing here writes to ``records.jsonl``. Promotion of expert labels into the training
records is a separate, deliberate step (planned for Milestone 8).
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import asdict, dataclass, field
from typing import Any

COMPARED_FIELDS = ("inscription_present", "script_type", "reading")


def _norm(value: Any) -> Any:
    return " ".join(value.split()) if isinstance(value, str) else value


@dataclass
class AnnotatorView:
    annotation_id: str
    annotator_id: str
    provenance_type: str
    review_state: str
    values: dict[str, Any]


@dataclass
class Resolution:
    artifact_id: str
    status: str
    label: str | None
    ground_truth_eligible: bool
    annotators: list[AnnotatorView] = field(default_factory=list)
    ai_predictions: list[AnnotatorView] = field(default_factory=list)
    disagreements: dict[str, dict[str, Any]] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _view(a: dict[str, Any]) -> AnnotatorView:
    return AnnotatorView(a["annotation_id"], a["annotator"]["annotator_id"], a["provenance_type"],
                         a["review_state"], {f: _norm(a["inscription"][f]) for f in COMPARED_FIELDS})


def _disagreements(views: list[AnnotatorView]) -> dict[str, dict[str, Any]]:
    out = {}
    for f in COMPARED_FIELDS:
        values = {v.annotator_id: v.values[f] for v in views}
        if len(set(values.values())) > 1:
            out[f] = values
    return out


def resolve_artifact(artifact_id: str, current: Iterable[dict[str, Any]]) -> Resolution:
    """Resolve the CURRENT (non-superseded) annotations of one artifact."""
    anns = sorted((a for a in current if a["artifact_id"] == artifact_id),
                  key=lambda a: (a["annotator"]["annotator_id"], a["annotation_id"]))
    humans = [_view(a) for a in anns if a["provenance_type"] != "ai_prediction"]
    ai = [_view(a) for a in anns if a["provenance_type"] == "ai_prediction"]
    res = Resolution(artifact_id, "unannotated", None, False, humans, ai)
    if not humans:
        return res
    res.disagreements = _disagreements(humans)
    experts = [v for v in humans if v.provenance_type == "expert_annotation"
               and v.review_state == "expert_reviewed"]
    if any(v.review_state == "disputed" for v in humans):
        res.status = "disputed"
        return res
    if experts:
        scripts = {v.values["script_type"] for v in experts}
        if len(scripts) == 1 and "unknown" not in scripts:
            res.status, res.label, res.ground_truth_eligible = "expert_label", scripts.pop(), True
        else:
            res.status = "disputed"
        return res
    scripts = {v.values["script_type"] for v in humans}
    if len(scripts) == 1:
        res.status = "provisional"
        label = next(iter(scripts))
        res.label = None if label == "unknown" else label
    else:
        res.status = "project_disagreement"
    return res


def resolve_all(artifact_ids: Iterable[str], current: list[dict[str, Any]]) -> list[Resolution]:
    return [resolve_artifact(a, current) for a in sorted(set(artifact_ids))]


__all__ = ["COMPARED_FIELDS", "AnnotatorView", "Resolution", "resolve_all", "resolve_artifact"]
