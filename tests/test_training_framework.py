"""Milestone 5 training framework.

The engine is exercised on tiny SYNTHETIC tensors (random noise with arbitrary labels)
on the CPU, with pretrained=False so no weights are downloaded. That checks plumbing
only. It is not training on data, and no metric here is a result.
"""

from __future__ import annotations

import warnings
from pathlib import Path

import numpy as np
import pytest
import torch
import yaml
from PIL import Image
from torch.utils.data import DataLoader, Dataset

from src.dataset.classes import ClassSpec
from src.dataset.loader import load_dataset
from src.training.__main__ import EXIT_BLOCKED
from src.training.__main__ import main as training_cli
from src.training.augmentation import (
    HorizontalFlipWarning,
    ImageGeometry,
    SafeScaleShift,
    SmallRotation,
    build_eval_transform,
    build_train_transform,
)
from src.training.checkpoint import (
    REQUIRED_KEYS,
    CheckpointError,
    build_checkpoint,
    check_checkpoint,
    load_checkpoint,
    save_checkpoint,
)
from src.training.config import (
    TRAINING_CONFIG_PATH,
    AugmentationConfig,
    ModelConfig,
    TrainingConfig,
    TrainingConfigError,
)
from src.training.data import DataError, PotteryImageDataset, make_loader
from src.training.engine import EarlyStopping, Trainer
from src.training.experiment import ExperimentRecord, make_experiment_id
from src.training.model import (
    build_model,
    count_parameters,
    num_outputs,
    set_backbone_trainable,
)
from src.training.run import BLOCKED_NO_DATA, run_training
from src.training.runtime import DeviceError, git_commit, seed_everything, select_device

FOUR = ("tamil_brahmi", "graffiti", "none", "uncertain")


def _cfg(**sections) -> TrainingConfig:
    data = yaml.safe_load(TRAINING_CONFIG_PATH.read_text(encoding="utf-8"))
    for name, values in sections.items():
        data[name] = {**data.get(name, {}), **values}
    return TrainingConfig.from_dict(data)


# --------------------------------------------------------------------------- #
# Configuration
# --------------------------------------------------------------------------- #


class TestConfig:
    def test_shipped_config_is_valid_and_consistent(self):
        cfg = TrainingConfig.load()
        cfg.check_against_project()
        assert cfg.model.name == "resnet18" and cfg.model.num_classes == 4
        assert cfg.data.batch_size <= 32          # conservative for 6 GB
        assert cfg.augmentation.horizontal_flip is False
        assert cfg.augmentation.hue == 0.0

    def test_required_keys_present(self):
        d = TrainingConfig.load().to_dict()
        for key in ("model", "data", "optimization", "runtime", "augmentation", "imbalance"):
            assert key in d
        for key in ("name", "num_classes", "pretrained", "freeze_backbone"):
            assert key in d["model"]
        for key in ("image_size", "batch_size", "num_workers"):
            assert key in d["data"]
        for key in ("epochs", "learning_rate", "weight_decay", "optimizer", "scheduler"):
            assert key in d["optimization"]
        for key in ("seed", "device", "mixed_precision"):
            assert key in d["runtime"]

    def test_unknown_key_is_an_error(self):
        with pytest.raises(TrainingConfigError, match="unknown key"):
            _cfg(model={"nme": "resnet18"})

    def test_bad_values_are_errors(self):
        with pytest.raises(TrainingConfigError, match="model.name"):
            _cfg(model={"name": "vit_huge"})
        with pytest.raises(TrainingConfigError, match="rotation_degrees"):
            _cfg(augmentation={"rotation_degrees": 90})
        with pytest.raises(TrainingConfigError, match="hue"):
            _cfg(augmentation={"hue": 0.2})
        with pytest.raises(TrainingConfigError, match="mode"):
            _cfg(early_stopping={"monitor": "loss", "mode": "max"})

    def test_two_imbalance_strategies_are_rejected(self):
        with pytest.raises(TrainingConfigError, match="ONE"):
            _cfg(imbalance={"strategy": ["class_weighted_loss", "weighted_sampler"]})

    def test_class_count_must_match_project(self):
        with pytest.raises(TrainingConfigError, match="num_classes"):
            _cfg(model={"num_classes": 5}).check_against_project()

    def test_image_size_must_match_preprocessing(self):
        with pytest.raises(TrainingConfigError, match="image_size"):
            _cfg(data={"image_size": 256}).check_against_project()


