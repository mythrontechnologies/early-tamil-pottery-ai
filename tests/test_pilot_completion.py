"""Pilot completion (2026-09-24): object original/reproduction status, review flags, promotion
rule P10, rule N15 (AI output never under a human tier), the read-only AI-draft layer, blank
independent worksheets, the extended agreement report and the per-claim verification report.

All annotations are SYNTHETIC (tmp_path). Tests that touch the live project only READ it.
"""

from __future__ import annotations

import csv
import json
from copy import deepcopy

import pytest
from test_expert_pilot import NOREFS, annotation, expert, plan

from src.annotation.agreement import compute_agreement, render_agreement
from src.annotation.ai_draft import AI_DRAFT_WARNING, is_ai_marked, load_ai_draft
from src.annotation.handoff import ANNOTATION_COLUMNS, build_handoff
from src.annotation.model import ANNOTATION_SCHEMA_VERSION, blank_annotation
from src.annotation.pilot import checklist, load_pilot, load_review_flags
from src.annotation.store import AnnotationRejected
from src.annotation.validate import validate_annotation
from src.dataset.schema import load_config
from src.knowledge.verification import UNRESOLVED_REF, claim_report

PROVENANCE_COLUMNS = {"artifact_id", "image_id", "local_path", "source_page", "license", "attribution"}


def _flag_config(art: str, kind: str = "possible_reproduction") -> dict:
    cfg = deepcopy(load_config())
    cfg["annotation_pilot"]["review_flags"] = [
        {"artifact": art, "kind": kind, "label": "REVIEW REQUIRED — possible reproduction / duplicate inscription",
         "related_artifact": "FIXTURE_PILOT_2", "confirmed": False}]
    return cfg


class TestObjectStatus:
    def test_schema_version_and_blank_default(self):
        a = blank_annotation("A_X", ["A_X__1"], annotator_id="t")
        assert ANNOTATION_SCHEMA_VERSION == "1.2.0"          # 1.2.0: adjudication, glyph regions, completeness
        assert a["object"]["object_status"] == "unknown"
        assert a["inscription"]["reading_completeness"] == "unknown"

    def test_schema_accepts_all_statuses_and_rejects_others(self):
        for s in ("original", "reproduction", "uncertain", "unknown"):
            assert not validate_annotation(annotation("A_X", obj=s))
        assert any(p.rule == "N1" for p in validate_annotation(annotation("A_X", obj="replica")))

    def test_record_without_the_field_is_still_valid(self):
        a = annotation("A_X")
        del a["object"]["object_status"]                       # a 1.0.0-style record
        assert not validate_annotation(a)

    def test_checklist_requires_object_status(self):
        assert checklist(expert("A_X", regions=[(0.1, 0.1, 0.1, 0.1)], obj="unknown"))["object_status_decided"] is False
        assert checklist(expert("A_X", regions=[(0.1, 0.1, 0.1, 0.1)], obj="uncertain"))["object_status_decided"] is True


class TestPromotionP10:
    def _expert_label(self, w, art, obj):
        w["store"].append(annotation(art, obj=obj), **NOREFS)
        w["store"].append(expert(art, obj=obj), **NOREFS)

    def test_expert_reproduction_is_never_promoted(self, world):
        art = world["arts"][0]
        self._expert_label(world, art, "reproduction")
        p = plan(world)
        assert not p.candidates
        assert any("P10" in r and "reproduction" in r for rej in p.rejections for r in rej.reasons)

    def test_expert_uncertain_object_status_is_not_promoted(self, world):
        art = world["arts"][0]
        self._expert_label(world, art, "uncertain")
        assert not plan(world).candidates

    def test_flagged_artifact_needs_explicit_original(self, world):
        art = world["arts"][0]
        self._expert_label(world, art, "unknown")
        p = plan(world, config=_flag_config(art))
        assert not p.candidates
        assert any("REVIEW REQUIRED" in r for rej in p.rejections for r in rej.reasons)

    def test_flagged_artifact_stated_original_can_be_a_candidate(self, world):
        art = world["arts"][0]
        self._expert_label(world, art, "original")
        assert [c.artifact_id for c in plan(world, config=_flag_config(art)).candidates] == [art]

    def test_duplicate_inscription_flag_alone_does_not_block(self, world):
        art = world["arts"][0]
        self._expert_label(world, art, "unknown")
        cfg = _flag_config(art, kind="possible_duplicate_inscription")
        assert [c.artifact_id for c in plan(world, config=cfg).candidates] == [art]

    def test_unflagged_unknown_status_keeps_existing_behaviour(self, world):
        art = world["arts"][0]
        self._expert_label(world, art, "unknown")
        assert [c.artifact_id for c in plan(world).candidates] == [art]


class TestAIDraftQuarantine:
    def _ai(self, art, prov="ai_prediction"):
        a = annotation(art, who="ai_draft_model", prov="project_annotation" if prov != "ai_prediction" else prov,
                       script="uncertain")
        a["notes"] = "AI-PREPARED DRAFT: synthetic"
        return a

    def test_n15_refuses_ai_output_under_a_human_tier(self, world):
        art = world["arts"][0]
        with pytest.raises(AnnotationRejected, match="N15"):
            world["store"].append(self._ai(art, prov="project_annotation"), **NOREFS)
        marked = annotation(art, who="SYN_human")
        marked["notes"] = "copied from AI DRAFT — NOT HUMAN EVIDENCE"
        assert any(p.rule == "N15" for p in validate_annotation(marked))

    def test_ai_prediction_is_stored_but_never_a_label(self, world):
        art = world["arts"][0]
        world["store"].append(self._ai(art), **NOREFS)
        p = plan(world, artifact_ids=[art])
        assert not p.candidates and "AI prediction" in p.rejections[0].reasons[0]

    def test_human_record_is_not_ai_marked(self):
        assert not is_ai_marked(annotation("A_X"))

    def test_load_ai_draft_refuses_mislabelled_records(self, tmp_path):
        f = tmp_path / "draft.jsonl"
        f.write_text(json.dumps(annotation("A_X", who="ai_x")) + "\n", encoding="utf-8")
        with pytest.raises(ValueError, match="ai_prediction"):
            load_ai_draft(f)
        assert load_ai_draft(tmp_path / "absent.jsonl") == {}

    def test_warning_text(self):
        assert AI_DRAFT_WARNING.startswith("AI-generated observation. Not archaeological evidence.")


