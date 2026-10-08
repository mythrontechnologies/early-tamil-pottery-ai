"""Milestone 11: software source pre-checks, expert adjudication, glyph regions, reading
completeness, the worksheet round trip, the annotation queue, the field-level disagreement
report, export, and the second acquisition pass.

Every annotation and registry record written here is SYNTHETIC test data in pytest's tmp_path.
Tests that touch the live project only READ it.
"""

from __future__ import annotations

import csv
import hashlib
import json
from copy import deepcopy
from datetime import date

import pytest
from test_expert_pilot import QUAL, annotation, expert, plan

from src.annotation.handoff import ANNOTATION_COLUMNS, EXPERT_COLUMNS, PRECHECK_COLUMNS, build_handoff
from src.annotation.resolve import resolve_artifact
from src.annotation.store import AnnotationRejected
from src.annotation.validate import validate_annotation, validate_annotations
from src.annotation.worksheet import (
    annotation_queue,
    build_worksheets,
    commit_worksheet,
    disagreement_report,
    export_annotations,
    import_worksheet,
    parse_dating_evidence,
    parse_regions,
)
from src.dataset.schema import ROOT
from src.knowledge.base import default_kb
from src.knowledge.precheck import (
    PRECHECK_PATH,
    load_prechecks,
    validate_prechecks,
    verification_from_precheck,
)
from src.knowledge.verification import VerificationRegistry, effective_statuses, verified_ref_ids

TODAY = date(2026, 10, 8)


# --------------------------------------------------------------------------- #
# Software pre-checks: useful pointers, never verification
# --------------------------------------------------------------------------- #


