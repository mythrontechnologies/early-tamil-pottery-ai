"""Class statistics and class-imbalance corrections.

Two corrections are available, and **only one may be used at a time**:

* ``class_weighted_loss`` - per-class weights passed to the loss function;
* ``weighted_sampler`` - per-image sampling weights for a ``WeightedRandomSampler``.

Using both corrects for imbalance twice. :func:`check_strategy` rejects that.

Counts can be taken per ``artifact`` (default) or per ``image``. Per-artifact counting
matches the evaluation unit and stops one heavily photographed sherd from dominating
the weights.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Any, Literal

from .classes import ClassSpec

ImbalanceStrategy = Literal["none", "class_weighted_loss", "weighted_sampler"]
CountUnit = Literal["artifact", "image"]
STRATEGIES: tuple[str, ...] = ("none", "class_weighted_loss", "weighted_sampler")


class ImbalanceError(ValueError):
    """Invalid imbalance configuration or unusable class counts."""


def check_strategy(strategy: str | Sequence[str]) -> str:
    """Validate the configured strategy. A list with two corrections is an error."""
    if isinstance(strategy, (list, tuple)):
        chosen = [s for s in strategy if s != "none"]
        if len(chosen) > 1:
            raise ImbalanceError(
                f"choose ONE imbalance strategy, got {chosen}: weighted loss and weighted "
                "sampling together double-count the correction"
            )
        strategy = chosen[0] if chosen else "none"
    if strategy not in STRATEGIES:
        raise ImbalanceError(f"unknown imbalance strategy {strategy!r}; use one of {STRATEGIES}")
    return strategy


def class_counts(records: Iterable[Any], spec: ClassSpec, unit: CountUnit = "artifact") -> dict[str, int]:
    """Counts per trainable class, in class-index order. Held-out labels are skipped."""
    if unit not in ("artifact", "image"):
        raise ImbalanceError(f"count unit must be 'artifact' or 'image', got {unit!r}")
    arts: dict[str, set[str]] = defaultdict(set)
    imgs: Counter[str] = Counter()
    for r in records:
        label = r.get("script_type")
        if label not in spec.trainable:
            continue
        arts[label].add(str(r.get("artifact_id")))
        imgs[label] += 1
    if unit == "artifact":
        return {c: len(arts[c]) for c in spec.trainable}
    return {c: imgs[c] for c in spec.trainable}


def class_weights(counts: dict[str, int], classes: Sequence[str]) -> list[float]:
    """Inverse-frequency weights, normalised to mean 1.0, in ``classes`` order.

    A class with zero examples cannot be weighted; that is an error, not a zero weight,
    because a silent zero would hide a missing class.
    """
    missing = [c for c in classes if counts.get(c, 0) <= 0]
    if missing:
        raise ImbalanceError(f"cannot weight classes with no examples: {missing}")
    raw = [1.0 / counts[c] for c in classes]
    mean = sum(raw) / len(raw)
    return [w / mean for w in raw]


def sample_weights(
    records: Sequence[Any],
    spec: ClassSpec,
    *,
    unit: CountUnit = "artifact",
    equalise_artifacts: bool = True,
) -> list[float]:
    """One sampling weight per record, for ``torch.utils.data.WeightedRandomSampler``.

    Each class receives equal total mass. With ``equalise_artifacts`` each artifact
    within a class also receives equal mass, split across its photographs.
    """
    counts = class_counts(records, spec, unit)
    class_weights(counts, spec.trainable)  # raises on an empty class
    per_artifact_images: Counter[str] = Counter(str(r.get("artifact_id")) for r in records)
    weights: list[float] = []
    for r in records:
        label = r.get("script_type")
        if label not in spec.trainable:
            raise ImbalanceError(f"record {r.get('image_id')!r} has non-trainable label {label!r}")
        w = 1.0 / counts[label]
        if equalise_artifacts:
            w /= per_artifact_images[str(r.get("artifact_id"))]
        weights.append(w)
    return weights


@dataclass(frozen=True)
class ClassRow:
    label: str
    status: str
    artifacts: int
    images: int
    artifact_percentage: float

    def to_dict(self) -> dict[str, Any]:
        return {"class": self.label, "status": self.status, "artifacts": self.artifacts,
                "images": self.images, "percentage_of_artifacts": round(self.artifact_percentage, 2)}


def imbalance_table(records: Iterable[Any], spec: ClassSpec) -> list[ClassRow]:
    """The pre-training class report: class, artifact count, image count, percentage.

    Percentages are of *trainable* artifacts. Held-out labels are listed with their
    counts and a percentage of 0.0, because they do not enter training.
    """
    from .classes import class_availability

    avail = class_availability(records, spec)
    total = sum(a.artifacts for a in avail if a.status == "trainable")
    rows = []
    for a in avail:
        pct = (100.0 * a.artifacts / total) if (total and a.status == "trainable") else 0.0
        rows.append(ClassRow(a.label, a.status, a.artifacts, a.images, pct))
    return rows


def render_imbalance_table(rows: Sequence[ClassRow]) -> str:
    lines = [f"    {'class':<28}{'status':<11}{'artifacts':>10}{'images':>9}{'% artifacts':>13}"]
    for r in rows:
        pct = f"{r.artifact_percentage:.1f}" if r.status == "trainable" else "held out"
        lines.append(f"    {r.label:<28}{r.status:<11}{r.artifacts:>10}{r.images:>9}{pct:>13}")
    return "\n".join(lines)


__all__ = [
    "STRATEGIES",
    "ClassRow",
    "ImbalanceError",
    "check_strategy",
    "class_counts",
    "class_weights",
    "imbalance_table",
    "render_imbalance_table",
    "sample_weights",
]
