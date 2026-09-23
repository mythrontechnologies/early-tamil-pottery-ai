"""Ingestion pipeline, dataset audit, and the training readiness gate.

The invariants under test:

* ingestion is all-or-nothing and never repairs a record;
* the audit never counts fixtures as research data;
* the readiness gate fails closed and blocks training today.
"""

from __future__ import annotations

import json

import pytest

from src.dataset.audit import audit, is_research_source
from src.dataset.convert import write_jsonl
from src.dataset.ingest import ingest
from src.dataset.readiness import (
    NotTrainingReadyError,
    ReadinessReport,
    assert_training_ready,
    count_images,
    evaluate,
    write_report,
)
from src.dataset.schema import RESEARCH_DATA_ROOT, RESEARCH_RECORDS_PATH


@pytest.fixture
def batch(tmp_path, base_record):
    """A one-record batch on disk, plus an empty destination."""
    src = tmp_path / "batch.jsonl"
    write_jsonl(src, [base_record])
    return src, tmp_path / "dest.jsonl"


# --------------------------------------------------------------------------- #
# Ingestion
# --------------------------------------------------------------------------- #


class TestIngestion:
    def test_dry_run_is_the_default(self, batch, tmp_path):
        src, dest = batch
        result = ingest(src, destination=dest, data_root=tmp_path / "nothing")
        assert result.accepted
        assert not result.committed
        assert not dest.exists(), "a dry run must not write"

    def test_commit_writes(self, batch, tmp_path):
        src, dest = batch
        result = ingest(src, destination=dest, data_root=tmp_path / "nothing", commit=True)
        assert result.accepted and result.committed
        assert dest.exists()
        assert len(dest.read_text(encoding="utf-8").strip().splitlines()) == 1

    def test_invalid_batch_is_rejected_whole(self, tmp_path, base_record, make_record):
        """One bad record rejects the batch; nothing partial is kept."""
        src, dest = tmp_path / "mixed.jsonl", tmp_path / "dest.jsonl"
        write_jsonl(src, [base_record, make_record(
            image_id="FIXTURE_BAD__exterior__1", artifact_id="FIXTURE_BAD",
            image_sha256="0" * 64, dating_lower_year=300, dating_upper_year=-200)])

        result = ingest(src, destination=dest, data_root=tmp_path / "nothing", commit=True)

        assert not result.accepted
        assert not result.committed
        assert not dest.exists()
        assert "R8" in {f.rule for f in result.validation.errors}

    def test_rejection_names_the_exact_reason(self, tmp_path, make_record):
        src = tmp_path / "bad.jsonl"
        write_jsonl(src, [make_record(context_reliability="surface_collection")])
        result = ingest(src, destination=tmp_path / "d.jsonl",
                        data_root=tmp_path / "nothing")
        assert not result.accepted
        messages = [f.message for f in result.validation.errors]
        assert any("stratigraphy" in m for m in messages)

    def test_never_repairs_a_record(self, tmp_path, make_record):
        """A missing recommended field is reported, never filled in."""
        src, dest = tmp_path / "sparse.jsonl", tmp_path / "dest.jsonl"
        write_jsonl(src, [make_record(site=...)])

        ingest(src, destination=dest, data_root=tmp_path / "nothing", commit=True)

        written = json.loads(dest.read_text(encoding="utf-8").splitlines()[0])
        assert "site" not in written, "ingestion must not invent a value"

    def test_merge_detects_collision_with_existing_records(self, tmp_path, base_record):
        """A batch valid on its own can still be invalid against the dataset."""
        dest = tmp_path / "dest.jsonl"
        write_jsonl(dest, [base_record])
        src = tmp_path / "again.jsonl"
        write_jsonl(src, [base_record])

        result = ingest(src, destination=dest, data_root=tmp_path / "nothing")
        assert not result.accepted
        assert "R1" in {f.rule for f in result.validation.errors}

    def test_no_merge_validates_the_batch_alone(self, tmp_path, base_record):
        dest = tmp_path / "dest.jsonl"
        write_jsonl(dest, [base_record])
        src = tmp_path / "again.jsonl"
        write_jsonl(src, [base_record])

        result = ingest(src, destination=dest, data_root=tmp_path / "nothing", merge=False)
        assert result.accepted

    def test_missing_source_is_reported(self, tmp_path):
        result = ingest(tmp_path / "absent.jsonl", destination=tmp_path / "d.jsonl")
        assert not result.accepted
        assert "does not exist" in result.reason

    def test_malformed_source_is_reported(self, tmp_path):
        src = tmp_path / "broken.jsonl"
        src.write_text("{not json\n", encoding="utf-8")
        result = ingest(src, destination=tmp_path / "d.jsonl")
        assert not result.accepted
        assert "could not parse" in result.reason

    def test_csv_input_accepted(self, tmp_path, base_record):
        from src.dataset.convert import jsonl_to_csv

        jsonl_src = tmp_path / "a.jsonl"
        write_jsonl(jsonl_src, [base_record])
        csv_src = tmp_path / "a.csv"
        jsonl_to_csv(jsonl_src, csv_src)

        result = ingest(csv_src, destination=tmp_path / "d.jsonl",
                        data_root=tmp_path / "nothing", commit=True)
        assert result.accepted and result.committed

    def test_skipped_image_check_is_reported_in_the_log(self, batch, tmp_path):
        src, dest = batch
        result = ingest(src, destination=dest, data_root=tmp_path / "nothing")
        assert any("SKIPPED" in line for line in result.stage_log)


