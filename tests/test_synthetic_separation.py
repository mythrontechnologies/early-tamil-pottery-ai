"""Milestone 9 safety: SYNTHETIC data can never pass for, or reach, archaeological data.

One class per required guarantee:

 1. synthetic files cannot enter data/raw (or any other research data directory);
 2. synthetic data cannot satisfy archaeological training readiness;
 3. synthetic checkpoints cannot be mistaken for real checkpoints;
 4. synthetic metrics cannot enter the archaeological evaluation report or history;
 5. synthetic labels cannot be promoted as archaeological expert labels;
 6. synthetic annotations cannot enter the expert annotation store;
 7. synthetic provenance is preserved;
 8. the dataset type is always explicit;
 9. removing the synthetic dataset does not change real-data readiness;
10. the real-data gates are unchanged (G1-G11, and `python -m src.training train` stays blocked).

Synthetic data here is the tiny dataset generated in pytest's temporary directory (conftest.py).
Nothing in this module writes under data/ or models/; attempts to do so are what is being refused.
"""

from __future__ import annotations

import inspect
import io
import json
from pathlib import Path

import pytest
import torch
from conftest import ROOT
from PIL import Image
from test_expert_pilot import NOREFS, annotation, expert

from src.dataset.convert import read_jsonl, write_jsonl
from src.synthetic import (
    EVALUATION_BANNER,
    MARKER,
    PROTECTED_DATA_DIRS,
    SYNTHETIC_LABELS,
    SyntheticSeparationError,
    assert_synthetic_destination,
    assert_synthetic_model_destination,
    synthetic_reasons,
)
from src.training.checkpoint import (
    CheckpointError,
    build_checkpoint,
    check_checkpoint,
    load_checkpoint,
    save_checkpoint,
)
from src.training.model import build_model


def _research_shaped(rec: dict, base_record: dict) -> dict:
    """A synthetic record dressed up in the research schema's fields, as an accident might produce."""
    return base_record | {"image_id": rec["image_id"], "artifact_id": rec["artifact_id"], "image_path": rec["image_path"],
                          "image_sha256": rec["image_sha256"], "script_type": "graffiti", "inscription_present": "yes"}


def _tiny_model():
    from src.training.config import ModelConfig

    return build_model(ModelConfig(name="resnet18", num_classes=4, pretrained=False))


def _ckpt(dataset_type: str, classes, synthetic=None):
    return build_checkpoint(_tiny_model(), model_name="resnet18", class_names=list(classes), epoch=0, metrics={},
                            monitor={"name": "loss", "value": 1.0, "mode": "min"}, config={},
                            dataset_fingerprint="fp", split_digest="sd", git={"commit": "x", "dirty": None},
                            dataset_type=dataset_type, synthetic=synthetic)


FOUR = ("tamil_brahmi", "graffiti", "none", "uncertain")


# 1 ------------------------------------------------------------------------------------------- #
class TestSyntheticFilesCannotEnterResearchData:
    @pytest.mark.parametrize("sub", ["raw", "raw/tamil_nadu_pottery", "external", "interim", "processed", "metadata", "."])
    def test_destination_guard(self, sub):
        with pytest.raises(SyntheticSeparationError):
            assert_synthetic_destination(ROOT / "data" / sub / "synthetic_attempt")

    def test_generator_refuses_data_raw_and_writes_nothing(self, tiny_synthetic):
        from src.synthetic.dataset import generate_dataset

        target = ROOT / "data" / "raw" / "synthetic_attempt"
        with pytest.raises(SyntheticSeparationError):
            generate_dataset(tiny_synthetic["cfg"], target)
        assert not target.exists()

    def test_allowed_destinations(self, tmp_path):
        assert_synthetic_destination(ROOT / "data" / "synthetic")
        assert_synthetic_destination(tmp_path / "anything")
        assert all(d.name in {"raw", "external", "interim", "processed", "metadata"} for d in PROTECTED_DATA_DIRS)

    def test_research_validator_rejects_a_synthetic_record(self, tiny_synthetic, base_record):
        from src.dataset.validation import validate_records

        rec = tiny_synthetic["records"][0]
        as_is = validate_records([rec])
        assert {"E1", "E6"} <= {f.rule for f in as_is.errors}
        dressed = validate_records([_research_shaped(rec, base_record)])
        assert any(f.rule == "E6" for f in dressed.errors), "a synthetic id/path is recognised even in research fields"

    def test_research_loader_rejects_synthetic_records(self, tiny_synthetic, base_record, tmp_path):
        from src.dataset.loader import load_dataset

        rp = tmp_path / "records.jsonl"
        write_jsonl(rp, [_research_shaped(r, base_record) for r in tiny_synthetic["records"][:4]])
        ds = load_dataset(rp, tiny_synthetic["root"])
        assert not ds.records and len(ds.rejections) == 4
        assert all(any(r.startswith("E6") for r in rej.reasons) for rej in ds.rejections)


