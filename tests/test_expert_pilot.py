"""Milestone 8: expert annotation pilot, inter-annotator agreement, reference verification,
reversible label promotion, and the dating / translation outputs.

Every annotation, verification and record here is SYNTHETIC test data built in pytest's
tmp_path from tests/fixtures/valid/base_record.json. Nothing is written under data/ or
knowledge/. Tests that touch the live project only READ it, and assert that nothing has been
fabricated and nothing was mutated.
"""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from datetime import date
from pathlib import Path

import pytest

from src.annotation.agreement import (
    char_similarity,
    cohens_kappa,
    compute_agreement,
    iou,
    pair_annotations,
    render_agreement,
)
from src.annotation.model import ANNOTATIONS_PATH, blank_annotation
from src.annotation.pilot import checklist, load_pilot, pilot_status
from src.annotation.promote import (
    PromotionError,
    execute_promotion,
    execute_revert,
    plan_promotion,
    plan_revert,
    read_log,
    render_plan,
)
from src.annotation.resolve import resolve_artifact
from src.annotation.store import AnnotationRejected, AnnotationStore
from src.annotation.validate import validate_annotation
from src.dataset.convert import read_jsonl
from src.dataset.schema import RESEARCH_RECORDS_PATH, load_config
from src.knowledge.base import load as load_kb
from src.knowledge.verification import (
    VerificationRegistry,
    VerificationRejected,
    effective_statuses,
    key_references,
    new_verification,
    reference_status,
    validate_registry,
    verified_ref_ids,
)
from src.reasoning.engine import (
    ALTERNATIVES,
    CATEGORIES,
    DISPUTED,
    INSUFFICIENT,
    analyze_artifact,
    render_text,
)
from src.reasoning.types import (
    Attributed,
    EvidenceItem,
    InscriptionInput,
    ReasoningInputs,
    ReferenceInfo,
)

QUAL = "SYNTHETIC epigraphist (test fixture; not a real person)"
NOREFS: dict = {"knowledge_ref_ids": set(), "verified_ref_ids": set()}
PROTECTED = ("image_id", "artifact_id", "image_path", "image_sha256", "source", "source_reference",
             "license", "redistributable", "research_usable", "commercially_usable", "rights_notes",
             "site", "collection", "split", "context_reliability", "stratigraphic_context",
             "verification_status", "image_width_px", "image_height_px")


def annotation(art, *, who="SYN_project", prov="project_annotation", script="tamil_brahmi",
               present=None, state="unreviewed", reading=None, regions=(), dating=None,
               itype=None, alts=(), refs=(), supersedes=None, conf="moderate", obj="original"):
    a = blank_annotation(art, [f"{art}__1"], annotator_id=who, provenance_type=prov,
                         qualification=QUAL if prov == "expert_annotation" else None,
                         supersedes=supersedes)
    a["object"]["object_status"] = obj
    ins = a["inscription"]
    if script == "none":
        ins.update(inscription_present="no", script_type="none", inscription_type="not_applicable",
                   reading="not_applicable", script_confidence=conf)
    elif script == "uncertain":
        ins.update(inscription_present=present or "uncertain", script_type="uncertain", script_confidence="low")
    elif script != "unknown":
        ins.update(inscription_present=present or "yes", script_type=script, script_confidence=conf)
    if reading:
        ins.update(reading=reading, reading_source="this_annotator", reading_confidence="low")
        a["interpretation"].update(interpretation_type=itype or "uncertain")
        if itype == "personal_name":
            a["interpretation"].update(translation="not_applicable",
                                       meaning="Proper name; no literal translation established.")
    ins["alternative_readings"] = [{"reading": r, "source": "this_annotator"} for r in alts]
    ins["regions"] = [{"image_id": f"{art}__1", "x": x, "y": y, "width": w, "height": h,
                       "label": "inscription"} for x, y, w, h in regions]
    if dating:
        lo, hi, basis = dating[:3]
        src = dating[3] if len(dating) > 3 else "annotator_observation"
        a["dating"] = {"estimated_start_year": lo, "estimated_end_year": hi, "dating_confidence": "low",
                       "dating_basis": [basis],
                       "dating_evidence": [{"evidence_id": "E1", "evidence_type": basis,
                                            "observation": "SYNTHETIC observation", "confidence": "low",
                                            "source_reference": src, "supports_start_year": lo,
                                            "supports_end_year": hi}]}
    a["references"] = [{"ref_id": r, "citation": f"SYNTHETIC citation {r}", "verification_status": s}
                       for r, s in refs]
    a["image_usability"] = [{"image_id": f"{art}__1", "usable_for_annotation": "yes"}]
    a["review_state"] = state
    return a


def expert(art, **kw):
    kw.setdefault("state", "expert_reviewed")
    kw.setdefault("who", "SYN_expert")
    return annotation(art, prov="expert_annotation", **kw)


def plan(w, **kw):
    kw.setdefault("ref_statuses", {})
    return plan_promotion(store=w["store"], records_path=w["records_path"], data_root=w["raw"],
                          knowledge_ref_ids=kw.pop("knowledge_ref_ids", set()),
                          verified_ref_ids=kw.pop("verified_ref_ids", set()), **kw)


def execute(w, approve=None, approver="SYN_reviewer", **kw):
    p = plan(w, **kw)
    return execute_promotion(lambda: plan(w, **kw), approver=approver,
                             approve=approve if approve is not None else p.plan_digest, log=w["log"])


def records_by_id(w) -> dict:
    return {r["image_id"]: r for r in read_jsonl(w["records_path"])}


# --------------------------------------------------------------------------- #
# Annotation creation and revisions (existing architecture, reused)
# --------------------------------------------------------------------------- #


class TestAnnotationCreation:
    def test_expert_annotation_created(self, world):
        a = world["store"].append(expert(world["arts"][0]), **NOREFS)
        assert a["annotator"]["role"] == "expert" and a["annotator"]["qualification"] == QUAL
        assert world["store"].current(world["arts"][0])[0]["review_state"] == "expert_reviewed"

    def test_project_annotation_created(self, world):
        a = world["store"].append(annotation(world["arts"][0]), **NOREFS)
        assert a["annotator"]["role"] == "project_annotator" and a["provenance_type"] == "project_annotation"

    def test_all_script_choices_accepted(self, world):
        for i, s in enumerate(("tamil_brahmi", "graffiti", "tamil_brahmi_and_graffiti", "none",
                               "uncertain", "other_script")):
            world["store"].append(annotation(world["arts"][i], script=s), **NOREFS)
        assert len(world["store"].all()) == 6

    def test_revision_keeps_history_and_agreement_uses_current(self, world):
        art = world["arts"][0]
        first = world["store"].append(annotation(art, script="graffiti"), **NOREFS)
        world["store"].append(annotation(art, script="tamil_brahmi", supersedes=first["annotation_id"]), **NOREFS)
        world["store"].append(expert(art), **NOREFS)
        assert len(world["store"].all()) == 3
        rep = compute_agreement(world["store"].current(), [art])
        assert rep.fields["script_type"].per_artifact[art] == {"a": "tamil_brahmi", "b": "tamil_brahmi"}

    def test_self_declared_verified_reference_rejected_n14(self, world):
        a = annotation(world["arts"][0], refs=[("S03", "verified_against_source")])
        with pytest.raises(AnnotationRejected, match="N14"):
            world["store"].append(a, knowledge_ref_ids={"S03"}, verified_ref_ids=set())
        assert world["store"].all() == []

    def test_registry_verified_reference_accepted(self, world):
        a = annotation(world["arts"][0], refs=[("S03", "verified_against_source")])
        world["store"].append(a, knowledge_ref_ids={"S03"}, verified_ref_ids={"S03"})

    def test_n14_skipped_only_when_not_requested(self):
        a = annotation("A_X", refs=[("S03", "verified_against_source")])
        assert "N14" not in {p.rule for p in validate_annotation(a)}
        assert "N14" in {p.rule for p in validate_annotation(a, verified_ref_ids=set())}


