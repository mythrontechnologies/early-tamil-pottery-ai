"""Synthetic training run.   SYNTHETIC TRAINING — NOT ARCHAEOLOGICAL MODEL EVALUATION

    python -m src.training train --dataset synthetic [--config configs/synthetic_training.yaml]
                                                     [--model resnet18] [--epochs N] [--resume CKPT]

The research path (``python -m src.training train``) is untouched: it still calls the readiness
gate first and stays blocked. This path never consults or satisfies that gate. It trains the
SAME architecture with the SAME Trainer, datasets, loaders, transforms, checkpoint format and
metrics on the synthetic engineering dataset, and files everything under ``models/synthetic/``:

    models/synthetic/checkpoints/<experiment>/{best,last}.pt   dataset_type=synthetic, marker, fingerprints
    models/synthetic/experiments/<experiment>/experiment.json  dataset_type=synthetic

Every number produced here measures the pipeline on generated images. None is an archaeological
result, and none may be reported as one.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import yaml

from src.dataset.convert import read_jsonl
from src.dataset.loader import DatasetRecord
from src.dataset.sampling import class_counts, class_weights, imbalance_table, render_imbalance_table
from src.dataset.schema import ROOT, load_config
from src.dataset.splits import partition_records
from src.evaluation.metrics import aggregate_by_artifact, evaluate_predictions
from src.training.augmentation import ImageGeometry, build_eval_transform, build_train_transform
from src.training.checkpoint import load_checkpoint, model_fingerprint
from src.training.config import TrainingConfig, TrainingConfigError
from src.training.data import PotteryImageDataset, make_loader
from src.training.engine import Trainer
from src.training.experiment import ExperimentRecord, make_experiment_id, split_summary
from src.training.model import build_model, count_parameters
from src.training.runtime import environment, git_commit, seed_everything, select_device

from . import (
    ARCHITECTURE_SLOTS,
    DATASET_TYPE,
    LABEL_WARNING,
    MARKER,
    PURPOSE,
    SYNTHETIC_LABELS,
    SYNTHETIC_MODELS_ROOT,
    TRAINING_BANNER,
    TRAINING_CONFIG_PATH,
    SyntheticSeparationError,
    assert_synthetic_model_destination,
)
from .config import SyntheticDatasetConfig
from .dataset import (
    SyntheticPaths,
    find_manifest,
    load_synthetic_dataset,
    synthetic_class_spec,
    synthetic_fingerprint,
)
from .generator import GENERATOR_VERSION

READINESS_NOTE = {
    "archaeological_readiness_gate": "not consulted",
    "training_ready_for_archaeology": False,
    "note": "Synthetic data can never satisfy the archaeological readiness gate (G1-G11); this run says nothing about it.",
}


@dataclass
class SyntheticTrainingConfig:
    training: TrainingConfig
    dataset_config: str = "configs/synthetic_dataset.yaml"
    reports_directory: str = "models/synthetic/reports"
    path: str = ""

    @classmethod
    def load(cls, path: Path | str | None = None, *, model: str | None = None,
             epochs: int | None = None) -> SyntheticTrainingConfig:
        p = Path(path) if path else TRAINING_CONFIG_PATH
        if not p.exists():
            raise TrainingConfigError(f"synthetic training config not found: {p}")
        data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
        unknown = sorted(set(data) - {"dataset_type", "dataset_config", "reports_directory", "training"})
        if unknown:
            raise TrainingConfigError(f"unknown top-level key(s) in {p.name}: {', '.join(unknown)}")
        if data.get("dataset_type") != DATASET_TYPE:
            raise TrainingConfigError(f"{p.name}: dataset_type must be {DATASET_TYPE!r} (this is the synthetic-only path)")
        training = dict(data.get("training") or {})
        if model:
            training["model"] = {**training.get("model", {}), "name": model}
        if epochs:
            training["optimization"] = {**training.get("optimization", {}), "epochs": int(epochs)}
        cfg = cls(TrainingConfig.from_dict(training), str(data.get("dataset_config", cls.dataset_config)),
                  str(data.get("reports_directory", cls.reports_directory)), str(p))
        cfg.validate()
        return cfg

    def validate(self) -> None:
        t = self.training
        problems = []
        for name, d in (("checkpoint.directory", t.checkpoint.directory), ("experiments.directory", t.experiments.directory),
                        ("reports_directory", self.reports_directory)):
            target = resolve(d)          # inside the repository: models/synthetic/ only (a temp dir is fine)
            try:
                assert_synthetic_model_destination(target)
                if _inside(target, ROOT):
                    target.resolve().relative_to(SYNTHETIC_MODELS_ROOT.resolve())
            except (SyntheticSeparationError, ValueError):
                problems.append(f"{name}={d!r} must be inside models/synthetic/")
        if t.model.num_classes != len(SYNTHETIC_LABELS):
            problems.append(f"model.num_classes={t.model.num_classes}; the synthetic task has {len(SYNTHETIC_LABELS)} classes")
        target = load_config().get("preprocessing", {}).get("target_size")
        if target is not None and int(target) != t.data.image_size:
            problems.append(f"data.image_size={t.data.image_size} but preprocessing.target_size={target}")
        if problems:
            raise TrainingConfigError("invalid synthetic training config:\n  - " + "\n  - ".join(problems))

    def dataset_cfg(self) -> SyntheticDatasetConfig:
        return SyntheticDatasetConfig.load(resolve(self.dataset_config))


def _inside(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
    except ValueError:
        return False
    return True


def resolve(path: str | Path) -> Path:
    p = Path(path)
    return p if p.is_absolute() else ROOT / p


@dataclass
class SyntheticRunOutcome:
    status: str                      # completed | blocked
    message: str
    experiment: str | None = None
    best_checkpoint: str | None = None
    last_checkpoint: str | None = None
    summary: dict[str, Any] = field(default_factory=dict)


def partition_metrics(trainer: Trainer, records: list[DatasetRecord], geometry: ImageGeometry, batch_size: int,
                 seed: int) -> dict[str, Any]:
    """Image- and artifact-level synthetic metrics of ``trainer.model`` on ``records``."""
    spec = synthetic_class_spec()
    ds = PotteryImageDataset(records, spec, build_eval_transform(geometry))
    preds = trainer.predict(make_loader(ds, train=False, batch_size=batch_size, seed=seed))
    image = evaluate_predictions(preds.y_true, preds.y_pred, spec.trainable, y_prob=preds.probabilities,
                                 provenance="synthetic", unit="image")
    aids = [records[i].artifact_id for i in preds.indices]
    _, a_true, a_prob = aggregate_by_artifact(aids, preds.y_true, preds.probabilities)
    artifact = evaluate_predictions(a_true, list(np.argmax(a_prob, axis=1)), spec.trainable, y_prob=a_prob,
                                    provenance="synthetic", unit="artifact")
    return {"image": image, "artifact": artifact, "predictions": preds, "artifact_probabilities": a_prob}


def run_synthetic_training(config_path: Path | str | None = None, manifest_path: Path | str | None = None,
                           resume_from: Path | str | None = None, *, model: str | None = None,
                           epochs: int | None = None, root: Path | str | None = None) -> SyntheticRunOutcome:
    print("=" * 72 + f"\n{TRAINING_BANNER}\n{PURPOSE}\n" + "=" * 72, flush=True)
    scfg = SyntheticTrainingConfig.load(config_path, model=model, epochs=epochs)
    cfg, dcfg = scfg.training, scfg.dataset_cfg()
    spec = synthetic_class_spec()
    paths = SyntheticPaths.at(root)
    dataset = load_synthetic_dataset(paths.root)
    if dataset.is_empty:
        return SyntheticRunOutcome("blocked", "No synthetic dataset: run `python -m src.synthetic generate`.")
    if not dataset.ok:
        return SyntheticRunOutcome("blocked", f"Synthetic dataset invalid: {[str(r) for r in dataset.rejections[:3]]}")
    manifest = find_manifest(dataset, paths.root, path=manifest_path)
    parts = partition_records(manifest, dataset)
    train_recs, val_recs, test_recs = parts["train"], parts["val"], parts["test"]
    raw = read_jsonl(paths.records)
    gens = {r["synthetic_generator_version"] for r in raw}
    if gens != {GENERATOR_VERSION}:
        return SyntheticRunOutcome("blocked", f"dataset made by generator {sorted(gens)}, code is {GENERATOR_VERSION}; regenerate")
    fingerprint = synthetic_fingerprint(raw, generator_version=GENERATOR_VERSION, config_digest=dcfg.digest,
                                        split_digest=manifest.digest)

    print("Class report (synthetic training partition):")
    print(render_imbalance_table(imbalance_table([r.record for r in train_recs], spec)))
    seed_state = seed_everything(cfg.runtime.seed, deterministic=cfg.runtime.deterministic)
    device = select_device(cfg.runtime.device, mixed_precision=cfg.runtime.mixed_precision)
    geometry = ImageGeometry.from_project(cfg.data.image_size)
    common: dict[str, Any] = dict(batch_size=cfg.data.batch_size, seed=cfg.runtime.seed, num_workers=cfg.data.num_workers,
                  pin_memory=cfg.data.pin_memory and device.device == "cuda")
    train_loader = make_loader(PotteryImageDataset(train_recs, spec, build_train_transform(cfg.augmentation, geometry)),
                               train=True, imbalance_strategy=cfg.imbalance.strategy, count_unit=cfg.imbalance.count_unit,
                               equalise_artifacts=cfg.imbalance.equalise_artifacts, **common)
    val_loader = make_loader(PotteryImageDataset(val_recs, spec, build_eval_transform(geometry)), train=False, **common)
    weights = None
    if cfg.imbalance.strategy == "class_weighted_loss":
        counts = class_counts([r.record for r in train_recs], spec, cfg.imbalance.count_unit)  # type: ignore[arg-type]
        weights = class_weights(counts, spec.trainable)

    exp_id = f"synthetic_{make_experiment_id(dataset.fingerprint, cfg.runtime.seed)}_{cfg.model.name}"
    ckpt_dir = assert_synthetic_model_destination(resolve(cfg.checkpoint.directory) / exp_id)
    git, env = git_commit(), environment()
    meta = {"marker": MARKER, "banner": TRAINING_BANNER, "purpose": PURPOSE, "label_warning": LABEL_WARNING,
            "experiment_id": exp_id, "generator_version": GENERATOR_VERSION, "generation_seed": dcfg.seed,
            "dataset_config_digest": dcfg.digest, "synthetic_fingerprint": fingerprint,
            "architecture_slots": ARCHITECTURE_SLOTS, "seed": cfg.runtime.seed, "environment": env,
            "training_config": scfg.path}
    model_obj = build_model(cfg.model)
    trainer = Trainer(model_obj, cfg, spec.trainable, device, class_weights=weights, checkpoint_dir=ckpt_dir,
                      provenance={"dataset_fingerprint": dataset.fingerprint, "split_digest": manifest.digest,
                                  "git": git, "dataset_type": DATASET_TYPE, "synthetic": meta})
    if resume_from is not None:
        print(f"Resuming from {resume_from} at epoch {trainer.resume(resume_from)}")
    print(f"Device {device.device} ({device.gpu_name or 'CPU'}), AMP {trainer.amp}; model {cfg.model.name}; "
          f"{len(train_recs)} train / {len(val_recs)} val / {len(test_recs)} test images", flush=True)
    start = time.perf_counter()
    fit = trainer.fit(train_loader, val_loader)
    train_seconds = time.perf_counter() - start
    for h in fit.history:
        print(f"  epoch {h.epoch:>2}  train loss {h.train_loss:.4f}  val loss {h.val_loss:.4f}  "
              f"val bal.acc {h.monitor if h.monitor is None else round(h.monitor, 4)}"
              f"{'  *best' if h.is_best else ''}  ({h.seconds:.1f}s)")

    metrics: dict[str, Any] = {"fit": fit.to_dict(), "training_seconds": round(train_seconds, 1)}
    if fit.best_checkpoint:
        ckpt = load_checkpoint(fit.best_checkpoint, class_names=spec.trainable, expected_dataset_type=DATASET_TYPE)
        trainer.model.load_state_dict(ckpt["state_dict"])
        res = partition_metrics(trainer, test_recs, geometry, cfg.data.batch_size, cfg.runtime.seed)
        metrics["test_image_level"] = res["image"].to_dict()
        metrics["test_artifact_level"] = res["artifact"].to_dict()
        print(res["artifact"].render())

    record = ExperimentRecord(
        experiment_id=exp_id,
        timestamp=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        status="completed",
        git_commit=git["commit"], git_dirty=git["dirty"],
        dataset_version={"dataset_type": DATASET_TYPE, "fingerprint": dataset.fingerprint,
                         "synthetic_fingerprint": fingerprint, "image_set_fingerprint": dataset.image_fingerprint,
                         "source": dataset.source, "records": dataset.raw_record_count,
                         "generator_version": GENERATOR_VERSION, "generation_seed": dcfg.seed,
                         "dataset_config_digest": dcfg.digest},
        config=cfg.to_dict() | {"synthetic_training_config": scfg.path},
        model={"name": cfg.model.name, "parameters": count_parameters(trainer.model),
               "fingerprint": model_fingerprint(trainer.model.state_dict()),
               "resumed_from": str(resume_from) if resume_from else None, "architecture_slots": ARCHITECTURE_SLOTS},
        seed=cfg.runtime.seed,
        device={**device.to_dict(), "seed_state": seed_state},
        environment=env,
        split={"strategy": manifest.strategy, "digest": manifest.digest, "manifest": manifest.default_filename(), "fold": None},
        training_split=split_summary(train_recs),
        validation_split=split_summary(val_recs),
        test_split=split_summary(test_recs),
        metrics=metrics,
        checkpoint={"best": fit.best_checkpoint, "last": fit.last_checkpoint},
        readiness=READINESS_NOTE,
        notes=[TRAINING_BANNER, PURPOSE, LABEL_WARNING,
               "Class labels are synthetic visual task categories; output slots follow architecture_slots."],
        dataset_type=DATASET_TYPE,
    )
    out = record.save(resolve(cfg.experiments.directory))
    art = metrics.get("test_artifact_level", {}).get("metrics") or {}
    summary = {"experiment": str(out), "model": cfg.model.name, "epochs_run": fit.epochs_run, "best_epoch": fit.best_epoch,
               "training_seconds": round(train_seconds, 1), "test_artifact_accuracy": art.get("accuracy"),
               "test_artifact_balanced_accuracy": art.get("balanced_accuracy"), "test_artifact_macro_f1": art.get("macro_f1")}
    return SyntheticRunOutcome("completed", f"{TRAINING_BANNER}: completed", str(out), fit.best_checkpoint,
                               fit.last_checkpoint, summary)


__all__ = [
    "READINESS_NOTE",
    "SyntheticRunOutcome",
    "SyntheticTrainingConfig",
    "partition_metrics",
    "resolve",
    "run_synthetic_training",
]