# 2 ------------------------------------------------------------------------------------------- #
class TestSyntheticCannotSatisfyReadiness:
    def test_gate_on_synthetic_records_fails(self, tiny_synthetic, base_record, tmp_path):
        from src.dataset.readiness import evaluate

        raw = evaluate(tiny_synthetic["root"] / "metadata" / "records.jsonl", tiny_synthetic["root"])
        assert not raw.training_ready
        gates = {g["id"]: g["passed"] for g in raw.gates}
        assert gates["G1"] is False and gates["G4"] is False
        rp = tmp_path / "records.jsonl"
        write_jsonl(rp, [_research_shaped(r, base_record) for r in tiny_synthetic["records"]])
        dressed = evaluate(rp, tiny_synthetic["root"], permit_noncanonical_source=True)
        assert not dressed.training_ready and {g["id"]: g["passed"] for g in dressed.gates}["G4"] is False

    def test_research_training_and_evaluation_stay_blocked(self, tiny_synthetic, capsys):
        from src.evaluation.__main__ import main as evaluation_cli
        from src.training.__main__ import EXIT_BLOCKED
        from src.training.__main__ import main as training_cli

        assert training_cli(["train"]) == EXIT_BLOCKED
        assert "Training blocked" in capsys.readouterr().out
        assert evaluation_cli(["evaluate"]) == 3
        assert "EVALUATION BLOCKED" in capsys.readouterr().out

    def test_research_cli_has_no_synthetic_overrides(self, capsys):
        from src.training.__main__ import EXIT_USAGE
        from src.training.__main__ import main as training_cli

        for extra in (["--epochs", "1"], ["--epochs", "0"], ["--model", "resnet34"]):
            assert training_cli(["train", *extra]) == EXIT_USAGE
            assert "synthetic only" in capsys.readouterr().err


# 3 ------------------------------------------------------------------------------------------- #
class TestSyntheticCheckpointsCannotBeMistaken:
    def test_real_classifier_refuses_a_synthetic_checkpoint(self, tiny_synthetic_model):
        from src.classification import CheckpointClassifier

        with pytest.raises(CheckpointError, match="SYNTHETIC ONLY"):        # the clear reason, not a class-list diff
            CheckpointClassifier(tiny_synthetic_model["checkpoint"])
        with pytest.raises(CheckpointError, match="SYNTHETIC"):
            load_checkpoint(tiny_synthetic_model["checkpoint"], expected_dataset_type="research")

    def test_synthetic_classifier_refuses_a_research_checkpoint(self, tmp_path):
        from src.synthetic.inference import SyntheticCheckpointClassifier

        path = save_checkpoint(_ckpt("research", FOUR), tmp_path / "research.pt")
        with pytest.raises(CheckpointError):
            SyntheticCheckpointClassifier(path)

    def test_structural_rules(self):
        meta = {"marker": MARKER}
        check_checkpoint(_ckpt("synthetic", SYNTHETIC_LABELS, meta))
        check_checkpoint(_ckpt("research", FOUR))
        for bad in (_ckpt("synthetic", SYNTHETIC_LABELS), _ckpt("synthetic", FOUR, meta), _ckpt("research", SYNTHETIC_LABELS)):
            with pytest.raises(CheckpointError):
                check_checkpoint(bad)

    def test_older_checkpoints_without_the_field_are_research(self):
        ck = _ckpt("research", FOUR)
        del ck["dataset_type"]
        check_checkpoint(ck, expected_dataset_type="research")
        with pytest.raises(CheckpointError):
            check_checkpoint(ck, expected_dataset_type="synthetic")

    def test_save_locations(self):
        syn = _ckpt("synthetic", SYNTHETIC_LABELS, {"marker": MARKER})
        for target in (ROOT / "models" / "checkpoints" / "x" / "best.pt", ROOT / "models" / "best.pt"):
            with pytest.raises(CheckpointError):
                save_checkpoint(syn, target)
            assert not target.exists()
        target = ROOT / "models" / "synthetic" / "checkpoints" / "_never" / "best.pt"
        with pytest.raises(CheckpointError):
            save_checkpoint(_ckpt("research", FOUR), target)
        assert not target.exists()

    def test_checkpoint_is_weights_only_loadable(self, tiny_synthetic_model):
        blob = torch.load(tiny_synthetic_model["checkpoint"], map_location="cpu", weights_only=True)
        assert blob["dataset_type"] == "synthetic" and blob["synthetic"]["marker"] == MARKER


