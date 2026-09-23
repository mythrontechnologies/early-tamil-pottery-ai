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
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from typing import Any

from src.dating.chronology import periods
from src.dating.estimate import AgeEstimate, estimate_age
from src.translation.interpret import InterpretationResult, interpret

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
                                    "alternative_readings": list(ins.alternative_readings)}
    if ins.reading.known:
        reasoning.append(f"Reading: '{ins.reading.value}' ({PROVENANCE_LABEL.get(ins.reading.provenance)}, "
                         f"{ins.reading.confidence} confidence, source: {ins.reading.source_reference}).")
        if ins.alternative_readings:
            reasoning.append("Alternative readings exist: " + "; ".join(
                f"'{r.get('reading')}' ({r.get('source')})" for r in ins.alternative_readings) + ".")
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

    # -- annotation state ----------------------------------------------------------------
    confidence = age.confidence
    if inputs.annotation_status in ("disputed", "project_disagreement"):
        limitations.append(f"Annotators disagree ({inputs.annotation_status}): "
                           + json.dumps(inputs.disagreements, ensure_ascii=False, sort_keys=True))
        confidence = min_confidence(confidence, "low")
    if inputs.annotation_status != "expert_label":
        limitations.append("No expert-reviewed label exists for this artifact.")

    unverified = sorted(r.ref_id for r in inputs.references.values()
                        if r.verification_status != "verified_against_source")
    if unverified:
        limitations.append("References not verified against the source: " + ", ".join(unverified) + ".")

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
    )


def render_text(r: AnalysisResult) -> str:
    """The report layout from the Milestone 7 brief. Every line comes from the result."""
    age = r.age
    est = age["display"] + (f" ({age['centuries']})" if age.get("centuries") else "")
    L = [f"ARTIFACT  {r.artifact_id}", "",
         "LIKELY PERIOD", f"  {r.period_estimate}", "",
         "ESTIMATED AGE", f"  {est}", "",
         "SCRIPT", f"  {r.script.get('statement')}", "",
         "READING", f"  {r.reading['value'] if r.reading['value'] not in ('not_available', 'unknown') else 'None established'}", "",
         "MEANING", f"  {r.interpretation['meaning']}", "",
         "WHY? (every line traces to a recorded input)"]
    L += [f"  • {line}" for line in r.reasoning]
    L += ["", "CONFIDENCE", f"  {r.confidence}"]
    if r.ai_predictions:
        L += ["", "AI PREDICTIONS (reported only; not evidence)"]
        L += [f"  • {json.dumps(p, ensure_ascii=False, sort_keys=True)}" for p in r.ai_predictions]
    L += ["", "LIMITATIONS"] + [f"  • {x}" for x in r.limitations]
    L += ["", r.disclaimer]
    return "\n".join(L)


__all__ = ["DISCLAIMER", "AnalysisResult", "analyze_artifact", "render_text"]
