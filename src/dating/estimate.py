"""Evidence-based age estimation.

Not ``image -> network -> "150 BCE"``. An age is a RANGE derived from explicit evidence
items, each with a type, an observation, numeric support bounds, a provenance and a
source. See docs/ARCHAEOLOGICAL_REASONING.md.

Algorithm (deterministic):

1. **Screen** every evidence item. Excluded, with the reason recorded:
   AI predictions; items without numeric bounds (kept as qualitative reasoning);
   stratigraphic / absolute dates whose association with the object is not secure
   (CHRONOLOGICAL_SCOPE Position D); stratigraphy without an excavated-stratified context;
   items citing an unknown reference.
2. **Combine** by evidence tier (1 stratigraphy, absolute_dating; 2 associated_material,
   archaeological_context; 3 palaeography, comparative_inscription, pottery_typology;
   4 linguistics, historical_reference), then by evidence_id. Each item narrows the
   running range by intersection. An item that contradicts the range built from stronger
   evidence is recorded as a **conflict** and does not narrow it.
3. **No usable evidence**: if the script is established as Tamil-Brahmi, report only the
   outer bound "no earlier than" the earliest competing position in configs/project.yaml
   (those positions describe when the script *began*, not when a given sherd was made),
   with confidence ``very_low``. Otherwise: **insufficient evidence**, no range at all.
4. **Confidence** is set by rules, never by a score: see ``_confidence``.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from src.reasoning.types import (
    CONFIDENCE_ORDER,
    Attributed,
    EvidenceItem,
    ReferenceInfo,
)

from .chronology import (
    check_range,
    describe_centuries,
    format_range,
    format_year,
    intersect,
    script_positions,
)

TIER = {"stratigraphy": 1, "absolute_dating": 1, "associated_material": 2,
        "archaeological_context": 2, "palaeography": 3, "comparative_inscription": 3,
        "pottery_typology": 3, "linguistics": 4, "historical_reference": 4}
SECURE_ASSOCIATION = ("direct", "same_context_secure")
ESTABLISHING_PROVENANCE = ("expert_annotation", "source_information")


@dataclass
class AgeEstimate:
    state: str                       # estimated | outer_bound_only | insufficient_evidence
    start_year: int | None = None
    end_year: int | None = None
    display: str = "Insufficient evidence"
    centuries: str = ""
    confidence: str = "unknown"
    used: list[str] = field(default_factory=list)           # evidence ids
    excluded: dict[str, str] = field(default_factory=dict)  # evidence id -> reason
    conflicts: list[str] = field(default_factory=list)
    reasoning: list[str] = field(default_factory=list)
    limitations: list[str] = field(default_factory=list)
    positions_cited: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _screen(e: EvidenceItem, context_reliability: str, refs: dict[str, ReferenceInfo]) -> str | None:
    if e.provenance == "ai_prediction":
        return "AI prediction: reported, never used as dating evidence"
    if e.supports_start_year is None and e.supports_end_year is None:
        return "no numeric bounds: qualitative observation only"
    check_range(e.supports_start_year, e.supports_end_year)
    if e.evidence_type in ("stratigraphy", "absolute_dating") and e.association not in SECURE_ASSOCIATION:
        return (f"association with this object is {e.association!r}; a dated context does not date "
                "an object not securely associated with it (CHRONOLOGICAL_SCOPE, Position D)")
    if e.evidence_type == "stratigraphy" and context_reliability != "excavated_stratified":
        return f"stratigraphic evidence but context_reliability is {context_reliability!r}"
    if e.source_reference not in ("annotator_observation", "this_annotator") and e.source_reference not in refs:
        return f"cites unknown reference {e.source_reference!r}"
    return None


def _confidence(used: list[EvidenceItem], conflicts: list[str], context_reliability: str,
                refs: dict[str, ReferenceInfo]) -> tuple[str, list[str]]:
    notes: list[str] = []
    if not used:
        return "unknown", notes
    types = {e.evidence_type for e in used}
    tiers = {TIER[e.evidence_type] for e in used}
    all_expert = all(e.provenance == "expert_annotation" for e in used)
    level = "low"
    if all_expert and len(types) >= 2 and min(tiers) <= 2 and not conflicts:
        level = "moderate"
        verified = all(e.source_reference in ("annotator_observation", "this_annotator")
                       or refs[e.source_reference].verification_status == "verified_against_source"
                       for e in used)
        if 1 in tiers and context_reliability == "excavated_stratified" and verified:
            level = "high"
    if not all_expert:
        notes.append("Part of the evidence is not expert-reviewed; confidence is capped at 'low'.")
        level = "low"
    unverified = sorted({e.source_reference for e in used if e.source_reference in refs
                         and refs[e.source_reference].verification_status != "verified_against_source"})
    if unverified:
        notes.append(f"Cited references not verified against the source ({', '.join(unverified)}); "
                     "confidence is capped at 'low'.")
        level = "low" if CONFIDENCE_ORDER.index(level) > CONFIDENCE_ORDER.index("low") else level
    if conflicts:
        notes.append("Evidence conflicts; confidence is capped at 'low'.")
        level = "low" if CONFIDENCE_ORDER.index(level) > CONFIDENCE_ORDER.index("low") else level
    best_item = max((e.confidence for e in used if e.confidence in CONFIDENCE_ORDER),
                    key=CONFIDENCE_ORDER.index, default="low")
    if CONFIDENCE_ORDER.index(best_item) < CONFIDENCE_ORDER.index(level):
        notes.append(f"No evidence item is rated above '{best_item}'.")
        level = best_item
    return level, notes


def estimate_age(
    evidence: list[EvidenceItem],
    *,
    script: Attributed | None = None,
    context_reliability: str = "unknown",
    references: dict[str, ReferenceInfo] | None = None,
    config: dict[str, Any] | None = None,
) -> AgeEstimate:
    refs = references or {}
    est = AgeEstimate(state="insufficient_evidence")
    usable: list[EvidenceItem] = []
    for e in sorted(evidence, key=lambda x: (TIER.get(x.evidence_type, 9), x.evidence_id)):
        reason = _screen(e, context_reliability, refs)
        if reason:
            est.excluded[e.evidence_id] = reason
            if reason.startswith("no numeric bounds"):
                est.reasoning.append(f"[{e.evidence_id}] {e.evidence_type}: {e.observation} "
                                     "(qualitative; does not bound the date)")
        else:
            usable.append(e)

    current: tuple[int | None, int | None] = (None, None)
    used: list[EvidenceItem] = []
    for e in usable:
        cand = intersect(current, (e.supports_start_year, e.supports_end_year))
        rng = format_range(e.supports_start_year, e.supports_end_year)
        if cand is None:
            est.conflicts.append(
                f"[{e.evidence_id}] {e.evidence_type} supports {rng}, which is incompatible with "
                f"{format_range(*current)} from stronger or earlier-listed evidence; not used to narrow")
            continue
        current = cand
        used.append(e)
        src = e.source_reference if e.source_reference not in ("this_annotator",) else "annotator_observation"
        est.reasoning.append(f"[{e.evidence_id}] {e.evidence_type} ({e.provenance}, {e.confidence} "
                             f"confidence, source: {src}): {e.observation} -> supports {rng}.")
    est.used = [e.evidence_id for e in used]

    if used:
        est.state = "estimated"
        est.start_year, est.end_year = current
        est.display = f"Estimated: {format_range(*current)}"
        if current[0] is not None and current[1] is not None:
            est.centuries = describe_centuries(*current)
        est.confidence, notes = _confidence(used, est.conflicts, context_reliability, refs)
        est.limitations += notes
        if current[0] is None or current[1] is None:
            est.limitations.append("The range is open-ended: the evidence bounds it on one side only.")
        return est

    positions = script_positions(config)
    if script is not None and script.value == "tamil_brahmi" and script.provenance in ESTABLISHING_PROVENANCE:
        dated = [p for p in positions if p.kind == "date_position" and p.lower_year is not None]
        earliest = min(p.lower_year for p in dated)            # type: ignore[type-var]
        est.state, est.start_year, est.end_year = "outer_bound_only", earliest, None
        est.display = f"Outer bound only: no earlier than {format_year(earliest)}"
        est.confidence = "very_low"
        est.positions_cited = [asdict(p) for p in positions]
        est.reasoning.append(
            f"The only dating information is the script identification (Tamil-Brahmi, "
            f"{script.provenance}). The competing positions on the EARLIEST Tamil-Brahmi range from "
            + "; ".join(f"{p.id}: {format_range(p.lower_year, p.upper_year)}" for p in dated)
            + ". Their earliest bound gives an outer limit only.")
        objections = [p for p in positions if p.kind != "date_position"]
        if objections:
            est.reasoning.append("Methodological objection recorded: " + "; ".join(
                f"{p.id} ({p.label})" for p in objections) + ".")
        est.limitations += [
            ("A script's date range is an outer bound, not the date of this object "
             "(docs/CHRONOLOGICAL_SCOPE.md §2)."),
            "The chronology positions are unverified and contested; none is chosen.",
        ]
        return est

    est.display = "Insufficient evidence"
    est.reasoning.append("No dating evidence with numeric bounds from a human source, and no "
                         "established script identification: no age range can be given.")
    return est


__all__ = ["SECURE_ASSOCIATION", "TIER", "AgeEstimate", "estimate_age"]
