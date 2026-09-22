"""Validation tests: rules R1-R15 (docs/SPLIT_METHODOLOGY.md §4) and E1-E5.

Each test asserts two things: that the intended rule fires, and - where it matters -
that no *other* rule fires, so a passing suite means the rules are independent rather
than merely noisy.
"""

from __future__ import annotations

import pytest

from src.dataset.validation import (
    RECOMMENDED_FIELDS,
    RULE_TITLES,
    DatasetValidator,
    validate_records,
)


def rules_fired(result, severity: str | None = None) -> set[str]:
    return {
        f.rule for f in result.findings if severity is None or f.severity == severity
    }


# --------------------------------------------------------------------------- #
# Valid records
# --------------------------------------------------------------------------- #


class TestValidRecords:
    def test_base_record_is_clean(self, base_record):
        result = validate_records([base_record])
        assert result.ok, [str(f) for f in result.findings]
        assert not result.findings, "the base fixture should produce no findings at all"

    def test_minimal_record_is_valid_but_warns(self, load_fixture):
        """Only the 10 required fields: valid, but R15 flags the omissions."""
        result = validate_records(load_fixture("valid/minimal_record.jsonl"))
        assert result.ok
        assert not result.errors
        assert rules_fired(result) == {"R15"}
        assert len(result.warnings) == len(RECOMMENDED_FIELDS)

    def test_sentinels_are_accepted(self, load_fixture):
        """unknown / not_available / not_applicable used correctly throughout."""
        result = validate_records(load_fixture("valid/unknown_heavy_record.jsonl"))
        assert result.ok, [str(f) for f in result.findings]
        assert not result.errors

    def test_multi_photo_artifact_is_valid(self, load_fixture):
        """Three photographs, one artifact, one split - the R3/R4 happy path."""
        records = load_fixture("valid/multi_photo_artifact.jsonl")
        assert len({r["artifact_id"] for r in records}) == 1
        assert len({r["image_id"] for r in records}) == 3

        result = validate_records(records)
        assert result.ok, [str(f) for f in result.findings]

    def test_valid_dating(self, make_record):
        result = validate_records([make_record(
            dating_lower_year=-300, dating_upper_year=-100,
            dating_source="SYNTHETIC FIXTURE",
        )])
        assert result.ok

    def test_null_dating_bounds_need_no_source(self, make_record):
        """R9 only applies when a numeric bound is actually given."""
        result = validate_records([make_record(
            dating_lower_year=None, dating_upper_year=None,
            dating_source="not_available", dating_basis=["unknown"],
        )])
        assert "R9" not in rules_fired(result)


# --------------------------------------------------------------------------- #
# E1 - schema layer
# --------------------------------------------------------------------------- #


class TestSchemaLayer:
    def test_empty_string_rejected(self, make_record):
        result = validate_records([make_record(site="")])
        assert not result.ok
        assert "E1" in rules_fired(result, "error")

    @pytest.mark.parametrize("field", ["image_id", "artifact_id", "script_type",
                                       "license", "redistributable", "label_source",
                                       "verification_status", "inscription_present",
                                       "source", "image_path"])
    def test_missing_required_field_rejected(self, make_record, field):
        result = validate_records([make_record(**{field: ...})])
        assert not result.ok
        assert any(f.rule == "E1" and "required" in f.message for f in result.errors)

    def test_year_zero_rejected(self, make_record):
        """There is no year 0: 1 BCE is -1 and 1 CE is 1."""
        result = validate_records([make_record(dating_lower_year=0)])
        assert not result.ok
        assert "E1" in rules_fired(result, "error")

    @pytest.mark.parametrize("year", [-1, 1, -200, 300])
    def test_valid_years_accepted(self, make_record, year):
        result = validate_records([make_record(
            dating_lower_year=year, dating_upper_year=400,
            dating_source="SYNTHETIC FIXTURE")])
        assert result.ok, [str(f) for f in result.findings]

    def test_unsupported_view_rejected(self, make_record):
        result = validate_records([make_record(view="side_angle_photo")])
        assert not result.ok
        assert "E1" in rules_fired(result, "error")

    def test_unsupported_label_source_rejected(self, make_record):
        result = validate_records([make_record(label_source="a_friend_told_me")])
        assert not result.ok

    def test_unknown_field_rejected(self, base_record):
        """A typo must fail loudly rather than vanish."""
        result = validate_records([base_record | {"artifcat_id": "typo"}])
        assert not result.ok

    def test_empty_dating_basis_rejected(self, make_record):
        result = validate_records([make_record(dating_basis=[])])
        assert not result.ok

    def test_non_dict_record_reported_not_crashed(self):
        result = validate_records(["not a record", 42])
        assert not result.ok
        assert len(result.errors) == 2

    def test_incompatible_schema_version(self, make_record):
        result = validate_records([make_record(schema_version="2.0.0")])
        assert "E4" in rules_fired(result, "error")


