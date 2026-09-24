"""Milestone 5 readiness gates G1-G11.

The positive path is exercised only on SYNTHETIC corpora in tmp_path, with
``permit_noncanonical_source=True``. That parameter is not reachable from
``assert_training_ready`` or from any CLI, which is what the last class checks.
"""

from __future__ import annotations

import inspect
import json

import pytest

from src.dataset.loader import load_dataset
from src.dataset.readiness import (
    GATES,
    NO_DATA_REASON,
    NotTrainingReadyError,
    assert_training_ready,
    evaluate,
)
from src.dataset.splits import make_split

FOUR = ("tamil_brahmi", "graffiti", "none", "uncertain")


def _gates(report) -> dict[str, bool | None]:
    return {g["id"]: g["passed"] for g in report.gates}


def _ready_corpus(tmp_path, synthetic_corpus, n=20, **kw):
    """A synthetic corpus that satisfies every gate, plus its split manifest."""
    c = synthetic_corpus(tmp_path, dict.fromkeys(FOUR, n), **kw)
    ds = load_dataset(c["records_path"], c["data_root"])
    manifest = make_split(ds).save(tmp_path / "manifest.json")
    return c, manifest


def _eval(c, manifest=None, **kw):
    return evaluate(c["records_path"], c["data_root"], manifest_path=manifest,
                    permit_noncanonical_source=True, **kw)


class TestLiveState:
    def test_live_dataset_is_blocked(self, live_research):
        report = evaluate()
        assert not report.training_ready
        if not live_research["records"]:
            assert report.reason == NO_DATA_REASON
            assert _gates(report)["G2"] is False and _gates(report)["G3"] is False
        else:
            # Acquired images are valid and permitted, but carry no expert labels.
            assert _gates(report)["G9"] is False
            assert all(n == 0 for n in report.artifacts_by_class.values())

    def test_assert_training_ready_raises(self):
        with pytest.raises(NotTrainingReadyError, match="Training is blocked"):
            assert_training_ready()

    def test_every_gate_is_reported(self):
        assert [g["id"] for g in evaluate().gates] == list(GATES)

    def test_unevaluated_gates_do_not_count_as_passed(self, tmp_path):
        """With no records most gates cannot be evaluated; that must not read as a pass."""
        report = evaluate(tmp_path / "absent.jsonl", tmp_path / "raw",
                          permit_noncanonical_source=True)
        assert any(g["passed"] is None for g in report.gates)
        assert not report.training_ready


class TestGatePositivePath:
    def test_synthetic_corpus_can_satisfy_every_gate_when_permitted(self, tmp_path,
                                                                    synthetic_corpus):
        """Proves the gate CAN open, so its blocking elsewhere is meaningful."""
        c, manifest = _ready_corpus(tmp_path, synthetic_corpus)
        report = _eval(c, manifest)
        assert report.training_ready, report.render()
        assert all(_gates(report).values())

    def test_same_corpus_is_blocked_without_the_test_permission(self, tmp_path, synthetic_corpus):
        c, manifest = _ready_corpus(tmp_path, synthetic_corpus)
        report = evaluate(c["records_path"], c["data_root"], manifest_path=manifest)
        assert not report.training_ready and _gates(report)["G1"] is False


