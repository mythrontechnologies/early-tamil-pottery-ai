"""Expert annotation pilot (Milestone 8).

The pilot is a list of artifacts (``annotation_pilot`` in configs/project.yaml) that each
need one current annotation from every required provenance tier, normally a project
annotator and an expert, so that agreement can be measured and expert labels can be
considered for promotion.

This module only REPORTS progress. It never creates an annotation, and it asserts nothing
about what the sherds carry: "is there an inscription, and in which script?" is the question
the annotators answer.

Completeness checklist for one annotation (``checklist``). These items make an annotation
*useful to the pilot*; they do not make it right, and a reading is deliberately NOT required
(record one only if it is supported):

    presence_decided     inscription_present is yes / no / uncertain (not 'unknown')
    script_decided       script_type is not 'unknown'
    regions_marked       an inscription region is marked when inscription_present = yes
    usability_assessed   every examined photograph has usable_for_annotation assessed
    object_status_decided  original / reproduction / uncertain recorded (schema 1.1.0)
    review_state_set     an expert annotation is expert_reviewed or disputed

Review flags (``annotation_pilot.review_flags``): questions about an artifact that only a
human can settle, e.g. "REVIEW REQUIRED — possible reproduction / duplicate inscription".
A flag changes no artifact identity or record; it is displayed, and promotion rule P10
refuses a ``possible_reproduction`` artifact until the experts state it is original.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from src.dataset.schema import load_config

from .resolve import resolve_artifact


@dataclass(frozen=True)
class ReviewFlag:
    artifact: str
    kind: str
    label: str
    related_artifact: str | None = None
    observation: str = ""
    raised: str = ""
    confirmed: bool = False


def load_review_flags(config: dict[str, Any] | None = None) -> dict[str, list[ReviewFlag]]:
    """artifact_id -> its review flags (empty when none are configured)."""
    p = (config or load_config()).get("annotation_pilot") or {}
    out: dict[str, list[ReviewFlag]] = {}
    for f in p.get("review_flags") or []:
        flag = ReviewFlag(str(f["artifact"]), str(f["kind"]), str(f.get("label", f["kind"])),
                          f.get("related_artifact"), " ".join(str(f.get("observation", "")).split()),
                          str(f.get("raised", "")), bool(f.get("confirmed", False)))
        out.setdefault(flag.artifact, []).append(flag)
    return out


@dataclass(frozen=True)
class Pilot:
    id: str
    description: str
    artifacts: tuple[str, ...]
    required_tiers: tuple[str, ...]


def load_pilot(config: dict[str, Any] | None = None) -> Pilot:
    p = (config or load_config()).get("annotation_pilot") or {}
    if not p.get("artifacts"):
        raise ValueError("configs/project.yaml has no annotation_pilot.artifacts")
    return Pilot(str(p.get("id", "pilot")), " ".join(str(p.get("description", "")).split()),
                 tuple(p["artifacts"]),
                 tuple(p.get("required_tiers", ["project_annotation", "expert_annotation"])))


def checklist(a: dict[str, Any]) -> dict[str, bool]:
    ins = a["inscription"]
    usable = {u["image_id"] for u in a.get("image_usability", [])
              if u.get("usable_for_annotation", "unknown") != "unknown"}
    marks = [r for r in ins.get("regions", [])
             if r["label"] in ("inscription", "graffiti", "possible_inscription")]
    items = {
        "presence_decided": ins["inscription_present"] != "unknown",
        "script_decided": ins["script_type"] != "unknown",
        "regions_marked": ins["inscription_present"] != "yes" or bool(marks),
        "usability_assessed": set(a["image_ids"]) <= usable,
        "object_status_decided": a["object"].get("object_status", "unknown") != "unknown",
    }
    if a["provenance_type"] == "expert_annotation":
        items["review_state_set"] = a["review_state"] in ("expert_reviewed", "disputed")
    return items


@dataclass
class PilotArtifactStatus:
    artifact_id: str
    in_records: bool
    annotations: dict[str, list[str]] = field(default_factory=dict)      # tier -> annotation ids
    missing_tiers: list[str] = field(default_factory=list)
    incomplete: dict[str, list[str]] = field(default_factory=dict)       # annotation id -> unmet items
    resolution: str = "unannotated"
    ground_truth_eligible: bool = False
    disagreements: dict[str, Any] = field(default_factory=dict)
    review_flags: list[str] = field(default_factory=list)

    @property
    def complete(self) -> bool:
        return self.in_records and not self.missing_tiers and not self.incomplete


@dataclass
class PilotStatus:
    pilot: Pilot
    artifacts: list[PilotArtifactStatus]

    @property
    def complete(self) -> int:
        return sum(a.complete for a in self.artifacts)

    def to_dict(self) -> dict[str, Any]:
        return {"pilot": asdict(self.pilot),
                "artifacts": [asdict(a) | {"complete": a.complete} for a in self.artifacts],
                "complete": self.complete}


def pilot_status(current: list[dict[str, Any]], record_artifacts: set[str],
                 pilot: Pilot | None = None) -> PilotStatus:
    pilot = pilot or load_pilot()
    flags = load_review_flags()
    rows = []
    for art in pilot.artifacts:
        mine = [a for a in current if a["artifact_id"] == art and a["provenance_type"] != "ai_prediction"]
        s = PilotArtifactStatus(art, art in record_artifacts)
        s.review_flags = [f"{f.label} ({f.kind}; related: {f.related_artifact or '-'}; "
                          f"{'confirmed' if f.confirmed else 'unconfirmed'})" for f in flags.get(art, [])]
        for a in mine:
            s.annotations.setdefault(a["provenance_type"], []).append(a["annotation_id"])
            unmet = [k for k, ok in checklist(a).items() if not ok]
            if unmet:
                s.incomplete[a["annotation_id"]] = unmet
        s.missing_tiers = [t for t in pilot.required_tiers if t not in s.annotations]
        res = resolve_artifact(art, current)
        s.resolution, s.ground_truth_eligible, s.disagreements = (
            res.status, res.ground_truth_eligible, res.disagreements)
        rows.append(s)
    return PilotStatus(pilot, rows)


def render_pilot(ps: PilotStatus) -> str:
    L = [f"PILOT  {ps.pilot.id}", f"  {ps.pilot.description}",
         f"  required tiers: {', '.join(ps.pilot.required_tiers)}",
         f"  complete: {ps.complete} / {len(ps.artifacts)}", ""]
    for s in ps.artifacts:
        tiers = ", ".join(f"{t}={len(ids)}" for t, ids in sorted(s.annotations.items())) or "none"
        L.append(f"  {s.artifact_id:<28} annotations: {tiers:<48} status: {s.resolution}"
                 + ("" if s.in_records else "  [NOT IN RECORDS]"))
        for f in s.review_flags:
            L.append(f"      FLAG {f}")
        if s.missing_tiers:
            L.append(f"      missing: {', '.join(s.missing_tiers)}")
        for aid, unmet in s.incomplete.items():
            L.append(f"      {aid} incomplete: {', '.join(unmet)}")
        if s.disagreements:
            L.append(f"      disagreements: {s.disagreements}")
    return "\n".join(L)


__all__ = ["Pilot", "PilotArtifactStatus", "PilotStatus", "ReviewFlag", "checklist", "load_pilot",
           "load_review_flags", "pilot_status", "render_pilot"]
