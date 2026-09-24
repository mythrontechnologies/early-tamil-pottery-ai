"""End-to-end training run on the research dataset. Gate first, always.

:func:`run_training` is the **only** code path that turns research records into a
trained model. Its first action is :func:`src.dataset.readiness.assert_training_ready`
on the canonical dataset (``data/metadata/records.jsonl`` + ``data/raw/``). It takes
no records path, no data root and no flag that could relax the gate, so it cannot be
pointed at fixtures or at an unvalidated folder of images.

Today it always returns a ``blocked`` outcome, because there is no authorised data.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

from src.dataset.classes import ClassSpec
from src.dataset.loader import load_dataset
from src.dataset.readiness import (
    NO_DATA_REASON,
    NotTrainingReadyError,
    ReadinessReport,
    assert_training_ready,
    evaluate,
)
from src.dataset.sampling import (
    class_counts,
    class_weights,
    imbalance_table,
    render_imbalance_table,
)
from src.dataset.schema import ROOT
from src.dataset.splits import SplitManifest, partition_records
from src.evaluation.metrics import aggregate_by_artifact, evaluate_predictions

from .augmentation import ImageGeometry, build_eval_transform, build_train_transform
from .checkpoint import load_checkpoint, model_fingerprint
from .config import TrainingConfig
from .data import PotteryImageDataset, make_loader
from .engine import Trainer
from .experiment import ExperimentRecord, make_experiment_id, split_summary
from .model import build_model, count_parameters
from .runtime import environment, git_commit, seed_everything, select_device

BLOCKED_NO_DATA = "Training blocked:\nNo authorized archaeological images are available."


@dataclass
class RunOutcome:
    status: str                     # "blocked" | "completed"
    message: str
    readiness: ReadinessReport | None = None
    experiments: list[str] = field(default_factory=list)


def blocked_message(report: ReadinessReport) -> str:
    if report.reason == NO_DATA_REASON:
        return BLOCKED_NO_DATA
    head = "Training blocked:"
    if report.record_count and not any(report.artifacts_by_class.values()):
        head += (f"\nNo expert-labelled training images are available: {report.record_count} "
                 "acquired image(s) carry no project label (script_type=unknown) and await "
                 "expert annotation.")
    return head + "\n" + "\n".join(f"  - {b}" for b in report.blockers)


def _resolve(path: str) -> Path:
    p = Path(path)
    return p if p.is_absolute() else ROOT / p


def run_training(config_path: Path | str | None = None,
                 manifest_path: Path | str | None = None,
                 resume_from: Path | str | None = None) -> RunOutcome:
    """Train on the canonical research dataset, or explain why not.

    ``resume_from`` continues a single-split run from its checkpoint, after the gate has passed
    again; the trainer refuses a checkpoint from another dataset version, model or class list."""
    cfg = TrainingConfig.load(config_path)
    spec = ClassSpec.from_config()
    cfg.check_against_project(spec)
    manifest_arg = Path(manifest_path) if manifest_path else (
        _resolve(cfg.data.split_manifest) if cfg.data.split_manifest else None)

    try:
        report = assert_training_ready(manifest_path=manifest_arg)
    except NotTrainingReadyError:
        report = evaluate(manifest_path=manifest_arg)
        return RunOutcome("blocked", blocked_message(report), report)

    # ---- beyond this point the gate has passed on the canonical dataset -----------
    dataset = load_dataset()
    manifest = SplitManifest.load(ROOT / report.split_manifest)  # type: ignore[operator]
    folds = list(range(int(manifest.k))) if manifest.strategy == "grouped_kfold" else [None]
    if resume_from is not None and len(folds) > 1:
        return RunOutcome("blocked", "Resume is supported for a single split, not a k-fold run "
                                     "(resume each fold's checkpoint separately).", report)
    outcome = RunOutcome("completed", "training completed", report)
    for fold in folds:
        path = _train_one(cfg, spec, dataset, manifest, report, fold, resume_from)
        outcome.experiments.append(str(path))
    return outcome


def _train_one(cfg: TrainingConfig, spec: ClassSpec, dataset: Any, manifest: SplitManifest,
               report: ReadinessReport, fold: int | None, resume_from: Path | str | None = None) -> Path:
    parts = partition_records(manifest, dataset, fold=fold)
    train_recs, val_recs = parts["train"], parts["val"]
    test_recs = parts.get("test")

    print("Class report (training partition):")
    print(render_imbalance_table(imbalance_table([r.record for r in train_recs], spec)))

    seed_state = seed_everything(cfg.runtime.seed, deterministic=cfg.runtime.deterministic)
    device = select_device(cfg.runtime.device, mixed_precision=cfg.runtime.mixed_precision)
    geometry = ImageGeometry.from_project(cfg.data.image_size)
    train_ds = PotteryImageDataset(train_recs, spec, build_train_transform(cfg.augmentation, geometry))
    val_ds = PotteryImageDataset(val_recs, spec, build_eval_transform(geometry))
    common = dict(batch_size=cfg.data.batch_size, seed=cfg.runtime.seed,
                  num_workers=cfg.data.num_workers,
                  pin_memory=cfg.data.pin_memory and device.device == "cuda")
    train_loader = make_loader(train_ds, train=True, imbalance_strategy=cfg.imbalance.strategy,
                               count_unit=cfg.imbalance.count_unit,
                               equalise_artifacts=cfg.imbalance.equalise_artifacts, **common)
    val_loader = make_loader(val_ds, train=False, **common)

    weights = None
    if cfg.imbalance.strategy == "class_weighted_loss":
        counts = class_counts([r.record for r in train_recs], spec, cfg.imbalance.count_unit)  # type: ignore[arg-type]
        weights = class_weights(counts, spec.trainable)

    exp_id = make_experiment_id(dataset.fingerprint, cfg.runtime.seed)
    if fold is not None:
        exp_id += f"_fold{fold}"
    git = git_commit()
    model = build_model(cfg.model)
    trainer = Trainer(
        model, cfg, spec.trainable, device, class_weights=weights,
        checkpoint_dir=_resolve(cfg.checkpoint.directory) / exp_id,
        provenance={"dataset_fingerprint": dataset.fingerprint,
                    "split_digest": manifest.digest, "git": git})
    if resume_from is not None:
        print(f"Resuming from {resume_from} at epoch {trainer.resume(resume_from)}")
    fit = trainer.fit(train_loader, val_loader)

    metrics: dict[str, Any] = {"fit": fit.to_dict()}
    if test_recs and fit.best_checkpoint:
        ckpt = load_checkpoint(fit.best_checkpoint, class_names=spec.trainable)
        trainer.model.load_state_dict(ckpt["state_dict"])
        test_ds = PotteryImageDataset(test_recs, spec, build_eval_transform(geometry))
        preds = trainer.predict(make_loader(test_ds, train=False, **common))
        image_level = evaluate_predictions(preds.y_true, preds.y_pred, spec.trainable,
                                           y_prob=preds.probabilities, unit="image")
        aids = [test_recs[i].artifact_id for i in preds.indices]
        _, a_true, a_prob = aggregate_by_artifact(aids, preds.y_true, preds.probabilities)
        artifact_level = evaluate_predictions(a_true, list(np.argmax(a_prob, axis=1)),
                                              spec.trainable, y_prob=a_prob, unit="artifact")
        metrics["test_image_level"] = image_level.to_dict()
        metrics["test_artifact_level"] = artifact_level.to_dict()
        print(artifact_level.render())

    record = ExperimentRecord(
        experiment_id=exp_id,
        timestamp=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        status="completed",
        git_commit=git["commit"], git_dirty=git["dirty"],
        dataset_version={"fingerprint": dataset.fingerprint,
                         "image_set_fingerprint": dataset.image_fingerprint,
                         "source": dataset.source, "records": dataset.raw_record_count},
        config=cfg.to_dict(),
        model={"name": cfg.model.name, "parameters": count_parameters(trainer.model),
               "fingerprint": model_fingerprint(trainer.model.state_dict()),
               "resumed_from": str(resume_from) if resume_from else None},
        seed=cfg.runtime.seed,
        device={**device.to_dict(), "seed_state": seed_state},
        environment=environment(),
        split={"strategy": manifest.strategy, "digest": manifest.digest,
               "manifest": report.split_manifest, "fold": fold},
        training_split=split_summary(train_recs),
        validation_split=split_summary(val_recs),
        test_split=split_summary(test_recs) if test_recs else None,
        metrics=metrics,
        checkpoint={"best": fit.best_checkpoint, "last": fit.last_checkpoint},
        readiness=report.to_dict(),
    )
    return record.save(_resolve(cfg.experiments.directory))


__all__ = ["BLOCKED_NO_DATA", "RunOutcome", "blocked_message", "run_training"]
