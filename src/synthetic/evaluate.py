"""Evaluate a synthetic checkpoint.   SYNTHETIC DATA ONLY — NOT ARCHAEOLOGICAL PERFORMANCE

    python -m src.evaluation evaluate --dataset synthetic --checkpoint <best.pt> [--partition test|val] [--json]

Refuses anything but a SYNTHETIC checkpoint trained on THIS synthetic dataset version and split.
Reports image- and artifact-level accuracy, balanced accuracy, precision, recall, F1 (macro,
weighted, per class), the confusion matrix, top-2 accuracy, calibration (ECE, MCE, Brier,
reliability bins) and the confidence distribution, and writes the report under
``models/synthetic/reports/`` only. It never touches the research evaluation path or history.
"""

from __future__ import annotations

import json
import textwrap
from pathlib import Path
from typing import Any

import numpy as np
from torch import nn

from src.dataset.loader import DatasetRecord
from src.dataset.splits import partition_records
from src.training.augmentation import ImageGeometry
from src.training.checkpoint import load_checkpoint
from src.training.config import ModelConfig, TrainingConfig
from src.training.engine import Trainer
from src.training.model import build_model
from src.training.runtime import DeviceInfo, select_device

from . import (
    ARCHITECTURE_SLOTS,
    DATASET_TYPE,
    EVALUATION_BANNER,
    LABEL_WARNING,
    MARKER,
    PURPOSE,
    SYNTHETIC_LABELS,
    assert_synthetic_model_destination,
)
from .dataset import SyntheticDatasetError, find_manifest, load_synthetic_dataset
from .train import SyntheticTrainingConfig, partition_metrics, resolve


def load_synthetic_model(checkpoint: Path | str, device: str = "auto") -> tuple[dict[str, Any], nn.Module, Trainer, DeviceInfo]:
    """A synthetic checkpoint as a ready-to-predict Trainer (refuses research checkpoints)."""
    ckpt = load_checkpoint(checkpoint, class_names=SYNTHETIC_LABELS, expected_dataset_type=DATASET_TYPE)
    cfg = TrainingConfig.from_dict(ckpt["config"])
    cfg.model.pretrained = False
    model = build_model(ModelConfig(name=ckpt["model_name"], num_classes=ckpt["num_classes"], pretrained=False,
                                    freeze_backbone=False, dropout=cfg.model.dropout))
    model.load_state_dict(ckpt["state_dict"])
    info = select_device(device, mixed_precision=cfg.runtime.mixed_precision)
    return ckpt, model, Trainer(model, cfg, SYNTHETIC_LABELS, info), info


def checkpoint_records(ckpt: dict[str, Any], partition: str, root: Path | str | None = None) -> list[DatasetRecord]:
    """The partition of the dataset version and split this checkpoint was trained on."""
    dataset = load_synthetic_dataset(root)
    if dataset.is_empty:
        raise SyntheticDatasetError("no synthetic dataset; run `python -m src.synthetic generate`")
    if ckpt["dataset_fingerprint"] != dataset.fingerprint:
        raise SyntheticDatasetError("the checkpoint was trained on a different synthetic dataset version "
                                    f"({ckpt['dataset_fingerprint'][:12]} != {dataset.fingerprint[:12]})")
    manifest = find_manifest(dataset, root, digest=ckpt["split_digest"])
    return partition_records(manifest, dataset)[partition]


def confidence_distribution(y_true: list[int], probs: np.ndarray, bins: int = 10) -> dict[str, Any]:
    conf = probs.max(axis=1)
    pred = probs.argmax(axis=1)
    correct = pred == np.asarray(y_true)
    edges = np.linspace(0, 1, bins + 1)
    hist_c, _ = np.histogram(conf[correct], bins=edges)
    hist_i, _ = np.histogram(conf[~correct], bins=edges)
    per_class = {}
    for i, name in enumerate(SYNTHETIC_LABELS):
        m = np.asarray(y_true) == i
        per_class[name] = {"n": int(m.sum()), "mean_confidence": round(float(conf[m].mean()), 4) if m.any() else None,
                           "mean_probability_of_true_class": round(float(probs[m, i].mean()), 4) if m.any() else None}
    return {"bins": [[round(float(edges[i]), 2), round(float(edges[i + 1]), 2)] for i in range(bins)],
            "correct": hist_c.tolist(), "incorrect": hist_i.tolist(),
            "share_below_0_5": round(float((conf < 0.5).mean()), 4), "mean_confidence": round(float(conf.mean()), 4),
            "per_true_class": per_class,
            "note": "Model probabilities on synthetic images; not archaeological confidence."}


