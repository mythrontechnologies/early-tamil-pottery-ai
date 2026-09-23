"""Typed training configuration, loaded from ``configs/training.yaml``.

The loader is strict. Unknown keys, impossible values and contradictory settings are
errors, because a silently ignored typo in a training config produces a model that was
not trained the way its report says it was.

Methodology constants (class list, split proportions, split seed, per-class threshold)
are **not** read from here. They come from ``configs/project.yaml`` via
``src.dataset``, and :func:`TrainingConfig.check_against_project` refuses a training
config that disagrees with them.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, fields
from pathlib import Path
from typing import Any

import yaml

from src.dataset.classes import ClassSpec
from src.dataset.sampling import check_strategy
from src.dataset.schema import ROOT, load_config

TRAINING_CONFIG_PATH = ROOT / "configs" / "training.yaml"

SUPPORTED_MODELS = ("resnet18", "resnet34", "efficientnet_b0", "mobilenet_v3_large")
OPTIMIZERS = ("adamw", "adam", "sgd")
SCHEDULERS = ("cosine", "step", "plateau", "none")
MONITORS = {"balanced_accuracy": "max", "macro_f1": "max", "accuracy": "max", "loss": "min"}


class TrainingConfigError(ValueError):
    """The training configuration is invalid."""


def _build(cls: type, data: dict[str, Any] | None, section: str) -> Any:
    data = dict(data or {})
    known = {f.name for f in fields(cls)}
    unknown = sorted(set(data) - known)
    if unknown:
        raise TrainingConfigError(f"[{section}] unknown key(s): {', '.join(unknown)}")
    return cls(**data)


@dataclass
class ModelConfig:
    name: str = "resnet18"
    num_classes: int = 4
    pretrained: bool = True
    freeze_backbone: bool = True
    unfreeze_backbone_at_epoch: int | None = 5
    dropout: float = 0.2


@dataclass
class DataConfig:
    image_size: int = 224
    batch_size: int = 16
    num_workers: int = 2
    pin_memory: bool = True
    split_manifest: str | None = None


@dataclass
class OptimizationConfig:
    epochs: int = 30
    optimizer: str = "adamw"
    learning_rate: float = 3e-4
    backbone_learning_rate: float = 3e-5
    weight_decay: float = 1e-4
    momentum: float = 0.9
    scheduler: str = "cosine"
    step_size: int = 10
    gamma: float = 0.1
    plateau_patience: int = 3
    gradient_clip_norm: float | None = 1.0
    label_smoothing: float = 0.0


@dataclass
class EarlyStoppingConfig:
    enabled: bool = True
    monitor: str = "balanced_accuracy"
    mode: str = "max"
    patience: int = 7
    min_delta: float = 0.001


@dataclass
class ImbalanceConfig:
    strategy: str = "class_weighted_loss"
    count_unit: str = "artifact"
    equalise_artifacts: bool = True


@dataclass
class RuntimeConfig:
    seed: int = 20260923
    device: str = "auto"
    mixed_precision: bool = True
    deterministic: bool = True


@dataclass
class CheckpointConfig:
    directory: str = "models/checkpoints"
    save_last: bool = True
    save_best: bool = True


@dataclass
class ExperimentsConfig:
    directory: str = "models/experiments"


@dataclass
class AugmentationConfig:
    enabled: bool = True
    horizontal_flip: bool = False
    rotation_degrees: float = 5.0
    brightness: float = 0.15
    contrast: float = 0.15
    saturation: float = 0.05
    hue: float = 0.0
    min_scale: float = 0.90
    translate: bool = True


@dataclass
class TrainingConfig:
    config_version: str = "1.0.0"
    model: ModelConfig = field(default_factory=ModelConfig)
    data: DataConfig = field(default_factory=DataConfig)
    optimization: OptimizationConfig = field(default_factory=OptimizationConfig)
    early_stopping: EarlyStoppingConfig = field(default_factory=EarlyStoppingConfig)
    imbalance: ImbalanceConfig = field(default_factory=ImbalanceConfig)
    runtime: RuntimeConfig = field(default_factory=RuntimeConfig)
    checkpoint: CheckpointConfig = field(default_factory=CheckpointConfig)
    experiments: ExperimentsConfig = field(default_factory=ExperimentsConfig)
    augmentation: AugmentationConfig = field(default_factory=AugmentationConfig)

    # -- construction -------------------------------------------------------

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TrainingConfig:
        sections = {
            "model": ModelConfig, "data": DataConfig, "optimization": OptimizationConfig,
            "early_stopping": EarlyStoppingConfig, "imbalance": ImbalanceConfig,
            "runtime": RuntimeConfig, "checkpoint": CheckpointConfig,
            "experiments": ExperimentsConfig, "augmentation": AugmentationConfig,
        }
        data = dict(data or {})
        unknown = sorted(set(data) - set(sections) - {"config_version"})
        if unknown:
            raise TrainingConfigError(f"unknown top-level key(s): {', '.join(unknown)}")
        built = {name: _build(klass, data.get(name), name) for name, klass in sections.items()}
        cfg = cls(config_version=str(data.get("config_version", "1.0.0")), **built)
        cfg.validate()
        return cfg

    @classmethod
    def load(cls, path: Path | str | None = None) -> TrainingConfig:
        p = Path(path) if path else TRAINING_CONFIG_PATH
        if not p.exists():
            raise TrainingConfigError(f"training config not found: {p}")
        return cls.from_dict(yaml.safe_load(p.read_text(encoding="utf-8")) or {})

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    # -- validation ---------------------------------------------------------

    def validate(self) -> None:
        m, d, o, e, i, a = (self.model, self.data, self.optimization, self.early_stopping,
                            self.imbalance, self.augmentation)
        problems: list[str] = []
        if m.name not in SUPPORTED_MODELS:
            problems.append(f"model.name {m.name!r} not in {SUPPORTED_MODELS}")
        if m.num_classes < 2:
            problems.append("model.num_classes must be >= 2")
        if not 0.0 <= m.dropout < 1.0:
            problems.append("model.dropout must be in [0, 1)")
        if m.unfreeze_backbone_at_epoch is not None and m.unfreeze_backbone_at_epoch < 0:
            problems.append("model.unfreeze_backbone_at_epoch must be >= 0 or null")
        if d.image_size < 32:
            problems.append("data.image_size must be >= 32")
        if d.batch_size < 1:
            problems.append("data.batch_size must be >= 1")
        if d.num_workers < 0:
            problems.append("data.num_workers must be >= 0")
        if o.epochs < 1:
            problems.append("optimization.epochs must be >= 1")
        if o.optimizer not in OPTIMIZERS:
            problems.append(f"optimization.optimizer {o.optimizer!r} not in {OPTIMIZERS}")
        if o.scheduler not in SCHEDULERS:
            problems.append(f"optimization.scheduler {o.scheduler!r} not in {SCHEDULERS}")
        if o.learning_rate <= 0 or o.backbone_learning_rate <= 0:
            problems.append("learning rates must be > 0")
        if not 0.0 <= o.label_smoothing < 1.0:
            problems.append("optimization.label_smoothing must be in [0, 1)")
        if e.monitor not in MONITORS:
            problems.append(f"early_stopping.monitor {e.monitor!r} not in {sorted(MONITORS)}")
        elif e.mode != MONITORS[e.monitor]:
            problems.append(f"early_stopping.mode must be {MONITORS[e.monitor]!r} for {e.monitor}")
        try:
            check_strategy(i.strategy)
        except ValueError as exc:
            problems.append(f"imbalance.strategy: {exc}")
        if i.count_unit not in ("artifact", "image"):
            problems.append("imbalance.count_unit must be 'artifact' or 'image'")
        if self.runtime.device not in ("auto", "cuda", "cpu"):
            problems.append("runtime.device must be auto, cuda or cpu")
        if not 0.0 <= a.rotation_degrees <= 15.0:
            problems.append("augmentation.rotation_degrees must be in [0, 15]; larger rotations "
                            "reorient the text rather than simulate a photographer's hand")
        if not 0.5 <= a.min_scale <= 1.0:
            problems.append("augmentation.min_scale must be in [0.5, 1.0]")
        if a.hue > 0.02:
            problems.append("augmentation.hue must be <= 0.02: surface colour carries ware "
                            "information (see docs/TRAINING_FRAMEWORK.md §4)")
        for name in ("brightness", "contrast", "saturation"):
            if not 0.0 <= getattr(a, name) <= 0.5:
                problems.append(f"augmentation.{name} must be in [0, 0.5]")
        if problems:
            raise TrainingConfigError("invalid training config:\n  - " + "\n  - ".join(problems))

    def check_against_project(self, spec: ClassSpec | None = None,
                              project: dict[str, Any] | None = None) -> None:
        """Refuse a training config that contradicts ``configs/project.yaml``."""
        spec = spec or ClassSpec.from_config()
        project = project or load_config()
        problems = []
        if self.model.num_classes != spec.num_classes:
            problems.append(
                f"model.num_classes={self.model.num_classes} but project.yaml defines "
                f"{spec.num_classes} trainable classes {list(spec.trainable)}")
        target = project.get("preprocessing", {}).get("target_size")
        if target is not None and int(target) != self.data.image_size:
            problems.append(f"data.image_size={self.data.image_size} but preprocessing."
                            f"target_size={target} in project.yaml")
        if problems:
            raise TrainingConfigError("training config disagrees with project.yaml:\n  - "
                                      + "\n  - ".join(problems))


__all__ = [
    "MONITORS",
    "OPTIMIZERS",
    "SCHEDULERS",
    "SUPPORTED_MODELS",
    "TRAINING_CONFIG_PATH",
    "AugmentationConfig",
    "TrainingConfig",
    "TrainingConfigError",
]