# --------------------------------------------------------------------------- #
# Model
# --------------------------------------------------------------------------- #


class TestModel:
    @pytest.mark.parametrize("n", [2, 4, 6])
    def test_configurable_class_count(self, n):
        model = build_model(ModelConfig(pretrained=False, num_classes=n))
        assert num_outputs(model) == n
        model.eval()
        assert model(torch.zeros(2, 3, 64, 64)).shape == (2, n)

    @pytest.mark.parametrize("name", ["resnet18", "resnet34", "efficientnet_b0", "mobilenet_v3_large"])
    def test_supported_backbones_build(self, name):
        model = build_model(ModelConfig(name=name, pretrained=False, num_classes=4))
        model.eval()
        assert model(torch.zeros(1, 3, 64, 64)).shape == (1, 4)

    def test_frozen_backbone_trains_only_the_head(self):
        model = build_model(ModelConfig(pretrained=False, freeze_backbone=True))
        counts = count_parameters(model)
        assert counts["trainable"] == 512 * 4 + 4       # resnet18 fc: 512 -> 4
        set_backbone_trainable(model, True)
        assert count_parameters(model)["trainable"] == counts["total"]

    def test_pretrained_false_does_not_download(self, monkeypatch):
        import torch.hub

        def fail(*a, **k):
            raise AssertionError("network access attempted")

        monkeypatch.setattr(torch.hub, "load_state_dict_from_url", fail)
        build_model(ModelConfig(pretrained=False))


# --------------------------------------------------------------------------- #
# Device / runtime
# --------------------------------------------------------------------------- #


class TestRuntime:
    def test_cpu_request(self):
        info = select_device("cpu")
        assert info.device == "cpu" and not info.amp_enabled

    def test_auto_falls_back_to_cpu_without_cuda(self):
        info = select_device("auto", cuda_available=False)
        assert info.device == "cpu" and info.fallback_reason and not info.amp_enabled

    def test_explicit_cuda_without_cuda_is_an_error(self):
        with pytest.raises(DeviceError):
            select_device("cuda", cuda_available=False)

    @pytest.mark.skipif(not torch.cuda.is_available(), reason="no CUDA device")
    def test_cuda_selected_when_available(self):
        info = select_device("auto")
        assert info.device == "cuda" and info.amp_enabled and info.gpu_name

    def test_seeding_is_reproducible(self):
        seed_everything(123)
        a = torch.rand(5)
        seed_everything(123)
        assert torch.equal(a, torch.rand(5))

    def test_git_commit_is_recorded(self):
        info = git_commit()
        assert set(info) == {"commit", "dirty"}


# --------------------------------------------------------------------------- #
# Augmentation
# --------------------------------------------------------------------------- #


def _geometry(size=64) -> ImageGeometry:
    return ImageGeometry.from_project(size)


class TestAugmentation:
    def test_eval_transform_is_deterministic(self):
        img = Image.new("RGB", (80, 50), (120, 60, 30))
        t = build_eval_transform(_geometry())
        assert t.deterministic and torch.equal(t(img), t(img))
        assert t(img).shape == (3, 64, 64)

    def test_train_transform_is_random_and_shaped(self):
        torch.manual_seed(0)
        img = Image.new("RGB", (80, 50), (120, 60, 30))
        t = build_train_transform(AugmentationConfig(), _geometry())
        assert not t.deterministic and t(img).shape == (3, 64, 64)

    def test_no_flip_by_default(self):
        names = build_train_transform(AugmentationConfig(), _geometry()).describe()
        assert "RandomHorizontalFlip" not in names and "RandomVerticalFlip" not in names

    def test_enabling_flip_warns(self):
        with pytest.warns(HorizontalFlipWarning):
            build_train_transform(AugmentationConfig(horizontal_flip=True), _geometry())

    def test_no_destructive_transforms(self):
        names = " ".join(build_train_transform(AugmentationConfig(), _geometry()).describe())
        for banned in ("RandomResizedCrop", "Perspective", "Elastic", "Erasing", "Blur"):
            assert banned not in names

    def test_scale_shift_never_crops(self):
        torch.manual_seed(0)
        op = SafeScaleShift(0.8, translate=True, fill=(0, 0, 0))
        for _ in range(30):
            out = op(Image.new("RGB", (64, 64), (255, 0, 0)))
            bbox = out.getbbox()
            assert bbox is not None
            w, h = bbox[2] - bbox[0], bbox[3] - bbox[1]
            assert w == h                                   # whole square kept, not clipped
            arr = np.asarray(out)
            red = int(np.all(arr == (255, 0, 0), axis=-1).sum())
            assert red == w * h

    def test_rotation_expands_rather_than_cropping(self):
        torch.manual_seed(0)
        img = Image.new("RGB", (60, 40), (200, 200, 200))
        out = SmallRotation(5, (0, 0, 0))(img)
        assert out.size[0] >= 60 and out.size[1] >= 40

    def test_eval_uses_letterbox_not_crop(self):
        img = Image.new("RGB", (200, 50), (255, 255, 255))
        tensor = build_eval_transform(ImageGeometry(64, (0, 0, 0), "bilinear",
                                                    (0, 0, 0), (1, 1, 1)))(img)
        assert tensor[:, 0, :].max() == 0          # top rows are padding
        assert tensor[:, 32, :].min() > 0.9        # middle row is the full-width image


