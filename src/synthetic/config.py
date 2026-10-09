"""Strict loader for ``configs/synthetic_dataset.yaml`` (generator settings).

Unknown keys and impossible values are errors: a silently ignored typo would make the dataset
differ from what its fingerprint and documentation say. The configuration digest (SHA-256 of
the canonical JSON) is part of the synthetic dataset fingerprint.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path
from typing import Any

import yaml

from . import DATASET_CONFIG_PATH, DATASET_TYPE


class SyntheticConfigError(ValueError):
    """The synthetic generator configuration is invalid."""


@dataclass(frozen=True)
class Views:
    min: int = 2
    max: int = 3
    p_extra: float = 0.2


@dataclass(frozen=True)
class Canvas:
    min_px: int = 300
    max_px: int = 420


@dataclass(frozen=True)
class JpegQuality:
    min: int = 60
    max: int = 95


@dataclass(frozen=True)
class Conditions:
    rotation_degrees_max: float = 20.0
    perspective_max: float = 0.07
    object_fill: tuple[float, float] = (0.55, 0.9)
    exposure: tuple[float, float] = (0.65, 1.35)
    contrast: tuple[float, float] = (0.75, 1.25)
    white_balance_jitter: float = 0.06
    blur_probability: float = 0.5
    blur_sigma_max: float = 1.6
    noise_sigma_max: float = 6.0
    occlusion_probability: float = 0.25
    occlusion_max_fraction: float = 0.12
    scratches_max: int = 6
    cracks_max: int = 2
    pits_max: int = 25


@dataclass(frozen=True)
class Marks:
    glyphs_per_row: tuple[int, int] = (3, 8)
    word_break_probability: float = 0.4
    graffiti_motifs: tuple[int, int] = (1, 3)
    uncertain_modes: tuple[str, ...] = ("cut_row", "faint", "fragment", "overscratched")


@dataclass(frozen=True)
class SplitConfig:
    seed: int = 20261003
    train: float = 0.70
    val: float = 0.15
    test: float = 0.15
    min_artifacts_per_class_for_holdout: int = 20
    k_folds: int = 5
    balance_secondary: tuple[str, ...] = ("synthetic_surface",)


UNCERTAIN_MODES = ("cut_row", "faint", "fragment", "overscratched")


def _build(cls: type, data: Any, section: str) -> Any:
    data = dict(data or {})
    unknown = sorted(set(data) - {f.name for f in fields(cls)})
    if unknown:
        raise SyntheticConfigError(f"[{section}] unknown key(s): {', '.join(unknown)}")
    for f in fields(cls):
        if f.name in data and isinstance(data[f.name], list):
            data[f.name] = tuple(data[f.name])
    return cls(**data)


@dataclass(frozen=True)
class SyntheticDatasetConfig:
    generator_version: str = "1.1.0"
    seed: int = 20261003
    artifacts_per_class: int = 250
    object_px: int = 512
    views: Views = field(default_factory=Views)
    canvas: Canvas = field(default_factory=Canvas)
    jpeg_quality: JpegQuality = field(default_factory=JpegQuality)
    conditions: Conditions = field(default_factory=Conditions)
    marks: Marks = field(default_factory=Marks)
    split: SplitConfig = field(default_factory=SplitConfig)
    dataset_type: str = DATASET_TYPE

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SyntheticDatasetConfig:
        data = dict(data or {})
        sections = {"views": Views, "canvas": Canvas, "jpeg_quality": JpegQuality, "conditions": Conditions,
                     "marks": Marks, "split": SplitConfig}
        scalars = {"generator_version", "seed", "artifacts_per_class", "object_px", "dataset_type"}
        unknown = sorted(set(data) - set(sections) - scalars)
        if unknown:
            raise SyntheticConfigError(f"unknown top-level key(s): {', '.join(unknown)}")
        if data.get("dataset_type", DATASET_TYPE) != DATASET_TYPE:
            raise SyntheticConfigError(f"dataset_type must be {DATASET_TYPE!r}; this loader builds synthetic data only")
        built = {name: _build(klass, data.get(name), name) for name, klass in sections.items()}
        cfg = cls(generator_version=str(data.get("generator_version", "1.1.0")),
                  seed=int(data.get("seed", 20261003)),
                  artifacts_per_class=int(data.get("artifacts_per_class", 250)),
                  object_px=int(data.get("object_px", 512)), **built)
        cfg.validate()
        return cfg

    @classmethod
    def load(cls, path: Path | str | None = None) -> SyntheticDatasetConfig:
        p = Path(path) if path else DATASET_CONFIG_PATH
        if not p.exists():
            raise SyntheticConfigError(f"synthetic dataset config not found: {p}")
        return cls.from_dict(yaml.safe_load(p.read_text(encoding="utf-8")) or {})

    def with_overrides(self, **changes: Any) -> SyntheticDatasetConfig:
        """A copy with top-level fields replaced (``artifacts_per_class``, ``seed``...), re-validated."""
        data = self.to_dict()
        data.update(changes)
        return SyntheticDatasetConfig.from_dict(data)

    def to_dict(self) -> dict[str, Any]:
        return json.loads(json.dumps(asdict(self)))          # tuples -> lists, plain JSON types

    @property
    def digest(self) -> str:
        blob = json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":")).encode("utf-8")
        return hashlib.sha256(blob).hexdigest()

    def validate(self) -> None:
        from .generator import GENERATOR_VERSION

        c, m, s, v = self.conditions, self.marks, self.split, self.views
        problems = []
        if self.generator_version != GENERATOR_VERSION:
            problems.append(f"generator_version {self.generator_version!r} but the code is {GENERATOR_VERSION!r}; "
                            "a dataset can only be reproduced by the generator version that made it")
        if self.artifacts_per_class < 1:
            problems.append("artifacts_per_class must be >= 1")
        if not 1 <= v.min <= v.max <= 6 or not 0 <= v.p_extra <= 1:
            problems.append("views: need 1 <= min <= max <= 6 and 0 <= p_extra <= 1")
        if not 64 <= self.canvas.min_px <= self.canvas.max_px <= 2048:
            problems.append("canvas: need 64 <= min_px <= max_px <= 2048")
        if self.object_px < 128:
            problems.append("object_px must be >= 128")
        if not 1 <= self.jpeg_quality.min <= self.jpeg_quality.max <= 100:
            problems.append("jpeg_quality: need 1 <= min <= max <= 100")
        if not 0 <= c.rotation_degrees_max <= 45 or not 0 <= c.perspective_max <= 0.2:
            problems.append("conditions: rotation_degrees_max in [0, 45], perspective_max in [0, 0.2]")
        for name in ("object_fill", "exposure", "contrast"):
            lo, hi = getattr(c, name)
            if not 0 < lo <= hi:
                problems.append(f"conditions.{name} must be an increasing positive pair")
        if not 0 < c.object_fill[1] <= 1:
            problems.append("conditions.object_fill upper bound must be <= 1")
        for name in ("blur_probability", "occlusion_probability", "occlusion_max_fraction", "white_balance_jitter"):
            if not 0 <= getattr(c, name) <= 1:
                problems.append(f"conditions.{name} must be in [0, 1]")
        if c.blur_sigma_max < 0 or c.noise_sigma_max < 0 or min(c.scratches_max, c.cracks_max, c.pits_max) < 0:
            problems.append("conditions: blur, noise and distractor counts must be >= 0")
        lo, hi = m.glyphs_per_row
        if not 2 <= lo <= hi <= 12:
            problems.append("marks.glyphs_per_row: need 2 <= min <= max <= 12")
        lo, hi = m.graffiti_motifs
        if not 1 <= lo <= hi <= 4:
            problems.append("marks.graffiti_motifs: need 1 <= min <= max <= 4")
        if not m.uncertain_modes or set(m.uncertain_modes) - set(UNCERTAIN_MODES):
            problems.append(f"marks.uncertain_modes must be a non-empty subset of {UNCERTAIN_MODES}")
        if abs(s.train + s.val + s.test - 1.0) > 1e-9 or min(s.train, s.val, s.test) <= 0:
            problems.append("split proportions must be positive and sum to 1")
        if problems:
            raise SyntheticConfigError("invalid synthetic dataset config:\n  - " + "\n  - ".join(problems))


__all__ = ["UNCERTAIN_MODES", "SyntheticConfigError", "SyntheticDatasetConfig"]