# --------------------------------------------------------------------------- #
# Audit
# --------------------------------------------------------------------------- #


class TestAudit:
    def test_empty_dataset_reports_zero(self):
        report = audit([], source=RESEARCH_RECORDS_PATH)
        assert report.total_records == 0
        assert report.unique_artifacts == 0
        assert report.is_research_dataset
        assert "REAL DATASET: 0 records" in report.render()

    def test_fixtures_are_not_research_data(self, fixtures_dir, load_fixture):
        src = fixtures_dir / "valid" / "multi_photo_artifact.jsonl"
        report = audit(load_fixture("valid/multi_photo_artifact.jsonl"), source=src)
        assert not report.is_research_dataset
        assert "SOURCE IS NOT THE RESEARCH DATASET" in report.render()
        assert "REAL DATASET: 0 records" not in report.render()

    def test_only_the_canonical_path_counts_as_research_data(self, tmp_path):
        assert is_research_source(RESEARCH_RECORDS_PATH)
        assert not is_research_source(tmp_path / "records.jsonl")

    def test_counts_artifacts_not_images(self, load_fixture):
        report = audit(load_fixture("valid/multi_photo_artifact.jsonl"))
        assert report.total_records == 3
        assert report.unique_artifacts == 1
        assert report.photos_per_artifact_max == 3

    def test_breakdowns_present(self, base_record):
        report = audit([base_record])
        assert report.by_script_type == {"tamil_brahmi": 1}
        assert report.by_inscription_present == {"yes": 1}
        assert report.by_site == {"FIXTURE_SITE_A": 1}
        assert report.by_label_source == {"expert_annotation": 1}
        assert report.artifacts_by_script_type == {"tamil_brahmi": 1}

    def test_presence_counts_ignore_sentinels(self, make_record):
        """'not_available' is not a translation."""
        report = audit([make_record(
            translation_en="not_available", transcription="not_applicable")])
        assert report.records_with_translation == 0
        assert report.records_with_transcription == 0

    def test_dating_counts(self, base_record, make_record):
        report = audit([base_record, make_record(
            image_id="FIXTURE_X__exterior__1", artifact_id="FIXTURE_X",
            image_sha256="f" * 64,
            dating_lower_year=None, dating_upper_year=None,
            dating_basis=["unknown"], dating_source="not_available")])
        assert report.records_with_dating == 1
        assert report.records_with_dating_basis == 1

    @pytest.mark.parametrize("basis", [["not_available"], ["unknown"], ["not_applicable"],
                                       ["unknown", "not_available"], [], None])
    def test_sentinel_dating_basis_is_not_evidence(self, make_record, basis):
        """Milestone 7 regression: a sentinel basis is the absence of a basis."""
        from src.dataset.audit import has_dating_evidence_basis

        rec = make_record(dating_basis=basis) if basis is not None else make_record(dating_basis=...)
        assert not has_dating_evidence_basis(rec)
        assert audit([rec]).records_with_dating_basis == 0

    @pytest.mark.parametrize("basis", [["palaeography"], ["not_available", "stratigraphy"]])
    def test_real_dating_basis_is_counted(self, make_record, basis):
        from src.dataset.audit import has_dating_evidence_basis

        assert has_dating_evidence_basis(make_record(dating_basis=basis))

    def test_audit_does_not_modify_records(self, make_record):
        rec = make_record(dating_basis=["not_available"])
        before = json.dumps(rec, sort_keys=True)
        audit([rec])
        assert json.dumps(rec, sort_keys=True) == before

    def test_live_dataset_counts_no_dating_basis(self, live_research):
        """All 30 acquired records carry dating_basis=['not_available']."""
        report = audit(live_research["records"])
        assert report.records_with_dating_basis == sum(
            1 for r in live_research["records"]
            if any(b not in ("unknown", "not_available", "not_applicable") for b in r["dating_basis"]))

    def test_validation_summary_folded_in(self, base_record):
        from src.dataset.validation import validate_records

        result = validate_records([base_record])
        report = audit([base_record], validation=result)
        assert report.validation_status == "PASS"
        assert report.validation_errors == 0

    def test_report_is_json_serialisable(self, base_record):
        json.dumps(audit([base_record]).to_dict())


# --------------------------------------------------------------------------- #
# Readiness gate
# --------------------------------------------------------------------------- #