class TestPrechecks:
    def test_live_registry_is_valid_and_software_only(self):
        pre = load_prechecks(today=TODAY)
        assert pre.ok, pre.problems
        assert pre.data["checked_by"] == "software_agent" and pre.data["effect"] == "none"
        assert {c["ref_id"] for c in pre.claim_checks} == {"R1", "S01", "S03"}

    def test_prechecks_change_no_status(self):
        # The registry is empty: every key reference keeps its knowledge-base status, nothing is verified.
        eff = effective_statuses()
        assert {k: eff[k].effective_status for k in ("R1", "S01", "S03")} == {
            "R1": "bibliographic_only", "S01": "transcribed_unverified", "S03": "transcribed_unverified"}
        assert verified_ref_ids() == set()

    def _live(self) -> dict:
        return json.loads(PRECHECK_PATH.read_text(encoding="utf-8"))

    def test_schema_refuses_a_human_or_an_effect(self):
        for key, value in (("checked_by", "project_member"), ("effect", "verifies")):
            data = self._live() | {key: value}
            assert any(p.startswith("PC1") for p in validate_prechecks(data, today=TODAY))

    def test_a_claim_cannot_be_found_in_a_catalogue(self):
        data = self._live()
        pc = next(c for c in data["claim_checks"] if c["precheck_id"] == "PC-R1-01")
        pc.update(finding="found_as_stated", locator_found="p. 1", excerpt="SYNTHETIC")
        assert any(p.startswith("PC6 PC-R1-01") for p in validate_prechecks(data, today=TODAY))

    def test_no_claim_found_in_an_unresolved_placeholder(self):
        data = self._live()
        data["claim_checks"].append({"precheck_id": "PC-R5-01", "ref_id": "R5",
                                     "claim_id": "config:chronology.position_D", "source_id": "SRC-R5C-DAI",
                                     "check_date": "2026-10-08", "finding": "found_as_stated",
                                     "locator_found": "p. 45", "excerpt": "SYNTHETIC", "notes": "-"})
        assert any(p.startswith("PC7 PC-R5-01") for p in validate_prechecks(data, today=TODAY))

    def test_claim_must_cite_the_reference_and_found_needs_excerpt(self):
        data = self._live()
        pc = next(c for c in data["claim_checks"] if c["precheck_id"] == "PC-S03-02")
        pc["claim_id"] = "kodumanal.assertions[0]"      # cites S01, not S03
        del pc["excerpt"]
        probs = validate_prechecks(data, today=TODAY)
        assert any(p.startswith("PC3 PC-S03-02") for p in probs)
        assert any(p.startswith("PC5 PC-S03-02") for p in probs)

    def test_future_dates_refused(self):
        data = self._live()
        data["claim_checks"][0]["check_date"] = "2099-01-01"
        assert any(p.startswith("PC8") for p in validate_prechecks(data, today=TODAY))

    def test_verification_from_precheck_needs_the_publication(self):
        with pytest.raises(ValueError, match="publication itself"):
            verification_from_precheck("PC-R1-01", verifier="SYN_person", verifier_role="project_member",
                                       verification_date="2026-10-08")

    def test_verification_from_precheck_is_a_human_record_validated_by_the_registry(self, tmp_path):
        rec = verification_from_precheck("PC-S03-02", verifier="SYN_person", verifier_role="project_member",
                                         verification_date="2026-10-08")
        assert rec["verifier"] == "SYN_person" and rec["source_access"] == "open_access_publication"
        assert rec["locator"] == "p. 58; pp. 62-63" and "software pre-check PC-S03-02" in rec["notes"]
        reg = VerificationRegistry(tmp_path / "reg.jsonl")
        reg.append(rec, today=TODAY)                      # V1-V10 accept it: a named human, a real copy
        assert reg.current()[0]["status"] == "verified_against_source"

    def test_cli_refuses_without_the_human_attestation(self, capsys):
        from src.knowledge.__main__ import main

        assert main(["verify-from-precheck", "PC-S03-02", "--verifier", "SYN_person", "--role",
                     "project_member", "--date", "2026-10-08"]) == 1
        assert "HUMAN check" in capsys.readouterr().out

    def test_claim_report_and_checklist_carry_the_precheck_label(self, tmp_path, capsys, live_research):
        from src.knowledge.__main__ import main

        assert main(["claim-report", "--ref", "S03", "--json"]) == 0
        rows = json.loads(capsys.readouterr().out)
        assert all(r["precheck"] and "NOT VERIFICATION" in r["precheck"]["label"] for r in rows)
        assert all(r["verification_status"] == "unverified" for r in rows)
        build_handoff(live_research["records"], tmp_path)
        with (tmp_path / "verification_checklist.csv").open(encoding="utf-8-sig", newline="") as fh:
            rows = list(csv.DictReader(fh))
        assert set(PRECHECK_COLUMNS) <= set(rows[0])
        s03 = [r for r in rows if r["ref_id"] == "S03"]
        assert all(r[PRECHECK_COLUMNS[2]].startswith("https://heritageuniversityofkerala.com/") for r in s03)
        assert all(r["status (verified_against_source/discrepancy_found/source_unavailable)"] == "" for r in rows)

    def test_fig17_transcription_keeps_every_printed_spelling(self):
        e = default_kb().entries["s03_keeladi_fig17"]
        assert e["reading_as_printed"] == "ce n ta n a va (ta) thi"
        assert len(e["alternative_readings_as_printed"]) == 2
        assert e["verification_status"] == "transcribed_unverified"
        assert "name of an individual" in e["interpretation_as_printed"]


# --------------------------------------------------------------------------- #
# Expert adjudication (schema 1.2.0, rule N18)
# --------------------------------------------------------------------------- #


def adjudicator(art, resolves, *, script="graffiti", outcome="decided", who="SYN_adjudicator", **kw):
    a = expert(art, who=who, script=script, **kw)
    a["adjudication"] = {"resolves": list(resolves), "outcome": outcome,
                         "basis": "SYNTHETIC: compared both annotations against the photograph"}
    return a


def _disputed(w):
    art = w["arts"][0]
    e1 = w["store"].append(expert(art, who="SYN_expert_a", script="tamil_brahmi"), **_norefs())
    e2 = w["store"].append(expert(art, who="SYN_expert_b", script="graffiti"), **_norefs())
    return art, e1, e2


def _norefs():
    return {"knowledge_ref_ids": set(), "verified_ref_ids": set()}