# --------------------------------------------------------------------------- #
# Agreement
# --------------------------------------------------------------------------- #


class TestAgreementStatistics:
    def test_kappa_perfect(self):
        assert cohens_kappa([("a", "a"), ("b", "b"), ("a", "a"), ("b", "b")]) == pytest.approx(1.0)

    def test_kappa_known_value(self):
        # po = 0.7, pe = 0.5*0.6 + 0.5*0.4 = 0.5 -> kappa = 0.4
        pairs = [("y", "y")] * 4 + [("n", "n")] * 3 + [("y", "n")] * 1 + [("n", "y")] * 2
        assert cohens_kappa(pairs) == pytest.approx(0.4)

    def test_kappa_below_chance_is_negative(self):
        assert cohens_kappa([("a", "b"), ("b", "a")]) < 0

    def test_kappa_undefined_not_one_when_single_category(self):
        assert cohens_kappa([("a", "a")] * 6) is None
        assert cohens_kappa([]) is None

    def test_iou(self):
        r = {"x": 0.1, "y": 0.1, "width": 0.2, "height": 0.2}
        assert iou(r, r) == pytest.approx(1.0)
        assert iou(r, {"x": 0.5, "y": 0.5, "width": 0.2, "height": 0.2}) == 0.0
        assert iou(r, {"x": 0.2, "y": 0.1, "width": 0.2, "height": 0.2}) == pytest.approx(1 / 3)

    def test_reading_similarity_normalises_whitespace_and_case(self):
        assert char_similarity("Sa  than", "sa than") == 1.0
        assert 0 < char_similarity("sathan", "satan") < 1


class TestAgreementReport:
    def _six(self, world, expert_scripts, project_scripts):
        for art, e, p in zip(world["arts"], expert_scripts, project_scripts):
            world["store"].append(annotation(art, script=p), **NOREFS)
            world["store"].append(expert(art, script=e), **NOREFS)
        return compute_agreement(world["store"].current(), world["arts"])

    def test_six_items_is_insufficient_sample_with_raw_counts(self, world):
        rep = self._six(world, ["tamil_brahmi", "graffiti", "none", "tamil_brahmi", "graffiti", "uncertain"],
                        ["tamil_brahmi", "tamil_brahmi", "none", "tamil_brahmi", "graffiti", "graffiti"])
        f = rep.fields["script_type"]
        assert f.items_compared == 6 and f.items_agreeing == 4
        assert f.raw_agreement == pytest.approx(4 / 6)
        assert f.statistic is not None and not f.interpretable and f.status == "insufficient_sample"
        assert sum(sum(r.values()) for r in f.confusion.values()) == 6
        assert len(f.disagreements) == 2
        assert "not interpretable" in render_agreement(rep)

    def test_all_same_category_kappa_undefined(self, world):
        rep = self._six(world, ["graffiti"] * 6, ["graffiti"] * 6)
        f = rep.fields["script_type"]
        assert f.raw_agreement == 1.0 and f.statistic is None and f.status == "undefined"

    def test_interpretable_only_above_threshold(self, world):
        cfg = deepcopy(load_config())
        cfg["agreement"]["min_items_for_kappa"] = 6
        for art, (p, e) in zip(world["arts"], [("graffiti", "graffiti"), ("none", "none"),
                                                ("graffiti", "none"), ("tamil_brahmi", "tamil_brahmi"),
                                                ("none", "none"), ("graffiti", "graffiti")]):
            world["store"].append(annotation(art, script=p), **NOREFS)
            world["store"].append(expert(art, script=e), **NOREFS)
        rep = compute_agreement(world["store"].current(), world["arts"], config=cfg)
        assert rep.fields["script_type"].interpretable and rep.fields["script_type"].status == "ok"

    def test_unknown_is_excluded_not_counted_as_agreement(self, world):
        art = world["arts"][0]
        world["store"].append(annotation(art, script="unknown"), **NOREFS)
        world["store"].append(expert(art, script="unknown", state="unreviewed"), **NOREFS)
        f = compute_agreement(world["store"].current(), [art]).fields["inscription_present"]
        assert f.items_compared == 0 and f.excluded and f.status == "no_data"

    def test_presence_regions_reading_dating_are_separate(self, world):
        art = world["arts"][0]
        world["store"].append(annotation(art, reading="SYN_A", regions=[(0.1, 0.1, 0.2, 0.2)],
                                         dating=(-200, 100, "palaeography")), **NOREFS)
        world["store"].append(expert(art, reading="SYN_B", regions=[(0.1, 0.1, 0.2, 0.2)],
                                     dating=(-200, 100, "pottery_typology")), **NOREFS)
        rep = compute_agreement(world["store"].current(), [art])
        assert set(rep.fields) == {"object_status", "inscription_present", "script_type", "inscription_type",
                                   "interpretation_type", "regions", "reading", "dating_evidence_types",
                                   "dating_range"}
        assert rep.fields["dating_range"].items_agreeing == 1          # identical (-200, 100)
        assert rep.fields["regions"].statistic == pytest.approx(1.0)
        assert rep.fields["reading"].items_agreeing == 0 and rep.fields["reading"].disagreements
        assert rep.fields["dating_evidence_types"].statistic == 0.0
        assert rep.fields["inscription_present"].items_agreeing == 1

    def test_agreement_never_resolves_or_mutates(self, world):
        art = world["arts"][0]
        world["store"].append(annotation(art, script="graffiti"), **NOREFS)
        world["store"].append(expert(art, who="SYN_e1", script="tamil_brahmi"), **NOREFS)
        world["store"].append(expert(art, who="SYN_e2", script="graffiti"), **NOREFS)
        before = world["store"].path.read_bytes()
        rep = compute_agreement(world["store"].current(), [art], "SYN_e1", "SYN_e2")
        assert rep.resolves_disagreement is False
        assert rep.fields["script_type"].disagreements
        assert world["store"].path.read_bytes() == before
        assert resolve_artifact(art, world["store"].current()).status == "disputed"

    def test_ambiguous_tier_is_skipped(self, world):
        art = world["arts"][0]
        world["store"].append(annotation(art, who="SYN_p1"), **NOREFS)
        world["store"].append(annotation(art, who="SYN_p2"), **NOREFS)
        world["store"].append(expert(art), **NOREFS)
        pairs, skipped = pair_annotations(world["store"].current(), [art], "project_annotation",
                                          "expert_annotation")
        assert not pairs and "more than one" in skipped[art]
        pairs, _ = pair_annotations(world["store"].current(), [art], "SYN_p2", "expert_annotation")
        assert art in pairs

    def test_ai_prediction_is_never_a_rater(self, world):
        art = world["arts"][0]
        ai = annotation(art, who="SYN_model", prov="ai_prediction")
        ai["review_state"] = "unreviewed"
        world["store"].append(ai, **NOREFS)
        world["store"].append(expert(art), **NOREFS)
        pairs, skipped = pair_annotations(world["store"].current(), [art], "SYN_model", "expert_annotation")
        assert not pairs and art in skipped

    def test_raters_must_differ(self):
        with pytest.raises(ValueError):
            pair_annotations([], [], "expert_annotation", "expert_annotation")