class TestReadinessGate:
    def test_real_dataset_is_not_training_ready(self, live_research):
        """The live state of the project: no expert-labelled data, so no training."""
        report = evaluate()
        assert report.training_ready is False
        assert report.record_count == len(live_research["records"])

    def test_every_real_image_is_recorded(self, live_research):
        """Every image under data/raw is described by exactly one research record."""
        assert count_images(RESEARCH_DATA_ROOT) == len(live_research["records"])

    def test_assert_training_ready_raises_today(self):
        with pytest.raises(NotTrainingReadyError, match="Training is blocked"):
            assert_training_ready()

    def test_missing_records_file_reports_the_documented_reason(self, tmp_path):
        report = evaluate(tmp_path / "absent.jsonl", tmp_path / "no_images")
        assert not report.training_ready
        assert report.reason == "No real archaeological images are currently available"

    def test_fixtures_cannot_make_the_gate_pass(self, tmp_path, fixtures_dir, load_fixture):
        """Even a validating fixture set is far below the artifact threshold."""
        records = load_fixture("valid/multi_photo_artifact.jsonl")
        dest = tmp_path / "records.jsonl"
        write_jsonl(dest, records)
        images = tmp_path / "raw" / "fixture_site"
        images.mkdir(parents=True)
        for record in records:
            (tmp_path / "raw" / record["image_path"]).write_bytes(b"fixture")

        report = evaluate(dest, tmp_path / "raw")
        assert not report.training_ready
        assert report.classes_below_threshold

    def test_unreadable_records_file_fails_closed(self, tmp_path):
        dest = tmp_path / "records.jsonl"
        dest.write_text("{not json\n", encoding="utf-8")
        report = evaluate(dest, tmp_path / "raw")
        assert not report.training_ready
        assert report.validation_status == "FAIL"

    def test_report_shape_matches_the_specification(self):
        report = evaluate()
        data = report.to_dict()
        for key in ("research_data_present", "record_count", "unique_artifacts",
                    "validation_status", "training_ready", "reason"):
            assert key in data
        assert isinstance(data["research_data_present"], bool)
        assert isinstance(data["training_ready"], bool)

    def test_report_writes_json(self, tmp_path):
        out = write_report(tmp_path / "readiness.json", evaluate())
        loaded = json.loads(out.read_text(encoding="utf-8"))
        assert loaded["training_ready"] is False

    def test_threshold_comes_from_config(self):
        from src.dataset.schema import load_config

        expected = load_config()["split"]["min_artifacts_per_class_for_holdout"]
        assert evaluate().min_artifacts_per_class_required == expected

    def test_render_is_printable(self):
        assert "TRAINING READINESS GATE" in evaluate().render()
        assert isinstance(ReadinessReport(**evaluate().to_dict()).to_json(), str)


# --------------------------------------------------------------------------- #
# Research-data hygiene
# --------------------------------------------------------------------------- #


class TestNoFabricatedData:
    def test_research_dataset_contains_no_fixtures(self, live_research):
        """Real records only: nothing synthetic, nothing without acquisition provenance."""
        for rec in live_research["records"]:
            blob = json.dumps(rec)
            assert "FIXTURE" not in blob and "SYNTHETIC" not in blob
            assert rec["image_id"] in live_research["provenance"]

    def test_research_records_carry_no_invented_labels(self, live_research):
        """Acquired images arrive unlabelled; a label needs an expert source (Milestone 6)."""
        for rec in live_research["records"]:
            if live_research["provenance"][rec["image_id"]]["project_label"] == "unknown":
                assert rec["script_type"] == "unknown"
                assert rec["inscription_present"] == "unknown"
                assert rec["label_source"] == "unknown"
                assert rec["transcription"] == "not_available"

    def test_no_unrecorded_images_under_data(self, live_research):
        from src.dataset.readiness import IMAGE_SUFFIXES

        recorded = {rec["image_path"] for rec in live_research["records"]}
        on_disk = {p.relative_to(RESEARCH_DATA_ROOT).as_posix()
                   for p in RESEARCH_DATA_ROOT.rglob("*") if p.suffix.lower() in IMAGE_SUFFIXES}
        assert on_disk == recorded

    def test_fixtures_live_outside_data(self, fixtures_dir):
        from src.dataset.schema import ROOT

        assert not fixtures_dir.is_relative_to(ROOT / "data")

    def test_every_fixture_is_marked_synthetic(self, fixtures_dir):
        """A fixture must never be mistakable for a real record.

        Either marker is acceptable: record fixtures use FIXTURE_ identifiers, while
        the image manifest declares itself SYNTHETIC. What matters is that no fixture
        file is silent about being invented.
        """
        markers = ("FIXTURE", "SYNTHETIC")
        for path in sorted(fixtures_dir.rglob("*.jsonl")) + sorted(
            fixtures_dir.rglob("*.json")
        ):
            text = path.read_text(encoding="utf-8")
            assert any(m in text for m in markers), (
                f"{path.relative_to(fixtures_dir)} carries no synthetic marker "
                f"(expected one of {markers})"
            )