class TestAdjudication:
    def test_disagreeing_experts_are_disputed_until_adjudicated(self, world):
        art, e1, e2 = _disputed(world)
        assert resolve_artifact(art, world["store"].current()).status == "disputed"
        adj = world["store"].append(adjudicator(art, [e1["annotation_id"], e2["annotation_id"]]), **_norefs())
        res = resolve_artifact(art, world["store"].current())
        assert (res.status, res.label, res.ground_truth_eligible) == ("adjudicated", "graffiti", True)
        assert res.adjudication_id == adj["annotation_id"]
        assert res.disagreements["script_type"]              # the disagreement is preserved, not erased

    def test_adjudicated_label_is_promoted_from_the_adjudication_only(self, world):
        art, e1, e2 = _disputed(world)
        adj = world["store"].append(adjudicator(art, [e1["annotation_id"], e2["annotation_id"]]), **_norefs())
        p = plan(world, artifact_ids=[art])
        assert [c.artifact_id for c in p.candidates] == [art]
        c = p.candidates[0]
        assert c.label == "graffiti" and c.source_annotation_ids == [adj["annotation_id"]]
        assert "expert adjudication resolving" in c.changes[0].after["notes"]

    def test_a_later_annotation_makes_the_adjudication_stale(self, world):
        art, e1, e2 = _disputed(world)
        world["store"].append(adjudicator(art, [e1["annotation_id"], e2["annotation_id"]]), **_norefs())
        world["store"].append(expert(art, who="SYN_expert_c", script="tamil_brahmi"), **_norefs())
        res = resolve_artifact(art, world["store"].current())
        assert res.status == "disputed" and "new adjudication" in res.notes[0]
        assert not plan(world, artifact_ids=[art]).candidates

    def test_insufficient_evidence_is_uncertain_not_a_guess(self, world):
        art, e1, e2 = _disputed(world)
        bad = adjudicator(art, [e1["annotation_id"], e2["annotation_id"]], outcome="insufficient_evidence")
        assert any(p.rule == "N18" for p in validate_annotation(bad))
        ok = adjudicator(art, [e1["annotation_id"], e2["annotation_id"]], script="uncertain",
                         outcome="insufficient_evidence")
        world["store"].append(ok, **_norefs())
        assert resolve_artifact(art, world["store"].current()).label == "uncertain"

    def test_only_a_reviewed_qualified_expert_adjudicates(self):
        a = annotation("A_X", who="SYN_project")
        a["adjudication"] = {"resolves": ["ann_" + "1" * 16, "ann_" + "2" * 16], "outcome": "decided",
                             "basis": "SYNTHETIC"}
        assert any(p.rule == "N18" for p in validate_annotation(a))
        b = adjudicator("A_X", ["ann_" + "1" * 16, "ann_" + "2" * 16])
        b["annotator"].pop("qualification")
        assert any(p.rule == "N18" for p in validate_annotation(b))
        c = adjudicator("A_X", ["ann_" + "1" * 16, "ann_" + "2" * 16])
        c["adjudication"]["resolves"].append(c["annotation_id"])
        assert any("itself" in p.message for p in validate_annotation(c))

    def test_adjudication_cannot_resolve_ai_or_unknown_or_foreign_annotations(self):
        ai = annotation("A_X", who="ai_model_v0", prov="ai_prediction")
        other = annotation("A_Y", who="SYN_project")
        adj = adjudicator("A_X", [ai["annotation_id"], other["annotation_id"], "ann_" + "f" * 16])
        msgs = [p.message for p in validate_annotations([ai, other, adj]).problems if p.rule == "N18"]
        assert any("AI prediction" in m for m in msgs)
        assert any("another artifact" in m for m in msgs)
        assert any("unknown annotation" in m for m in msgs)


# --------------------------------------------------------------------------- #
# Glyph regions (N19) and reading completeness (N20)
# --------------------------------------------------------------------------- #


def _char(i, sign=None, label="character", x=0.1):
    r = {"image_id": "A_X__1", "x": x, "y": 0.1, "width": 0.05, "height": 0.05, "label": label}
    if sign is not None:
        r["sign_index"] = sign
    return r