# --------------------------------------------------------------------------- #
# Pilot
# --------------------------------------------------------------------------- #


class TestPilot:
    def test_pilot_is_the_six_keezhadi_closeups(self, live_research):
        p = load_pilot()
        assert p.artifacts == tuple(f"WMC_KEELADI_MUS_SHERD_{n}" for n in range(105, 111))
        assert set(p.required_tiers) == {"project_annotation", "expert_annotation"}
        assert "NOT assumed" in p.description
        if live_research["records"]:
            assert set(p.artifacts) <= live_research["artifacts"]

    def test_pilot_artifacts_carry_no_label(self, live_research):
        pilot = set(load_pilot().artifacts)
        for r in live_research["records"]:
            if r["artifact_id"] in pilot:
                assert r["script_type"] == "unknown" and r["label_source"] == "unknown"

    def test_live_pilot_status_reports_missing_tiers(self, live_research):
        store = AnnotationStore()
        ps = pilot_status(store.current(), live_research["artifacts"])
        assert len(ps.artifacts) == 6
        for s in ps.artifacts:
            assert s.in_records or not live_research["records"]
            if not store.for_artifact(s.artifact_id):
                assert s.missing_tiers == ["project_annotation", "expert_annotation"]

    def test_checklist(self):
        a = expert("A_X", regions=[(0.1, 0.1, 0.1, 0.1)])
        assert all(checklist(a).values())
        b = expert("A_X", state="unreviewed")
        assert checklist(b)["regions_marked"] is False and checklist(b)["review_state_set"] is False
        assert checklist(blank_annotation("A_X", ["A_X__1"], annotator_id="t"))["presence_decided"] is False

    def test_reading_not_required_by_checklist(self):
        assert "reading" not in " ".join(checklist(expert("A_X", regions=[(0, 0, 0.1, 0.1)])))

    def test_pilot_status_complete_with_both_tiers(self, world):
        from src.annotation.pilot import Pilot

        art = world["arts"][0]
        pilot = Pilot("t", "t", (art,), ("project_annotation", "expert_annotation"))
        world["store"].append(annotation(art, regions=[(0.1, 0.1, 0.1, 0.1)]), **NOREFS)
        assert pilot_status(world["store"].current(), {art}, pilot).complete == 0
        world["store"].append(expert(art, regions=[(0.1, 0.1, 0.1, 0.1)]), **NOREFS)
        assert pilot_status(world["store"].current(), {art}, pilot).complete == 1


# --------------------------------------------------------------------------- #
# Reference verification
# --------------------------------------------------------------------------- #


def good_verification(**kw):
    base = {"ref_id": "S03", "citation": "SYNTHETIC citation", "claim": "SYNTHETIC claim",
            "claim_id": "s03_keeladi_sathan", "status": "verified_against_source",
            "verifier": "SYN_verifier", "verifier_role": "expert", "verification_date": "2026-01-02",
            "locator": "SYNTHETIC p. 0", "source_location": "SYNTHETIC library shelfmark",
            "source_access": "physical_copy"}
    base.update(kw)
    return new_verification(**base)


def vrules(v, today=date(2026, 9, 23)):
    return {p.rule for p in validate_registry([v], today=today).problems}


class TestReferenceVerification:
    def test_complete_verified_record_is_valid(self):
        assert vrules(good_verification()) == set()

    @pytest.mark.parametrize("field,value", [
        ("verifier", "not_applicable"), ("verifier_role", "not_applicable"),
        ("verification_date", "not_applicable"), ("locator", "not_available"),
        ("source_location", "not_available"), ("source_access", "not_accessed"),
    ])
    def test_verified_requires_every_detail(self, field, value):
        assert "V3" in vrules(good_verification(**{field: value}))

    def test_future_date_rejected(self):
        assert "V3" in vrules(good_verification(verification_date="2099-01-01"))

    def test_no_ai_verifier_role(self):
        assert "V1" in vrules(good_verification(verifier_role="ai_model"))

    def test_discrepancy_needs_explanation(self):
        assert "V4" in vrules(good_verification(status="discrepancy_found"))
        assert "V4" not in vrules(good_verification(status="discrepancy_found", notes="SYNTHETIC: differs"))

    def test_source_unavailable_means_not_accessed(self):
        v = good_verification(status="source_unavailable", notes="SYNTHETIC: no copy")
        assert "V5" in vrules(v)
        v = good_verification(status="source_unavailable", source_access="not_accessed", notes="SYNTHETIC")
        assert "V5" not in vrules(v)

    def test_unverified_carries_no_date(self):
        v = new_verification(ref_id="S03", citation="c", claim="c", status="unverified",
                             verification_date="2026-01-01")
        assert "V6" in vrules(v)

    def test_unknown_reference_and_claim(self):
        assert "V2" in vrules(good_verification(ref_id="NOT_A_REF"))
        assert "V7" in vrules(good_verification(claim_id="not_a_claim"))

    def test_registry_is_append_only_and_rejects_invalid(self, tmp_path):
        reg = VerificationRegistry(tmp_path / "v.jsonl")
        with pytest.raises(VerificationRejected):
            reg.append(good_verification(locator="not_available"), today=date(2026, 9, 23))
        assert reg.all() == []
        first = reg.append(good_verification(), today=date(2026, 9, 23))
        before = reg.path.read_text(encoding="utf-8")
        reg.append(good_verification(status="discrepancy_found", notes="SYNTHETIC",
                                     supersedes=first["verification_id"]), today=date(2026, 9, 23))
        assert reg.path.read_text(encoding="utf-8").startswith(before)
        assert len(reg.current()) == 1

    def test_supersede_must_match_reference_and_claim(self, tmp_path):
        reg = VerificationRegistry(tmp_path / "v.jsonl")
        first = reg.append(good_verification(), today=date(2026, 9, 23))
        with pytest.raises(VerificationRejected, match="V8"):
            reg.append(good_verification(claim_id="s03_keeladi_eravathan",
                                         supersedes=first["verification_id"]), today=date(2026, 9, 23))

    def test_effective_status_lists_verified_claims(self):
        v = good_verification()
        st = reference_status("S03", current=[v])
        assert st.verified and st.effective_status == "verified_against_source"
        assert st.verified_claims[0]["claim_id"] == "s03_keeladi_sathan"
        assert st.knowledge_base_status == "transcribed_unverified"

    def test_discrepancy_overrides_verification(self):
        cur = [good_verification(), good_verification(claim_id="s03_keeladi_eravathan",
                                                      status="discrepancy_found", notes="SYNTHETIC")]
        assert reference_status("S03", current=cur).effective_status == "discrepancy_found"
        assert "S03" not in verified_ref_ids(cur)

    def test_source_unavailable_stays_unverified(self):
        v = good_verification(ref_id="R1", claim_id="config:chronology.position_A",
                              status="source_unavailable", source_access="not_accessed", notes="SYNTHETIC")
        assert reference_status("R1", current=[v]).effective_status == "bibliographic_only"

    def test_knowledge_base_cannot_self_verify_k6(self, tmp_path):
        (tmp_path / "references").mkdir()
        (tmp_path / "references" / "r.yaml").write_text(
            "kind: references\nentries:\n  - id: SX\n    citation: SYNTHETIC\n"
            "    verification_status: verified_against_source\n    verified_by: SYN\n"
            "    verified_on: '2026-01-01'\n", encoding="utf-8")
        kb = load_kb(tmp_path)
        assert kb.ok
        assert "K6" in {p.rule for p in validate_registry([], kb=kb).problems}

    def test_key_references_are_configured_and_live_unverified(self):
        assert key_references() == ["R1", "S01", "S03"]
        eff = effective_statuses()
        for rid in ("R1", "S01", "S03"):
            assert rid in eff
            if not VerificationRegistry().all():
                assert not eff[rid].verified

    def test_live_registry_valid_and_nothing_self_verified(self):
        res = VerificationRegistry().validate()
        assert res.ok, [str(p) for p in res.problems]
        for v in VerificationRegistry().all():
            if v["status"] == "verified_against_source":
                assert v["verifier"] != "not_applicable" and v["source_access"] != "not_accessed"

    def test_verify_cli_is_dry_run_by_default(self, monkeypatch, tmp_path, capsys):
        from src.knowledge import __main__ as kcli

        target = tmp_path / "reg.jsonl"
        monkeypatch.setattr(kcli, "VerificationRegistry", lambda: VerificationRegistry(target))
        code = kcli.main(["verify", "--ref", "S03", "--claim-id", "s03_keeladi_sathan",
                          "--status", "verified_against_source", "--verifier", "SYN_v",
                          "--role", "expert", "--date", "2026-01-02", "--locator", "SYN p. 0",
                          "--source-location", "SYN", "--access", "physical_copy"])
        assert code == 0 and "DRY RUN" in capsys.readouterr().out and not target.exists()


