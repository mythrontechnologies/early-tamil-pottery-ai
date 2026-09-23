"""Milestone 7: chronology arithmetic, evidence-based dating, interpretation, the reasoning
engine, and the knowledge base. All evidence here is SYNTHETIC unless stated otherwise.
"""

from __future__ import annotations

import json

import pytest

from src.dating.chronology import (
    YearError,
    century_of,
    check_range,
    check_year,
    format_range,
    hull,
    intersect,
    periods,
    script_positions,
    years_between,
)
from src.dating.estimate import estimate_age
from src.knowledge.base import load
from src.reasoning.engine import DISCLAIMER, analyze_artifact, render_text
from src.reasoning.types import (
    ArchaeologicalContext,
    Attributed,
    EvidenceItem,
    InscriptionInput,
    LinguisticFeature,
    ReasoningInputs,
    ReferenceInfo,
)
from src.translation.interpret import (
    NO_READING,
    NO_TRANSLATION,
    PERSONAL_NAME,
    interpret,
)

VERIFIED = {"RV": ReferenceInfo("RV", "SYNTHETIC verified ref", "verified_against_source")}
UNVERIFIED = {"RU": ReferenceInfo("RU", "SYNTHETIC unverified ref", "unverified")}


def ev(eid="E1", etype="palaeography", lo=-300, hi=100, prov="expert_annotation", conf="moderate",
       src="annotator_observation", assoc="not_applicable"):
    return EvidenceItem(eid, etype, "SYNTHETIC observation", prov, conf, src, lo, hi, "", assoc)


# --------------------------------------------------------------------------- #
# Chronology arithmetic
# --------------------------------------------------------------------------- #


class TestYears:
    def test_no_year_zero(self):
        with pytest.raises(YearError, match="no year 0"):
            check_year(0)

    def test_range_order(self):
        with pytest.raises(YearError):
            check_range(100, -100)
        assert check_range(-100, None) == (-100, None)

    def test_years_between_skips_zero(self):
        assert years_between(-1, 1) == 1
        assert years_between(-200, 100) == 299
        assert years_between(100, 200) == 100

    @pytest.mark.parametrize("year,expected", [(-150, "2nd century BCE"), (-100, "1st century BCE"),
                                               (-101, "2nd century BCE"), (1, "1st century CE"),
                                               (211, "3rd century CE"), (-1100, "11th century BCE")])
    def test_century(self, year, expected):
        assert century_of(year) == expected

    def test_format_and_set_operations(self):
        assert format_range(-200, -50) == "200 BCE – 50 BCE"
        assert format_range(-600, None) == "no earlier than 600 BCE"
        assert intersect((-300, 100), (-100, 300)) == (-100, 100)
        assert intersect((-300, -200), (-100, 100)) is None
        assert hull([(-300, -200), (-100, 100)]) == (-300, 100)

    def test_positions_and_periods_come_from_config(self):
        ids = {p.id for p in script_positions()}
        assert ids == {"A", "B", "C", "D"}
        assert all(p.verification_status == "unverified" for p in script_positions())
        assert [p.id for p in periods()] == ["early_historic_tamil_nadu"]


# --------------------------------------------------------------------------- #
# Dating
# --------------------------------------------------------------------------- #