# --------------------------------------------------------------------------- #
# Data
# --------------------------------------------------------------------------- #


class TestData:
    def test_dataset_items(self, tmp_path, synthetic_corpus):
        c = synthetic_corpus(tmp_path, {"tamil_brahmi": 1, "none": 1})
        ds = load_dataset(c["records_path"], c["data_root"])
        spec = ClassSpec.from_config()
        tds = PotteryImageDataset(ds.records, spec, build_eval_transform(_geometry()))
        x, y, i = tds[0]
        assert x.shape == (3, 64, 64) and y == spec.index_of(ds.records[i].script_type)

    def test_held_out_label_is_refused(self, tmp_path, synthetic_corpus):
        c = synthetic_corpus(tmp_path, {"other_script": 1})
        ds = load_dataset(c["records_path"], c["data_root"])
        with pytest.raises(DataError, match="non-trainable"):
            PotteryImageDataset(ds.records, ClassSpec.from_config(), build_eval_transform(_geometry()))

    def test_weighted_sampler_is_seeded(self, tmp_path, synthetic_corpus):
        c = synthetic_corpus(tmp_path, {cl: n for cl, n in zip(FOUR, (1, 2, 3, 4))})
        ds = load_dataset(c["records_path"], c["data_root"])
        tds = PotteryImageDataset(ds.records, ClassSpec.from_config(),
                                  build_eval_transform(_geometry(32)))

        def order():
            loader = make_loader(tds, batch_size=4, train=True, seed=7,
                                 imbalance_strategy="weighted_sampler")
            return [int(i) for _, _, idx in loader for i in idx]

        assert order() == order()


# --------------------------------------------------------------------------- #
# Engine (synthetic tensors)
# --------------------------------------------------------------------------- #


class _NoiseDataset(Dataset):
    """SYNTHETIC random tensors with arbitrary labels. Exercises plumbing only."""

    def __init__(self, n: int, classes: int, size: int = 32, seed: int = 0) -> None:
        g = torch.Generator().manual_seed(seed)
        self.x = torch.randn(n, 3, size, size, generator=g)
        self.y = [i % classes for i in range(n)]

    def __len__(self) -> int:
        return len(self.y)

    def __getitem__(self, i):
        return self.x[i], self.y[i], i


def _trainer(tmp_path: Path, **sections) -> Trainer:
    defaults = dict(
        model={"pretrained": False, "unfreeze_backbone_at_epoch": 1},
        optimization={"epochs": 2},
        runtime={"device": "cpu", "mixed_precision": False},
    )
    for k, v in sections.items():
        defaults[k] = {**defaults.get(k, {}), **v}
    cfg = _cfg(**defaults)
    return Trainer(build_model(cfg.model), cfg, FOUR, select_device("cpu"),
                   class_weights=[1.0, 2.0, 1.0, 0.5], checkpoint_dir=tmp_path / "ckpt",
                   provenance={"dataset_fingerprint": "SYNTHETIC", "split_digest": "SYNTHETIC",
                               "git": {"commit": "test", "dirty": None}})