class TestUnverifiedConfidenceCap:
    def _inputs(self, status, claims=()):
        ev = (EvidenceItem("E1", "stratigraphy", "SYN", "expert_annotation", "high", "S03", -300, -100,
                           association="direct"),
              EvidenceItem("E2", "palaeography", "SYN", "expert_annotation", "high", "S03", -300, -100))
        from src.reasoning.types import ArchaeologicalContext

        return ReasoningInputs(
            "SYN", dating_evidence=ev,
            archaeological_context=ArchaeologicalContext(context_reliability=Attributed("excavated_stratified")),
            references={"S03": ReferenceInfo("S03", "SYN", status, tuple(claims))},
            annotation_status="expert_label")

    def test_unverified_reference_caps_confidence_at_low(self):
        r = analyze_artifact(self._inputs("transcribed_unverified"))
        assert r.confidence == "low"
        assert any("not verified" in x for x in r.limitations)

    def test_verified_reference_lifts_the_cap_and_names_the_claim(self):
        r = analyze_artifact(self._inputs("verified_against_source", ["SYNTHETIC claim"]))
        assert r.confidence == "high"
        assert any("verified only for: SYNTHETIC claim" in x for x in r.limitations)

    def test_annotation_cannot_self_verify_in_reasoning(self, world):
        from src.reasoning.from_annotations import build_inputs

        art = world["arts"][0]
        a = expert(art, dating=(-300, -100, "palaeography", "S03"), refs=[("S03", "verified_against_source")])
        world["store"].append(a, knowledge_ref_ids={"S03"}, verified_ref_ids={"S03"})   # simulated registry
        inputs = build_inputs(art, store=world["store"], records=world["records"], provenance={})
        assert inputs.references["S03"].verification_status != "verified_against_source"   # live registry decides
        assert analyze_artifact(inputs).confidence in ("low", "very_low", "unknown")


# --------------------------------------------------------------------------- #
# Promotion
# --------------------------------------------------------------------------- #


class TestPromotionDryRun:
    def test_dry_run_writes_nothing(self, world):
        world["store"].append(expert(world["arts"][0]), **NOREFS)
        before = world["records_path"].read_bytes()
        mtime = world["records_path"].stat().st_mtime_ns
        p = plan(world)
        assert p.dry_run and p.executable and len(p.candidates) == 1
        assert world["records_path"].read_bytes() == before
        assert world["records_path"].stat().st_mtime_ns == mtime
        assert not world["log"].exists()
        assert "DRY RUN" in render_plan(p)

    def test_annotations_alone_never_mutate_records(self, world):
        before = world["records_path"].read_bytes()
        for art in world["arts"]:
            world["store"].append(expert(art), **NOREFS)
        assert world["records_path"].read_bytes() == before

    def test_plan_digest_is_deterministic(self, world):
        world["store"].append(expert(world["arts"][0]), **NOREFS)
        assert plan(world).plan_digest == plan(world).plan_digest

    def test_invalid_store_blocks_everything(self, world):
        bad = expert(world["arts"][0])
        bad["annotator"]["role"] = "project_annotator"
        world["store"].path.write_text(json.dumps(bad) + "\n", encoding="utf-8")
        p = plan(world)
        assert not p.candidates and not p.executable and p.validation_errors

    def test_live_cli_dry_run_does_not_mutate(self, capsys):
        from src.annotation.__main__ import main

        before = RESEARCH_RECORDS_PATH.read_bytes() if RESEARCH_RECORDS_PATH.exists() else b""
        assert main(["promote", "--dry-run", "--pilot"]) == 0
        out = capsys.readouterr().out
        assert "DRY RUN" in out
        after = RESEARCH_RECORDS_PATH.read_bytes() if RESEARCH_RECORDS_PATH.exists() else b""
        assert after == before

    def test_live_cli_execute_without_approval_refused(self, capsys):
        from src.annotation.__main__ import main

        before = RESEARCH_RECORDS_PATH.read_bytes() if RESEARCH_RECORDS_PATH.exists() else b""
        assert main(["promote", "--execute", "--approver", "SYN"]) == 1
        assert "REFUSED" in capsys.readouterr().out
        after = RESEARCH_RECORDS_PATH.read_bytes() if RESEARCH_RECORDS_PATH.exists() else b""
        assert after == before