# 4 ------------------------------------------------------------------------------------------- #
class TestSyntheticMetricsStayOutOfArchaeologicalHistory:
    def test_experiment_records_are_filed_by_dataset_type(self, tiny_synthetic_model):
        from src.training.experiment import ExperimentRecord

        rec = ExperimentRecord.load(tiny_synthetic_model["experiment"])
        assert rec.dataset_type == "synthetic"
        with pytest.raises(SyntheticSeparationError):
            rec.save(ROOT / "models" / "experiments")
        rec.dataset_type = "research"
        with pytest.raises(SyntheticSeparationError):
            rec.save(ROOT / "models" / "synthetic" / "experiments")
        assert not (ROOT / "models" / "experiments" / rec.experiment_id).exists()

    def test_synthetic_training_config_refuses_research_directories(self, tmp_path):
        import yaml

        from src.synthetic.train import SyntheticTrainingConfig
        from src.training.config import TrainingConfigError

        data = yaml.safe_load((ROOT / "configs" / "synthetic_training.yaml").read_text(encoding="utf-8"))
        for section, key, value in (("checkpoint", "directory", "models/checkpoints"),
                                    ("experiments", "directory", "models/experiments"),
                                    ("checkpoint", "directory", "data/raw/x")):
            bad = json.loads(json.dumps(data))
            bad["training"][section][key] = value
            p = tmp_path / "bad.yaml"
            p.write_text(yaml.safe_dump(bad), encoding="utf-8")
            with pytest.raises(TrainingConfigError):
                SyntheticTrainingConfig.load(p)
        wrong = json.loads(json.dumps(data)) | {"dataset_type": "research"}
        p.write_text(yaml.safe_dump(wrong), encoding="utf-8")
        with pytest.raises(TrainingConfigError):
            SyntheticTrainingConfig.load(p)

    def test_synthetic_reports_carry_the_banner(self):
        import numpy as np

        from src.evaluation.metrics import evaluate_predictions

        rep = evaluate_predictions([0, 1, 2, 3], [0, 1, 2, 2], list(SYNTHETIC_LABELS), y_prob=np.eye(4)[[0, 1, 2, 2]],
                                   provenance="synthetic", unit="artifact")
        assert EVALUATION_BANNER in rep.render() and EVALUATION_BANNER in rep.message

    def test_workflow_evaluation_stage_ignores_synthetic_runs(self, tiny_synthetic_model):
        from src.workflow import workflow_status

        stage = {s.name: s for s in workflow_status(decode_images=False).stages}["evaluation"]
        assert stage.status != "PASS"
        assert not str(tiny_synthetic_model["experiment"]).startswith(str(ROOT / "models" / "experiments"))

    def test_report_writer_refuses_research_directories(self):
        with pytest.raises(SyntheticSeparationError):
            assert_synthetic_model_destination(ROOT / "models" / "experiments" / "x.json")