class TestGlyphsAndCompleteness:
    def test_character_regions_need_unique_sign_indices(self):
        a = annotation("A_X")
        a["inscription"]["regions"] = [_char(0)]
        assert any(p.rule == "N19" for p in validate_annotation(a))
        a["inscription"]["regions"] = [_char(0, 1), _char(1, 1, x=0.3)]
        assert any("used twice" in p.message for p in validate_annotation(a))
        a["inscription"]["regions"] = [_char(0, 1), {**_char(1, 2, x=0.3), "sign_reading": "?"}]
        assert not [p for p in validate_annotation(a) if p.rule == "N19"]

    def test_only_character_regions_carry_signs(self):
        a = annotation("A_X")
        a["inscription"]["regions"] = [_char(0, 1, label="inscription")]
        assert any(p.rule == "N19" for p in validate_annotation(a))

    def test_completeness_matches_the_reading(self):
        a = annotation("A_X", reading="SYNTHETIC-READING")
        a["inscription"]["reading_completeness"] = "illegible"
        assert any(p.rule == "N20" for p in validate_annotation(a))
        b = annotation("A_X")
        b["inscription"]["reading_completeness"] = "partial"
        assert any(p.rule == "N20" for p in validate_annotation(b))
        a["inscription"]["reading_completeness"] = "partial"
        assert not [p for p in validate_annotation(a) if p.rule == "N20"]

    def test_promoted_character_region_keeps_its_sign_as_a_note(self, world):
        art = world["arts"][1]
        e = expert(art)
        e["inscription"]["regions"] = [{"image_id": f"{art}__1", "x": 0.1, "y": 0.1, "width": 0.1, "height": 0.1,
                                        "label": "character", "sign_index": 1, "sign_reading": "?"}]
        world["store"].append(e, **_norefs())
        c = plan(world, artifact_ids=[art]).candidates[0]
        reg = c.changes[0].after["inscription_regions"][0]
        assert reg["region_label"] == "other" and "sign 1" in reg["notes"]


# --------------------------------------------------------------------------- #
# Worksheet round trip, queue, disagreement report, export
# --------------------------------------------------------------------------- #


def _header_key(header: list[str], name: str) -> str:
    return next(h for h in header if h.split(" (")[0] == name)