class TestPromotionRejections:
    def test_disputed_experts_rejected(self, world):
        art = world["arts"][0]
        world["store"].append(expert(art, who="SYN_e1", script="tamil_brahmi"), **NOREFS)
        world["store"].append(expert(art, who="SYN_e2", script="graffiti"), **NOREFS)
        p = plan(world)
        assert not p.candidates and "disputed" in p.rejections[0].reasons[0]

    def test_disputed_review_state_rejected(self, world):
        art = world["arts"][0]
        world["store"].append(expert(art, state="disputed"), **NOREFS)
        assert plan(world).rejections[0].status == "disputed"

    def test_project_only_rejected(self, world):
        art = world["arts"][0]
        world["store"].append(annotation(art, who="SYN_p1"), **NOREFS)
        world["store"].append(annotation(art, who="SYN_p2"), **NOREFS)
        p = plan(world)
        assert not p.candidates and "project label never becomes an expert label" in p.rejections[0].reasons[0]

    def test_project_reviewed_project_annotation_still_rejected(self, world):
        world["store"].append(annotation(world["arts"][0], state="project_reviewed"), **NOREFS)
        assert plan(world).rejections[0].status == "provisional"

    def test_unreviewed_expert_rejected(self, world):
        world["store"].append(expert(world["arts"][0], state="unreviewed"), **NOREFS)
        assert not plan(world).candidates

    def test_ai_prediction_rejected(self, world):
        ai = annotation(world["arts"][0], who="SYN_model", prov="ai_prediction")
        ai["review_state"] = "unreviewed"
        world["store"].append(ai, **NOREFS)
        p = plan(world)
        assert not p.candidates and "AI" in p.rejections[0].reasons[0]

    def test_ai_never_source_of_promoted_label(self, world):
        art = world["arts"][0]
        ai = annotation(art, who="SYN_model", prov="ai_prediction", script="graffiti")
        ai["review_state"] = "unreviewed"
        world["store"].append(ai, **NOREFS)
        e = world["store"].append(expert(art), **NOREFS)
        [c] = plan(world).candidates
        assert c.source_annotation_ids == [e["annotation_id"]] and c.label == "tamil_brahmi"

    def test_expert_without_qualification_rejected(self, world):
        a = expert(world["arts"][0])
        del a["annotator"]["qualification"]
        world["store"].append(a, **NOREFS)
        assert "qualification" in plan(world).rejections[0].reasons[0]

    def test_experts_disagreeing_on_presence_rejected(self, world):
        art = world["arts"][0]
        world["store"].append(expert(art, who="SYN_e1", script="uncertain", present="uncertain"), **NOREFS)
        world["store"].append(expert(art, who="SYN_e2", script="uncertain", present="yes"), **NOREFS)
        assert "P3" in plan(world).rejections[0].reasons[0]

    def test_other_script_rejected(self, world):
        world["store"].append(expert(world["arts"][0], script="other_script"), **NOREFS)
        assert "P4" in plan(world).rejections[0].reasons[0]

    def test_no_silent_overwrite_of_source_backed_label(self, world):
        recs = read_jsonl(world["records_path"])
        recs[0].update(script_type="graffiti", inscription_present="yes",
                       label_source="published_epigraphic_corpus")
        from src.dataset.convert import write_jsonl

        write_jsonl(world["records_path"], recs)
        world["store"].append(expert(world["arts"][0]), **NOREFS)
        p = plan(world)
        assert not p.candidates and "P6" in p.rejections[0].reasons[0]

    def test_sha_mismatch_rejected(self, world):
        (world["raw"] / world["records"][0]["image_path"]).write_bytes(b"tampered")
        world["store"].append(expert(world["arts"][0]), **NOREFS)
        assert "P7" in plan(world).rejections[0].reasons[0]

    def test_invalid_promoted_record_rejected_by_dataset_validator(self, world):
        # stratigraphy needs an excavated, stratified context (R10); these records have none.
        a = expert(world["arts"][0], dating=(-300, -100, "stratigraphy"))
        a["dating"]["dating_evidence"][0]["association"] = "direct"
        world["store"].append(a, **NOREFS)
        p = plan(world)
        assert not p.candidates and any("R10" in r for r in p.rejections[0].reasons)

    def test_one_rejection_does_not_block_others(self, world):
        world["store"].append(expert(world["arts"][0], state="disputed"), **NOREFS)
        world["store"].append(expert(world["arts"][1]), **NOREFS)
        p = plan(world)
        assert [c.artifact_id for c in p.candidates] == [world["arts"][1]] and len(p.rejections) == 1


class TestPromotionExecution:
    def test_successful_promotion(self, world):
        art = world["arts"][0]
        world["store"].append(annotation(art, script="graffiti"), **NOREFS)
        e = world["store"].append(expert(art, regions=[(0.1, 0.2, 0.3, 0.4)], conf="high"), **NOREFS)
        entry = execute(world)
        rec = records_by_id(world)[f"{art}__1"]
        assert rec["script_type"] == "tamil_brahmi" and rec["inscription_present"] == "yes"
        assert rec["label_source"] == "expert_annotation" and rec["label_confidence"] == "high"
        assert rec["inscription_regions"] == [{"x": 10, "y": 20, "w": 30, "h": 40, "region_label": "inscription",
                                               "annotator": "SYN_expert",
                                               "notes": f"expert annotation {e['annotation_id']}"}]
        assert (e["annotation_id"] in rec["notes"] and e["annotation_id"] in rec["annotator"]) or QUAL in rec["annotator"]
        assert entry["source_annotation_ids"] == {art: [e["annotation_id"]]}
        assert entry["notes"][art][0].startswith("Recorded disagreement")      # project said graffiti
        from src.dataset.validation import validate_records

        assert validate_records(read_jsonl(world["records_path"]), data_root=world["raw"],
                                verify_hashes=True).ok

    def test_provenance_and_sha_preserved(self, world):
        art = world["arts"][0]
        world["store"].append(expert(art), **NOREFS)
        before = records_by_id(world)
        execute(world)
        after = records_by_id(world)
        for iid, rec in before.items():
            for f in PROTECTED:
                assert after[iid][f] == rec[f], f
        img = world["raw"] / after[f"{art}__1"]["image_path"]
        assert hashlib.sha256(img.read_bytes()).hexdigest() == after[f"{art}__1"]["image_sha256"]
        assert after[f"{world['arts'][1]}__1"] == before[f"{world['arts'][1]}__1"]

    def test_unverified_evidence_stays_marked(self, world):
        a = expert(world["arts"][0], dating=(-200, 100, "palaeography", "S03"),
                   refs=[("S03", "unverified")])
        world["store"].append(a, knowledge_ref_ids={"S03"}, verified_ref_ids=set())
        execute(world, knowledge_ref_ids={"S03"}, ref_statuses={"S03": "transcribed_unverified"})
        rec = records_by_id(world)[f"{world['arts'][0]}__1"]
        assert rec["verification_status"] == "unverified"
        assert "S03 (transcribed_unverified)" in rec["dating_source"]
        assert rec["dating_reliability"] == "project_estimate"
        assert (rec["dating_lower_year"], rec["dating_upper_year"]) == (-200, 100)
        assert "expert estimate; not a published date" in rec["dating_text"]

    def test_approval_required(self, world):
        world["store"].append(expert(world["arts"][0]), **NOREFS)
        before = world["records_path"].read_bytes()
        with pytest.raises(PromotionError, match="digest"):
            execute(world, approve="0" * 64)
        with pytest.raises(PromotionError, match="approver"):
            execute(world, approver="")
        assert world["records_path"].read_bytes() == before and not world["log"].exists()

    def test_plan_changed_after_review_refused(self, world):
        world["store"].append(expert(world["arts"][0]), **NOREFS)
        digest = plan(world).plan_digest
        world["store"].append(expert(world["arts"][1]), **NOREFS)
        with pytest.raises(PromotionError):
            execute(world, approve=digest)

    def test_second_run_is_unchanged_not_duplicated(self, world):
        world["store"].append(expert(world["arts"][0]), **NOREFS)
        execute(world)
        p = plan(world)
        assert p.unchanged == [world["arts"][0]] and not p.candidates

    def test_lowest_expert_confidence_used(self, world):
        art = world["arts"][0]
        world["store"].append(expert(art, who="SYN_e1", conf="high"), **NOREFS)
        world["store"].append(expert(art, who="SYN_e2", conf="low"), **NOREFS)
        execute(world)
        assert records_by_id(world)[f"{art}__1"]["label_confidence"] == "low"

    def test_none_label_sets_reading_fields_not_applicable(self, world):
        world["store"].append(expert(world["arts"][0], script="none"), **NOREFS)
        execute(world)
        rec = records_by_id(world)[f"{world['arts'][0]}__1"]
        assert rec["script_type"] == "none" and rec["inscription_present"] == "no"
        assert rec["transcription"] == rec["translation_en"] == "not_applicable"


