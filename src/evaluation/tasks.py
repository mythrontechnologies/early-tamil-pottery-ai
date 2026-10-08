"""Evaluation of every task the pipeline could one day perform on REAL data (Milestone 11).

Pure functions over predictions and expert-promoted ground truth. Nothing here loads a model or
a dataset, so nothing here can run before the readiness gate allows it; ``src.evaluation``
calls these only after the gate has passed, and only with expert-promoted labels.

* ``detection_report``    inscription-region detection: greedy IoU matching, precision / recall /
                          F1 at IoU 0.5 and 0.75, mean IoU of matched boxes, per-image misses
* ``ocr_report``          transcription: CER, WER, exact-reading accuracy, and a failure analysis
                          (no output / partly right / wrong); illegible references are excluded,
                          never scored as an error of the model
* ``error_analysis``      classification: every misclassified artifact with its confidence, the
                          high-confidence errors, and accuracy per confidence bin
* ``robustness_report``   the same model re-scored under photographic perturbations
                          (``src.evaluation.perturbations``): lighting, blur, noise, compression,
                          rotation, scale, crop, occlusion

Every report states its ``evidence_tier``: ``real_expert_labelled`` is the only tier that may be
called a real-data validation result. Synthetic benchmarks live in ``src.synthetic`` and are never
merged into these reports.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from itertools import pairwise
from typing import Any

import numpy as np

from .ocr import character_error_rate, word_error_rate

Box = tuple[float, float, float, float]          # x, y, w, h (any consistent unit)
TIERS = ("real_expert_labelled", "synthetic_engineering", "test_fixture")


def iou(a: Box, b: Box) -> float:
    ax2, ay2, bx2, by2 = a[0] + a[2], a[1] + a[3], b[0] + b[2], b[1] + b[3]
    iw, ih = max(0.0, min(ax2, bx2) - max(a[0], b[0])), max(0.0, min(ay2, by2) - max(a[1], b[1]))
    inter = iw * ih
    union = a[2] * a[3] + b[2] * b[3] - inter
    return inter / union if union > 0 else 0.0


def match_boxes(pred: Sequence[Box], gt: Sequence[Box], threshold: float = 0.5) -> list[tuple[int, int, float]]:
    """Greedy one-to-one matching by descending IoU. Returns (pred index, gt index, iou)."""
    cand = sorted(((iou(p, g), i, j) for i, p in enumerate(pred) for j, g in enumerate(gt)), reverse=True)
    used_p: set[int] = set()
    used_g: set[int] = set()
    out = []
    for v, i, j in cand:
        if v < threshold:
            break
        if i in used_p or j in used_g:
            continue
        used_p.add(i)
        used_g.add(j)
        out.append((i, j, v))
    return out


def _prf(tp: int, fp: int, fn: int) -> dict[str, Any]:
    p = tp / (tp + fp) if tp + fp else None
    r = tp / (tp + fn) if tp + fn else None
    f = 2 * p * r / (p + r) if p and r else (0.0 if p is not None and r is not None else None)
    return {"precision": p, "recall": r, "f1": f, "true_positives": tp, "false_positives": fp, "false_negatives": fn}


def detection_report(gt: dict[str, list[Box]], pred: dict[str, list[Box]], *,
                     thresholds: Sequence[float] = (0.5, 0.75), evidence_tier: str = "real_expert_labelled") -> dict[str, Any]:
    """Region detection over images with ground-truth regions (``gt``) and predictions (``pred``).

    An image absent from ``pred`` counts as no detection. Images whose ground truth is an empty list
    are images an expert marked as carrying no region: any prediction there is a false positive."""
    if evidence_tier not in TIERS:
        raise ValueError(f"unknown evidence tier {evidence_tier!r}")
    out: dict[str, Any] = {"evidence_tier": evidence_tier, "images": len(gt), "by_threshold": {}}
    for t in thresholds:
        tp = fp = fn = 0
        ious: list[float] = []
        missed: list[str] = []
        for image_id, boxes in sorted(gt.items()):
            p = pred.get(image_id, [])
            m = match_boxes(p, boxes, t)
            tp, fp, fn = tp + len(m), fp + len(p) - len(m), fn + len(boxes) - len(m)
            ious += [v for _, _, v in m]
            if len(m) < len(boxes):
                missed.append(image_id)
        out["by_threshold"][f"iou_{t:g}"] = _prf(tp, fp, fn) | {
            "mean_iou_of_matches": float(np.mean(ious)) if ious else None, "images_with_missed_regions": missed}
    return out


def ocr_report(pairs: Sequence[tuple[str, str | None]], *, illegible: Sequence[bool] | None = None,
               evidence_tier: str = "real_expert_labelled") -> dict[str, Any]:
    """``pairs`` = (expert reference reading, model hypothesis or None).

    A reference flagged ``illegible`` (the expert could not read it) is excluded: an unreadable
    inscription is not a test of the model. Failure categories: ``no_output`` (the model declined),
    ``exact``, ``partial`` (CER < 0.5), ``wrong`` (CER >= 0.5)."""
    flags = list(illegible) if illegible is not None else [False] * len(pairs)
    scored = [(r, h) for (r, h), ill in zip(pairs, flags) if not ill and r]
    buckets = {"exact": 0, "partial": 0, "wrong": 0, "no_output": 0}
    cers, wers = [], []
    for ref, hyp in scored:
        if not hyp:
            buckets["no_output"] += 1
            continue
        c = character_error_rate(ref, hyp)
        cers.append(c)
        wers.append(word_error_rate(ref, hyp))
        buckets["exact" if c == 0 else "partial" if c < 0.5 else "wrong"] += 1
    n = len(scored)
    return {"evidence_tier": evidence_tier, "references": n, "excluded_illegible": sum(flags),
            "cer_mean": float(np.mean(cers)) if cers else None, "wer_mean": float(np.mean(wers)) if wers else None,
            "exact_reading_accuracy": buckets["exact"] / n if n else None,
            "coverage": (n - buckets["no_output"]) / n if n else None, "failures": buckets,
            "note": "CER/WER compare with the expert's reading; they say nothing about readings no expert gave"}


def error_analysis(artifact_ids: Sequence[str], y_true: Sequence[int], y_prob: np.ndarray,
                   class_names: Sequence[str], *, high_confidence: float = 0.8,
                   bins: Sequence[float] = (0.0, 0.4, 0.6, 0.8, 1.0001)) -> dict[str, Any]:
    """Every error with its confidence, and how accuracy varies with confidence."""
    prob = np.asarray(y_prob, dtype=float)
    pred, conf = prob.argmax(axis=1), prob.max(axis=1)
    errors: list[dict[str, Any]] = [
        {"artifact_id": a, "true": class_names[t], "predicted": class_names[int(p)], "confidence": float(c)}
              for a, t, p, c in zip(artifact_ids, y_true, pred, conf) if int(p) != int(t)]
    by_bin = []
    for lo, hi in pairwise(bins):
        m = (conf >= lo) & (conf < hi)
        n = int(m.sum())
        by_bin.append({"confidence": f"[{lo:.1f}, {min(hi, 1.0):.1f}]", "n": n,
                       "accuracy": float((pred[m] == np.asarray(y_true)[m]).mean()) if n else None})
    return {"errors": sorted(errors, key=lambda e: -e["confidence"]),
            "high_confidence_errors": sum(e["confidence"] >= high_confidence for e in errors),
            "accuracy_by_confidence": by_bin,
            "note": "a model probability is not archaeological confidence; high-confidence errors are the ones to "
                    "inspect first (shortcuts such as lighting, display glass or photographer)"}


def robustness_report(predict: Callable[[list[Any]], np.ndarray], images: list[Any], y_true: Sequence[int],
                      perturbations: dict[str, tuple[str, str, Any]] | None = None,
                      ids: Sequence[str] | None = None, *, evidence_tier: str = "real_expert_labelled") -> dict[str, Any]:
    """Accuracy of ``predict`` (PIL images -> probabilities) on clean and perturbed copies.

    Perturbations are seeded by ``ids`` (default: position), so a re-run is identical."""
    from .perturbations import PHOTOGRAPHIC, seed

    perturbations = perturbations or PHOTOGRAPHIC
    ids = list(ids) if ids is not None else [str(i) for i in range(len(images))]
    y = np.asarray(y_true)
    rows: dict[str, Any] = {}
    clean_acc = None
    for name, (family, severity, fn) in perturbations.items():
        batch = images if fn is None else [fn(im, seed(f"{name}:{i}")) for im, i in zip(images, ids)]
        acc = float((np.asarray(predict(batch)).argmax(axis=1) == y).mean()) if len(y) else None
        if name == "clean":
            clean_acc = acc
        rows[name] = {"family": family, "severity": severity, "accuracy": acc}
    for r in rows.values():
        r["drop_from_clean"] = (clean_acc - r["accuracy"]) if clean_acc is not None and r["accuracy"] is not None else None
    return {"evidence_tier": evidence_tier, "images": len(images), "clean_accuracy": clean_acc, "perturbations": rows}


__all__ = ["TIERS", "detection_report", "error_analysis", "iou", "match_boxes", "ocr_report", "robustness_report"]
