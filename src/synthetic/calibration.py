"""Temperature scaling for the synthetic classifier.   SYNTHETIC ENGINEERING BENCHMARK

    python -m src.synthetic calibrate [--checkpoint models/synthetic/checkpoints/<run>/best.pt]

The Milestone 9 model is overconfident on held-out synthetic images (mean confidence 0.978 against
0.877 accuracy). A single temperature ``T`` is fitted on the VALIDATION split by minimising the
negative log-likelihood of ``softmax(log p / T)``; the TEST split is only measured, never used to fit.
The result is bound to the checkpoint's model fingerprint, so it is refused for any other weights.

A calibrated probability is still a model probability on synthetic images. It is never an
archaeological confidence.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import torch

from src.evaluation.calibration import calibration_report

from . import DATASET_TYPE, MARKER, SYNTHETIC_MODELS_ROOT, assert_synthetic_model_destination

CALIBRATION_DIR = SYNTHETIC_MODELS_ROOT / "calibration"
METHOD = "temperature_scaling"
STATUS = "Synthetic benchmark calibration (temperature scaling on the synthetic validation split)"


class CalibrationError(ValueError):
    """No usable calibration for this checkpoint."""


def log_probs(probabilities: np.ndarray) -> np.ndarray:
    return np.log(np.clip(np.asarray(probabilities, np.float64), 1e-12, 1.0))


def apply_temperature(probabilities: np.ndarray, temperature: float) -> np.ndarray:
    z = log_probs(probabilities) / float(temperature)
    z -= z.max(axis=1, keepdims=True)
    e = np.exp(z)
    return e / e.sum(axis=1, keepdims=True)


def fit_temperature(probabilities: np.ndarray, labels: list[int] | np.ndarray, *, max_iter: int = 200) -> float:
    """The T > 0 minimising NLL of softmax(log p / T) on held-out (validation) predictions."""
    z = torch.tensor(log_probs(probabilities), dtype=torch.float64)
    y = torch.tensor(np.asarray(labels), dtype=torch.long)
    log_t = torch.zeros(1, dtype=torch.float64, requires_grad=True)
    opt = torch.optim.LBFGS([log_t], lr=0.1, max_iter=max_iter, line_search_fn="strong_wolfe")

    def closure() -> torch.Tensor:
        opt.zero_grad()
        loss = torch.nn.functional.cross_entropy(z / torch.exp(log_t), y)
        loss.backward()
        return loss

    opt.step(closure)
    return float(torch.exp(log_t).item())


def summary(labels: list[int], probabilities: np.ndarray) -> dict[str, Any]:
    rep = calibration_report(labels, probabilities)
    assert rep is not None
    pred = np.asarray(probabilities).argmax(axis=1)
    return {"n": rep["n_samples"], "accuracy": round(float((pred == np.asarray(labels)).mean()), 4), "ece": rep["ece"],
            "mce": rep["mce"], "brier": rep["brier"], "mean_confidence": rep["confidence_analysis"]["mean_confidence"],
            "nll": round(float(-np.mean(log_probs(probabilities)[np.arange(len(labels)), labels])), 4)}


@dataclass
class Calibration:
    temperature: float
    model_fingerprint: str
    dataset_fingerprint: str
    split_digest: str
    checkpoint: str
    experiment_id: str | None
    metrics: dict[str, Any] = field(default_factory=dict)
    method: str = METHOD
    fitted_on: str = "val"
    status: str = STATUS
    dataset_type: str = DATASET_TYPE
    marker: str = MARKER
    created_utc: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def apply(self, probabilities: np.ndarray) -> np.ndarray:
        return apply_temperature(probabilities, self.temperature)

    def save(self, directory: Path = CALIBRATION_DIR) -> Path:
        out = Path(directory) / f"{self.experiment_id or self.model_fingerprint[:16]}.json"
        assert_synthetic_model_destination(out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(self.to_dict(), indent=2) + "\n", encoding="utf-8", newline="\n")
        return out

    @classmethod
    def load(cls, path: Path | str) -> Calibration:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        if data.get("dataset_type") != DATASET_TYPE or data.get("marker") != MARKER or data.get("method") != METHOD:
            raise CalibrationError(f"{path} is not a synthetic temperature-scaling calibration")
        cal = cls(**data)
        if not (0.05 <= cal.temperature <= 20):
            raise CalibrationError(f"implausible temperature {cal.temperature}")
        return cal


def calibration_for(ckpt: dict[str, Any], directory: Path = CALIBRATION_DIR) -> Calibration | None:
    """The calibration fitted for exactly these weights (matched by model fingerprint), if any."""
    if not Path(directory).is_dir():
        return None
    for p in sorted(Path(directory).glob("*.json")):
        try:
            cal = Calibration.load(p)
        except (CalibrationError, ValueError, TypeError, KeyError):
            continue
        if cal.model_fingerprint == ckpt.get("model_fingerprint"):
            if cal.dataset_fingerprint != ckpt.get("dataset_fingerprint"):
                raise CalibrationError("calibration and checkpoint disagree on the dataset version")
            return cal
    return None


def calibrate_checkpoint(checkpoint: Path | str, *, root: Path | str | None = None, device: str = "auto",
                         save: bool = True) -> Calibration:
    """Fit T on the validation split of the checkpoint's own dataset version; measure val and test."""
    from src.training.augmentation import ImageGeometry, build_eval_transform
    from src.training.data import PotteryImageDataset, make_loader
    from src.training.runtime import git_commit

    from .dataset import synthetic_class_spec
    from .evaluate import checkpoint_records, load_synthetic_model

    ckpt, _, trainer, _ = load_synthetic_model(checkpoint, device)
    spec = synthetic_class_spec()
    geometry = ImageGeometry.from_project(trainer.cfg.data.image_size)
    preds = {}
    for part in ("val", "test"):
        recs = checkpoint_records(ckpt, part, root)
        ds = PotteryImageDataset(recs, spec, build_eval_transform(geometry))
        preds[part] = trainer.predict(make_loader(ds, train=False, batch_size=trainer.cfg.data.batch_size,
                                                  seed=trainer.cfg.runtime.seed))
    t = fit_temperature(preds["val"].probabilities, preds["val"].y_true)
    metrics = {part: {"before": summary(p.y_true, p.probabilities),
                      "after": summary(p.y_true, apply_temperature(p.probabilities, t))}
               for part, p in preds.items()}
    meta = ckpt.get("synthetic") or {}
    cal = Calibration(temperature=round(t, 6), model_fingerprint=ckpt["model_fingerprint"],
                      dataset_fingerprint=ckpt["dataset_fingerprint"], split_digest=ckpt["split_digest"],
                      checkpoint=Path(checkpoint).as_posix(), experiment_id=meta.get("experiment_id"), metrics=metrics,
                      created_utc=datetime.now(timezone.utc).isoformat(timespec="seconds"))
    cal.metrics["git"] = git_commit()
    if save:
        cal.metrics["path"] = str(cal.save())
    return cal


def confidence_words(p: float) -> str:
    """Plain wording for a calibrated synthetic model probability (never an archaeological confidence)."""
    if p >= 0.9:
        return "high model confidence"
    if p >= 0.7:
        return "moderate model confidence"
    if p >= 0.5:
        return "low model confidence"
    return "very low model confidence: the model is unsure"


__all__ = ["CALIBRATION_DIR", "METHOD", "STATUS", "Calibration", "CalibrationError", "apply_temperature",
           "calibrate_checkpoint", "calibration_for", "confidence_words", "fit_temperature", "summary"]
