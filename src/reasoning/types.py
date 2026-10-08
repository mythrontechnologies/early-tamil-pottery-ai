"""Structured inputs to the reasoning layer.

Every value arrives with its provenance (who asserts it) and, where relevant, a confidence
and a source reference. The reasoning layer consumes these structures, never free text,
so every statement it makes can be traced back to an input.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

PROVENANCES = ("expert_annotation", "source_information", "project_annotation", "ai_prediction", "none")
CONFIDENCE_ORDER = ("unknown", "very_low", "low", "moderate", "high")


@dataclass(frozen=True)
class Attributed:
    """A value plus who asserts it."""

    value: Any
    provenance: str = "none"
    confidence: str = "unknown"
    source_reference: str = "not_available"
    annotation_id: str | None = None

    @property
    def known(self) -> bool:
        return self.value not in (None, "unknown", "not_available", "not_applicable", "")


UNKNOWN = Attributed("unknown")


@dataclass(frozen=True)
class VisualFeatures:
    object_type: Attributed = UNKNOWN
    pottery_type: Attributed = UNKNOWN
    source_label: str = "not_available"          # what the SOURCE says the image shows, verbatim


@dataclass(frozen=True)
class InscriptionInput:
    inscription_present: Attributed = UNKNOWN
    script_type: Attributed = UNKNOWN
    reading: Attributed = Attributed("not_available")
    transliteration: str = "not_available"
    alternative_readings: tuple[dict[str, Any], ...] = ()
    interpretation_type: Attributed = Attributed("not_applicable")
    translation: Attributed = Attributed("not_available")
    meaning: str = "not_available"
    #: Annotation schema 1.2.0: complete | partial | fragmentary | illegible | unknown | not_applicable
    reading_completeness: str = "unknown"


@dataclass(frozen=True)
class LinguisticFeature:
    feature_type: str
    observation: str
    provenance: str
    confidence: str = "unknown"
    source_reference: str = "annotator_observation"
    significance: str = ""


@dataclass(frozen=True)
class EvidenceItem:
    evidence_id: str
    evidence_type: str
    observation: str
    provenance: str
    confidence: str = "unknown"
    source_reference: str = "annotator_observation"
    supports_start_year: int | None = None
    supports_end_year: int | None = None
    supports: str = ""
    association: str = "not_applicable"


@dataclass(frozen=True)
class ArchaeologicalContext:
    site: Attributed = UNKNOWN
    context_reliability: Attributed = UNKNOWN
    stratigraphic_context: Attributed = Attributed("not_available")


@dataclass(frozen=True)
class ReferenceInfo:
    ref_id: str
    citation: str
    verification_status: str                     # EFFECTIVE status (registry-backed, Milestone 8)
    verified_claims: tuple[str, ...] = ()        # the only claims a human verified


@dataclass
class ReasoningInputs:
    artifact_id: str
    visual_features: VisualFeatures = field(default_factory=VisualFeatures)
    inscription: InscriptionInput = field(default_factory=InscriptionInput)
    linguistic_features: tuple[LinguisticFeature, ...] = ()
    archaeological_context: ArchaeologicalContext = field(default_factory=ArchaeologicalContext)
    dating_evidence: tuple[EvidenceItem, ...] = ()
    references: dict[str, ReferenceInfo] = field(default_factory=dict)
    ai_predictions: tuple[dict[str, Any], ...] = ()
    annotation_status: str = "unannotated"        # from src.annotation.resolve
    disagreements: dict[str, Any] = field(default_factory=dict)
    # Milestone 8: every current human annotator's own dating range, side by side. Shown and
    # compared, never averaged. Each: annotation_id, annotator_id, provenance, start_year,
    # end_year, basis, confidence.
    annotator_dating_positions: tuple[dict[str, Any], ...] = ()


def min_confidence(*levels: str) -> str:
    known = [lv for lv in levels if lv in CONFIDENCE_ORDER]
    return min(known, key=CONFIDENCE_ORDER.index) if known else "unknown"


__all__ = ["CONFIDENCE_ORDER", "PROVENANCES", "UNKNOWN", "ArchaeologicalContext", "Attributed",
           "EvidenceItem", "InscriptionInput", "LinguisticFeature", "ReasoningInputs",
           "ReferenceInfo", "VisualFeatures", "min_confidence"]
