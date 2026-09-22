"""Milestone 1 tests: the schema contract itself.

These do not test data ingestion (Milestone 2). They test that the schema is a valid
JSON Schema, that it encodes the integrity rules the project depends on, and that the
example record demonstrates the format correctly.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml
from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parent.parent
SCHEMA_PATH = ROOT / "data" / "metadata" / "schema" / "image_record.schema.json"
EXAMPLE_PATH = ROOT / "data" / "metadata" / "schema" / "_example_record.json"
CONFIG_PATH = ROOT / "configs" / "project.yaml"


@pytest.fixture(scope="module")
def schema() -> dict:
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def config() -> dict:
    return yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def example(schema: dict) -> dict:
    raw = json.loads(EXAMPLE_PATH.read_text(encoding="utf-8"))
    return {k: v for k, v in raw.items() if not k.startswith("_")}


# --- the schema is well formed ------------------------------------------------


def test_schema_is_valid_json_schema(schema: dict) -> None:
    Draft202012Validator.check_schema(schema)


def test_example_validates(schema: dict, example: dict) -> None:
    errors = sorted(Draft202012Validator(schema).iter_errors(example), key=lambda e: list(e.path))
    assert not errors, "\n".join(f"{list(e.path)}: {e.message}" for e in errors)


def test_example_is_flagged_as_not_real_data() -> None:
    """The example must announce that it is fictitious, or someone will cite it."""
    raw = json.loads(EXAMPLE_PATH.read_text(encoding="utf-8"))
    assert "_WARNING" in raw
    assert "NOT REAL ARCHAEOLOGICAL DATA" in raw["_WARNING"]


def test_example_exercises_every_field(schema: dict, example: dict) -> None:
    """The example is the format's documentation; it should show every field."""
    assert set(example) == set(schema["properties"])


# --- the schema encodes the project's integrity rules -------------------------


def test_split_key_is_required(schema: dict) -> None:
    """artifact_id is the leakage defence. It cannot be optional."""
    assert "artifact_id" in schema["required"]
    assert "image_id" in schema["required"]


def test_rights_fields_are_required(schema: dict) -> None:
    assert "license" in schema["required"]
    assert "redistributable" in schema["required"]


def test_label_provenance_is_required(schema: dict) -> None:
    """A label with no recorded source cannot be treated as ground truth."""
    assert "script_type" in schema["required"]
    assert "label_source" in schema["required"]
    assert "verification_status" in schema["required"]


def test_classifier_classes_are_a_subset_of_script_type(schema: dict, config: dict) -> None:
    allowed = set(schema["properties"]["script_type"]["enum"])
    cfg = config["classification"]
    assert set(cfg["classes"]) <= allowed
    assert set(cfg["held_out_labels"]) <= allowed
    assert not set(cfg["classes"]) & set(cfg["held_out_labels"])


def test_uncertain_is_an_available_label(schema: dict) -> None:
    """'uncertain' must be expressible, or annotators are forced to guess."""
    assert "uncertain" in schema["properties"]["script_type"]["enum"]
    assert "uncertain" in schema["properties"]["inscription_present"]["enum"]


def test_year_zero_is_rejected(schema: dict) -> None:
    """There is no year 0 in the BCE/CE scheme; -1 is followed by 1."""
    validator = Draft202012Validator(schema["$defs"]["signed_year"])
    assert list(validator.iter_errors(0)), "year 0 must be rejected"
    for ok in (-1, 1, -200, 300, None):
        assert not list(validator.iter_errors(ok)), f"{ok} should be accepted"


def test_empty_strings_are_rejected(schema: dict) -> None:
    """Absence must be an explicit sentinel, never an empty cell."""
    validator = Draft202012Validator(schema["$defs"]["free_text"])
    assert list(validator.iter_errors(""))
    for sentinel in ("unknown", "not_available", "not_applicable"):
        assert not list(validator.iter_errors(sentinel))


def test_dating_basis_cannot_be_empty(schema: dict) -> None:
    """A date with no recorded basis is the thing this project exists to prevent."""
    prop = schema["properties"]["dating_basis"]
    assert prop["minItems"] >= 1
    assert "unknown" in prop["items"]["enum"]


def test_unknown_fields_are_rejected(schema: dict, example: dict) -> None:
    """additionalProperties: false - a typo must fail loudly, not vanish."""
    bad = dict(example, artifcat_id="typo")
    assert list(Draft202012Validator(schema).iter_errors(bad))


# --- config consistency -------------------------------------------------------


def test_split_proportions_sum_to_one(config: dict) -> None:
    s = config["split"]
    assert abs(s["train"] + s["val"] + s["test"] - 1.0) < 1e-9


def test_split_groups_by_artifact_not_image(config: dict) -> None:
    assert config["split"]["group_key"] == "artifact_id"


def test_chronology_is_not_presented_as_verified(config: dict) -> None:
    """Nothing in the chronology may claim verification until a human checks it."""
    chron = config["chronology"]
    for key in ("ingestion_scope", "modelling_scope"):
        assert chron[key]["verification_status"] != "verified_against_source"
    for pos in chron["tamil_brahmi_earliest_positions"]:
        assert pos["verification_status"] != "verified_against_source"


def test_chronology_records_competing_positions(config: dict) -> None:
    """The early date of Tamil-Brahmi is contested; the config must not pick one."""
    positions = config["chronology"]["tamil_brahmi_earliest_positions"]
    assert len(positions) >= 2
    assert config["chronology"]["fallback_policy"] == "union_of_cited_positions"


def test_modelling_scope_within_ingestion_scope(config: dict) -> None:
    ing, mod = config["chronology"]["ingestion_scope"], config["chronology"]["modelling_scope"]
    assert ing["lower_year"] <= mod["lower_year"]
    assert mod["upper_year"] <= ing["upper_year"]


def test_unknown_rights_are_not_redistributable(config: dict) -> None:
    assert config["integrity"]["unknown_rights_are_redistributable"] is False
