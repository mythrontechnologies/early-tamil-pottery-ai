"""Milestone 7: annotation schema, provenance separation, multiple annotators, review
states, regions, interpretation rules, dating evidence, references, quality separation,
and the annotation UI.

All annotations here are SYNTHETIC test data written to tmp_path. The real annotation
store is only ever read, to check nothing has been fabricated.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from src.annotation.form import (
    build_annotation,
    clean_evidence,
    crop_view,
    draw_regions,
)
from src.annotation.model import (
    ANNOTATIONS_PATH,
    blank_annotation,
    load_annotation_schema,
    pixels_to_region,
    region_to_pixels,
)
from src.annotation.quality import quality_report
from src.annotation.resolve import resolve_artifact
from src.annotation.store import AnnotationRejected, AnnotationStore
from src.annotation.validate import validate_annotation, validate_annotations
from src.dataset.schema import load_schema

ART, IMGS = "FIXTURE_ART_A", ["FIXTURE_ART_A__1", "FIXTURE_ART_A__2"]
ART_IMAGES = {ART: set(IMGS), "FIXTURE_ART_B": {"FIXTURE_ART_B__1"}}


def rules(a, **kw):
    return {p.rule for p in validate_annotation(a, artifact_images=ART_IMAGES, **kw)}


def ann(annotator="tester_a", prov="project_annotation", **kw):
    a = blank_annotation(ART, IMGS, annotator_id=annotator, provenance_type=prov, **kw)
    return a


def with_reading(a, reading="FIXTURE_READING", source="this_annotator"):
    a["inscription"].update(inscription_present="yes", script_type="tamil_brahmi",
                            script_confidence="low", reading=reading, reading_source=source,
                            reading_confidence="low")
    return a


@pytest.fixture
def store(tmp_path) -> AnnotationStore:
    records = tmp_path / "records.jsonl"
    records.write_text("".join(json.dumps({"artifact_id": a, "image_id": i}) + "\n"
                               for a, ims in ART_IMAGES.items() for i in sorted(ims)), encoding="utf-8")
    return AnnotationStore(tmp_path / "annotations.jsonl", records)


# --------------------------------------------------------------------------- #
# Schema
# --------------------------------------------------------------------------- #


class TestSchema:
    def test_blank_annotation_is_valid_and_asserts_nothing(self):
        a = ann()
        assert rules(a) == set()
        assert a["inscription"]["script_type"] == "unknown"
        assert a["inscription"]["inscription_present"] == "unknown"
        assert a["dating"]["estimated_start_year"] is None
        assert a["interpretation"]["translation"] == "not_available"

    def test_vocabularies_match_the_image_record_schema(self):
        img = load_schema()["properties"]
        an = load_annotation_schema()["properties"]
        assert an["inscription"]["properties"]["script_type"]["enum"] == img["script_type"]["enum"]
        assert an["object"]["properties"]["pottery_type"]["enum"] == img["pottery_type"]["enum"]

    def test_unknown_fields_rejected(self):
        a = ann()
        a["ground_truth"] = True
        assert "N1" in rules(a)

    def test_year_zero_rejected(self):
        a = ann()
        a["dating"]["estimated_start_year"] = 0
        assert "N1" in rules(a)

    def test_empty_strings_rejected(self):
        a = ann()
        a["object"]["fabric"] = ""
        assert "N1" in rules(a)


# --------------------------------------------------------------------------- #
# Provenance and review state
# --------------------------------------------------------------------------- #


class TestProvenance:
    def test_role_must_match_provenance(self):
        a = ann()
        a["annotator"]["role"] = "expert"
        assert "N4" in rules(a)

    def test_project_annotation_cannot_be_expert_reviewed(self):
        a = ann()
        a["review_state"] = "expert_reviewed"
        assert "N4" in rules(a)

    def test_expert_annotation_can_be_expert_reviewed(self):
        a = ann("expert_x", "expert_annotation", qualification="SYNTHETIC epigraphist")
        a["review_state"] = "expert_reviewed"
        assert "N4" not in rules(a)

    def test_ai_prediction_is_always_unreviewed(self):
        a = ann("model_v0", "ai_prediction")
        a["review_state"] = "project_reviewed"
        assert "N4" in rules(a)

    def test_source_information_must_cite(self):
        a = ann(prov="source_information")
        assert "N5" in rules(a)
        a["references"] = [{"ref_id": "S03", "citation": "SYNTHETIC", "verification_status": "unverified"}]
        assert "N5" not in rules(a)

    @pytest.mark.parametrize("state", ["unreviewed", "project_reviewed", "expert_reviewed", "disputed"])
    def test_review_states_exist(self, state):
        assert state in load_annotation_schema()["properties"]["review_state"]["enum"]


# --------------------------------------------------------------------------- #
# Inscription: unknown vs uncertain, regions
# --------------------------------------------------------------------------- #


class TestInscription:
    def test_unknown_presence_cannot_carry_a_script(self):
        a = ann()
        a["inscription"].update(script_type="tamil_brahmi", script_confidence="low")
        assert "N6" in rules(a)

    def test_uncertain_presence_may_carry_uncertain_script(self):
        a = ann()
        a["inscription"].update(inscription_present="uncertain", script_type="uncertain",
                                script_confidence="low")
        assert rules(a) == set()

    def test_absent_inscription_requires_none(self):
        a = ann()
        a["inscription"].update(inscription_present="no", script_type="tamil_brahmi", script_confidence="low")
        assert "N6" in rules(a)

    def test_asserted_script_needs_confidence(self):
        a = ann()
        a["inscription"].update(inscription_present="yes", script_type="graffiti")
        assert "N6" in rules(a)

    def test_region_must_be_on_an_examined_photo_and_inside(self):
        a = with_reading(ann())
        a["inscription"]["regions"] = [{"image_id": "OTHER", "x": 0.9, "y": 0.1, "width": 0.2,
                                        "height": 0.1, "label": "inscription"}]
        found = [p.message for p in validate_annotation(a, artifact_images=ART_IMAGES) if p.rule == "N3"]
        assert len(found) == 2

    def test_region_coordinates_are_normalised(self):
        a = with_reading(ann())
        a["inscription"]["regions"] = [{"image_id": IMGS[0], "x": 10, "y": 0, "width": 0.1,
                                        "height": 0.1, "label": "inscription"}]
        assert "N1" in rules(a)

    def test_region_pixel_round_trip(self):
        r = pixels_to_region(400, 300, 800, 200, 4000, 3000)
        assert r == {"x": 0.1, "y": 0.1, "width": 0.2, "height": 0.066667}
        assert region_to_pixels(r, 4000, 3000) == {"x": 400, "y": 300, "w": 800, "h": 200}

    def test_reading_needs_a_source(self):
        a = with_reading(ann(), source="not_available")
        assert "N7" in rules(a)

    def test_no_reading_no_interpretation(self):
        a = ann()
        a["interpretation"]["interpretation_type"] = "lexical_word"
        assert "N7" in rules(a)


# --------------------------------------------------------------------------- #
# Translation / meaning
# --------------------------------------------------------------------------- #


class TestTranslation:
    def test_personal_name_has_no_translation(self):
        a = with_reading(ann())
        a["interpretation"].update(interpretation_type="personal_name", translation="FIXTURE meaning",
                                   translation_source="this_annotator", translation_confidence="low")
        assert "N8" in rules(a)
        a["interpretation"].update(translation="not_applicable",
                                   meaning="Proper name; no literal translation established.")
        assert "N8" not in rules(a)

    def test_translation_requires_a_source(self):
        a = with_reading(ann())
        a["interpretation"].update(interpretation_type="lexical_word", translation="FIXTURE",
                                   translation_confidence="low")
        assert "N8" in rules(a)

    def test_symbol_cannot_be_translated(self):
        a = with_reading(ann())
        a["interpretation"].update(interpretation_type="symbol", translation="FIXTURE",
                                   translation_source="this_annotator", translation_confidence="low")
        assert "N8" in rules(a)


# --------------------------------------------------------------------------- #
# Dating evidence
# --------------------------------------------------------------------------- #


def evidence(eid="E1", etype="palaeography", lo=-200, hi=100, **kw):
    e = {"evidence_id": eid, "evidence_type": etype, "observation": "SYNTHETIC observation",
         "supports_start_year": lo, "supports_end_year": hi, "confidence": "low",
         "source_reference": "annotator_observation"}
    e.update(kw)
    return e


class TestDating:
    def test_range_without_evidence_rejected(self):
        a = ann()
        a["dating"].update(estimated_start_year=-200, estimated_end_year=100, dating_confidence="low",
                           dating_basis=["palaeography"])
        assert "N9" in rules(a)

    def test_range_with_evidence_accepted(self):
        a = ann()
        a["dating"].update(estimated_start_year=-200, estimated_end_year=100, dating_confidence="low",
                           dating_basis=["palaeography"], dating_evidence=[evidence()])
        assert rules(a) == set()

    def test_reversed_range_rejected(self):
        a = ann()
        a["dating"].update(estimated_start_year=100, estimated_end_year=-200, dating_confidence="low",
                           dating_basis=["palaeography"], dating_evidence=[evidence()])
        assert "N9" in rules(a)

    def test_year_zero_in_evidence_rejected(self):
        a = ann()
        a["dating"].update(dating_basis=["palaeography"], dating_evidence=[evidence(lo=0)])
        assert "N1" in rules(a)

    def test_sentinel_basis_with_confidence_rejected(self):
        a = ann()
        a["dating"]["dating_confidence"] = "moderate"
        assert "N9" in rules(a)

    def test_basis_must_match_evidence(self):
        a = ann()
        a["dating"].update(dating_basis=["stratigraphy"], dating_evidence=[evidence()])
        assert "N9" in rules(a)

    def test_stratigraphy_must_state_association(self):
        a = ann()
        a["dating"].update(dating_basis=["stratigraphy"], dating_evidence=[evidence(etype="stratigraphy")])
        assert "N9" in rules(a)

    def test_missing_evidence_means_unknown(self):
        d = ann()["dating"]
        assert d["dating_confidence"] == "unknown" and d["dating_basis"] == ["not_available"]


# --------------------------------------------------------------------------- #
# References
# --------------------------------------------------------------------------- #


class TestReferences:
    def test_unresolved_citation_rejected(self):
        a = with_reading(ann(), source="R99")
        assert "N10" in rules(a)

    def test_citation_resolves_to_annotation_reference(self):
        a = with_reading(ann(), source="R99")
        a["references"] = [{"ref_id": "R99", "citation": "SYNTHETIC", "verification_status": "unverified"}]
        assert "N10" not in rules(a)

    def test_citation_resolves_to_knowledge_base(self):
        a = with_reading(ann(), source="S03")
        assert "N10" not in rules(a, knowledge_ref_ids={"S03"})


# --------------------------------------------------------------------------- #
# Store: append-only, multiple annotators, revisions
# --------------------------------------------------------------------------- #


class TestStore:
    def test_append_and_read(self, store):
        store.append(ann(), knowledge_ref_ids=set())
        assert len(store.all()) == 1

    def test_invalid_annotation_is_not_written(self, store):
        a = ann()
        a["review_state"] = "expert_reviewed"
        with pytest.raises(AnnotationRejected):
            store.append(a, knowledge_ref_ids=set())
        assert store.all() == []

    def test_unknown_artifact_rejected(self, store):
        a = blank_annotation("NOT_AN_ARTIFACT", ["x"], annotator_id="t1")
        with pytest.raises(AnnotationRejected, match="N2"):
            store.append(a, knowledge_ref_ids=set())

    def test_two_annotators_coexist(self, store):
        store.append(ann("tester_a"), knowledge_ref_ids=set())
        store.append(ann("tester_b"), knowledge_ref_ids=set())
        assert len(store.current(ART)) == 2

    def test_revision_supersedes_without_deleting(self, store):
        first = store.append(ann("tester_a"), knowledge_ref_ids=set())
        store.append(ann("tester_a", supersedes=first["annotation_id"]), knowledge_ref_ids=set())
        assert len(store.all()) == 2 and len(store.current(ART)) == 1

    def test_cannot_supersede_another_annotator(self, store):
        first = store.append(ann("tester_a"), knowledge_ref_ids=set())
        with pytest.raises(AnnotationRejected, match="N11"):
            store.append(ann("tester_b", supersedes=first["annotation_id"]), knowledge_ref_ids=set())

    def test_store_never_rewrites_existing_lines(self, store):
        store.append(ann("tester_a"), knowledge_ref_ids=set())
        before = store.path.read_text(encoding="utf-8")
        store.append(ann("tester_b"), knowledge_ref_ids=set())
        assert store.path.read_text(encoding="utf-8").startswith(before)

    def test_duplicate_ids_detected(self):
        a = ann()
        assert any(p.rule == "N12" for p in validate_annotations([a, copy.deepcopy(a)]).problems)


# --------------------------------------------------------------------------- #
# Resolution / disagreement
# --------------------------------------------------------------------------- #


def scripted(annotator, prov, script, state="unreviewed"):
    a = ann(annotator, prov, qualification="SYNTHETIC" if prov == "expert_annotation" else None)
    if script == "uncertain":
        a["inscription"].update(inscription_present="uncertain", script_type="uncertain", script_confidence="low")
    elif script != "unknown":
        a["inscription"].update(inscription_present="yes", script_type=script, script_confidence="moderate")
    a["review_state"] = state
    return a


class TestResolution:
    def test_unannotated(self):
        assert resolve_artifact(ART, []).status == "unannotated"

    def test_ai_prediction_never_labels(self):
        r = resolve_artifact(ART, [scripted("model", "ai_prediction", "tamil_brahmi")])
        assert r.status == "unannotated" and r.label is None and len(r.ai_predictions) == 1

    def test_project_agreement_is_only_provisional(self):
        r = resolve_artifact(ART, [scripted("a", "project_annotation", "tamil_brahmi"),
                                   scripted("b", "project_annotation", "tamil_brahmi")])
        assert r.status == "provisional" and not r.ground_truth_eligible

    def test_brief_example_disagreement(self):
        """annotator A -> Tamil-Brahmi, B -> uncertain, expert -> Tamil-Brahmi."""
        anns = [scripted("a", "project_annotation", "tamil_brahmi"),
                scripted("b", "project_annotation", "uncertain"),
                scripted("expert", "expert_annotation", "tamil_brahmi", "expert_reviewed")]
        r = resolve_artifact(ART, anns)
        assert r.status == "expert_label" and r.label == "tamil_brahmi" and r.ground_truth_eligible
        assert r.disagreements["script_type"] == {"a": "tamil_brahmi", "b": "uncertain",
                                                  "expert": "tamil_brahmi"}

    def test_experts_disagreeing_is_disputed(self):
        r = resolve_artifact(ART, [scripted("e1", "expert_annotation", "tamil_brahmi", "expert_reviewed"),
                                   scripted("e2", "expert_annotation", "graffiti", "expert_reviewed")])
        assert r.status == "disputed" and not r.ground_truth_eligible

    def test_unreviewed_expert_is_not_ground_truth(self):
        r = resolve_artifact(ART, [scripted("e1", "expert_annotation", "tamil_brahmi")])
        assert not r.ground_truth_eligible


# --------------------------------------------------------------------------- #
# Form, quality separation, UI, live data
# --------------------------------------------------------------------------- #


class TestFormAndQuality:
    def test_empty_form_produces_blank_annotation(self):
        a = build_annotation({"artifact_id": ART, "image_ids": IMGS, "annotator_id": "t1"})
        assert rules(a) == set() and a["inscription"]["script_type"] == "unknown"

    def test_blank_evidence_rows_dropped_and_ids_assigned(self):
        ev = clean_evidence([{"observation": ""}, {"observation": "x", "evidence_type": "stratigraphy"}])
        assert [e["evidence_id"] for e in ev] == ["E1"] and ev[0]["association"] == "not_established"

    def test_personal_name_forces_no_translation(self):
        a = build_annotation({"artifact_id": ART, "image_ids": IMGS, "annotator_id": "t1",
                              "interpretation_type": "personal_name", "translation": "SYNTHETIC"})
        assert a["interpretation"]["translation"] == "not_applicable"

    def test_region_drawing_and_zoom_do_not_modify_the_original(self):
        from PIL import Image

        img = Image.new("RGB", (100, 80), (10, 20, 30))
        before = img.tobytes()
        region = {"image_id": "i", "x": 0.1, "y": 0.1, "width": 0.5, "height": 0.5, "label": "inscription"}
        drawn = draw_regions(img, [region], "i")
        assert img.tobytes() == before and drawn.tobytes() != before
        assert crop_view(img, 0.0, 0.5, 0.0, 0.5).size == (50, 40)

    def test_technical_quality_and_usability_are_separate(self, tmp_path):
        rec = {"image_id": IMGS[0], "artifact_id": ART, "image_sha256": "a" * 64}
        side = tmp_path / "p" / "x.json"
        side.parent.mkdir()
        side.write_text(json.dumps({"source": {"source_sha256": "a" * 64},
                                    "quality": {"flags": ["possibly_blurry"], "width_px": 10}}))
        a = ann()
        a["image_usability"] = [{"image_id": IMGS[0], "usable_for_annotation": "yes"}]
        [row] = quality_report([rec], [a], tmp_path / "p")
        assert row.technical_flags == ["possibly_blurry"]
        assert next(iter(row.usability.values()))["usable_for_annotation"] == "yes"


class TestLiveState:
    def test_no_fabricated_annotations_on_real_data(self):
        """Milestone 7 builds infrastructure only: no real annotation exists yet, and
        none claims expert status without an expert."""
        if not ANNOTATIONS_PATH.exists():
            return
        for line in ANNOTATIONS_PATH.read_text(encoding="utf-8").splitlines():
            a = json.loads(line)
            if a["provenance_type"] == "expert_annotation":
                assert a["annotator"].get("qualification")

    def test_records_remain_unknown(self, live_research):
        assert all(r["script_type"] == "unknown" for r in live_research["records"])


class TestAnnotationApp:
    def test_app_renders_and_saves_to_a_temporary_store(self, tmp_path, monkeypatch, live_research):
        if not live_research["records"]:
            pytest.skip("no research records to annotate")
        from streamlit.testing.v1 import AppTest

        target = tmp_path / "annotations.jsonl"
        monkeypatch.setenv("ETPAI_ANNOTATIONS_PATH", str(target))
        root = Path(__file__).resolve().parents[1]
        at = AppTest.from_file(str(root / "app" / "annotate.py"), default_timeout=180).run()
        assert not at.exception
        at.sidebar.text_input(key="annotator_id").set_value("SYNTHETIC_tester").run()
        next(b for b in at.button if "Save" in b.label).click().run()
        assert not at.exception and at.success
        [saved] = [json.loads(x) for x in target.read_text(encoding="utf-8").splitlines()]
        assert saved["inscription"]["script_type"] == "unknown"
        assert saved["provenance_type"] == "project_annotation"
        assert not ANNOTATIONS_PATH.exists() or target != ANNOTATIONS_PATH