# --------------------------------------------------------------------------- #
# E3 - path hygiene
# --------------------------------------------------------------------------- #


class TestPathHygiene:
    @pytest.mark.parametrize("path", [
        "fixture_site\\backslash.jpg",
        "/absolute/path.jpg",
        "C:/drive/letter.jpg",
        "../escapes/upward.jpg",
    ])
    def test_unsafe_paths_rejected(self, make_record, path):
        result = validate_records([make_record(image_path=path)])
        assert "E3" in rules_fired(result, "error"), path

    def test_safe_relative_path_accepted(self, make_record):
        result = validate_records([make_record(image_path="site/a/b.jpg")])
        assert "E3" not in rules_fired(result)


# --------------------------------------------------------------------------- #
# R5, R6, R7 - inscription and script consistency
# --------------------------------------------------------------------------- #


class TestScriptConsistency:
    def test_r5_no_inscription_but_script_claimed(self, make_record):
        result = validate_records([make_record(
            inscription_present="no", script_type="tamil_brahmi")])
        assert "R5" in rules_fired(result, "error")

    def test_r6_none_script_requires_not_applicable_readings(self, make_record):
        result = validate_records([make_record(
            inscription_present="no", script_type="none",
            transcription="FIXTURE_SHOULD_BE_NOT_APPLICABLE")])
        fired = [f for f in result.errors if f.rule == "R6"]
        assert fired and fired[0].field == "transcription"

    def test_r6_satisfied_when_all_reading_fields_not_applicable(self, load_fixture):
        result = validate_records(load_fixture("valid/unknown_heavy_record.jsonl"))
        assert "R6" not in rules_fired(result)

    @pytest.mark.parametrize("detail", ["unknown", "not_available", "not_applicable"])
    def test_r7_other_script_needs_a_named_script(self, make_record, detail):
        result = validate_records([make_record(
            script_type="other_script", script_type_other_detail=detail)])
        assert "R7" in rules_fired(result, "error")

    def test_r7_satisfied_with_a_real_detail(self, make_record):
        result = validate_records([make_record(
            script_type="other_script",
            script_type_other_detail="FIXTURE_SCRIPT_PLACEHOLDER")])
        assert "R7" not in rules_fired(result)


# --------------------------------------------------------------------------- #
# R8, R9, R10 - dating
# --------------------------------------------------------------------------- #


class TestDating:
    def test_r8_reversed_bounds(self, make_record):
        result = validate_records([make_record(
            dating_lower_year=300, dating_upper_year=-200)])
        assert "R8" in rules_fired(result, "error")

    def test_r8_equal_bounds_allowed(self, make_record):
        result = validate_records([make_record(
            dating_lower_year=-200, dating_upper_year=-200,
            dating_source="SYNTHETIC FIXTURE")])
        assert "R8" not in rules_fired(result)

    @pytest.mark.parametrize("source", ["unknown", "not_available", "not_applicable"])
    def test_r9_numeric_date_requires_a_source(self, make_record, source):
        result = validate_records([make_record(dating_source=source)])
        assert "R9" in rules_fired(result, "error")

    @pytest.mark.parametrize("context", [
        "surface_collection", "excavated_unstratified",
        "museum_unprovenanced", "unprovenanced", "unknown",
    ])
    def test_r10_stratigraphic_date_needs_stratified_context(self, make_record, context):
        """A surface find carries no stratigraphic date, however published."""
        result = validate_records([make_record(context_reliability=context)])
        assert "R10" in rules_fired(result, "error")

    def test_r10_satisfied_when_stratified(self, base_record):
        assert base_record["context_reliability"] == "excavated_stratified"
        assert "stratigraphy" in base_record["dating_basis"]
        assert "R10" not in rules_fired(validate_records([base_record]))

    def test_r10_not_applied_without_stratigraphic_basis(self, make_record):
        result = validate_records([make_record(
            dating_basis=["palaeography"], context_reliability="surface_collection")])
        assert "R10" not in rules_fired(result)


