"""Classification metrics, and the rule that evaluation without real data is blocked.

Metrics are computed from the confusion matrix directly, so undefined values stay
undefined instead of being turned into zeros:

* recall for a class with no true examples is ``None`` (undefined), not 0;
* precision for a class that was never predicted is 0 if the class has true examples
  (the model missed all of them) and ``None`` if it has none;
* macro averages are taken over classes **with support**, and the report lists any
  class excluded for having none. A silent zero for a missing class would drag a macro
  score down; a silent omission would hide that the class was never tested.

``balanced_accuracy`` is the macro recall over supported classes.

Nothing here decides whether a number is meaningful. :func:`evaluate_predictions` does:
an empty evaluation returns a ``BLOCKED`` report carrying
``NO REAL DATA — EVALUATION BLOCKED``, and a non-research provenance is stamped on the
report so a fixture score can never be read as a result.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import asdict, dataclass, field
from typing import Any, Literal

import numpy as np

BLOCKED_MESSAGE = "NO REAL DATA — EVALUATION BLOCKED"
Provenance = Literal["research", "synthetic_test"]


class EmptyEvaluationError(ValueError):
    """There are no samples to evaluate."""


@dataclass
class ClassMetrics:
    precision: float | None
    recall: float | None
    f1: float | None
    support: int
    predicted: int


@dataclass
class ClassificationMetrics:
    n_samples: int
    class_names: list[str]
    accuracy: float
    balanced_accuracy: float | None
    macro_precision: float | None
    macro_recall: float | None
    macro_f1: float | None
    weighted_f1: float | None
    per_class: dict[str, ClassMetrics]
    confusion_matrix: list[list[int]]           # rows = true, columns = predicted
    top_k_accuracy: dict[int, float] = field(default_factory=dict)
    classes_without_support: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def confusion_matrix(y_true: Sequence[int], y_pred: Sequence[int], num_classes: int) -> np.ndarray:
    cm = np.zeros((num_classes, num_classes), dtype=np.int64)
    for t, p in zip(y_true, y_pred):
        if not (0 <= t < num_classes and 0 <= p < num_classes):
            raise ValueError(f"label out of range: true={t}, pred={p}, classes={num_classes}")
        cm[t, p] += 1
    return cm


def _mean(values: list[float]) -> float | None:
    return float(np.mean(values)) if values else None


def top_k_accuracy(y_true: Sequence[int], y_prob: np.ndarray, k: int) -> float:
    probs = np.asarray(y_prob, dtype=np.float64)
    if probs.ndim != 2 or probs.shape[0] != len(y_true):
        raise ValueError("y_prob must be (n_samples, n_classes)")
    # Stable ordering: ties resolved by lower class index, so results are deterministic.
    order = np.argsort(-probs, axis=1, kind="stable")[:, :k]
    hits = [int(t) in row for t, row in zip(y_true, order)]
    return float(np.mean(hits))


def compute_metrics(
    y_true: Sequence[int],
    y_pred: Sequence[int],
    class_names: Sequence[str],
    *,
    y_prob: np.ndarray | None = None,
    top_k: Sequence[int] = (2,),
) -> ClassificationMetrics:
    """Multiclass metrics. Raises :class:`EmptyEvaluationError` on zero samples."""
    y_true = [int(v) for v in y_true]
    y_pred = [int(v) for v in y_pred]
    if len(y_true) != len(y_pred):
        raise ValueError("y_true and y_pred differ in length")
    if not y_true:
        raise EmptyEvaluationError(BLOCKED_MESSAGE)
    n = len(class_names)
    cm = confusion_matrix(y_true, y_pred, n)
    support = cm.sum(axis=1)
    predicted = cm.sum(axis=0)
    tp = np.diag(cm)

    per_class: dict[str, ClassMetrics] = {}
    for i, name in enumerate(class_names):
        s, p_n, t = int(support[i]), int(predicted[i]), int(tp[i])
        recall = t / s if s > 0 else None
        if p_n > 0:
            precision: float | None = t / p_n
        else:
            precision = 0.0 if s > 0 else None
        if recall is None or precision is None:
            f1 = None
        elif precision + recall == 0:
            f1 = 0.0
        else:
            f1 = 2 * precision * recall / (precision + recall)
        per_class[name] = ClassMetrics(precision, recall, f1, s, p_n)

    supported = [c for c in class_names if per_class[c].support > 0]
    total = sum(per_class[c].support for c in supported)
    weighted = [per_class[c].f1 * per_class[c].support for c in supported
                if per_class[c].f1 is not None]

    topk: dict[int, float] = {}
    if y_prob is not None:
        for k in top_k:
            if 1 < k < n:
                topk[int(k)] = top_k_accuracy(y_true, y_prob, int(k))

    macro_recall = _mean([per_class[c].recall for c in supported])  # type: ignore[misc]
    return ClassificationMetrics(
        n_samples=len(y_true),
        class_names=list(class_names),
        accuracy=float(tp.sum() / len(y_true)),
        balanced_accuracy=macro_recall,
        macro_precision=_mean([per_class[c].precision for c in supported]),  # type: ignore[misc]
        macro_recall=macro_recall,
        macro_f1=_mean([per_class[c].f1 for c in supported if per_class[c].f1 is not None]),
        weighted_f1=(sum(weighted) / total) if total else None,
        per_class=per_class,
        confusion_matrix=cm.tolist(),
        top_k_accuracy=topk,
        classes_without_support=[c for c in class_names if c not in supported],
    )


def aggregate_by_artifact(
    artifact_ids: Sequence[str], y_true: Sequence[int], y_prob: np.ndarray
) -> tuple[list[str], list[int], np.ndarray]:
    """Average class probabilities over all photographs of each artifact.

    The artifact is the unit of evidence, so artifact-level metrics are the headline;
    image-level metrics over-count heavily photographed sherds. Raises if one artifact
    carries two different labels.
    """
    probs = np.asarray(y_prob, dtype=np.float64)
    groups: dict[str, list[int]] = {}
    for i, aid in enumerate(artifact_ids):
        groups.setdefault(str(aid), []).append(i)
    ids, labels, rows = [], [], []
    for aid in sorted(groups):
        idx = groups[aid]
        labs = {int(y_true[i]) for i in idx}
        if len(labs) != 1:
            raise ValueError(f"artifact {aid!r} has inconsistent labels {sorted(labs)}")
        ids.append(aid)
        labels.append(labs.pop())
        rows.append(probs[idx].mean(axis=0))
    return ids, labels, np.vstack(rows) if rows else np.zeros((0, probs.shape[1]))


@dataclass
class EvaluationReport:
    status: Literal["COMPLETED", "BLOCKED"]
    provenance: str
    unit: str
    message: str
    metrics: ClassificationMetrics | None = None

    def to_dict(self) -> dict[str, Any]:
        return {"status": self.status, "provenance": self.provenance, "unit": self.unit,
                "message": self.message,
                "metrics": self.metrics.to_dict() if self.metrics else None}

    def render(self) -> str:
        if self.status == "BLOCKED":
            return f"{'=' * 68}\n{self.message}\n{'=' * 68}"
        m = self.metrics
        assert m is not None
        lines = ["=" * 68]
        if self.provenance != "research":
            lines.append(f"!! {self.provenance.upper()} DATA - NOT AN ARCHAEOLOGICAL RESULT !!")
        lines += [f"Evaluation ({self.unit}-level, n={m.n_samples})",
                  f"  accuracy           {m.accuracy:.4f}",
                  f"  balanced accuracy  {_fmt(m.balanced_accuracy)}",
                  f"  macro precision    {_fmt(m.macro_precision)}",
                  f"  macro recall       {_fmt(m.macro_recall)}",
                  f"  macro F1           {_fmt(m.macro_f1)}",
                  f"  weighted F1        {_fmt(m.weighted_f1)}"]
        for k, v in m.top_k_accuracy.items():
            lines.append(f"  top-{k} accuracy     {v:.4f}")
        lines.append("  per class (precision / recall / F1 / support):")
        for name, c in m.per_class.items():
            lines.append(f"    {name:<28} {_fmt(c.precision)} / {_fmt(c.recall)} / "
                         f"{_fmt(c.f1)} / {c.support}")
        if m.classes_without_support:
            lines.append(f"  classes with no examples (excluded from macro): "
                         f"{m.classes_without_support}")
        lines.append("  confusion matrix (rows = true, cols = predicted):")
        for name, row in zip(m.class_names, m.confusion_matrix):
            lines.append(f"    {name:<28} {row}")
        lines.append("=" * 68)
        return "\n".join(lines)


def _fmt(v: float | None) -> str:
    return "undefined" if v is None else f"{v:.4f}"


def blocked_report(reason: str = BLOCKED_MESSAGE, *, unit: str = "artifact") -> EvaluationReport:
    message = BLOCKED_MESSAGE if reason == BLOCKED_MESSAGE else f"{BLOCKED_MESSAGE}\n{reason}"
    return EvaluationReport("BLOCKED", "none", unit, message)


def evaluate_predictions(
    y_true: Sequence[int],
    y_pred: Sequence[int],
    class_names: Sequence[str],
    *,
    y_prob: np.ndarray | None = None,
    provenance: Provenance = "research",
    unit: str = "image",
) -> EvaluationReport:
    """Metrics wrapped in a report; empty input gives a ``BLOCKED`` report, not zeros."""
    if len(y_true) == 0:
        return blocked_report(unit=unit)
    metrics = compute_metrics(y_true, y_pred, class_names, y_prob=y_prob)
    message = ("evaluation completed" if provenance == "research"
               else f"{provenance} data: metrics exercise the code, they are not a result")
    return EvaluationReport("COMPLETED", provenance, unit, message, metrics)


__all__ = [
    "BLOCKED_MESSAGE",
    "ClassMetrics",
    "ClassificationMetrics",
    "EmptyEvaluationError",
    "EvaluationReport",
    "aggregate_by_artifact",
    "blocked_report",
    "compute_metrics",
    "confusion_matrix",
    "evaluate_predictions",
    "top_k_accuracy",
]
