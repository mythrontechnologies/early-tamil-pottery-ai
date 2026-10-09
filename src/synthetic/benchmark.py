"""The integrated synthetic evaluation (Milestone 10).

    python -m src.evaluation synthetic [--partition test] [--skip-robustness] [--json]

    SYNTHETIC ENGINEERING BENCHMARK — every number measures the pipeline on generated images.

Wording is part of the result: "accuracy on the synthetic benchmark", "glyph recognition accuracy on the
synthetic glyph benchmark", "synthetic chronology reasoning test". Never Tamil-Brahmi accuracy, never OCR
accuracy on inscriptions, never date prediction accuracy.

A. classification (image and artifact level; calibration before/after temperature scaling)
B. detection: synthetic inscription regions and glyph rows (IoU >= 0.5), false alarms on no-mark images
C. OCR: glyph accuracy with true glyph regions; segmentation of true rows by every strategy; reading of
   true rows; end to end (detected row -> selected segmentation -> GlyphNet)
D. calibration (ECE, MCE, Brier, NLL) of the deployed, temperature-scaled classifier
E. robustness (blur, noise, occlusion, scale, exposure, contrast)
F. interpretation and synthetic chronology agreement with the same rules applied to ground truth
G. latency and memory of the complete pipeline
"""

from __future__ import annotations

import json
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

from src.dataset.splits import partition_records

from . import DATASET_TYPE, MARKER, PURPOSE, SYNTHETIC_MODELS_ROOT, assert_synthetic_model_destination
from .dataset import SyntheticPaths, find_manifest, load_synthetic_dataset
from .lexicon import METHOD, SPEC_ID, decode, grammatical_interpretation
from .lexicon import target as language_target
from .ocr_benchmark import _rgb, classify, enhanced_gray, glyph_crops
from .pipeline import SyntheticPipeline
from .reasoning import chronology
from .vision import (
    STRATEGIES,
    detect_regions,
    inscription_regions,
    match_boxes,
    reading_scores,
    segment,
    segmentation_scores,
)

BANNER = "SYNTHETIC ENGINEERING BENCHMARK"
REPORT_DIR = SYNTHETIC_MODELS_ROOT / "reports" / "benchmark"
ROBUSTNESS_SET = ("clean", "blur_sigma2", "noise_sigma16", "occlusion_16pct", "scale_0.6", "exposure_0.5", "contrast_0.5")
GLYPHS = [f"SG{i:02d}" for i in range(16)]


def _prf(tp: int, fp: int, fn: int) -> dict[str, float]:
    p = tp / (tp + fp) if tp + fp else 0.0
    r = tp / (tp + fn) if tp + fn else 0.0
    return {"precision": round(p, 4), "recall": round(r, 4), "f1": round(2 * p * r / (p + r), 4) if p + r else 0.0,
            "true_positives": tp, "false_positives": fp, "false_negatives": fn}


