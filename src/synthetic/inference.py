"""Synthetic images in the inference pipeline.   Synthetic demonstration — not archaeological evidence

``src.inference.analyze`` identifies an image by SHA-256. A match with the synthetic records
makes the result ``dataset_type: synthetic`` (indicator ``SYNTHETIC DEMONSTRATION``), applies no
human evidence, and classifies it ONLY with a :class:`SyntheticCheckpointClassifier`. A research
photograph or an unregistered upload is never shown to a synthetic model, and a synthetic image
is never shown to a model of the archaeological classes.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from PIL import Image

from src.classification import ClassificationResult
from src.dataset.convert import read_jsonl

from . import (
    DATASET_TYPE,
    LABEL_WARNING,
    MARKER,
    PURPOSE,
    RECORDS_PATH,
    SYNTHETIC_LABELS,
    SYNTHETIC_MODELS_ROOT,
    UI_BANNER,
)

NO_SYNTHETIC_MODEL = ("No synthetic demonstration model is loaded (train one with `python -m src.training train "
                      "--dataset synthetic`). Classification unavailable.")

REAL_INFERENCE_UNAVAILABLE = ("Real archaeological inference is unavailable until expert-labelled training data is "
                              "available.")

INDICATORS = {
    "research": ("REAL RESEARCH DATA", "A registered research photograph: its SHA-256 matches data/metadata/records.jsonl."),
    "synthetic": ("SYNTHETIC DEMONSTRATION", UI_BANNER),
    "unregistered": ("UNREGISTERED IMAGE", "No provenance: the image matches neither a research record nor the "
                                           "synthetic engineering dataset."),
}

_INDEX: dict[str, Any] = {"key": None, "by_sha": {}}


def synthetic_index(path: Path = RECORDS_PATH) -> dict[str, dict[str, Any]]:
    """SHA-256 -> synthetic record, re-read only when the records file changes."""
    if not path.exists():
        return {}
    st = path.stat()
    key = (str(path), st.st_mtime_ns, st.st_size)
    if _INDEX["key"] != key:
        _INDEX["by_sha"] = {r["image_sha256"]: r for r in read_jsonl(path)}
        _INDEX["key"] = key
    return _INDEX["by_sha"]


def dataset_block(kind: str, record: dict[str, Any] | None = None) -> dict[str, Any]:
    indicator, statement = INDICATORS[kind]
    block: dict[str, Any] = {"dataset_type": kind, "indicator": indicator, "statement": statement}
    if kind == "research":
        block |= {"notice": "REAL RESEARCH PHOTO DETECTED", "ml_inference": REAL_INFERENCE_UNAVAILABLE,
                  "synthetic_models_applied": False}
    if kind == "unregistered":
        block |= {"ml_inference": "No model is applied to an image without provenance.", "synthetic_models_applied": False}
    if kind == DATASET_TYPE:
        block |= {"warning_code": "synthetic_not_archaeological"}
    if kind == DATASET_TYPE and record is not None:
        block |= {
            "marker": MARKER, "purpose": PURPOSE, "label_warning": LABEL_WARNING,
            "artifact_id": record["artifact_id"], "image_id": record["image_id"],
            "generator_version": record["synthetic_generator_version"], "generation_seed": record["generation_seed"],
            "ground_truth": {"label": record["script_type"], "inscription_present": record["inscription_present"],
                             "inscription_type": record["inscription_type"],
                             "uncertain_mode": record["synthetic_uncertain_mode"],
                             "glyph_sequence": record["synthetic_glyph_sequence"],
                             "note": "Synthetic generator ground truth: a task label, not evidence."},
        }
    return block


class NoSyntheticModel:
    name = "none"

    def classify(self, image: Image.Image) -> ClassificationResult:
        return ClassificationResult("no_model", NO_SYNTHETIC_MODEL)


class SyntheticCheckpointClassifier:
    """Runs a SYNTHETIC checkpoint (refuses a research one) on a synthetic image. AI output, never evidence."""

    def __init__(self, checkpoint: Path | str, *, device: str = "cpu", calibrated: bool = True,
                 calibration_dir: Path | None = None) -> None:
        import torch

        from src.training.augmentation import ImageGeometry, build_eval_transform
        from src.training.checkpoint import load_checkpoint
        from src.training.config import ModelConfig
        from src.training.model import build_model

        from .calibration import STATUS, calibration_for

        ckpt = load_checkpoint(checkpoint, class_names=SYNTHETIC_LABELS, map_location=device,
                               expected_dataset_type=DATASET_TYPE)
        model = build_model(ModelConfig(name=ckpt["model_name"], num_classes=ckpt["num_classes"], pretrained=False,
                                        freeze_backbone=False))
        model.load_state_dict(ckpt["state_dict"])
        self._torch, self.device = torch, torch.device(device)
        self.model = model.to(self.device).eval()
        self.class_names = list(ckpt["class_names"])
        self.transform = build_eval_transform(ImageGeometry.from_project())
        self.name = f"synthetic_checkpoint:{ckpt['model_name']}"
        meta = ckpt.get("synthetic") or {}
        # the temperature fitted for exactly these weights (matched by model fingerprint), if any
        self.calibration = (calibration_for(ckpt, calibration_dir) if calibration_dir else calibration_for(ckpt)) if calibrated else None
        self.calibration_status = (STATUS if self.calibration is not None
                                   else "UNCALIBRATED: raw softmax of the synthetic model (run `python -m src.synthetic calibrate`)")
        self.ckpt_meta = {"dataset_fingerprint": ckpt["dataset_fingerprint"], "split_digest": ckpt["split_digest"],
                          "model_fingerprint": ckpt.get("model_fingerprint")}
        self.info = {"name": ckpt["model_name"], "fingerprint": ckpt.get("model_fingerprint"),
                     "dataset_type": DATASET_TYPE, "marker": MARKER, "dataset_fingerprint": ckpt["dataset_fingerprint"],
                     "synthetic_fingerprint": meta.get("synthetic_fingerprint"), "experiment_id": meta.get("experiment_id"),
                     "epoch": ckpt["epoch"], "checkpoint": Path(checkpoint).name,
                     "calibration": ({"method": self.calibration.method, "temperature": self.calibration.temperature,
                                      "fitted_on": self.calibration.fitted_on} if self.calibration else None)}

    def probabilities(self, image: Image.Image):
        """Unrounded class probabilities, temperature-scaled when a calibration exists for these weights."""
        torch = self._torch
        with torch.no_grad():
            x = self.transform(image.convert("RGB")).unsqueeze(0).to(self.device)
            probs = torch.softmax(self.model(x).float(), dim=1).cpu().numpy()
        return (self.calibration.apply(probs) if self.calibration is not None else probs)[0]

    def classify(self, image: Image.Image) -> ClassificationResult:
        probs = self.probabilities(image)
        p = {c: round(float(v), 6) for c, v in zip(self.class_names, probs)}
        best = max(p, key=lambda c: (p[c], -self.class_names.index(c)))
        kind = "calibrated model probability" if self.calibration is not None else "uncalibrated model probability"
        return ClassificationResult(
            "predicted",
            f"SYNTHETIC MODEL ON A SYNTHETIC IMAGE (demonstration only): highest {kind} '{best}' ({p[best]:.2f}). "
            f"{LABEL_WARNING} A model probability is not an archaeological confidence.",
            label=best, probabilities=p, model=self.info)


def latest_synthetic_checkpoint(root: Path = SYNTHETIC_MODELS_ROOT / "checkpoints") -> Path | None:
    """The newest ``best.pt`` under models/synthetic/checkpoints/, if any."""
    found = sorted(root.glob("*/best.pt"), key=lambda p: p.stat().st_mtime) if root.is_dir() else []
    return found[-1] if found else None


__all__ = ["INDICATORS", "NO_SYNTHETIC_MODEL", "REAL_INFERENCE_UNAVAILABLE", "NoSyntheticModel", "SyntheticCheckpointClassifier", "dataset_block",
           "latest_synthetic_checkpoint", "synthetic_index"]