class TestPromotionUncertainty:
    def test_agreed_reading_promoted(self, world):
        world["store"].append(expert(world["arts"][0], reading="SYN_READING", alts=["SYN_ALT"]), **NOREFS)
        execute(world)
        rec = records_by_id(world)[f"{world['arts'][0]}__1"]
        assert rec["transcription"] == "SYN_READING" and rec["transcription_encoding"] == "romanized"
        assert rec["alternative_readings"][0].startswith("SYN_ALT (this_annotator; via ann_")
        assert "not a published reading" in rec["reading_source"]

    def test_expert_reading_disagreement_preserved_not_resolved(self, world):
        art = world["arts"][0]
        world["store"].append(expert(art, who="SYN_e1", reading="SYN_ONE"), **NOREFS)
        world["store"].append(expert(art, who="SYN_e2", reading="SYN_TWO"), **NOREFS)
        execute(world)
        rec = records_by_id(world)[f"{art}__1"]
        assert rec["transcription"] == "not_available" and rec["reading_status"] == "disputed"
        joined = " ".join(rec["alternative_readings"])
        assert "SYN_ONE" in joined and "SYN_TWO" in joined

    def test_personal_name_gets_no_translation(self, world):
        world["store"].append(expert(world["arts"][0], reading="SYN_NAME", itype="personal_name"), **NOREFS)
        execute(world)
        assert records_by_id(world)[f"{world['arts'][0]}__1"]["translation_en"] == "not_applicable"

    def test_conflicting_expert_dates_not_averaged(self, world):
        art = world["arts"][0]
        world["store"].append(expert(art, who="SYN_e1", dating=(-300, -200, "palaeography")), **NOREFS)
        world["store"].append(expert(art, who="SYN_e2", dating=(100, 200, "palaeography")), **NOREFS)
        execute(world)
        rec = records_by_id(world)[f"{art}__1"]
        assert rec["dating_reliability"] == "disputed"
        assert rec["dating_lower_year"] is None and rec["dating_upper_year"] is None
        assert "300 BCE – 200 BCE" in rec["dating_text"] and "100 CE – 200 CE" in rec["dating_text"]
        # No midpoint anywhere. (Checked as a date, not the bare substring "50": the text embeds
        # random annotation ids, which may contain "50".)
        assert "50 BCE" not in rec["dating_text"] and "50 CE" not in rec["dating_text"]

    def test_range_across_the_era_has_no_year_zero(self, world):
        world["store"].append(expert(world["arts"][0], dating=(-1, 1, "palaeography")), **NOREFS)
        execute(world)
        rec = records_by_id(world)[f"{world['arts'][0]}__1"]
        assert (rec["dating_lower_year"], rec["dating_upper_year"]) == (-1, 1)
        assert "1 BCE – 1 CE" in rec["dating_text"]

    def test_year_zero_annotation_cannot_reach_promotion(self, world):
        a = expert(world["arts"][0], dating=(-100, 100, "palaeography"))
        a["dating"]["estimated_end_year"] = 0
        with pytest.raises(AnnotationRejected):
            world["store"].append(a, **NOREFS)


class TestReversal:
    def test_revert_restores_bytes_exactly(self, world):
        original = world["records_path"].read_bytes()
        world["store"].append(expert(world["arts"][0], regions=[(0.1, 0.1, 0.1, 0.1)]), **NOREFS)
        entry = execute(world)
        assert world["records_path"].read_bytes() != original
        rp = plan_revert(entry["promotion_id"], records_path=world["records_path"], log=world["log"])
        assert rp.executable and world["records_path"].read_bytes() != original      # dry run
        execute_revert(entry["promotion_id"], approver="SYN_reviewer", approve=rp.plan_digest,
                       records_path=world["records_path"], log=world["log"])
        assert world["records_path"].read_bytes() == original

    def test_audit_trail_is_append_only(self, world):
        world["store"].append(expert(world["arts"][0]), **NOREFS)
        entry = execute(world)
        first = world["log"].read_text(encoding="utf-8")
        rp = plan_revert(entry["promotion_id"], records_path=world["records_path"], log=world["log"])
        execute_revert(entry["promotion_id"], approver="SYN_reviewer", approve=rp.plan_digest,
                       records_path=world["records_path"], log=world["log"])
        assert world["log"].read_text(encoding="utf-8").startswith(first)
        log = read_log(world["log"])
        assert [e["action"] for e in log] == ["promote", "revert"]
        assert log[1]["reverts"] == entry["promotion_id"]
        p = log[0]
        for k in ("approver", "executed_utc", "plan_digest", "records_sha256_before",
                  "records_sha256_after", "annotations_sha256", "source_annotation_ids", "changes"):
            assert p[k]
        assert p["changes"][0]["before"]["script_type"] == "unknown"
        assert p["changes"][0]["image_sha256"] == world["records"][0]["image_sha256"]

    def test_revert_refused_when_record_changed_since(self, world):
        world["store"].append(expert(world["arts"][0]), **NOREFS)
        entry = execute(world)
        recs = read_jsonl(world["records_path"])
        recs[0]["notes"] = "SYNTHETIC later edit"
        from src.dataset.convert import write_jsonl

        write_jsonl(world["records_path"], recs)
        rp = plan_revert(entry["promotion_id"], records_path=world["records_path"], log=world["log"])
        assert not rp.executable and rp.conflicts
        with pytest.raises(PromotionError):
            execute_revert(entry["promotion_id"], approver="SYN", approve=rp.plan_digest,
                           records_path=world["records_path"], log=world["log"])

    def test_double_revert_refused(self, world):
        world["store"].append(expert(world["arts"][0]), **NOREFS)
        entry = execute(world)
        rp = plan_revert(entry["promotion_id"], records_path=world["records_path"], log=world["log"])
        execute_revert(entry["promotion_id"], approver="SYN", approve=rp.plan_digest,
                       records_path=world["records_path"], log=world["log"])
        with pytest.raises(PromotionError, match="already been reverted"):
            plan_revert(entry["promotion_id"], records_path=world["records_path"], log=world["log"])

    def test_revert_needs_approval(self, world):
        world["store"].append(expert(world["arts"][0]), **NOREFS)
        entry = execute(world)
        before = world["records_path"].read_bytes()
        with pytest.raises(PromotionError):
            execute_revert(entry["promotion_id"], approver="SYN", approve="wrong",
                           records_path=world["records_path"], log=world["log"])
        assert world["records_path"].read_bytes() == before

    def test_unknown_promotion(self, world):
        with pytest.raises(PromotionError):
            plan_revert("prm_0000000000000000", records_path=world["records_path"], log=world["log"])