# --------------------------------------------------------------------------- #
# R11, R12, R13, R14, R15
# --------------------------------------------------------------------------- #


class TestRemainingRecordRules:
    @pytest.mark.parametrize("rights", ["unknown", "no"])
    def test_r11_blocks_export_of_non_redistributable(self, make_record, rights):
        record = make_record(redistributable=rights)
        assert validate_records([record]).ok, "R11 must not fire outside export mode"
        result = validate_records([record], export_mode=True)
        assert "R11" in rules_fired(result, "error")

    def test_r11_allows_export_when_yes(self, base_record):
        assert validate_records([base_record], export_mode=True).ok

    def test_r12_excluded_needs_a_reason(self, make_record):
        result = validate_records([make_record(
            split="excluded", split_exclusion_reason="not_applicable")])
        assert "R12" in rules_fired(result, "error")

    def test_r12_satisfied_with_a_reason(self, make_record):
        result = validate_records([make_record(
            split="excluded", split_exclusion_reason="FIXTURE reason")])
        assert "R12" not in rules_fired(result)

    def test_r13_region_outside_image(self, make_record):
        result = validate_records([make_record(inscription_regions=[
            {"x": 1100, "y": 850, "w": 400, "h": 200, "region_label": "inscription"}])])
        assert "R13" in rules_fired(result, "error")

    def test_r13_region_flush_to_edge_allowed(self, make_record):
        result = validate_records([make_record(inscription_regions=[
            {"x": 0, "y": 0, "w": 1200, "h": 900, "region_label": "inscription"}])])
        assert "R13" not in rules_fired(result)

    def test_r13_skipped_when_dimensions_unknown(self, make_record):
        result = validate_records([make_record(
            image_width_px=None, image_height_px=None,
            inscription_regions=[{"x": 9999, "y": 9999, "w": 10, "h": 10,
                                  "region_label": "inscription"}])])
        assert "R13" not in rules_fired(result)

    def test_r14_warns_on_unverified_test_label(self, make_record):
        result = validate_records([make_record(
            split="test", label_source="project_annotation_unverified")])
        assert "R14" in rules_fired(result, "warning")
        assert result.ok, "R14 is a warning, not an error"

    def test_r14_becomes_failure_under_strict(self, make_record):
        result = validate_records([make_record(
            split="test", label_source="project_annotation_unverified")], strict=True)
        assert not result.ok

    def test_r15_warns_per_missing_recommended_field(self, make_record):
        result = validate_records([make_record(site=..., pottery_type=...)])
        missing = {f.field for f in result.warnings if f.rule == "R15"}
        assert missing == {"site", "pottery_type"}
        assert result.ok


# --------------------------------------------------------------------------- #
# R1, R3, R4, E5 - dataset-wide
# --------------------------------------------------------------------------- #