class TestDating:
    def test_no_evidence_is_insufficient(self):
        est = estimate_age([])
        assert est.state == "insufficient_evidence" and est.start_year is None
        assert est.confidence == "unknown" and est.display == "Insufficient evidence"

    def test_script_only_gives_outer_bound_not_a_date(self):
        est = estimate_age([], script=Attributed("tamil_brahmi", "expert_annotation", "high"))
        assert est.state == "outer_bound_only" and est.end_year is None
        assert est.start_year == min(p.lower_year for p in script_positions() if p.lower_year)
        assert est.confidence == "very_low"
        assert any("outer bound" in x for x in est.limitations)
        assert any("objection" in r for r in est.reasoning)          # Position D surfaced

    def test_project_script_alone_does_not_establish_a_bound(self):
        est = estimate_age([], script=Attributed("tamil_brahmi", "project_annotation", "high"))
        assert est.state == "insufficient_evidence"

    def test_ai_script_prediction_never_dates(self):
        est = estimate_age([], script=Attributed("tamil_brahmi", "ai_prediction", "high"))
        assert est.state == "insufficient_evidence"

    def test_single_palaeographic_item_is_low(self):
        est = estimate_age([ev()])
        assert (est.start_year, est.end_year) == (-300, 100) and est.confidence == "low"

    def test_intersection_narrows(self):
        est = estimate_age([ev("E1", "palaeography", -300, 100),
                            ev("E2", "associated_material", -200, 200)])
        assert (est.start_year, est.end_year) == (-200, 100)

    def test_conflict_is_reported_not_averaged(self):
        est = estimate_age([ev("E1", "associated_material", -300, -200),
                            ev("E2", "palaeography", 100, 200)])
        assert (est.start_year, est.end_year) == (-300, -200)       # stronger tier wins
        assert est.conflicts and est.confidence == "low"
        assert est.used == ["E1"]

    def test_ai_evidence_excluded(self):
        est = estimate_age([ev(prov="ai_prediction")])
        assert est.state == "insufficient_evidence" and "AI prediction" in est.excluded["E1"]

    def test_insecure_association_excluded(self):
        est = estimate_age([ev(etype="absolute_dating", assoc="same_context_insecure")],
                           context_reliability="excavated_stratified")
        assert "Position D" in est.excluded["E1"]

    def test_stratigraphy_needs_stratified_context(self):
        est = estimate_age([ev(etype="stratigraphy", assoc="direct")], context_reliability="unknown")
        assert "context_reliability" in est.excluded["E1"]

    def test_unknown_reference_excluded(self):
        est = estimate_age([ev(src="NOPE")])
        assert "unknown reference" in est.excluded["E1"]

    def test_high_needs_verified_stratified_expert_evidence(self):
        items = [ev("E1", "stratigraphy", -250, -50, conf="high", src="RV", assoc="direct"),
                 ev("E2", "palaeography", -300, -1, conf="high", src="RV")]
        est = estimate_age(items, context_reliability="excavated_stratified", references=VERIFIED)
        assert est.confidence == "high" and (est.start_year, est.end_year) == (-250, -50)

    def test_unverified_reference_caps_confidence(self):
        items = [ev("E1", "stratigraphy", -250, -50, conf="high", src="RU", assoc="direct"),
                 ev("E2", "palaeography", -300, -1, conf="high", src="RU")]
        est = estimate_age(items, context_reliability="excavated_stratified", references=UNVERIFIED)
        assert est.confidence == "low" and any("not verified" in x for x in est.limitations)

    def test_project_evidence_caps_confidence(self):
        items = [ev("E1", "associated_material", -250, -50, prov="project_annotation", conf="high"),
                 ev("E2", "palaeography", -300, -1, prov="project_annotation", conf="high")]
        assert estimate_age(items).confidence == "low"

    def test_qualitative_evidence_reported_not_used(self):
        est = estimate_age([ev(lo=None, hi=None)])
        assert est.state == "insufficient_evidence" and "qualitative" in est.reasoning[0]

    def test_open_ended_range_flagged(self):
        est = estimate_age([ev(lo=-300, hi=None)])
        assert est.end_year is None and any("open-ended" in x for x in est.limitations)


# --------------------------------------------------------------------------- #
# Interpretation
# --------------------------------------------------------------------------- #


class TestInterpretation:
    def test_no_reading(self):
        assert interpret(InscriptionInput()).meaning == NO_READING

    def test_personal_name(self):
        r = interpret(InscriptionInput(reading=Attributed("FIXTURE", "expert_annotation", "high", "RV"),
                                       interpretation_type=Attributed("personal_name", "expert_annotation")))
        assert r.state == "personal_name" and r.translation == "not_applicable" and r.meaning == PERSONAL_NAME

    def test_no_translation_established(self):
        r = interpret(InscriptionInput(reading=Attributed("FIXTURE", "expert_annotation", "high", "RV"),
                                       interpretation_type=Attributed("unknown", "expert_annotation")))
        assert r.meaning == NO_TRANSLATION and r.translation == "not_available"

    def test_ai_translation_is_ignored(self):
        r = interpret(InscriptionInput(reading=Attributed("FIXTURE", "expert_annotation", "high", "RV"),
                                       interpretation_type=Attributed("lexical_word", "expert_annotation"),
                                       translation=Attributed("SYNTHETIC gloss", "ai_prediction", "high", "model")))
        assert r.state == "no_translation"

    def test_sourced_translation_reported_with_provenance(self):
        r = interpret(InscriptionInput(reading=Attributed("FIXTURE", "expert_annotation", "high", "RV"),
                                       interpretation_type=Attributed("lexical_word", "expert_annotation"),
                                       translation=Attributed("SYNTHETIC gloss", "expert_annotation", "moderate", "RV")))
        assert r.state == "translated" and r.source == "RV" and r.provenance == "expert_annotation"


