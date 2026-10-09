"""Deterministic archaeological reasoning.

    result = analyze_artifact(inputs)     # ReasoningInputs -> AnalysisResult

Each component is a replaceable module with a structured interface:

    script assessment      (here)                    -> who says which script, how confidently
    interpretation         src.translation.interpret -> translation / meaning, or "none established"
    age estimation         src.dating.estimate       -> evidence-based range, or "insufficient evidence"
    period label           (here, from project.yaml) -> where a range falls, never a date in itself

A future ML component (e.g. a script classifier) plugs in by supplying an ``Attributed``
value with ``provenance='ai_prediction'``. By construction such values are reported
separately and never counted as evidence.

Same inputs -> same output: no randomness, no clock, no network, sorted collections, and
an ``inputs_digest`` over the canonical inputs.

Milestone 8 adds, without changing how anything is estimated:

* ``status_statements``: the fixed phrases "Insufficient evidence", "Disputed / requires
  expert resolution" and "Alternative reading(s) recorded" wherever they apply;
* ``dating_summary``: estimated period, basis, confidence and important uncertainty, with the
  evidence sorted into seven categories (object/context, palaeographic, linguistic,
  archaeological context, absolute dating, publication attribution, uncertainty);
* annotators' own dating ranges side by side. Differing ranges are a conflict: they are all
  shown, none is chosen, nothing is averaged, and confidence is capped at ``low``.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from typing import Any

from src.dating.chronology import format_range, periods
from src.dating.estimate import AgeEstimate, estimate_age
from src.translation.interpret import NO_TRANSLATION, InterpretationResult, interpret

from .types import Attributed, ReasoningInputs, min_confidence

DISCLAIMER = ("IMPORTANT: This is an AI-assisted research estimate built from recorded evidence. It is "
              "not a definitive archaeological identification, reading or date, and it is not a "
              "substitute for expert epigraphic or archaeological assessment.")

PROVENANCE_LABEL = {
    "expert_annotation": "expert annotation",
    "source_information": "published / source statement",
    "project_annotation": "project annotation (not expert-reviewed)",
    "ai_prediction": "AI prediction (not evidence)",
    "none": "no source",
}

INSUFFICIENT = "Insufficient evidence"
DISPUTED = "Disputed / requires expert resolution"
ALTERNATIVES = "Alternative reading(s) recorded"
PARTIAL = "Partial transcription: some signs lost or doubtful"
FRAGMENTARY = "Fragmentary: only isolated signs read"
ILLEGIBLE = "Inscription illegible: no transcription"

#: Dating-evidence categories of the Milestone 8 brief. The seventh, "uncertainty", is filled
#: from conflicts, exclusions and unverified references, not from an evidence type.
EVIDENCE_CATEGORY = {
    "pottery_typology": "object_context", "associated_material": "object_context",
    "palaeography": "palaeographic", "comparative_inscription": "palaeographic",
    "linguistics": "linguistic",
    "archaeological_context": "archaeological_context", "stratigraphy": "archaeological_context",
    "absolute_dating": "absolute_dating",
    "historical_reference": "publication_attribution",
}
CATEGORIES = ("object_context", "palaeographic", "linguistic", "archaeological_context",
              "absolute_dating", "publication_attribution", "uncertainty")
SELF = ("annotator_observation", "this_annotator")


@dataclass
class AnalysisResult:
    artifact_id: str
    identification: dict[str, Any]
    script: dict[str, Any]
    reading: dict[str, Any]
    interpretation: dict[str, Any]
    period_estimate: str
    age: dict[str, Any]
    confidence: str
    reasoning: list[str] = field(default_factory=list)
    evidence: list[dict[str, Any]] = field(default_factory=list)
    ai_predictions: list[dict[str, Any]] = field(default_factory=list)
    limitations: list[str] = field(default_factory=list)
    disclaimer: str = DISCLAIMER
    inputs_digest: str = ""
    status_statements: list[str] = field(default_factory=list)
    dating_summary: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _attr(a: Attributed) -> dict[str, Any]:
    return {"value": a.value, "provenance": a.provenance,
            "provenance_label": PROVENANCE_LABEL.get(a.provenance, a.provenance),
            "confidence": a.confidence, "source": a.source_reference}


def _digest(inputs: ReasoningInputs) -> str:
    blob = json.dumps(asdict(inputs), sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def _period_label(age: AgeEstimate, config: dict[str, Any] | None) -> str:
    if age.state == "insufficient_evidence":
        return "Undetermined: insufficient evidence"
    lo, hi = age.start_year, age.end_year
    if lo is None or hi is None:
        return "Undetermined: the range is open-ended"
    labels = []
    for p in periods(config):
        tag = f"{p.label} (project's provisional periodisation, {p.verification_status})"
        if p.lower_year <= lo and hi <= p.upper_year:
            labels.append(f"Within {tag}")
        elif hi >= p.lower_year and lo <= p.upper_year:
            labels.append(f"Overlaps {tag}")
    return "; ".join(labels) or "Outside the project's named periods"


def _positions_conflict(positions: tuple[dict[str, Any], ...]) -> bool:
    ranges = {(p.get("start_year"), p.get("end_year")) for p in positions
              if p.get("start_year") is not None or p.get("end_year") is not None}
    return len(ranges) > 1


def _position_text(p: dict[str, Any]) -> str:
    stated = p.get("start_year") is not None or p.get("end_year") is not None
    rng = format_range(p["start_year"], p["end_year"]) if stated else "no range stated"
    return (f"{p['annotator_id']} ({PROVENANCE_LABEL.get(p['provenance'], p['provenance'])}): {rng}; "
            f"basis {', '.join(p.get('basis') or ['none stated'])}; confidence {p.get('confidence')}")


def _dating_summary(inputs: ReasoningInputs, age: AgeEstimate, confidence: str,
                    limitations: list[str]) -> dict[str, Any]:
    """Estimated period / basis / confidence / important uncertainty, evidence by category."""
    by_cat: dict[str, list[str]] = {c: [] for c in CATEGORIES}
    basis: list[str] = []
    for e in sorted(inputs.dating_evidence, key=lambda x: x.evidence_id):
        bounded = e.supports_start_year is not None or e.supports_end_year is not None
        rng = format_range(e.supports_start_year, e.supports_end_year) if bounded else "no bounds"
        used = e.evidence_id in age.used
        state = "used" if used else f"not used: {age.excluded.get(e.evidence_id, 'conflicts with stronger evidence')}"
        line = f"[{e.evidence_id}] {e.observation} -> {rng} ({e.provenance}, {e.confidence}; {state})"
        by_cat[EVIDENCE_CATEGORY.get(e.evidence_type, "uncertainty")].append(line)
        if used:
            basis.append(f"[{e.evidence_id}] {e.evidence_type}: {e.observation}")
        if e.source_reference not in SELF and e.evidence_type != "historical_reference":
            ref = inputs.references.get(e.source_reference)
            by_cat["publication_attribution"].append(
                f"[{e.evidence_id}] attributed to {e.source_reference} "
                f"({ref.verification_status if ref else 'unknown reference'})")
    uncertainty = list(age.conflicts)
    uncertainty += [x for x in limitations if "not verified" in x or "disagree" in x
                    or "open-ended" in x or "outer bound" in x or "not used" in x]
    if _positions_conflict(inputs.annotator_dating_positions):
        uncertainty.append("Annotators give different chronological positions; none is chosen and "
                           "they are not averaged.")
    if age.state == "estimated":
        period = f"approximately {format_range(age.start_year, age.end_year)}"
    elif age.state == "outer_bound_only":
        period = f"{age.display} (an outer bound, not a date for this object)"
    else:
        period = INSUFFICIENT
        uncertainty.append("No usable dating evidence has been recorded for this object.")
    by_cat["uncertainty"] = list(dict.fromkeys(uncertainty))
    return {"estimated_period": period, "centuries": age.centuries, "basis": basis or ["none"],
            "confidence": confidence, "important_uncertainty": by_cat["uncertainty"] or ["None recorded."],
            "evidence_by_category": by_cat,
            "annotator_positions": list(inputs.annotator_dating_positions)}


def analyze_artifact(
    inputs: ReasoningInputs | None = None,
    *,
    artifact_id: str = "unspecified",
    visual_features: Any = None,
    inscription: Any = None,
    linguistic_features: Any = (),
    archaeological_context: Any = None,
    dating_evidence: Any = (),
    references: Any = None,
    config: dict[str, Any] | None = None,
) -> AnalysisResult:
    """Analyse one artifact from structured evidence.

    Pass a ``ReasoningInputs``, or the components as keywords:
    ``analyze_artifact(visual_features=..., inscription=..., linguistic_features=...,
    archaeological_context=..., dating_evidence=..., references=...)``.
    """
    if inputs is None:
        from .types import ArchaeologicalContext, InscriptionInput, VisualFeatures

        inputs = ReasoningInputs(
            artifact_id=artifact_id,
            visual_features=visual_features or VisualFeatures(),
            inscription=inscription or InscriptionInput(),
            linguistic_features=tuple(linguistic_features),
            archaeological_context=archaeological_context or ArchaeologicalContext(),
            dating_evidence=tuple(dating_evidence),
            references=dict(references or {}),
        )
    ins, ctx = inputs.inscription, inputs.archaeological_context
    limitations: list[str] = []
    reasoning: list[str] = []

    # -- identification: object, as recorded -------------------------------------------
    vf = inputs.visual_features
    identification = {"object_type": _attr(vf.object_type), "pottery_type": _attr(vf.pottery_type),
                      "site": _attr(ctx.site), "context_reliability": _attr(ctx.context_reliability),
                      "source_label": vf.source_label}

    # -- script ----------------------------------------------------------------------------
    s = ins.script_type
    script = _attr(s)
    if not s.known:
        script["statement"] = "Script not determined."
        reasoning.append("Script: not determined by any human annotator or source.")
    else:
        script["statement"] = f"{s.value} ({PROVENANCE_LABEL.get(s.provenance, s.provenance)}, {s.confidence} confidence)"
        reasoning.append(f"Script: {script['statement']}.")
        if s.provenance == "project_annotation":
            limitations.append("The script identification is a project annotation, not expert-reviewed.")

    # -- reading ---------------------------------------------------------------------------
    reading = _attr(ins.reading) | {"transliteration": ins.transliteration,
                                    "alternative_readings": list(ins.alternative_readings),
                                    "completeness": ins.reading_completeness,
                                    "inscription_present": _attr(ins.inscription_present),
                                    "annotation_id": ins.reading.annotation_id}
    statements: list[str] = []
    if ins.reading_completeness == "illegible" and not ins.reading.known:
        reasoning.append("Reading: marks were examined and are illegible; no sign is supplied by inference.")
        statements.append(ILLEGIBLE)
    if ins.reading.known:
        reasoning.append(f"Reading: '{ins.reading.value}' ({PROVENANCE_LABEL.get(ins.reading.provenance)}, "
                         f"{ins.reading.confidence} confidence, source: {ins.reading.source_reference}).")
        if ins.reading_completeness in ("partial", "fragmentary"):
            reasoning.append(f"The reading is {ins.reading_completeness}: lost or doubtful signs are not supplied, "
                             "and any meaning is limited to what is read.")
            statements.append(PARTIAL if ins.reading_completeness == "partial" else FRAGMENTARY)
        if ins.alternative_readings:
            reasoning.append("Alternative readings exist: " + "; ".join(
                f"'{r.get('reading')}' ({r.get('source')})" for r in ins.alternative_readings) + ".")
            statements.append(ALTERNATIVES)
    else:
        reasoning.append("Reading: none established.")

    # -- interpretation -------------------------------------------------------------------
    interp: InterpretationResult = interpret(ins)
    reasoning.append(f"Meaning: {interp.meaning}")

    # -- linguistic features (reported; they date nothing unless an evidence item says so)
    for f in sorted(inputs.linguistic_features, key=lambda x: (x.feature_type, x.observation)):
        if f.provenance == "ai_prediction":
            continue
        reasoning.append(f"Linguistic ({f.feature_type}, {PROVENANCE_LABEL.get(f.provenance)}, "
                         f"{f.confidence}): {f.observation} [source: {f.source_reference}]")

    # -- age ----------------------------------------------------------------------------
    age = estimate_age(list(inputs.dating_evidence), script=s,
                       context_reliability=str(ctx.context_reliability.value),
                       references=inputs.references, config=config)
    reasoning += [f"Dating: {r}" for r in age.reasoning]
    reasoning += [f"Dating conflict: {c}" for c in age.conflicts]
    limitations += age.limitations
    for eid, why in sorted(age.excluded.items()):
        if not why.startswith("no numeric bounds"):
            limitations.append(f"Evidence {eid} not used: {why}.")
    if ctx.context_reliability.value in ("unknown", "museum_unprovenanced", "unprovenanced", "not_available"):
        limitations.append("No secure archaeological context is recorded for this object.")

    # -- annotators' own chronological positions: side by side, never averaged -------------
    positions = inputs.annotator_dating_positions
    positions_conflict = _positions_conflict(positions)
    if positions_conflict:
        reasoning.append("Dating conflict between annotators (not averaged): "
                         + " | ".join(_position_text(p) for p in positions) + ".")
        limitations.append("Annotators disagree on the date; each position is reported and none is chosen.")

    # -- annotation state ----------------------------------------------------------------
    confidence = age.confidence
    if positions_conflict:
        confidence = min_confidence(confidence, "low")
    if inputs.annotation_status in ("disputed", "project_disagreement"):
        limitations.append(f"Annotators disagree ({inputs.annotation_status}): "
                           + json.dumps(inputs.disagreements, ensure_ascii=False, sort_keys=True))
        confidence = min_confidence(confidence, "low")
    if inputs.annotation_status == "adjudicated":
        limitations.append("The label comes from an expert adjudication of disagreeing annotations; "
                           "the disagreement is preserved.")
    elif inputs.annotation_status != "expert_label":
        limitations.append("No expert-reviewed label exists for this artifact.")

    unverified = sorted(r.ref_id for r in inputs.references.values()
                        if r.verification_status != "verified_against_source")
    if unverified:
        limitations.append("References not verified against the source: " + ", ".join(unverified) + ".")
    for r in sorted(inputs.references.values(), key=lambda r: r.ref_id):
        if r.verification_status == "verified_against_source":
            limitations.append(f"{r.ref_id} is verified only for: "
                               + "; ".join(r.verified_claims or ("(no claim listed)",))
                               + ". Other claims citing it remain unverified.")

    if positions_conflict:
        statements.append("Conflicting chronological positions / requires expert resolution")
    if not s.known and not ins.reading.known and age.state == "insufficient_evidence":
        statements.insert(0, INSUFFICIENT)
    elif age.state == "insufficient_evidence":
        statements.append(f"Dating: {INSUFFICIENT}")
    if inputs.annotation_status == "disputed":           # a dispute is always stated first
        statements.insert(0, DISPUTED)
    elif inputs.annotation_status == "project_disagreement":
        statements.insert(0, "Project annotators disagree / requires expert resolution")

    evidence = [asdict(e) | {"used": e.evidence_id in age.used,
                             "excluded_reason": age.excluded.get(e.evidence_id)}
                for e in sorted(inputs.dating_evidence, key=lambda x: x.evidence_id)]

    return AnalysisResult(
        artifact_id=inputs.artifact_id,
        identification=identification,
        script=script,
        reading=reading,
        interpretation=interp.to_dict(),
        period_estimate=_period_label(age, config),
        age=age.to_dict(),
        confidence=confidence,
        reasoning=reasoning,
        evidence=evidence,
        ai_predictions=sorted(inputs.ai_predictions, key=lambda p: json.dumps(p, sort_keys=True)),
        limitations=list(dict.fromkeys(limitations)),
        inputs_digest=_digest(inputs),
        status_statements=list(dict.fromkeys(statements)),
        dating_summary=_dating_summary(inputs, age, confidence, limitations),
    )


def render_text(r: AnalysisResult) -> str:
    """The report layout from the Milestone 7 brief. Every line comes from the result."""
    age = r.age
    est = age["display"] + (f" ({age['centuries']})" if age.get("centuries") else "")
    L = [f"ARTIFACT  {r.artifact_id}", ""]
    if r.status_statements:
        L += ["STATUS"] + [f"  {x}" for x in r.status_statements] + [""]
    L += ["LIKELY PERIOD", f"  {r.period_estimate}", "",
          "ESTIMATED AGE", f"  {est}", ""]
    ds = r.dating_summary
    if ds:
        L += ["DATING",
              f"  Estimated period: {ds['estimated_period']}",
              "  Basis: " + "; ".join(ds["basis"]),
              f"  Confidence: {ds['confidence']}",
              "  Important uncertainty: " + "; ".join(ds["important_uncertainty"])]
        L += [f"  Position: {_position_text(p)}" for p in ds.get("annotator_positions", [])]
        L.append("")
    rd, it = r.reading, r.interpretation
    L += ["SCRIPT", f"  {r.script.get('statement')}", "",
          "READING (transcription)",
          f"  {rd['value'] if rd['value'] not in ('not_available', 'unknown') else 'None established'}"
          + (f"  [{rd['completeness']}]" if rd.get("completeness") not in (None, "unknown", "not_applicable") else "")]
    if rd.get("transliteration") not in (None, "not_available", "not_applicable", "unknown"):
        L.append(f"  Transliteration: {rd['transliteration']}")
    L += [f"  Alternative reading: {x.get('reading')} ({x.get('source')})"
          for x in rd.get("alternative_readings", [])]
    translation = {"translated": it["translation"], "personal_name": "Not applicable (proper name)",
                   "not_translatable": "Not applicable"}.get(it["state"], NO_TRANSLATION)
    L += ["", "TRANSLATION", f"  {translation}", "",
          "INTERPRETATION (what the inscription appears to represent)", f"  {it['meaning']}", "",
          "WHY? (every line traces to a recorded input)"]
    L += [f"  • {line}" for line in r.reasoning]
    L += ["", "CONFIDENCE", f"  {r.confidence}"]
    if r.ai_predictions:
        L += ["", "AI PREDICTIONS (reported only; not evidence)"]
        L += [f"  • {json.dumps(p, ensure_ascii=False, sort_keys=True)}" for p in r.ai_predictions]
    L += ["", "LIMITATIONS"] + [f"  • {x}" for x in r.limitations]
    L += ["", r.disclaimer]
    return "\n".join(L)


__all__ = ["ALTERNATIVES", "CATEGORIES", "DISCLAIMER", "DISPUTED", "EVIDENCE_CATEGORY", "FRAGMENTARY", "ILLEGIBLE",
           "INSUFFICIENT", "PARTIAL", "AnalysisResult", "analyze_artifact", "render_text"]