class TestTrainingGateUnchanged:
    def test_thresholds_not_relaxed(self):
        cfg = load_config()
        assert cfg["split"]["min_artifacts_per_class_for_holdout"] == 20
        assert cfg["classification"]["classes"] == ["tamil_brahmi", "graffiti", "none", "uncertain"]

    def test_small_promoted_pilot_is_still_blocked(self, world):
        for art in world["arts"]:
            world["store"].append(expert(art, script="graffiti"), **NOREFS)
        execute(world)
        from src.dataset.readiness import evaluate

        rep = evaluate(world["records_path"], world["raw"], permit_noncanonical_source=True)
        assert rep.training_ready is False
        failed = {g["id"] for g in rep.gates if g["passed"] is not True}
        assert {"G9", "G10"} <= failed

    def test_live_records_untouched(self, live_research):
        for r in live_research["records"]:
            assert r["script_type"] == "unknown" and r["label_source"] == "unknown"
        from src.annotation.promote import read_log as rl

        assert all(e["action"] in ("promote", "revert") for e in rl())


# --------------------------------------------------------------------------- #
# Reasoning outputs: dating statement, translation vs interpretation, uncertainty
# --------------------------------------------------------------------------- #


def _ins(reading="not_available", itype="not_applicable", translation="not_available", alts=()):
    return InscriptionInput(
        inscription_present=Attributed("yes", "expert_annotation", "moderate"),
        script_type=Attributed("tamil_brahmi", "expert_annotation", "moderate"),
        reading=Attributed(reading, "expert_annotation", "low", "this_annotator"),
        alternative_readings=tuple({"reading": a, "source": "this_annotator"} for a in alts),
        interpretation_type=Attributed(itype, "expert_annotation", "low", "this_annotator"),
        translation=Attributed(translation, "expert_annotation", "low", "this_annotator"))


class TestReasoningOutputs:
    def test_insufficient_evidence(self):
        r = analyze_artifact(ReasoningInputs("SYN"))
        assert r.status_statements[0] == INSUFFICIENT
        assert r.dating_summary["estimated_period"] == INSUFFICIENT
        assert set(r.dating_summary["evidence_by_category"]) == set(CATEGORIES)
        assert "Estimated period: Insufficient evidence" in render_text(r)

    def test_disputed_statement(self):
        r = analyze_artifact(ReasoningInputs("SYN", annotation_status="disputed",
                                             disagreements={"script_type": {"a": "x", "b": "y"}}))
        assert r.status_statements[0] == DISPUTED

    def test_alternative_readings_recorded(self):
        r = analyze_artifact(ReasoningInputs("SYN", inscription=_ins("SYN_A", alts=["SYN_B"])))
        assert ALTERNATIVES in r.status_statements
        assert "Alternative reading: SYN_B" in render_text(r)

    def test_personal_name_is_interpretation_not_translation(self):
        r = analyze_artifact(ReasoningInputs("SYN", inscription=_ins("SYN_NAME", "personal_name",
                                                                       "not_applicable")))
        text = render_text(r)
        assert "Not applicable (proper name)" in text
        assert "Proper name; no literal translation established." in text

    def test_no_reading_no_translation(self):
        text = render_text(analyze_artifact(ReasoningInputs("SYN", inscription=_ins())))
        assert "TRANSLATION\n  No translation established." in text

    def test_ai_gloss_is_not_a_translation(self):
        ins = _ins("SYN_A", "lexical_word")
        ins = InscriptionInput(**{**ins.__dict__, "translation": Attributed("SYN gloss", "ai_prediction",
                                                                         "high", "model")})
        assert analyze_artifact(ReasoningInputs("SYN", inscription=ins)).interpretation["state"] == "no_translation"

    def test_dating_statement_shape(self):
        ev = (EvidenceItem("E1", "palaeography", "SYN forms", "expert_annotation", "low",
                           "annotator_observation", -200, 100),)
        r = analyze_artifact(ReasoningInputs("SYN", dating_evidence=ev, annotation_status="expert_label"))
        ds = r.dating_summary
        assert ds["estimated_period"] == "approximately 200 BCE – 100 CE"
        assert ds["basis"] == ["[E1] palaeography: SYN forms"]
        assert ds["confidence"] == "low"
        assert ds["evidence_by_category"]["palaeographic"]
        text = render_text(r)
        for part in ("Estimated period:", "Basis:", "Confidence:", "Important uncertainty:"):
            assert part in text

    def test_publication_attribution_marks_verification_status(self):
        ev = (EvidenceItem("E1", "palaeography", "SYN", "expert_annotation", "low", "S03", -200, 100),)
        r = analyze_artifact(ReasoningInputs("SYN", dating_evidence=ev,
                                             references={"S03": ReferenceInfo("S03", "SYN", "transcribed_unverified")}))
        assert "S03 (transcribed_unverified)" in " ".join(r.dating_summary["evidence_by_category"]["publication_attribution"])

    def test_conflicting_evidence_remains_conflicting(self):
        ev = (EvidenceItem("E1", "associated_material", "SYN", "expert_annotation", "moderate",
                           "annotator_observation", -300, -200),
              EvidenceItem("E2", "palaeography", "SYN", "expert_annotation", "moderate",
                           "annotator_observation", 100, 200))
        r = analyze_artifact(ReasoningInputs("SYN", dating_evidence=ev))
        assert r.age["conflicts"] and r.dating_summary["important_uncertainty"]
        assert r.age["start_year"] == -300 and r.age["end_year"] == -200     # not a blend
        assert any("E2" in x for x in r.dating_summary["important_uncertainty"])

    def test_conflicting_annotator_positions_shown_side_by_side(self):
        positions = ({"annotation_id": "ann_a", "annotator_id": "SYN_a", "provenance": "expert_annotation",
                      "start_year": -300, "end_year": -200, "basis": ["palaeography"], "confidence": "moderate"},
                     {"annotation_id": "ann_b", "annotator_id": "SYN_b", "provenance": "expert_annotation",
                      "start_year": 100, "end_year": 200, "basis": ["palaeography"], "confidence": "moderate"})
        r = analyze_artifact(ReasoningInputs("SYN", annotator_dating_positions=positions))
        text = render_text(r)
        assert "300 BCE – 200 BCE" in text and "100 CE – 200 CE" in text
        assert any("Conflicting chronological positions" in s for s in r.status_statements)
        assert r.confidence in ("low", "very_low", "unknown")
        assert "50 BCE" not in text and "averag" in text

    def test_date_not_copied_from_site_caption(self, live_research):
        """The uploader's caption dates the Keeladi deposit; the object gets no date from it."""
        from src.reasoning.from_annotations import build_inputs

        pilot = [a for a in load_pilot().artifacts if a in live_research["artifacts"]]
        if not pilot:
            pytest.skip("pilot artifacts not present")
        for art in pilot:
            if AnnotationStore().for_artifact(art):
                continue
            r = analyze_artifact(build_inputs(art))
            assert r.age["state"] == "insufficient_evidence" and r.age["start_year"] is None

    def test_live_reasoning_all_insufficient_without_annotations(self, live_research):
        from src.reasoning.from_annotations import build_inputs

        if ANNOTATIONS_PATH.exists() or not live_research["records"]:
            pytest.skip("annotations exist or no records")
        for art in sorted(live_research["artifacts"]):
            r = analyze_artifact(build_inputs(art))
            assert INSUFFICIENT in r.status_statements