# 5 ------------------------------------------------------------------------------------------- #
class TestSyntheticLabelsCannotBePromoted:
    def test_records_containing_synthetic_data_block_promotion(self, tiny_synthetic, world, tmp_path):
        from src.annotation.promote import plan_promotion

        rp = tmp_path / "records.jsonl"
        write_jsonl(rp, world["records"] + [tiny_synthetic["records"][0]])
        plan = plan_promotion(store=world["store"], records_path=rp, data_root=world["raw"], ref_statuses={},
                              **NOREFS)
        assert not plan.executable and any(e.startswith("P0") for e in plan.validation_errors)

    def test_a_synthetic_artifact_is_rejected(self, world):
        from src.annotation.promote import plan_promotion

        plan = plan_promotion(store=world["store"], records_path=world["records_path"], data_root=world["raw"],
                              artifact_ids=["SYNTH-A0001"], ref_statuses={}, **NOREFS)
        assert [r.status for r in plan.rejections] == ["synthetic"] and "P0" in plan.rejections[0].reasons[0]


# 6 ------------------------------------------------------------------------------------------- #
class TestSyntheticAnnotationsRejected:
    def test_store_refuses_annotations_of_synthetic_artifacts(self, world, tiny_synthetic):
        from src.annotation.store import AnnotationRejected

        rec = tiny_synthetic["records"][0]
        for a in (expert(rec["artifact_id"]), annotation(rec["artifact_id"])):
            a["image_ids"] = [rec["image_id"]]
            with pytest.raises(AnnotationRejected) as err:
                world["store"].append(a, **NOREFS)
            assert any(p.rule == "N17" for p in err.value.validation.problems)
        assert world["store"].all() == []

    def test_synthetic_label_on_a_real_artifact_is_refused(self, world):
        from src.annotation.validate import validate_annotation

        a = expert(world["arts"][0])
        a["inscription"]["script_type"] = "synthetic_graffiti_like"
        assert "N17" in {p.rule for p in validate_annotation(a)}