class TestGateFailures:
    def test_missing_class_blocks(self, tmp_path, synthetic_corpus):
        c = synthetic_corpus(tmp_path, {"tamil_brahmi": 20, "graffiti": 20, "uncertain": 20})
        report = _eval(c)
        assert _gates(report)["G9"] is False and not report.training_ready
        assert "none" in next(g["detail"] for g in report.gates if g["id"] == "G9")

    def test_insufficient_artifacts_block(self, tmp_path, synthetic_corpus):
        c = synthetic_corpus(tmp_path, dict.fromkeys(FOUR, 4))
        report = _eval(c)
        assert _gates(report)["G10"] is False
        assert set(report.classes_below_threshold) == set(FOUR)

    def test_kfold_manifest_uses_k_as_the_threshold(self, tmp_path, synthetic_corpus):
        c = synthetic_corpus(tmp_path, dict.fromkeys(FOUR, 6))
        ds = load_dataset(c["records_path"], c["data_root"])
        manifest = make_split(ds).save(tmp_path / "kfold.json")
        report = _eval(c, manifest)
        assert report.split_strategy == "grouped_kfold"
        assert report.min_artifacts_per_class_required == 5
        assert _gates(report)["G10"] is True

    def test_invalid_metadata_blocks(self, tmp_path, synthetic_corpus):
        c, manifest = _ready_corpus(tmp_path, synthetic_corpus)
        recs = c["records"]
        recs[0]["view"] = "sideways"
        c["records_path"].write_text("".join(json.dumps(r) + "\n" for r in recs), encoding="utf-8")
        report = _eval(c, manifest)
        assert _gates(report)["G4"] is False and _gates(report)["G5"] is False

    def test_bad_hash_blocks(self, tmp_path, synthetic_corpus):
        c, manifest = _ready_corpus(tmp_path, synthetic_corpus)
        (c["data_root"] / c["records"][0]["image_path"]).write_bytes(b"changed")
        report = _eval(c, manifest)
        assert _gates(report)["G5"] is False and not report.training_ready

    def test_duplicate_photograph_across_artifacts_blocks(self, tmp_path, synthetic_corpus):
        c, manifest = _ready_corpus(tmp_path, synthetic_corpus)
        recs = c["records"]
        recs[1]["image_sha256"] = recs[0]["image_sha256"]
        c["records_path"].write_text("".join(json.dumps(r) + "\n" for r in recs), encoding="utf-8")
        report = _eval(c, manifest, verify_hashes=False)
        assert _gates(report)["G6"] is False

    def test_artifact_across_splits_blocks(self, tmp_path, synthetic_corpus):
        c = synthetic_corpus(tmp_path, dict.fromkeys(FOUR, 20), images_per_artifact=2)
        recs = c["records"]
        recs[0]["split"], recs[1]["split"] = "train", "test"   # same artifact, two splits
        c["records_path"].write_text("".join(json.dumps(r) + "\n" for r in recs), encoding="utf-8")
        report = _eval(c)
        assert _gates(report)["G4"] is False   # R3
        assert not report.training_ready

    def test_unknown_label_source_blocks(self, tmp_path, synthetic_corpus):
        c = synthetic_corpus(tmp_path, dict.fromkeys(FOUR, 20), overrides={"label_source": "unknown"})
        assert _gates(_eval(c))["G7"] is False

    def test_rights_not_established_blocks(self, tmp_path, synthetic_corpus):
        c = synthetic_corpus(tmp_path, dict.fromkeys(FOUR, 20),
                             overrides={"research_usable": "unknown"})
        report = _eval(c)
        assert _gates(report)["G8"] is False
        assert "research_usable" in next(g["detail"] for g in report.gates if g["id"] == "G8")

    def test_absent_rights_field_counts_as_not_permitted(self, tmp_path, synthetic_corpus):
        c = synthetic_corpus(tmp_path, dict.fromkeys(FOUR, 20))
        recs = [{k: v for k, v in r.items() if k != "research_usable"} for r in c["records"]]
        c["records_path"].write_text("".join(json.dumps(r) + "\n" for r in recs), encoding="utf-8")
        assert _gates(_eval(c))["G8"] is False

    def test_missing_manifest_blocks(self, tmp_path, synthetic_corpus):
        c = synthetic_corpus(tmp_path, dict.fromkeys(FOUR, 20))
        report = _eval(c, tmp_path / "no_such_manifest.json")
        assert _gates(report)["G11"] is False

    def test_stale_manifest_blocks(self, tmp_path, synthetic_corpus):
        c, manifest = _ready_corpus(tmp_path, synthetic_corpus)
        recs = c["records"]
        recs[0]["notes"] = "SYNTHETIC edited after splitting"
        c["records_path"].write_text("".join(json.dumps(r) + "\n" for r in recs), encoding="utf-8")
        report = _eval(c, manifest)
        assert _gates(report)["G11"] is False
        assert "different dataset" in next(g["detail"] for g in report.gates if g["id"] == "G11")

    def test_no_images_blocks(self, tmp_path, synthetic_corpus):
        c, manifest = _ready_corpus(tmp_path, synthetic_corpus)
        for p in c["data_root"].rglob("*.png"):
            p.unlink()
        report = _eval(c, manifest)
        assert _gates(report)["G3"] is False and report.reason == NO_DATA_REASON


class TestGateBases:
    def test_every_gate_declares_a_basis(self):
        for gid, (_, _, basis) in GATES.items():
            assert basis in {"engineering", "project_methodology", "rights"}, gid

    def test_no_gate_claims_an_archaeological_basis(self):
        assert all(basis != "archaeological" for _, _, basis in GATES.values())


class TestNoBypass:
    def test_assert_training_ready_has_no_relaxing_parameter(self):
        params = set(inspect.signature(assert_training_ready).parameters)
        assert params == {"records_path", "data_root", "manifest_path"}

    def test_cli_has_no_bypass(self):
        from src.dataset.__main__ import build_parser as dataset_parser
        from src.training.__main__ import build_parser as training_parser

        for parser in (dataset_parser(), training_parser()):
            assert "permit" not in parser.format_help().lower()
            for action in parser._subparsers._group_actions:  # type: ignore[union-attr]
                for sub in action.choices.values():
                    assert "permit" not in sub.format_help().lower()
                    assert "force" not in sub.format_help().lower()

    def test_run_training_takes_no_data_paths(self):
        from src.training.run import run_training

        params = set(inspect.signature(run_training).parameters)
        # resume_from is a CHECKPOINT of the canonical dataset (the trainer refuses one from
        # another dataset version); it cannot point training at other records or images.
        assert params == {"config_path", "manifest_path", "resume_from"}
        assert not any(w in p for p in params for w in ("record", "data", "root", "image", "permit"))