# --------------------------------------------------------------------------- #
# Engine
# --------------------------------------------------------------------------- #


def full_inputs() -> ReasoningInputs:
    return ReasoningInputs(
        artifact_id="FIXTURE_ART_A",
        inscription=InscriptionInput(
            inscription_present=Attributed("yes", "expert_annotation", "high"),
            script_type=Attributed("tamil_brahmi", "expert_annotation", "high"),
            reading=Attributed("FIXTURE_READING", "expert_annotation", "moderate", "RV"),
            interpretation_type=Attributed("personal_name", "expert_annotation", "moderate", "RV")),
        linguistic_features=(LinguisticFeature("word_form", "SYNTHETIC feature", "expert_annotation", "low", "RV"),),
        archaeological_context=ArchaeologicalContext(Attributed("FIXTURE_SITE", "source_information"),
                                                     Attributed("excavated_stratified", "source_information")),
        dating_evidence=(ev("E1", "stratigraphy", -250, -50, conf="high", src="RV", assoc="direct"),
                         ev("E2", "palaeography", -300, -1, conf="moderate", src="RV")),
        references=dict(VERIFIED),
        annotation_status="expert_label")


class TestEngine:
    def test_full_evidence_analysis(self):
        r = analyze_artifact(full_inputs())
        assert r.age["state"] == "estimated" and (r.age["start_year"], r.age["end_year"]) == (-250, -50)
        assert r.confidence == "high"
        assert r.interpretation["state"] == "personal_name"
        assert "Early Historic" in r.period_estimate and "unverified" in r.period_estimate
        assert r.disclaimer == DISCLAIMER

    def test_keyword_interface(self):
        i = full_inputs()
        r = analyze_artifact(artifact_id=i.artifact_id, inscription=i.inscription,
                             archaeological_context=i.archaeological_context,
                             dating_evidence=i.dating_evidence, references=i.references)
        assert r.age["state"] == "estimated"

    def test_deterministic(self):
        a, b = analyze_artifact(full_inputs()), analyze_artifact(full_inputs())
        assert json.dumps(a.to_dict(), sort_keys=True) == json.dumps(b.to_dict(), sort_keys=True)

    def test_empty_inputs_say_insufficient(self):
        r = analyze_artifact(ReasoningInputs("FIXTURE_ART_A"))
        assert r.period_estimate.startswith("Undetermined") and r.confidence == "unknown"
        assert r.age["display"] == "Insufficient evidence"
        text = render_text(r)
        assert "Insufficient evidence" in text and "not a definitive" in text

    def test_no_fabricated_evidence(self):
        """Every evidence item in the output is one of the inputs; nothing is added."""
        i = full_inputs()
        r = analyze_artifact(i)
        assert [e["evidence_id"] for e in r.evidence] == sorted(e.evidence_id for e in i.dating_evidence)
        for line in r.reasoning:
            if line.startswith("Dating: ["):
                assert any(f"[{e.evidence_id}]" in line for e in i.dating_evidence)

    def test_disagreement_caps_confidence(self):
        i = full_inputs()
        i.annotation_status = "disputed"
        i.disagreements = {"script_type": {"a": "tamil_brahmi", "b": "uncertain"}}
        r = analyze_artifact(i)
        assert r.confidence == "low" and any("disagree" in x for x in r.limitations)

    def test_ai_predictions_reported_separately(self):
        i = ReasoningInputs("FIXTURE_ART_A", ai_predictions=({"script_type": "tamil_brahmi"},))
        r = analyze_artifact(i)
        assert r.ai_predictions and r.script["statement"] == "Script not determined."
        assert "AI PREDICTIONS (reported only; not evidence)" in render_text(r)

    def test_never_claims_certainty(self):
        text = render_text(analyze_artifact(full_inputs())).lower()
        assert "definitely" not in text and "certainly" not in text


