"""Calibration and confidence analysis of model probabilities.

These describe how well a MODEL's probabilities match its own hit rate on held-out,
expert-labelled data. They say nothing about archaeological confidence, which comes from
evidence (src.reasoning). With few samples they are noisy; ``n`` is always reported, and a
bin with no samples is reported as empty, not as zero error.

* ECE  expected calibration error: sum over bins of |accuracy - mean confidence| x bin share
* MCE  maximum calibration error over non-empty bins
* Brier multiclass Brier score: mean squared error between the probability vector and the
       one-hot truth (0 = perfect; 2 = confidently wrong)
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import numpy as np


def calibration_report(y_true: Sequence[int], y_prob: np.ndarray, *, n_bins: int = 10) -> dict[str, Any] | None:
    """ECE, MCE, Brier, reliability bins and confidence analysis; ``None`` for no samples."""
    probs = np.asarray(y_prob, dtype=np.float64)
    y = np.asarray([int(v) for v in y_true])
    if y.size == 0:
        return None
    if probs.ndim != 2 or probs.shape[0] != y.size:
        raise ValueError("y_prob must be (n_samples, n_classes) and match y_true")
    if n_bins < 1:
        raise ValueError("n_bins must be >= 1")
    conf = probs.max(axis=1)
    pred = probs.argmax(axis=1)
    correct = pred == y
    onehot = np.zeros_like(probs)
    onehot[np.arange(y.size), y] = 1.0
    brier = float(((probs - onehot) ** 2).sum(axis=1).mean())

    edges = np.linspace(0.0, 1.0, n_bins + 1)
    bins, ece, mce = [], 0.0, 0.0
    for i in range(n_bins):
        lo, hi = edges[i], edges[i + 1]
        mask = (conf > lo) & (conf <= hi) if i else (conf >= lo) & (conf <= hi)
        n = int(mask.sum())
        if n == 0:
            bins.append({"range": [round(float(lo), 3), round(float(hi), 3)], "n": 0, "accuracy": None, "mean_confidence": None})
            continue
        acc, mc = float(correct[mask].mean()), float(conf[mask].mean())
        gap = abs(acc - mc)
        ece += gap * n / y.size
        mce = max(mce, gap)
        bins.append({"range": [round(float(lo), 3), round(float(hi), 3)], "n": n, "accuracy": round(float(acc), 6),
                     "mean_confidence": round(float(mc), 6), "gap": round(float(gap), 6)})

    def _mean(mask: np.ndarray) -> float | None:
        return float(conf[mask].mean()) if mask.any() else None

    return {
        "n_samples": int(y.size), "n_bins": n_bins,
        "ece": round(float(ece), 6), "mce": round(float(mce), 6), "brier": round(float(brier), 6),
        "reliability": bins,
        "confidence_analysis": {
            "mean_confidence": round(float(conf.mean()), 6),
            "mean_confidence_correct": _mean(correct),
            "mean_confidence_incorrect": _mean(~correct),
            "overconfident": bool(conf.mean() > correct.mean()),
            "note": "Model probabilities, not archaeological confidence.",
        },
    }


__all__ = ["calibration_report"]