def _fill(path, rows_by_image: dict[str, dict[str, str]]):
    with path.open(encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        header, rows = list(reader.fieldnames), list(reader)
    for r in rows:
        for k, v in rows_by_image.get(r["image_id"], {}).items():
            r[_header_key(header, k)] = v
    with path.open("w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=header)
        w.writeheader()
        w.writerows(rows)
    return path


GOOD = {"annotator_id": "SYN_project", "object_status": "original", "inscription_present": "yes",
        "script_type": "graffiti", "script_confidence": "low", "regions": "0.1,0.2,0.3,0.2 graffiti",
        "usable_for_annotation": "yes", "uncertainty_notes": "SYNTHETIC worksheet answer"}


class TestWorksheets:
    def test_blank_worksheets_cover_every_photo_and_assert_nothing(self, world):
        files = build_worksheets(world["records"], world["tmp"] / "ws")
        with files[1].open(encoding="utf-8-sig", newline="") as fh:
            rows = list(csv.DictReader(fh))
        assert len(rows) == 6
        judgement = [c for c in list(EXPERT_COLUMNS) + list(ANNOTATION_COLUMNS)]
        assert all(not r[c] for r in rows for c in judgement)

    def test_round_trip_dry_run_then_commit(self, world):
        ws = build_worksheets(world["records"], world["tmp"] / "ws")[0]
        img = world["records"][0]["image_id"]
        _fill(ws, {img: GOOD})
        imp = import_worksheet(ws, "project", world["store"], kb_refs={})
        assert imp.ok, imp.problems
        assert imp.skipped_rows == 5 and len(imp.annotations) == 1
        a = imp.annotations[0]
        assert a["provenance_type"] == "project_annotation" and a["review_state"] == "unreviewed"
        assert a["inscription"]["regions"][0]["label"] == "graffiti"
        assert not world["store"].all()                     # dry run wrote nothing
        assert commit_worksheet(imp, world["store"]) == 1
        assert resolve_artifact(a["artifact_id"], world["store"].current()).status == "provisional"

    def test_existing_annotation_needs_revise(self, world):
        ws = build_worksheets(world["records"], world["tmp"] / "ws")[0]
        img = world["records"][0]["image_id"]
        _fill(ws, {img: GOOD})
        commit_worksheet(import_worksheet(ws, "project", world["store"], kb_refs={}), world["store"])
        again = import_worksheet(ws, "project", world["store"], kb_refs={})
        assert not again.ok and "--revise" in again.problems[0]
        rev = import_worksheet(ws, "project", world["store"], kb_refs={}, revise=True)
        assert rev.ok and rev.annotations[0]["supersedes"]

    def test_all_or_nothing(self, world):
        ws = build_worksheets(world["records"], world["tmp"] / "ws")[0]
        r0, r1 = world["records"][0]["image_id"], world["records"][1]["image_id"]
        _fill(ws, {r0: GOOD, r1: {**GOOD, "dating_range": "-300..-100"}})   # a range without evidence (N9)
        imp = import_worksheet(ws, "project", world["store"], kb_refs={})
        assert not imp.ok and any("N9" in p for p in imp.problems)
        with pytest.raises(AnnotationRejected):
            commit_worksheet(imp, world["store"])
        assert not world["store"].all()

    def test_project_worksheet_cannot_claim_expert_review(self, world):
        ws = build_worksheets(world["records"], world["tmp"] / "ws")[1]          # expert layout
        img = world["records"][0]["image_id"]
        _fill(ws, {img: {**GOOD, "review_state": "expert_reviewed"}})
        imp = import_worksheet(ws, "project", world["store"], kb_refs={})
        assert any("cannot set review_state" in p for p in imp.problems)
        exp = import_worksheet(ws, "expert", world["store"], kb_refs={})
        assert exp.ok and exp.annotations[0]["review_state"] == "expert_reviewed"

    def test_parsers(self):
        regs, note = parse_regions("0.1,0.1,0.2,0.2 character #1 'ka'; 0.4,0.1,0.2,0.2 character #2", "I")
        assert note is None and regs[0]["sign_reading"] == "ka" and regs[1]["sign_index"] == 2
        assert parse_regions("upper left, near the rim", "I") == ([], "upper left, near the rim")
        ev = parse_dating_evidence("stratigraphy; SYNTHETIC layer; -200..-100; S03", "context only")
        assert ev[0]["association"] == "same_context_insecure" and ev[0]["confidence"] == "unknown"
        with pytest.raises(ValueError):
            parse_dating_evidence("vibes; looks old; -500..-400; me", "object")

    def test_queue_and_disagreement_report(self, world):
        art = world["arts"][0]
        world["store"].append(annotation(art, who="SYN_p1", script="tamil_brahmi"), **_norefs())
        world["store"].append(annotation(art, who="SYN_p2", script="graffiti"), **_norefs())
        rows = annotation_queue(world["records"], world["store"].current(), (world["arts"][2],))
        assert rows[0].artifact_id == world["arts"][2] and rows[0].in_pilot
        mine = next(r for r in rows if r.artifact_id == art)
        assert mine.status == "project_disagreement" and "expert_annotation" in mine.missing_tiers
        rep = disagreement_report([art], world["store"].current())[0]
        assert "script_type" in rep["disagreeing_fields"] and not rep["expert_reviewed"]
        assert rep["fields"]["reading"]["state"] == "not assessed"     # nobody read it: not a disagreement

    def test_export_labels_every_tier(self, world):
        art = world["arts"][0]
        world["store"].append(annotation(art), **_norefs())
        world["store"].append(annotation(art, who="ai_model_v0", prov="ai_prediction"), **_norefs())
        jl, cs = export_annotations(world["store"].current(), world["tmp"] / "export")
        with cs.open(encoding="utf-8-sig", newline="") as fh:
            rows = list(csv.DictReader(fh))
        assert {r["provenance_tier"] for r in rows} == {"project_annotation", "ai_prediction"}
        assert {r["is_ai_output"] for r in rows if r["provenance_tier"] == "ai_prediction"} == {"True"}
        assert len(jl.read_text(encoding="utf-8").splitlines()) == 2


# --------------------------------------------------------------------------- #
# Second acquisition pass (live data, read-only)
# --------------------------------------------------------------------------- #


class TestMilestone11Acquisition:
    def test_new_records_are_unlabelled_licensed_and_hashed(self, live_research):
        from src.acquisition.provenance import read_registry

        prov = {p["image_id"]: p for p in read_registry()}
        new = [r for r in live_research["records"] if r["artifact_id"].startswith("WMC_GMC_ADICHANALLUR_")]
        assert len(new) == 4 and len({r["artifact_id"] for r in new}) == 4
        for r in new:
            assert (r["script_type"], r["inscription_present"], r["label_source"]) == ("unknown",) * 3
            assert r["dating_lower_year"] is None and r["dating_text"] == "not_available"   # caption date not copied
            p = prov[r["image_id"]]
            assert p["license"] == "CC-BY-3.0" and "Sailko" in p["attribution_text"]
            assert p["dataset_id"] == "wmc_tamil_nadu_pottery_m11"
            path = ROOT / "data" / "raw" / r["image_path"]
            if path.exists():
                assert hashlib.sha256(path.read_bytes()).hexdigest() == r["image_sha256"]

    def test_plan_lists_no_licence_and_no_label(self):
        import yaml

        plan_ = yaml.safe_load((ROOT / "configs/acquisition/milestone11_wikimedia_commons.yaml")
                               .read_text(encoding="utf-8"))
        text = json.dumps(plan_)
        assert "CC-BY" not in text and "license" not in text.lower().replace("licences", "")
        for item in plan_["datasets"][0]["items"]:
            assert "NOT A LABEL" in item["curation_note"]
            assert "script_type" not in item.get("record", {})


def test_qual_fixture_is_synthetic():
    assert "SYNTHETIC" in QUAL and deepcopy(GOOD)["annotator_id"].startswith("SYN")


# --------------------------------------------------------------------------- #
# Near-duplicate leakage across artifacts (split refusal)
# --------------------------------------------------------------------------- #


def _textured(path, seed: int, size: int = 160):
    import random

    from PIL import Image, ImageDraw

    rnd = random.Random(seed)
    im = Image.new("RGB", (size, size), (rnd.randrange(256), 120, 90))
    d = ImageDraw.Draw(im)
    for _ in range(25):
        x, y = rnd.randrange(size), rnd.randrange(size)
        d.rectangle([x, y, x + rnd.randrange(10, 60), y + rnd.randrange(10, 60)], fill=(rnd.randrange(256),) * 3)
    im.save(path)
    return path


class TestNearDuplicates:
    def test_resized_copy_under_another_artifact_is_found(self, tmp_path):
        from PIL import Image

        from src.dataset.near_duplicates import find_near_duplicates

        a = _textured(tmp_path / "a.png", 1)
        b = tmp_path / "b.jpg"
        Image.open(a).resize((120, 120)).save(b, quality=70)          # different bytes, same picture
        c = _textured(tmp_path / "c.png", 2)
        pairs, skipped = find_near_duplicates([("IMG_A", "ART_1", a), ("IMG_B", "ART_2", b), ("IMG_C", "ART_3", c)])
        assert [(p.image_a, p.image_b) for p in pairs] == [("IMG_A", "IMG_B")] and not skipped
        assert not find_near_duplicates([("IMG_A", "ART_1", a), ("IMG_B", "ART_1", b)])[0]   # same artifact: fine

    def test_a_human_exception_clears_a_pair(self, tmp_path):
        from PIL import Image

        from src.dataset.near_duplicates import find_near_duplicates

        a = _textured(tmp_path / "a.png", 3)
        b = tmp_path / "b.png"
        Image.open(a).save(b)
        pairs, _ = find_near_duplicates([("IMG_A", "ART_1", a), ("IMG_B", "ART_2", b)],
                                        allowed={frozenset(("ART_1", "ART_2"))})
        assert pairs == []

    def test_featureless_images_are_not_compared(self, tmp_path):
        from PIL import Image

        from src.dataset.near_duplicates import find_near_duplicates

        for n in (1, 2):
            Image.new("RGB", (40, 40), (90, 90, 90)).save(tmp_path / f"f{n}.png")
        pairs, skipped = find_near_duplicates([("F1", "ART_1", tmp_path / "f1.png"), ("F2", "ART_2", tmp_path / "f2.png")])
        assert pairs == [] and all("featureless" in s for s in skipped)

    def test_split_refuses_near_duplicates(self, tmp_path, synthetic_corpus):
        from PIL import Image

        from src.dataset.classes import ClassSpec
        from src.dataset.loader import load_dataset
        from src.dataset.splits import SplitSettings, check_splittable

        c = synthetic_corpus(tmp_path, {"tamil_brahmi": 5, "graffiti": 5, "none": 5, "uncertain": 5})
        recs = c["records"]
        _textured(c["data_root"] / recs[0]["image_path"], 7)
        Image.open(c["data_root"] / recs[0]["image_path"]).resize((38, 38)).resize((40, 40)).save(
            c["data_root"] / recs[1]["image_path"])
        for r in recs[:2]:
            r["image_sha256"] = hashlib.sha256((c["data_root"] / r["image_path"]).read_bytes()).hexdigest()
        c["records_path"].write_text("".join(json.dumps(r) + "\n" for r in recs), encoding="utf-8")
        ds = load_dataset(c["records_path"], c["data_root"])
        _, problems = check_splittable(ds, ClassSpec.from_config(), SplitSettings.from_config(), "grouped_kfold")
        assert any("near-duplicate photographs across artifacts" in p for p in problems)


# --------------------------------------------------------------------------- #
# Real-data evaluation tasks (pure functions; the CLI is gated)
# --------------------------------------------------------------------------- #


class TestEvaluationTasks:
    def test_detection_iou_matching(self):
        from src.evaluation.tasks import detection_report

        gt = {"I1": [(0, 0, 10, 10)], "I2": [(0, 0, 10, 10), (50, 50, 10, 10)], "I3": []}
        pred = {"I1": [(1, 1, 10, 10)], "I2": [(0, 0, 10, 10)], "I3": [(5, 5, 5, 5)]}
        r = detection_report(gt, pred)["by_threshold"]["iou_0.5"]
        assert (r["true_positives"], r["false_positives"], r["false_negatives"]) == (2, 1, 1)
        assert r["images_with_missed_regions"] == ["I2"]
        strict = detection_report(gt, pred)["by_threshold"]["iou_0.75"]
        assert strict["true_positives"] == 1                      # the shifted box fails at 0.75

    def test_ocr_excludes_illegible_and_buckets_failures(self):
        from src.evaluation.tasks import ocr_report

        r = ocr_report([("sathan", "sathan"), ("eravathan", "eravatan"), ("visaki", None), ("xx", "abcdef")],
                       illegible=[False, False, False, True])
        assert r["references"] == 3 and r["excluded_illegible"] == 1
        assert r["failures"] == {"exact": 1, "partial": 1, "wrong": 0, "no_output": 1}
        assert r["exact_reading_accuracy"] == pytest.approx(1 / 3)

    def test_error_analysis_ranks_confident_errors_first(self):
        import numpy as np

        from src.evaluation.tasks import error_analysis

        prob = np.array([[0.9, 0.1], [0.2, 0.8], [0.55, 0.45]])
        r = error_analysis(["A", "B", "C"], [1, 1, 1], prob, ["tamil_brahmi", "graffiti"])
        assert [e["artifact_id"] for e in r["errors"]] == ["A", "C"] and r["high_confidence_errors"] == 1

    def test_robustness_is_deterministic_and_reports_drop(self):
        import numpy as np
        from PIL import Image

        from src.evaluation.tasks import robustness_report

        imgs = [Image.new("RGB", (32, 32), (200, 200, 200)), Image.new("RGB", (32, 32), (20, 20, 20))]

        def predict(batch):          # "bright" -> class 0: a toy rule, exercised only to test the harness
            return np.array([[1.0, 0.0] if np.asarray(im).mean() > 100 else [0.0, 1.0] for im in batch])

        a = robustness_report(predict, imgs, [0, 1], ids=["X1", "X2"], evidence_tier="test_fixture")
        b = robustness_report(predict, imgs, [0, 1], ids=["X1", "X2"], evidence_tier="test_fixture")
        assert a == b and a["clean_accuracy"] == 1.0
        assert a["perturbations"]["exposure_0.5"]["drop_from_clean"] == 0.5     # the bright image goes dark
        assert {r["family"] for r in a["perturbations"].values()} >= {"lighting", "scale", "crop", "noise", "occlusion"}

    def test_unknown_evidence_tier_is_refused(self):
        from src.evaluation.tasks import detection_report

        with pytest.raises(ValueError):
            detection_report({}, {}, evidence_tier="probably_real")

    def test_detection_and_ocr_cli_are_blocked_without_expert_truth(self, tmp_path, capsys):
        from src.evaluation.__main__ import main

        pred = tmp_path / "p.jsonl"
        pred.write_text('{"image_id": "x", "regions": [[0, 0, 1, 1]]}\n', encoding="utf-8")
        assert main(["detection", "--predictions", str(pred)]) == 3
        assert main(["ocr", "--predictions", str(pred)]) == 3
        assert "EVALUATION BLOCKED" in capsys.readouterr().out


# --------------------------------------------------------------------------- #
# Conservative transcription outcomes (reading completeness in the reasoning)
# --------------------------------------------------------------------------- #


class TestReadingOutcomes:
    def _inputs(self, reading, completeness, itype="uncertain"):
        from src.reasoning.types import Attributed, InscriptionInput, ReasoningInputs

        rd = Attributed(reading, "expert_annotation", "low", "this_annotator", "ann_" + "a" * 16) if reading else \
            Attributed("not_available")
        return ReasoningInputs("SYN_ART", inscription=InscriptionInput(
            inscription_present=Attributed("yes", "expert_annotation", "moderate"),
            script_type=Attributed("tamil_brahmi", "expert_annotation", "moderate"),
            reading=rd, interpretation_type=Attributed(itype, "expert_annotation"),
            reading_completeness=completeness))

    def test_partial_reading_is_stated_and_never_completed(self):
        from src.reasoning.engine import PARTIAL, analyze_artifact, render_text

        r = analyze_artifact(self._inputs("sa[..]n", "partial"))
        assert PARTIAL in r.status_statements and r.reading["completeness"] == "partial"
        assert "[partial]" in render_text(r) and r.interpretation["state"] == "no_translation"

    def test_illegible_gives_no_transcription(self):
        from src.reasoning.engine import ILLEGIBLE, analyze_artifact

        r = analyze_artifact(self._inputs(None, "illegible"))
        assert ILLEGIBLE in r.status_statements and r.reading["value"] == "not_available"
        assert r.interpretation["state"] == "no_reading"

    def test_personal_name_has_no_literal_translation(self):
        from src.reasoning.engine import analyze_artifact
        from src.translation.interpret import PERSONAL_NAME

        r = analyze_artifact(self._inputs("sathan", "complete", itype="personal_name"))
        assert r.interpretation["state"] == "personal_name" and r.interpretation["meaning"] == PERSONAL_NAME


def test_csv_cells_cannot_run_as_spreadsheet_formulas(tmp_path):
    from src.annotation.handoff import _write, safe_cell

    assert safe_cell("=HYPERLINK(\"http://x\")") == "'=HYPERLINK(\"http://x\")"
    assert safe_cell("-300..-100") == "-300..-100"                      # signed years untouched
    out = _write(tmp_path / "x.csv", ["a"], [{"a": "@SUM(1)"}])
    assert "'@SUM(1)" in out.read_text(encoding="utf-8-sig")
