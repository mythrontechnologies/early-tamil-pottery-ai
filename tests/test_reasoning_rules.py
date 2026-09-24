"""One test per reasoning rule (final engineering phase, Phase 4).

Every input is SYNTHETIC. The rules:

 R-a  insufficient evidence is a valid final answer
 R-b  unsupported claims are marked unsupported (AI values are reported, never used)
 R-c  conflicting evidence is reported, and conflicting dates are never averaged
 R-d  a translation is never invented; it needs a human source
 R-e  a personal name gets no literal translation
 R-f  there is no year 0
 R-g  unverified references cap confidence
 R-h  a dated context does not date an object not securely associated with it
 R-i  a script identification alone gives an outer bound, never a date
 R-j  annotators' disagreement caps confidence and is stated first
 R-k  the same inputs give the same output (digest)
"""

from __future__ import annotations

import json

import pytest

from src.dating.chronology import YearError, check_range, format_range, years_between
from src.reasoning.engine import DISPUTED, INSUFFICIENT, analyze_artifact
from src.reasoning.types import (
    ArchaeologicalContext,
    Attributed,
    EvidenceItem,
    InscriptionInput,
    ReasoningInputs,
    ReferenceInfo,
)
from src.translation.interpret import NO_READING, NO_TRANSLATION, PERSONAL_NAME

EXPERT = "expert_annotation"
STRAT = ArchaeologicalContext(context_reliability=Attributed("excavated_stratified", "source_information"))


def ev(eid, etype, lo, hi, prov=EXPERT, src="annotator_observation", conf="high", assoc="direct"):
    return EvidenceItem(eid, etype, f"SYNTHETIC {etype}", prov, conf, src, lo, hi, association=assoc)


def refs(status):
    return {"R1": ReferenceInfo("R1", "SYNTHETIC citation", status)}


def test_a_insufficient_evidence_is_a_valid_answer():
    r = analyze_artifact(ReasoningInputs("SYN"))
    assert r.status_statements[0] == INSUFFICIENT and r.age["state"] == "insufficient_evidence"
    assert r.confidence == "unknown" and r.age["start_year"] is None


def test_b_ai_values_are_reported_never_used():
    ins = InscriptionInput(inscription_present=Attributed("yes", "ai_prediction"),
                           script_type=Attributed("tamil_brahmi", "ai_prediction", "high"))
    r = analyze_artifact(ReasoningInputs("SYN", inscription=ins,
                                         dating_evidence=(ev("E1", "palaeography", -300, -100, prov="ai_prediction"),),
                                         ai_predictions=({"stage": "script_classification", "label": "tamil_brahmi"},)))
    assert r.age["state"] == "insufficient_evidence"
    assert "AI prediction" in r.age["excluded"]["E1"]
    assert r.ai_predictions and r.script["provenance"] == "ai_prediction"
    assert r.script["provenance_label"] == "AI prediction (not evidence)"


def test_c_conflicting_dates_reported_and_not_averaged():
    r = analyze_artifact(ReasoningInputs("SYN", archaeological_context=STRAT, dating_evidence=(
        ev("E1", "stratigraphy", -300, -200), ev("E2", "palaeography", 100, 200))))
    assert r.age["conflicts"] and "E2" not in r.age["used"]
    assert (r.age["start_year"], r.age["end_year"]) == (-300, -200)   # stronger evidence only; no midpoint
    assert r.confidence in ("low", "very_low")
    assert "-50" not in json.dumps(r.age) and "50 BCE" not in r.age["display"]


def test_d_no_invented_translation():
    ins = InscriptionInput(reading=Attributed("SYN_READING", EXPERT, "moderate", "this_annotator"),
                           interpretation_type=Attributed("lexical_word", EXPERT),
                           translation=Attributed("SYN_MEANING", EXPERT, "low", "not_available"))
    assert analyze_artifact(ReasoningInputs("SYN", inscription=ins)).interpretation["meaning"] == NO_TRANSLATION
    ai = InscriptionInput(reading=Attributed("SYN_READING", EXPERT, "moderate", "this_annotator"),
                          translation=Attributed("SYN_MEANING", "ai_prediction", "high", "some_model"))
    assert analyze_artifact(ReasoningInputs("SYN", inscription=ai)).interpretation["state"] == "no_translation"
    assert analyze_artifact(ReasoningInputs("SYN")).interpretation["meaning"] == NO_READING


def test_e_personal_name_has_no_literal_translation():
    ins = InscriptionInput(reading=Attributed("சாதன்", EXPERT, "moderate", "this_annotator"),
                           interpretation_type=Attributed("personal_name", EXPERT, "moderate"),
                           translation=Attributed("SHOULD_NOT_APPEAR", EXPERT, "high", "R1"))
    it = analyze_artifact(ReasoningInputs("SYN", inscription=ins)).interpretation
    assert it["state"] == "personal_name" and it["translation"] == "not_applicable"
    assert it["meaning"] == PERSONAL_NAME


def test_f_no_year_zero():
    with pytest.raises(YearError):
        check_range(0, 100)
    with pytest.raises(YearError):
        analyze_artifact(ReasoningInputs("SYN", dating_evidence=(ev("E1", "palaeography", -100, 0),)))
    assert years_between(-1, 1) == 1 and format_range(-1, 1) == "1 BCE – 1 CE"


@pytest.mark.parametrize("status, expected", [("bibliographic_only", "low"),
                                               ("transcribed_unverified", "low"),
                                               ("verified_against_source", "moderate")])
def test_g_unverified_references_cap_confidence(status, expected):
    r = analyze_artifact(ReasoningInputs("SYN", archaeological_context=STRAT, references=refs(status),
                                         dating_evidence=(ev("E1", "archaeological_context", -300, -100, src="R1"),
                                                          ev("E2", "palaeography", -250, -50, src="R1"))))
    assert r.confidence == expected


def test_h_insecure_association_does_not_date_the_object():
    r = analyze_artifact(ReasoningInputs("SYN", archaeological_context=STRAT, dating_evidence=(
        ev("E1", "absolute_dating", -500, -400, assoc="not_established"),)))
    assert r.age["state"] == "insufficient_evidence" and "association" in r.age["excluded"]["E1"]


def test_i_script_alone_is_an_outer_bound_only():
    ins = InscriptionInput(script_type=Attributed("tamil_brahmi", EXPERT, "high"))
    r = analyze_artifact(ReasoningInputs("SYN", inscription=ins))
    assert r.age["state"] == "outer_bound_only" and r.age["end_year"] is None
    assert r.confidence == "very_low"


def test_j_disagreement_caps_confidence_and_is_stated_first():
    r = analyze_artifact(ReasoningInputs("SYN", archaeological_context=STRAT, annotation_status="disputed",
                                         disagreements={"script_type": {"a": "graffiti", "b": "tamil_brahmi"}},
                                         dating_evidence=(ev("E1", "stratigraphy", -300, -100),
                                                          ev("E2", "archaeological_context", -250, -50))))
    assert r.status_statements[0] == DISPUTED and r.confidence in ("low", "very_low")


def test_k_deterministic():
    make = lambda: ReasoningInputs("SYN", dating_evidence=(ev("E2", "palaeography", -300, -100),  # noqa: E731
                                                           ev("E1", "linguistics", -250, 50)))
    a, b = analyze_artifact(make()), analyze_artifact(make())
    assert a.inputs_digest == b.inputs_digest and a.to_dict() == b.to_dict()