# 7 ------------------------------------------------------------------------------------------- #
class TestSyntheticProvenancePreserved:
    def test_every_image_is_reproducible_from_its_provenance(self, tiny_synthetic):
        from src.synthetic.generator import build_artifact, generate_view

        prov = read_jsonl(tiny_synthetic["root"] / "manifests" / "provenance.jsonl")
        for p in prov[:: max(1, len(prov) // 5)]:
            seed, idx, _ = p["random_streams"]["view"]
            assert seed == tiny_synthetic["cfg"].seed
            gv = generate_view(tiny_synthetic["cfg"], build_artifact(tiny_synthetic["cfg"], idx, p["class"]),
                               p["random_streams"]["view"][2] - 100)
            assert gv.sha256 == p["image_sha256"] and gv.view_params == p["view_params"]

    def test_lock_records_every_fingerprint(self, tiny_synthetic):
        lock = json.loads((tiny_synthetic["root"] / "manifests" / "dataset_lock.json").read_text(encoding="utf-8"))
        for key in ("records_fingerprint", "image_set_fingerprint", "metadata_fingerprint", "config_digest",
                    "split_digest", "synthetic_fingerprint", "generator_version", "generation_seed"):
            assert lock[key] not in (None, ""), key
        assert lock["dataset_type"] == "synthetic" and lock["synthetic_marker"] == MARKER


# 8 ------------------------------------------------------------------------------------------- #
class TestDatasetTypeAlwaysExplicit:
    def test_everywhere(self, tiny_synthetic, tiny_synthetic_model, world):
        from src.inference import analyze

        assert all(r["dataset_type"] == "synthetic" for r in tiny_synthetic["records"])
        assert all(p["dataset_type"] == "synthetic"
                   for p in read_jsonl(tiny_synthetic["root"] / "manifests" / "provenance.jsonl"))
        assert load_checkpoint(tiny_synthetic_model["checkpoint"])["dataset_type"] == "synthetic"
        assert json.loads(tiny_synthetic_model["experiment"].read_text(encoding="utf-8"))["dataset_type"] == "synthetic"
        index = {r["image_sha256"]: r for r in tiny_synthetic["records"]}
        rec = tiny_synthetic["records"][0]
        buf = io.BytesIO()
        Image.new("RGB", (70, 70), (5, 5, 5)).save(buf, format="PNG")
        kinds = {analyze(tiny_synthetic["root"] / rec["image_path"], records=[], synthetic_records=index).dataset_type,
                 analyze(buf.getvalue(), records=[], synthetic_records=index).dataset_type,
                 analyze(world["raw"] / world["records"][0]["image_path"], records=world["records"], store=world["store"],
                         synthetic_records=index).dataset_type}
        assert kinds == {"synthetic", "unregistered", "research"}

    def test_reasons_recognise_synthetic_data(self, tiny_synthetic, base_record):
        assert synthetic_reasons(tiny_synthetic["records"][0])
        assert synthetic_reasons({"artifact_id": "SYNTH-A0001"}) and synthetic_reasons({"dataset_type": "synthetic"})
        assert synthetic_reasons(base_record) == []


# 9 ------------------------------------------------------------------------------------------- #
class TestRemovingSyntheticDataChangesNothingReal:
    def test_readiness_is_independent_of_synthetic_data(self, tiny_synthetic_config_dir):
        import shutil

        from src.dataset.readiness import count_images, evaluate

        before = evaluate().to_dict()
        images = count_images()
        from conftest import tiny_synthetic_config

        from src.synthetic.dataset import generate_dataset

        generate_dataset(tiny_synthetic_config(), tiny_synthetic_config_dir)
        during = evaluate().to_dict()
        shutil.rmtree(tiny_synthetic_config_dir)
        after = evaluate().to_dict()
        assert before == during == after and count_images() == images

    def test_research_gate_code_never_reads_synthetic_locations(self):
        import src.dataset.loader as loader
        import src.dataset.readiness as readiness

        for module in (readiness, loader):
            src = inspect.getsource(module)
            for name in ("src.synthetic", "data/synthetic", "SYNTHETIC_ROOT", "RECORDS_PATH as", "models/synthetic"):
                assert name not in src, (module.__name__, name)


@pytest.fixture
def tiny_synthetic_config_dir(tmp_path) -> Path:
    return tmp_path / "throwaway_synthetic"


# 10 ------------------------------------------------------------------------------------------ #
class TestRealGatesUnchanged:
    def test_gate_table_is_pinned(self):
        from src.dataset.readiness import GATES

        assert GATES == {
            "G1": ("records come from the canonical research dataset", "integrity", "engineering"),
            "G2": ("records exist", "data_presence", "engineering"),
            "G3": ("image files exist", "data_presence", "engineering"),
            "G4": ("metadata validation passes", "validation", "engineering"),
            "G5": ("every record loads and its hash is verified", "validation", "engineering"),
            "G6": ("no photograph is recorded under two artifacts", "leakage", "engineering"),
            "G7": ("every training label has a known source", "labels", "project_methodology"),
            "G8": ("research use of every training image is permitted", "rights", "rights"),
            "G9": ("every trainable class is present", "classes", "project_methodology"),
            "G10": ("minimum artifacts per class", "statistics", "engineering"),
            "G11": ("verified artifact-level split manifest", "leakage", "engineering"),
        }

    def test_no_relaxing_parameter_exists(self):
        from src.dataset.readiness import assert_training_ready
        from src.training.run import run_training

        assert list(inspect.signature(assert_training_ready).parameters) == ["records_path", "data_root", "manifest_path"]
        assert list(inspect.signature(run_training).parameters) == ["config_path", "manifest_path", "resume_from"]

    def test_project_classes_and_thresholds_unchanged(self):
        from src.dataset.classes import ClassSpec
        from src.dataset.splits import SplitSettings

        spec = ClassSpec.from_config()
        assert spec.trainable == FOUR and not set(spec.trainable) & set(SYNTHETIC_LABELS)
        s = SplitSettings.from_config()
        assert s.min_artifacts_per_class_for_holdout == 20 and s.k_folds == 5 and s.ratios == (0.7, 0.15, 0.15)

    def test_live_gate_blocks_and_ignores_synthetic(self):
        from src.dataset.readiness import evaluate

        rep = evaluate()
        assert not rep.training_ready
        assert not any(c in SYNTHETIC_LABELS for c in rep.artifacts_by_class)