class TestIndependentWorksheets:
    def test_worksheets_prefill_only_provenance(self, tmp_path, live_research):
        if not live_research["records"]:
            pytest.skip("no research records")
        pack = build_handoff(live_research["records"], tmp_path)
        for name in ("pilot_worksheet_project_annotator.csv", "pilot_worksheet_expert.csv"):
            with (tmp_path / name).open(encoding="utf-8-sig", newline="") as fh:
                rows = list(csv.DictReader(fh))
            assert len(rows) == 6
            for r in rows:
                filled = {k for k, v in r.items() if v}
                assert filled <= PROVENANCE_COLUMNS, f"{name}: judgement prefilled: {filled - PROVENANCE_COLUMNS}"
                assert "ai_" not in json.dumps(r)
        assert not (tmp_path / "ai_draft_annotations.jsonl").exists()
        assert pack.photos == 6

    def test_worksheet_asks_object_status_and_unknown_script(self):
        cols = " ".join(ANNOTATION_COLUMNS)
        assert "object_status (original/reproduction/uncertain/unknown)" in cols
        assert "unknown)" in next(c for c in ANNOTATION_COLUMNS if c.startswith("script_type"))


class TestExtendedAgreement:
    def test_object_status_and_dating_range_disagreements_are_listed(self, world):
        a, b = world["arts"][:2]
        world["store"].append(annotation(a, obj="original", dating=(-300, -100, "palaeography")), **NOREFS)
        world["store"].append(expert(a, obj="reproduction", dating=(-200, 100, "palaeography")), **NOREFS)
        world["store"].append(annotation(b, obj="uncertain", dating=(-300, -200, "palaeography")), **NOREFS)
        world["store"].append(expert(b, obj="uncertain", dating=(100, 200, "palaeography")), **NOREFS)
        rep = compute_agreement(world["store"].current(), [a, b])
        assert rep.fields["object_status"].disagreements == [{"artifact_id": a, "a": "original", "b": "reproduction"}]
        rel = {k: v["relation"] for k, v in rep.fields["dating_range"].per_artifact.items()}
        assert rel == {a: "overlapping", b: "disjoint"}
        assert rep.fields["dating_range"].items_agreeing == 0           # overlap is not agreement
        assert "object_status" in rep.items[a]["disagree"] and "dating_range" in rep.items[b]["disagree"]

    def test_undetermined_fields_are_reported_per_item(self, world):
        art = world["arts"][0]
        world["store"].append(annotation(art, obj="unknown"), **NOREFS)
        world["store"].append(expert(art), **NOREFS)
        rep = compute_agreement(world["store"].current(), [art])
        assert "object_status" in rep.items[art]["undetermined"]

    def test_small_sample_kappa_value_is_withheld_in_text(self, world):
        for art, (p, e) in zip(world["arts"], [("graffiti", "graffiti"), ("none", "none"), ("graffiti", "none"),
                                                ("tamil_brahmi", "tamil_brahmi"), ("none", "none"),
                                                ("graffiti", "graffiti")]):
            world["store"].append(annotation(art, script=p), **NOREFS)
            world["store"].append(expert(art, script=e), **NOREFS)
        text = render_agreement(compute_agreement(world["store"].current(), world["arts"]))
        lines = text.splitlines()
        line = lines[lines.index(next(x for x in lines if x.startswith("script_type"))) + 1]
        assert "withheld" in line and "not interpretable" in line and "n=6 < 30" in line
        assert "0.7" not in line                                   # the kappa value itself is not printed
        assert "ITEM-LEVEL REVIEW" in text


class TestLivePilotFlagsAndClaims:
    def test_107_and_109_are_flagged_unconfirmed_and_remain_separate_artifacts(self, live_research):
        flags = load_review_flags()
        for art, related in (("WMC_KEELADI_MUS_SHERD_107", "WMC_KEELADI_MUS_SHERD_106"),
                             ("WMC_KEELADI_MUS_SHERD_109", "WMC_KEELADI_MUS_SHERD_108")):
            [f] = flags[art]
            assert f.kind == "possible_reproduction" and f.related_artifact == related
            assert f.label == "REVIEW REQUIRED — possible reproduction / duplicate inscription"
            assert f.confirmed is False
            if live_research["records"]:
                assert art in live_research["artifacts"]                  # identity unchanged
        assert set(flags) <= set(load_pilot().artifacts)

    def test_claim_report_lists_unresolved_r3_r5_and_nothing_verified(self):
        rows = claim_report()
        by_ref = {r["ref_id"] for r in rows}
        assert {"R1", "S01", "S03", "R3", "R5"} <= by_ref
        for r in rows:
            if r["ref_id"] in ("R3", "R5"):
                assert r["expected_publication"].startswith(UNRESOLVED_REF)
        # Live registry: until a human verifier commits a check, every claim is unverified.
        from src.knowledge.verification import VerificationRegistry

        if not VerificationRegistry().all():
            assert {r["verification_status"] for r in rows} == {"unverified"}