def detection_metrics(pipe: SyntheticPipeline, records: list[Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    per: dict[str, list[Any]] = {"regions": [0, 0, 0, []], "rows": [0, 0, 0, []]}
    by_class: dict[str, list[int]] = {}
    false_alarm_images = no_mark_images = 0
    for r in records:
        rgb = _rgb(r.image_path)
        found = detect_regions(pipe.bundle.region_detector, rgb)
        truth = {"regions": inscription_regions(r.record),
                 "rows": [g for g in r.record["synthetic_regions"] if g["kind"] == "glyph_row"]}
        for key in ("regions", "rows"):
            pred: list[tuple[float, ...]] = [(d.x, d.y, d.width, d.height) for d in found[key]]
            gt: list[tuple[float, ...]] = [(g["x"], g["y"], g["width"], g["height"]) for g in truth[key]]
            m = match_boxes(pred, gt)
            per[key][0] += len(m)
            per[key][1] += len(pred) - len(m)
            per[key][2] += len(gt) - len(m)
            per[key][3] += [iou for _, _, iou in m]
            if key == "regions":
                c = by_class.setdefault(r.script_type, [0, 0, 0])
                c[0] += len(m)
                c[1] += len(pred) - len(m)
                c[2] += len(gt) - len(m)
        if r.script_type == "synthetic_none":
            no_mark_images += 1
            false_alarm_images += bool(found["regions"])
    for key, (tp, fp, fn, ious) in per.items():
        out[key] = _prf(tp, fp, fn) | {"mean_iou_of_matches": round(float(np.mean(ious)), 4) if ious else None}
    out["regions"]["class"] = "synthetic_inscription_region"
    out["regions_by_true_class"] = {k: _prf(*v) for k, v in sorted(by_class.items())}
    out["false_alarm_rate_on_no_mark_images"] = round(false_alarm_images / max(no_mark_images, 1), 4)
    out["iou_threshold"] = 0.5
    return out


def ocr_metrics(pipe: SyntheticPipeline, records: list[Any]) -> dict[str, Any]:
    b = pipe.bundle
    crops, labels, _ = glyph_crops(records)
    pred, _ = classify(b.glyph_classifier, list(crops))
    glyph_acc = float(np.mean([p == GLYPHS[y] for p, y in zip(pred, labels)])) if len(pred) else None
    rows = [(enhanced_gray(_rgb(r.image_path)), r.record) for r in records if r.script_type == "synthetic_tamil_brahmi_like"]
    strategies = {}
    for s in STRATEGIES:
        def seg(g: np.ndarray, _s: str = s) -> list[Any]:
            return segment(_s, g, b.glyph_centers)

        strategies[s] = {"segmentation": segmentation_scores(seg, rows),
                         "reading_true_rows": reading_scores(s, b.glyph_classifier, rows, b.glyph_centers)}
    return {"glyph_accuracy_true_regions": round(glyph_acc, 4) if glyph_acc is not None else None,
            "glyphs": len(labels), "rows": len(rows), "selected_strategy": b.strategy,
            "selected_on": b.manifest["segmentation"]["selected_on"], "strategies": strategies}


def end_to_end(pipe: SyntheticPipeline, records: list[Any]) -> dict[str, Any]:
    """Every test image through the complete pipeline, compared with the generator's ground truth."""
    from .vision import rates

    pairs, interp_ok, interp_n, chron_ok, label_ok, lat, mem = [], 0, 0, 0, 0, [], []
    lang_n, lang_ok, pred_status, target_status = 0, Counter[str](), Counter[str](), Counter[str]()
    for r in records:
        rec = dict(r.record)
        a = pipe.run(r.image_path, record=rec)
        lat.append(a["performance"]["total_seconds"])
        if a["performance"]["peak_gpu_memory_mib"] is not None:
            mem.append(a["performance"]["peak_gpu_memory_mib"])
        label_ok += a["classification"]["label"] == r.script_type
        truth_words = rec["synthetic_glyph_sequence"]
        if r.script_type == "synthetic_tamil_brahmi_like":
            pairs.append((truth_words, a["ocr"]["words"]))
            interp_n += 1
            truth = grammatical_interpretation(decode(truth_words))
            interp_ok += (truth["status"], truth["clauses"]) == (a["interpretation"]["status"], a["interpretation"]["clauses"])
            target, pred = rec["synthetic_language_target"], a["synthetic_language"]      # target: evaluation only
            lang_n += 1
            lang_ok["translation_exact"] += (pred["status"], pred["translation"]) == (target["status"], target["translation"])
            lang_ok["transliteration_exact"] += pred["transliteration"] == target["transliteration"]
            lang_ok["status_agreement"] += pred["status"] == target["status"]
            lang_ok["targets_consistent_with_spec"] += language_target(truth_words) == target
            pred_status[pred["status"]] += 1
            target_status[target["status"]] += 1
        truth_chron = chronology(words=truth_words, synthetic_class=r.script_type, class_confidence=1.0, ocr_score=1.0,
                                 surface=rec.get("synthetic_surface"))
        chron_ok += (truth_chron.state, truth_chron.categories) == (a["chronology"]["state"], a["chronology"]["categories"])
    n = max(len(records), 1)
    return {"images": len(records), "classification_accuracy_through_pipeline": round(label_ok / n, 4),
            "ocr": rates(pairs), "grammatical_interpretation_agreement": round(interp_ok / max(interp_n, 1), 4),
            "synthetic_language": {"images": lang_n} | {
                k: round(lang_ok[k] / max(lang_n, 1), 4)
                for k in ("translation_exact", "transliteration_exact", "status_agreement", "targets_consistent_with_spec")}
                | {"predicted_status": dict(sorted(pred_status.items())), "target_status": dict(sorted(target_status.items()))},
            "synthetic_chronology_reasoning_test": {"agreement_with_ground_truth_rules": round(chron_ok / n, 4),
                                                    "images": len(records)},
            "latency_seconds": {"mean": round(float(np.mean(lat)), 4), "p95": round(float(np.percentile(lat, 95)), 4),
                                "max": round(float(np.max(lat)), 4)},
            "peak_gpu_memory_mib": max(mem) if mem else None, "device": pipe.device}


def run_synthetic_benchmark(*, partition: str = "test", root: Path | str | None = None, device: str = "auto",
                            robustness: bool = True, save: bool = True, log: Any = print,
                            pipeline: SyntheticPipeline | None = None, checkpoint: Path | str | None = None) -> dict[str, Any]:
    from src.training.runtime import environment, git_commit

    from .config import SyntheticDatasetConfig
    from .evaluate import evaluate_checkpoint
    from .inference import latest_synthetic_checkpoint
    from .robustness import run_robustness

    start = time.perf_counter()
    paths = SyntheticPaths.at(root)
    ds = load_synthetic_dataset(paths.root, verify_hashes=False)
    records = partition_records(find_manifest(ds, paths.root), ds)[partition]
    pipe = pipeline or SyntheticPipeline(device=device)
    ckpt = checkpoint or latest_synthetic_checkpoint()
    if ckpt is None:
        raise FileNotFoundError("no synthetic checkpoint: run `python -m src.training train --dataset synthetic`")
    log("A. classification ...")
    ev = evaluate_checkpoint(ckpt, partition, root=root, device=device, save=False)
    cal = pipe.classifier.calibration
    log("B. detection ...")
    det = detection_metrics(pipe, records)
    log("C. OCR ...")
    ocr = ocr_metrics(pipe, records)
    log("F/G. complete pipeline on every image ...")
    e2e = end_to_end(pipe, records)
    rob = None
    if robustness:
        log("E. robustness ...")
        rob = run_robustness(ckpt, partition=partition, root=root, device=device, names=list(ROBUSTNESS_SET), save=False)["results"]
    cfg = SyntheticDatasetConfig.load()
    now = datetime.now(timezone.utc)
    run_id = f"benchmark_{now.strftime('%Y%m%dT%H%M%SZ')}_{partition}"
    report = {
        "banner": BANNER, "marker": MARKER, "purpose": PURPOSE, "dataset_type": DATASET_TYPE, "run_id": run_id,
        "created_utc": now.isoformat(timespec="seconds"), "partition": partition, "git": git_commit(),
        "environment": environment(), "seed": cfg.seed, "generator_version": pipe.provenance["generator_version"],
        "dataset_config_digest": cfg.digest, "dataset_fingerprint": pipe.provenance["dataset_fingerprint"],
        "synthetic_fingerprint": pipe.provenance["synthetic_fingerprint"], "split_digest": pipe.provenance["split_digest"],
        "models": {"classifier": pipe.provenance["classifier"], "vision_bundle": pipe.provenance["vision_bundle"]},
        "A_classification": {"artifact_level": ev["artifact_level"]["metrics"], "image_level": ev["image_level"]["metrics"],
                             "wording": "accuracy on the synthetic benchmark (four synthetic task classes)"},
        "B_detection": det,
        "C_ocr": ocr | {"end_to_end": e2e["ocr"],
                        "wording": "glyph recognition on the synthetic glyph benchmark; not OCR of any script"},
        "D_calibration": ({"method": cal.method, "temperature": cal.temperature, "fitted_on": cal.fitted_on,
                           "test_before": cal.metrics.get("test", {}).get("before"),
                           "test_after": cal.metrics.get("test", {}).get("after")} if cal else None),
        "E_robustness": rob,
        "F_interpretation_and_chronology": {"grammatical_interpretation_agreement": e2e["grammatical_interpretation_agreement"],
                                            "synthetic_chronology_reasoning_test": e2e["synthetic_chronology_reasoning_test"]},
        "H_synthetic_language": e2e["synthetic_language"] | {
            "spec": SPEC_ID, "method": METHOD,
            "wording": "translation of the predicted glyph codes under the FICTIONAL synthetic-language specification, "
                       "compared with held-out synthetic targets; not Tamil-Brahmi translation accuracy"},
        "G_performance": {"latency_seconds": e2e["latency_seconds"], "peak_gpu_memory_mib": e2e["peak_gpu_memory_mib"],
                          "device": e2e["device"], "classification_accuracy_through_pipeline": e2e["classification_accuracy_through_pipeline"]},
        "seconds": round(time.perf_counter() - start, 1),
    }
    if save:
        out = REPORT_DIR / f"{run_id}.json"
        assert_synthetic_model_destination(out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
        report["report_path"] = str(out)
    return report


def render_benchmark(r: dict[str, Any]) -> str:
    a, ai = r["A_classification"]["artifact_level"], r["A_classification"]["image_level"]
    d, o, c, f, g = r["B_detection"], r["C_ocr"], r["D_calibration"], r["F_interpretation_and_chronology"], r["G_performance"]
    L = ["#" * 76, f"#  {BANNER}", f"#  {MARKER}", "#  Every number measures the pipeline on generated images.", "#" * 76,
         f"partition {r['partition']} · synthetic fingerprint {r['synthetic_fingerprint'][:16]} · generator {r['generator_version']}", "",
         "A. CLASSIFICATION — accuracy on the synthetic benchmark (four synthetic task classes)",
         f"   artifact level  accuracy {a['accuracy']:.4f}  balanced {a['balanced_accuracy']:.4f}  macro F1 {a['macro_f1']:.4f}",
         f"   image level     accuracy {ai['accuracy']:.4f}  balanced {ai['balanced_accuracy']:.4f}  macro F1 {ai['macro_f1']:.4f}",
         "   per class F1 (artifact): " + ", ".join(f"{k} {v['f1']:.3f}" for k, v in a["per_class"].items()), "",
         "B. DETECTION — synthetic inscription regions and glyph rows (IoU >= 0.5)",
         f"   regions  P {d['regions']['precision']:.4f}  R {d['regions']['recall']:.4f}  F1 {d['regions']['f1']:.4f}  "
         f"mean IoU {d['regions']['mean_iou_of_matches']}",
         f"   rows     P {d['rows']['precision']:.4f}  R {d['rows']['recall']:.4f}  F1 {d['rows']['f1']:.4f}  "
         f"mean IoU {d['rows']['mean_iou_of_matches']}",
         f"   false-alarm rate on no-mark images {d['false_alarm_rate_on_no_mark_images']}", "",
         "C. OCR — glyph recognition on the synthetic glyph benchmark (not OCR of any script)",
         f"   glyph accuracy with true glyph regions {o['glyph_accuracy_true_regions']} ({o['glyphs']} glyphs)"]
    for s, v in o["strategies"].items():
        mark = "  <- selected on val" if s == o["selected_strategy"] else ""
        L.append(f"   {s:<16} segmentation F1 {v['segmentation']['f1']:.4f}  glyph count {v['segmentation']['glyph_count_accuracy']:.4f}  "
                 f"true-row CER {v['reading_true_rows']['cer']:.4f}  WER {v['reading_true_rows']['wer']:.4f}{mark}")
    e = o["end_to_end"]
    L += [f"   END TO END (detected row -> {o['selected_strategy']} -> GlyphNet)  CER {e['cer']:.4f}  WER {e['wer']:.4f}  "
          f"exact rows {e['exact_sequence_rate']:.4f}", ""]
    if c:
        b, af = c["test_before"], c["test_after"]
        L += [f"D. CALIBRATION — temperature {c['temperature']} fitted on {c['fitted_on']} (image level, {r['partition']})",
              f"   ECE {b['ece']:.4f} -> {af['ece']:.4f}   MCE {b['mce']:.4f} -> {af['mce']:.4f}   Brier {b['brier']:.4f} -> {af['brier']:.4f}"
              f"   mean confidence {b['mean_confidence']:.3f} -> {af['mean_confidence']:.3f} (accuracy {af['accuracy']:.3f})", ""]
    if r["E_robustness"]:
        L.append("E. ROBUSTNESS — synthetic robustness is not archaeological robustness (image balanced accuracy)")
        L += [f"   {k:<16} {v['image_balanced_accuracy']:.4f}  ({v.get('delta_image_balanced_accuracy', 0):+.4f})"
              for k, v in r["E_robustness"].items()]
        L.append("")
    L += ["F. SYNTHETIC INTERPRETATION AND CHRONOLOGY REASONING TEST",
          (f"   grammatical interpretation (agent / action / object) agreement with held-out targets "
           f"{f['grammatical_interpretation_agreement']:.4f}" if "grammatical_interpretation_agreement" in f else
           f"   interpretation agreement (retired placeholder categories) {f.get('interpretation_agreement', 0):.4f}"),
          f"   synthetic chronology reasoning test: agreement {f['synthetic_chronology_reasoning_test']['agreement_with_ground_truth_rules']:.4f}", ""]
    h = r.get("H_synthetic_language")
    if h:
        L += [f"H. SYNTHETIC LANGUAGE — NOT TAMIL-BRAHMI ({h['spec']}; {h['method']})",
              f"   {h['images']} Tamil-Brahmi-like images: exact translation {h['translation_exact']:.4f}  transliteration "
              f"{h['transliteration_exact']:.4f}  status {h['status_agreement']:.4f}  (targets consistent with the spec "
              f"{h['targets_consistent_with_spec']:.4f})",
              f"   predicted status {h['predicted_status']}  target status {h['target_status']}", ""]
    L += [
          f"G. PERFORMANCE — complete pipeline on {g['device']}: mean {g['latency_seconds']['mean'] * 1000:.1f} ms, "
          f"p95 {g['latency_seconds']['p95'] * 1000:.1f} ms; peak GPU memory {g['peak_gpu_memory_mib']} MiB", "", PURPOSE]
    if r.get("report_path"):
        L.append(f"report: {r['report_path']}")
    return "\n".join(L)


__all__ = ["BANNER", "ROBUSTNESS_SET", "detection_metrics", "end_to_end", "ocr_metrics", "render_benchmark",
           "run_synthetic_benchmark"]
