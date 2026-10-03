"""Script classification of a whole photograph: an AI OBSERVATION, never evidence.

``NoModelClassifier`` (the default) says that no trained classifier exists: training is
blocked until the readiness gate passes on expert-labelled data, so there is no model to
run. ``CheckpointClassifier`` runs a checkpoint written by ``src.training`` (loaded with
``weights_only=True`` and its fingerprint checked). Its output is a probability per class,
labelled ``ai_prediction``, with the model's fingerprint and the dataset fingerprint it was
trained on. The reasoning layer lists it under AI predictions; it never becomes a script
identification, a label or a date.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Protocol

from PIL import Image

NO_MODEL = ("No trained script classifier exists: training is blocked until enough expert-labelled "
            "artifacts exist in every class (python -m src.dataset readiness). Classification unavailable.")


@dataclass
class ClassificationResult:
    status: str                                  # no_model | predicted
    statement: str
    label: str | None = None                     # argmax class, only when status == predicted
    probabilities: dict[str, float] = field(default_factory=dict)
    model: dict[str, Any] = field(default_factory=dict)   # name, fingerprint, dataset fingerprint
    provenance: str = "ai_prediction"
    is_evidence: bool = False                    # always False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class ScriptClassifier(Protocol):
    name: str

    def classify(self, image: Image.Image) -> ClassificationResult: ...


class NoModelClassifier:
    name = "none"

    def classify(self, image: Image.Image) -> ClassificationResult:
        return ClassificationResult("no_model", NO_MODEL)


class CheckpointClassifier:
    """Runs a ``src.training`` checkpoint on one image (CPU unless ``device`` says otherwise)."""

    def __init__(self, checkpoint: Path | str, *, device: str = "cpu") -> None:
        import torch

        from src.dataset.classes import ClassSpec
        from src.training.augmentation import ImageGeometry, build_eval_transform
        from src.training.checkpoint import load_checkpoint
        from src.training.config import ModelConfig
        from src.training.model import build_model

        spec = ClassSpec.from_config()
        ckpt = load_checkpoint(checkpoint, class_names=spec.trainable, map_location=device,
                               expected_dataset_type="research")
        model = build_model(ModelConfig(name=ckpt["model_name"], num_classes=ckpt["num_classes"],
                                        pretrained=False))
        model.load_state_dict(ckpt["state_dict"])
        self._torch, self.device = torch, torch.device(device)
        self.model = model.to(self.device).eval()
        self.class_names = list(ckpt["class_names"])
        self.transform = build_eval_transform(ImageGeometry.from_project())
        self.name = f"checkpoint:{ckpt['model_name']}"
        self.info = {"name": ckpt["model_name"], "fingerprint": ckpt.get("model_fingerprint"),
                     "dataset_fingerprint": ckpt["dataset_fingerprint"], "epoch": ckpt["epoch"],
                     "checkpoint": Path(checkpoint).name}

    def classify(self, image: Image.Image) -> ClassificationResult:
        torch = self._torch
        with torch.no_grad():
            x = self.transform(image.convert("RGB")).unsqueeze(0).to(self.device)
            probs = torch.softmax(self.model(x).float(), dim=1)[0].cpu().tolist()
        p = {c: round(float(v), 6) for c, v in zip(self.class_names, probs)}
        best = max(p, key=lambda c: (p[c], -self.class_names.index(c)))
        return ClassificationResult(
            "predicted",
            f"AI prediction (not evidence): highest model probability for '{best}' ({p[best]:.2f}). "
            "A model probability is not an archaeological confidence.",
            label=best, probabilities=p, model=self.info)


__all__ = ["NO_MODEL", "CheckpointClassifier", "ClassificationResult", "NoModelClassifier", "ScriptClassifier"]