class TestEngine:
    def test_fit_runs_and_writes_checkpoints(self, tmp_path):
        trainer = _trainer(tmp_path)
        loader = DataLoader(_NoiseDataset(16, 4), batch_size=8)
        result = trainer.fit(loader, DataLoader(_NoiseDataset(8, 4, seed=1), batch_size=8))
        assert result.epochs_run == 2 and result.best_epoch is not None
        assert Path(result.best_checkpoint).exists() and Path(result.last_checkpoint).exists()
        assert result.history[0].backbone_trainable is False
        assert result.history[1].backbone_trainable is True        # unfrozen at epoch 1

    def test_checkpoint_structure(self, tmp_path):
        trainer = _trainer(tmp_path)
        loader = DataLoader(_NoiseDataset(8, 4), batch_size=8)
        result = trainer.fit(loader, loader)
        ckpt = load_checkpoint(result.best_checkpoint, class_names=FOUR)
        for key in REQUIRED_KEYS:
            assert key in ckpt
        assert ckpt["class_names"] == list(FOUR) and ckpt["model_name"] == "resnet18"
        model = build_model(ModelConfig(pretrained=False))
        model.load_state_dict(ckpt["state_dict"])

    def test_checkpoint_class_mismatch_is_refused(self, tmp_path):
        model = build_model(ModelConfig(pretrained=False))
        ckpt = build_checkpoint(model, model_name="resnet18", class_names=FOUR, epoch=0,
                                metrics={}, monitor={}, config={}, dataset_fingerprint="x",
                                split_digest="y", git={})
        path = save_checkpoint(ckpt, tmp_path / "c.pt")
        with pytest.raises(CheckpointError, match="class list mismatch"):
            load_checkpoint(path, class_names=("a", "b", "c", "d"))
        with pytest.raises(CheckpointError, match="missing"):
            check_checkpoint({"format_version": "1.0.0"})

    def test_early_stopping(self):
        es = EarlyStopping("max", patience=2, min_delta=0.01)
        assert es.improved(0.5) and not es.improved(0.505) and not es.should_stop
        assert not es.improved(0.4) and es.should_stop
        es_min = EarlyStopping("min", patience=1, min_delta=0.0)
        assert es_min.improved(1.0) and es_min.improved(0.9) and not es_min.improved(0.95)

    def test_early_stop_halts_fit(self, tmp_path):
        trainer = _trainer(tmp_path, optimization={"epochs": 10, "learning_rate": 1e-12,
                                                   "backbone_learning_rate": 1e-12},
                           early_stopping={"patience": 1, "min_delta": 0.5})
        loader = DataLoader(_NoiseDataset(8, 4), batch_size=8)
        result = trainer.fit(loader, loader)
        assert result.stopped_early and result.epochs_run < 10

    @pytest.mark.skipif(not torch.cuda.is_available(), reason="no CUDA device")
    def test_one_step_on_cuda_with_amp(self, tmp_path):
        cfg = _cfg(model={"pretrained": False}, optimization={"epochs": 1},
                   runtime={"device": "cuda", "mixed_precision": True})
        trainer = Trainer(build_model(cfg.model), cfg, FOUR, select_device("cuda"))
        assert trainer.amp
        loader = DataLoader(_NoiseDataset(8, 4), batch_size=4)
        assert trainer.fit(loader, loader).epochs_run == 1

    def test_experiment_record_roundtrip(self, tmp_path):
        rec = ExperimentRecord(
            experiment_id=make_experiment_id("SYNTHETIC" * 3, 1), timestamp="t", status="completed",
            git_commit="c", git_dirty=False, dataset_version={"fingerprint": "SYNTHETIC"},
            config={}, model={}, seed=1, device={}, environment={}, split={},
            training_split={}, validation_split={}, test_split=None)
        path = rec.save(tmp_path)
        assert ExperimentRecord.load(path).experiment_id == rec.experiment_id


# --------------------------------------------------------------------------- #
# The training command on the real (empty) dataset
# --------------------------------------------------------------------------- #


class TestTrainingIsBlocked:
    def test_run_training_is_blocked(self, live_research):
        outcome = run_training()
        assert outcome.status == "blocked"
        assert outcome.message.startswith("Training blocked:")
        if not live_research["records"]:
            assert outcome.message == BLOCKED_NO_DATA
        else:
            assert "No expert-labelled training images are available" in outcome.message
        assert not outcome.experiments

    def test_train_command_stops_safely(self, capsys):
        with warnings.catch_warnings():
            warnings.simplefilter("error")        # no warnings, no crash
            code = training_cli(["train"])
        assert code == EXIT_BLOCKED
        assert "Training blocked:" in capsys.readouterr().out

    def test_no_checkpoint_or_experiment_was_written(self):
        from src.dataset.schema import ROOT

        for d in ("models/checkpoints", "models/experiments"):
            p = ROOT / d
            assert not p.exists() or not any(p.iterdir())