def evaluate_checkpoint(checkpoint: Path | str, partition: str = "test", *, root: Path | str | None = None,
                        config_path: Path | str | None = None, device: str = "auto", save: bool = True) -> dict[str, Any]:
    ckpt, _, trainer, info = load_synthetic_model(checkpoint, device)
    records = checkpoint_records(ckpt, partition, root)
    cfg = trainer.cfg
    res = partition_metrics(trainer, records, ImageGeometry.from_project(cfg.data.image_size), cfg.data.batch_size,
                       cfg.runtime.seed)
    preds = res["predictions"]
    rows = [{"image_id": records[i].image_id, "artifact_id": records[i].artifact_id,
             "true": SYNTHETIC_LABELS[t], "predicted": SYNTHETIC_LABELS[p],
             "confidence": round(float(preds.probabilities[k].max()), 4)}
            for k, (i, t, p) in enumerate(zip(preds.indices, preds.y_true, preds.y_pred))]
    meta = ckpt.get("synthetic", {})
    report = {
        "banner": EVALUATION_BANNER, "dataset_type": DATASET_TYPE, "marker": MARKER, "purpose": PURPOSE,
        "label_warning": LABEL_WARNING, "architecture_slots": ARCHITECTURE_SLOTS,
        "checkpoint": str(checkpoint), "experiment_id": meta.get("experiment_id"), "model": ckpt["model_name"],
        "model_fingerprint": ckpt.get("model_fingerprint"), "epoch": ckpt["epoch"],
        "dataset_fingerprint": ckpt["dataset_fingerprint"], "synthetic_fingerprint": meta.get("synthetic_fingerprint"),
        "split_digest": ckpt["split_digest"], "partition": partition, "device": info.device,
        "image_level": res["image"].to_dict(), "artifact_level": res["artifact"].to_dict(),
        "confidence_distribution": {"image": confidence_distribution(preds.y_true, preds.probabilities)},
        "predictions": rows,
    }
    if save:
        report["report_path"] = str(save_report(report, f"evaluation_{partition}.json", config_path))
    return report


def save_report(report: dict[str, Any], name: str, config_path: Path | str | None = None) -> Path:
    scfg = SyntheticTrainingConfig.load(config_path)
    out = resolve(scfg.reports_directory) / (report.get("experiment_id") or "unknown_experiment") / name
    assert_synthetic_model_destination(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    return out


def render_evaluation(rep: dict[str, Any]) -> str:
    from src.evaluation.metrics import ClassificationMetrics, ClassMetrics, EvaluationReport

    def report(d: dict[str, Any]) -> EvaluationReport:
        m = dict(d["metrics"])
        m["per_class"] = {k: ClassMetrics(**v) for k, v in m["per_class"].items()}
        m["top_k_accuracy"] = {int(k): v for k, v in m["top_k_accuracy"].items()}
        return EvaluationReport(d["status"], d["provenance"], d["unit"], d["message"], ClassificationMetrics(**m))

    cd = rep["confidence_distribution"]["image"]
    L = ["#" * 72, f"#  {EVALUATION_BANNER}", *(f"#  {line}" for line in textwrap.wrap(PURPOSE, 66)), "#" * 72,
         f"checkpoint {rep['checkpoint']}  (model {rep['model']}, epoch {rep['epoch']}, partition {rep['partition']})",
         f"synthetic fingerprint {rep['synthetic_fingerprint']}", "",
         "ARTIFACT LEVEL (headline: probabilities averaged over each artifact's views)",
         report(rep["artifact_level"]).render(), "", "IMAGE LEVEL", report(rep["image_level"]).render(), "",
         f"Confidence distribution (image level; mean {cd['mean_confidence']}, share < 0.5: {cd['share_below_0_5']})"]
    for (lo, hi), c, i in zip(cd["bins"], cd["correct"], cd["incorrect"]):
        L.append(f"    [{lo:.1f}, {hi:.1f}]  correct {c:>4}  incorrect {i:>4}")
    L += [f"Output slots: {ARCHITECTURE_SLOTS} (tensor positions only; labels keep their synthetic meaning).",
          LABEL_WARNING]
    if rep.get("report_path"):
        L.append(f"report: {rep['report_path']}")
    return "\n".join(L)


__all__ = ["checkpoint_records", "confidence_distribution", "evaluate_checkpoint", "load_synthetic_model",
           "render_evaluation", "save_report"]