class TestLiveIntegrity:
    def test_no_fabricated_expert_labels_or_promotions(self):
        from src.annotation.promote import read_log as rl

        if not ANNOTATIONS_PATH.exists():
            assert rl() == []
        for line in (ANNOTATIONS_PATH.read_text(encoding="utf-8").splitlines()
                     if ANNOTATIONS_PATH.exists() else []):
            a = json.loads(line)
            assert "SYNTHETIC" not in json.dumps(a)

    def test_test_fixtures_stay_out_of_data(self):
        root = Path(__file__).resolve().parents[1] / "data"
        for sub in ("raw", "processed"):
            for p in (root / sub).rglob("*"):
                assert "FIXTURE" not in p.name and "SYNTHETIC" not in p.name
        if RESEARCH_RECORDS_PATH.exists():
            assert "FIXTURE" not in RESEARCH_RECORDS_PATH.read_text(encoding="utf-8")


# --------------------------------------------------------------------------- #
# Expert handoff pack: blank worksheets and the verification-checklist import
# --------------------------------------------------------------------------- #


def _csv(path):
    import csv

    with path.open(encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


class TestHandoffPack:
    def test_worksheets_carry_identity_only(self, tmp_path, live_research):
        from src.annotation.handoff import (
            ANNOTATION_COLUMNS,
            EXPERT_COLUMNS,
            build_handoff,
        )

        pack = build_handoff(live_research["records"], tmp_path / "pack")
        rows = _csv(tmp_path / "pack" / "pilot_worksheet_expert.csv")
        assert len(rows) == pack.photos == (6 if live_research["records"] else 0)
        for r in rows:
            assert all(r[c] == "" for c in (*EXPERT_COLUMNS, *ANNOTATION_COLUMNS))
            assert r["source_page"].startswith("https://commons.wikimedia.org/")
            assert "century" not in json.dumps(r)          # the uploader's dating caption stays out
        assert {r["artifact_id"] for r in rows} <= set(load_pilot().artifacts)

    def test_checklist_lists_key_reference_claims_blank(self, tmp_path, live_research):
        from src.annotation.handoff import VERIFICATION_COLUMNS, build_handoff

        build_handoff(live_research["records"], tmp_path / "pack")
        rows = _csv(tmp_path / "pack" / "verification_checklist.csv")
        assert {r["ref_id"] for r in rows} == {"R1", "S01", "S03"}
        assert all(r[c] == "" for r in rows for c in VERIFICATION_COLUMNS)
        assert "s03_keeladi_sathan" in {r["claim_id"] for r in rows}

    def test_handoff_cli_writes_only_to_out(self, tmp_path, capsys):
        from src.annotation.__main__ import main

        before = RESEARCH_RECORDS_PATH.read_bytes() if RESEARCH_RECORDS_PATH.exists() else b""
        assert main(["handoff", "--out", str(tmp_path / "o")]) == 0
        assert (tmp_path / "o" / "verification_checklist.csv").exists()
        assert (RESEARCH_RECORDS_PATH.read_bytes() if RESEARCH_RECORDS_PATH.exists() else b"") == before


def _filled_checklist(tmp_path, **fill):
    import csv

    from src.annotation.handoff import build_handoff

    build_handoff([], tmp_path / "pack")
    path = tmp_path / "pack" / "verification_checklist.csv"
    rows = _csv(path)
    for r in rows:
        if r["claim_id"] == "s03_keeladi_sathan":
            for k in r:
                if k.split(" (")[0] in fill:
                    r[k] = fill[k.split(" (")[0]]
    with path.open("w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    return path


GOOD_ROW = {"status": "verified_against_source", "locator_found": "SYNTHETIC p. 0",
            "verifier_id": "SYN_verifier", "verifier_role": "expert", "verification_date": "2026-01-02",
            "source_location": "SYNTHETIC library", "source_access": "physical_copy"}


class TestChecklistImport:
    def test_blank_checklist_imports_nothing(self, tmp_path):
        from src.knowledge.verification import import_checklist

        imp = import_checklist(_filled_checklist(tmp_path), VerificationRegistry(tmp_path / "r.jsonl"))
        assert imp.ok and imp.records == [] and imp.skipped == 10

    def test_filled_row_validates_and_commits(self, tmp_path):
        from src.knowledge.verification import commit_checklist, import_checklist

        reg = VerificationRegistry(tmp_path / "r.jsonl")
        imp = import_checklist(_filled_checklist(tmp_path, **GOOD_ROW), reg, today=date(2026, 9, 23))
        assert imp.ok and len(imp.records) == 1 and imp.records[0]["ref_id"] == "S03"
        assert not reg.path.exists()                                     # import alone writes nothing
        assert commit_checklist(imp, reg, today=date(2026, 9, 23)) == 1
        assert reference_status("S03", current=reg.current()).verified

    def test_incomplete_row_rejects_whole_import(self, tmp_path):
        from src.knowledge.verification import commit_checklist, import_checklist

        reg = VerificationRegistry(tmp_path / "r.jsonl")
        imp = import_checklist(_filled_checklist(tmp_path, **{**GOOD_ROW, "locator_found": ""}), reg,
                               today=date(2026, 9, 23))
        assert not imp.ok and "V3" in {p.rule for p in imp.problems}
        with pytest.raises(VerificationRejected):
            commit_checklist(imp, reg, today=date(2026, 9, 23))
        assert not reg.path.exists()

    def test_recheck_supersedes_previous_record(self, tmp_path):
        from src.knowledge.verification import commit_checklist, import_checklist

        reg = VerificationRegistry(tmp_path / "r.jsonl")
        first = commit_checklist(import_checklist(_filled_checklist(tmp_path, **GOOD_ROW), reg,
                                                  today=date(2026, 9, 23)), reg, today=date(2026, 9, 23))
        assert first == 1
        again = import_checklist(_filled_checklist(tmp_path, **{**GOOD_ROW, "status": "discrepancy_found",
                                                                "notes": "SYNTHETIC: differs"}),
                                 reg, today=date(2026, 9, 23))
        assert again.ok and again.records[0]["supersedes"] == reg.all()[0]["verification_id"]
        commit_checklist(again, reg, today=date(2026, 9, 23))
        assert reference_status("S03", current=reg.current()).effective_status == "discrepancy_found"