class TestDatasetWideRules:
    def test_r1_duplicate_image_id(self, load_fixture):
        result = validate_records(load_fixture("invalid/duplicate_image_id.jsonl"))
        assert "R1" in rules_fired(result, "error")
        assert "R4" not in rules_fired(result), "hashes differ; only R1 should fire"

    def test_r3_artifact_split_across_splits(self, load_fixture):
        result = validate_records(load_fixture("invalid/split_conflict.jsonl"))
        fired = [f for f in result.errors if f.rule == "R3"]
        assert fired
        assert "FIXTURE_ART_043" in fired[0].message
        assert "train" in fired[0].message and "test" in fired[0].message

    def test_r3_satisfied_for_multi_photo_artifact(self, load_fixture):
        result = validate_records(load_fixture("valid/multi_photo_artifact.jsonl"))
        assert "R3" not in rules_fired(result)

    def test_r4_same_photo_under_two_artifacts(self, load_fixture):
        """The leakage route that artifact_id grouping alone does not catch."""
        result = validate_records(load_fixture("invalid/duplicate_hash.jsonl"))
        assert "R4" in rules_fired(result, "error")

    def test_e5_duplicate_photo_within_one_artifact_is_a_warning(self, make_record):
        a = make_record(image_id="FIXTURE_A__exterior__1")
        b = make_record(image_id="FIXTURE_A__exterior__2")
        result = validate_records([a, b])
        assert "E5" in rules_fired(result, "warning")
        assert "R4" not in rules_fired(result)
        assert result.ok

    def test_sentinel_hashes_do_not_collide(self, make_record):
        """Two records with image_sha256='not_available' are not the same photo."""
        a = make_record(image_id="FIXTURE_A__exterior__1", artifact_id="FIXTURE_A",
                        image_sha256="not_available")
        b = make_record(image_id="FIXTURE_B__exterior__1", artifact_id="FIXTURE_B",
                        image_sha256="not_available")
        result = validate_records([a, b])
        assert "R4" not in rules_fired(result)
        assert "E5" not in rules_fired(result)


# --------------------------------------------------------------------------- #
# R2 / E2 - files on disk
# --------------------------------------------------------------------------- #


class TestFileChecks:
    def test_r2_missing_image_reported(self, tmp_path, make_record):
        result = validate_records([make_record()], data_root=tmp_path)
        assert "R2" in rules_fired(result, "error")

    def test_r2_present_image_accepted(self, tmp_path, make_record):
        target = tmp_path / "fixture_site" / "FIXTURE_ART_001__exterior__1.jpg"
        target.parent.mkdir(parents=True)
        target.write_bytes(b"not a real image - fixture bytes")
        result = validate_records([make_record()], data_root=tmp_path)
        assert "R2" not in rules_fired(result)

    def test_e2_hash_mismatch_detected(self, tmp_path, make_record):
        target = tmp_path / "fixture_site" / "FIXTURE_ART_001__exterior__1.jpg"
        target.parent.mkdir(parents=True)
        target.write_bytes(b"fixture bytes")
        result = validate_records([make_record()], data_root=tmp_path, verify_hashes=True)
        assert "E2" in rules_fired(result, "error")

    def test_e2_hash_match_accepted(self, tmp_path, make_record):
        import hashlib

        payload = b"fixture bytes"
        target = tmp_path / "fixture_site" / "FIXTURE_ART_001__exterior__1.jpg"
        target.parent.mkdir(parents=True)
        target.write_bytes(payload)
        record = make_record(image_sha256=hashlib.sha256(payload).hexdigest())
        result = validate_records([record], data_root=tmp_path, verify_hashes=True)
        assert result.ok, [str(f) for f in result.findings]

    def test_skipped_checks_are_reported_not_passed(self, make_record):
        """A skipped check must never look like a passing one."""
        result = validate_records([make_record()], data_root=None)
        assert result.images_checked is False
        assert "SKIPPED" in result.summary()


# --------------------------------------------------------------------------- #
# Meta
# --------------------------------------------------------------------------- #


class TestRuleCoverage:
    def test_all_fifteen_documented_rules_exist(self):
        documented = {f"R{i}" for i in range(1, 16)}
        assert documented <= set(RULE_TITLES)

    def test_engineering_rules_are_separately_namespaced(self):
        """E* rules are engineering checks, not archaeological claims."""
        assert {"E1", "E2", "E3", "E4", "E5"} <= set(RULE_TITLES)
        assert all(r[0] in {"R", "E"} for r in RULE_TITLES)

    def test_validator_never_mutates_input(self, base_record):
        import copy

        before = copy.deepcopy(base_record)
        DatasetValidator().validate([base_record])
        assert base_record == before, "validation must report, never repair"

    def test_findings_are_deterministic(self, load_fixture):
        records = load_fixture("invalid/split_conflict.jsonl")
        a = [str(f) for f in validate_records(records).findings]
        b = [str(f) for f in validate_records(records).findings]
        assert a == b