class TestRealArtifacts:
    def test_every_real_artifact_is_insufficient_without_annotations(self, live_research):
        from src.annotation.model import ANNOTATIONS_PATH
        from src.reasoning.from_annotations import build_inputs

        if ANNOTATIONS_PATH.exists():
            pytest.skip("real annotations exist; covered by annotation-specific tests")
        for aid in sorted(live_research["artifacts"]):
            r = analyze_artifact(build_inputs(aid, records=live_research["records"]))
            assert r.age["state"] == "insufficient_evidence"
            assert r.script["statement"] == "Script not determined."
            assert r.reading["value"] == "not_available"

    def test_from_annotations_uses_expert_over_project(self, tmp_path, live_research):
        from src.annotation.model import blank_annotation
        from src.annotation.store import AnnotationStore
        from src.reasoning.from_annotations import build_inputs

        if not live_research["records"]:
            pytest.skip("no research records")
        rec = live_research["records"][0]
        aid, imgs = rec["artifact_id"], [rec["image_id"]]
        store = AnnotationStore(tmp_path / "a.jsonl")
        p = blank_annotation(aid, imgs, annotator_id="SYNTHETIC_proj")
        p["inscription"].update(inscription_present="uncertain", script_type="uncertain", script_confidence="low")
        e = blank_annotation(aid, imgs, annotator_id="SYNTHETIC_exp", provenance_type="expert_annotation",
                             qualification="SYNTHETIC")
        e["inscription"].update(inscription_present="yes", script_type="tamil_brahmi", script_confidence="moderate")
        e["review_state"] = "expert_reviewed"
        store.append(p, knowledge_ref_ids=set())
        store.append(e, knowledge_ref_ids=set())
        i = build_inputs(aid, store=store, records=live_research["records"])
        assert i.inscription.script_type.provenance == "expert_annotation"
        assert i.annotation_status == "expert_label" and "script_type" in i.disagreements
        r = analyze_artifact(i)
        assert r.age["state"] == "outer_bound_only"           # script alone never dates the object


# --------------------------------------------------------------------------- #
# Knowledge base
# --------------------------------------------------------------------------- #


class TestKnowledgeBase:
    def test_loads_cleanly(self):
        kb = load()
        assert kb.ok, kb.problems
        assert {"R1", "S01", "S03", "R6"} <= set(kb.references)

    def test_every_assertion_is_referenced(self):
        kb = load()
        for eid, e in kb.entries.items():
            items = e.get("assertions", []) + ([e] if "reference_ids" in e else [])
            assert items, f"{eid} asserts nothing and should not exist"
            for a in items:
                assert a["reference_ids"] and all(r in kb.references for r in a["reference_ids"])

    def test_nothing_is_evidence_grade_yet(self):
        kb = load()
        assert not any(kb.is_evidence_grade(r) for r in kb.references)

    def test_bad_reference_rejected(self, tmp_path):
        (tmp_path / "references").mkdir()
        (tmp_path / "sites").mkdir()
        (tmp_path / "references" / "r.yaml").write_text(
            "kind: references\nentries:\n- id: X1\n  citation: SYNTHETIC\n  verification_status: unverified\n",
            encoding="utf-8")
        (tmp_path / "sites" / "s.yaml").write_text(
            "kind: sites\nentries:\n- id: fixture_site\n  assertions:\n  - statement: SYNTHETIC\n"
            "    reference_ids: [X9]\n    verification_status: unverified\n", encoding="utf-8")
        assert any(p.startswith("K3") for p in load(tmp_path).problems)

    def test_verified_claim_requires_verifier(self, tmp_path):
        (tmp_path / "references").mkdir()
        (tmp_path / "references" / "r.yaml").write_text(
            "kind: references\nentries:\n- id: X1\n  citation: SYNTHETIC\n"
            "  verification_status: verified_against_source\n", encoding="utf-8")
        assert any(p.startswith("K5") for p in load(tmp_path).problems)
