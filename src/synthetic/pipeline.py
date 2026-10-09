"""The complete synthetic AI pipeline (Milestone 10).

    Synthetic model output — not archaeological evidence.

    image -> 01 load -> 02 preprocess -> 03 classify (ResNet18 + temperature scaling)
          -> 04 detect (RegionNet: synthetic inscription regions + glyph rows)
          -> 05 segment (selected strategy) -> 06 OCR (GlyphNet)
          -> 07 interpret: the deterministic synthetic-language decoder (src.synthetic.lexicon) turns the PREDICTED
             glyph codes into a fictional transliteration and English translation (``synthetic_language``) and a
             structured grammatical interpretation - agent, action, object per clause (``interpretation``); two
             separate fields. SYNTHETIC LANGUAGE — NOT TAMIL-BRAHMI. (The placeholder categories of
             src.synthetic.interpretation were retired on 2026-10-09.)
          -> 08 reason (synthetic chronology, reasoning, evidence chain)
          -> reading_results (src.synthetic.reading): transcription, transliteration, translation, completeness

The decoder sees only the predicted codes: never the record, the artifact id, the file name or the generator's
ground truth, which ``ground_truth_check`` alone compares afterwards (evaluation, not inference).

Every stage is timed (CUDA synchronised) and reported through an optional ``on_stage`` callback, so a
UI can show real progress. The pipeline refuses to start unless the classifier checkpoint and the
vision bundle were trained on the same synthetic dataset version and split. It never runs on a real
research photograph: callers pass only images identified as synthetic (``src.inference`` checks
SHA-256 identity), and the result is stamped ``dataset_type: synthetic`` with the warning code
``synthetic_not_archaeological``.
"""

from __future__ import annotations

import io
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image

from src.evaluation.ocr import edit_distance

from . import DATASET_TYPE, LABEL_WARNING, MARKER, PURPOSE, UI_BANNER
from .calibration import confidence_words
from .inference import SyntheticCheckpointClassifier, latest_synthetic_checkpoint
from .lexicon import decode as decode_language
from .lexicon import grammatical_interpretation
from .lexicon import target as language_target
from .ocr_benchmark import WORD_SEPARATOR, _iou, enhanced_gray
from .reading import synthetic_reading_results
from .reasoning import chronology, evidence_chain, reasoning_lines
from .vision import VisionBundle, VisionModelError, detect_regions, load_bundle, read_glyphs, segment

STATEMENT = "Synthetic model output — not archaeological evidence."
WARNING_CODE = "synthetic_not_archaeological"
TRANSCRIPTION_LABEL = "Synthetic glyph transcription"
STAGES: tuple[tuple[str, str], ...] = (
    ("load", "Load"), ("preprocess", "Preprocess"), ("classify", "Classify"), ("detect", "Detect"),
    ("segment", "Segment"), ("ocr", "OCR"), ("interpret", "Interpret"), ("reason", "Reason"))
DISPLAY_LABELS = {
    "synthetic_tamil_brahmi_like": "Synthetic Tamil-Brahmi-like class",
    "synthetic_graffiti_like": "Synthetic graffiti-like class",
    "synthetic_none": "Synthetic no-mark class",
    "synthetic_uncertain": "Synthetic uncertain class",
}


#: How the OCR crop is chosen (selected on the VALIDATION split, 82 rows, end-to-end CER):
#: row box only 0.125 · row box at threshold 0.3 0.108 · row box united with the region containing it 0.095.
OCR_CROP_POLICY = "glyph row united with the synthetic inscription region that contains it (selected on val)"


def ocr_crop(row: Any, regions: list[Any], W: int, H: int) -> tuple[int, int, int, int]:
    """The row channel says WHICH region is a glyph row; the region channel gives its fuller extent."""
    x0, y0, x1, y1 = row.pixels(W, H)
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    holders = [g.pixels(W, H) for g in regions]
    holders = [b for b in holders if b[0] <= cx <= b[2] and b[1] <= cy <= b[3]]
    if holders:
        b = max(holders, key=lambda q: (q[2] - q[0]) * (q[3] - q[1]))
        x0, y0, x1, y1 = min(x0, b[0]), min(y0, b[1]), max(x1, b[2]), max(y1, b[3])
    return x0, y0, x1, y1


class SyntheticPipelineError(RuntimeError):
    """The synthetic models are missing or were trained on different synthetic data."""


def _rgb(image: Image.Image | np.ndarray | bytes | Path | str) -> Image.Image:
    if isinstance(image, Image.Image):
        return image.convert("RGB")
    if isinstance(image, np.ndarray):
        return Image.fromarray(image).convert("RGB")
    if isinstance(image, (bytes, bytearray)):
        with Image.open(io.BytesIO(image)) as im:
            return im.convert("RGB")
    with Image.open(Path(image)) as im:
        return im.convert("RGB")


class SyntheticPipeline:
    def __init__(self, checkpoint: Path | str | None = None, bundle: VisionBundle | Path | str | None = None, *,
                 device: str = "auto", calibration_dir: Path | None = None) -> None:
        import torch

        self._torch = torch
        dev = "cuda" if device in ("auto", "cuda") and torch.cuda.is_available() else "cpu"
        self.device = dev
        ckpt = Path(checkpoint) if checkpoint else latest_synthetic_checkpoint()
        if ckpt is None:
            raise SyntheticPipelineError("no synthetic classifier checkpoint; run `python -m src.training train --dataset synthetic`")
        self.classifier = SyntheticCheckpointClassifier(ckpt, device=dev, calibration_dir=calibration_dir)
        try:
            self.bundle = (bundle if isinstance(bundle, VisionBundle) else load_bundle(bundle)).to(dev)
        except VisionModelError as exc:
            raise SyntheticPipelineError(str(exc)) from exc
        cm, bm = self.classifier.ckpt_meta, self.bundle.manifest
        if (cm["dataset_fingerprint"], cm["split_digest"]) != (bm["dataset_fingerprint"], bm["split_digest"]):
            raise SyntheticPipelineError("the classifier and the vision bundle were trained on different synthetic "
                                         "dataset versions or splits; retrain one of them")
        self.provenance = {
            "dataset_type": DATASET_TYPE, "marker": MARKER, "device": dev,
            "dataset_fingerprint": bm["dataset_fingerprint"], "synthetic_fingerprint": bm.get("synthetic_fingerprint"),
            "split_digest": bm["split_digest"], "generator_version": bm.get("generator_version"),
            "classifier": self.classifier.info,
            "vision_bundle": {"run_id": bm["run_id"], "segmentation": self.bundle.strategy, "ocr_crop": OCR_CROP_POLICY,
                              "models": {k: {"model_fingerprint": v["model_fingerprint"], "parameters": v["parameters"]}
                                         for k, v in bm["models"].items()}},
        }

    # ------------------------------------------------------------------ #

    def run(self, image: Image.Image | np.ndarray | bytes | Path | str, *, record: dict[str, Any] | None = None,
            on_stage: Callable[[dict[str, Any]], None] | None = None) -> dict[str, Any]:
        """Run every stage once. ``record`` (the synthetic record, when the image is a dataset image) adds the
        generator's ground truth as a benchmark check; it never changes a prediction."""
        import psutil

        torch = self._torch
        cuda = self.device == "cuda"
        if cuda:
            torch.cuda.reset_peak_memory_stats()
        proc = psutil.Process()
        cpu0, wall0 = proc.cpu_times(), time.perf_counter()
        stages: list[dict[str, Any]] = []
        state: dict[str, Any] = {}

        def stage(key: str, fn: Callable[[], tuple[str, dict[str, Any]]]) -> None:
            t = time.perf_counter()
            summary, data = fn()
            if cuda:
                torch.cuda.synchronize()
            title = dict(STAGES)[key]
            entry = {"key": key, "number": len(stages) + 1, "title": title, "seconds": round(time.perf_counter() - t, 5),
                     "summary": summary, "synthetic": True}
            stages.append(entry)
            state[key] = data
            if on_stage:
                on_stage(entry)

        def load() -> tuple[str, dict[str, Any]]:
            img = _rgb(image)
            return f"{img.size[0]}×{img.size[1]} px synthetic image decoded", {"image": img}

        def preprocess() -> tuple[str, dict[str, Any]]:
            img = state["load"]["image"]
            rgb = np.asarray(img)
            return "letterboxed for the classifier; enhanced grayscale for detection and OCR", {
                "rgb": rgb, "gray": enhanced_gray(rgb)}

        def classify() -> tuple[str, dict[str, Any]]:
            probs = self.classifier.probabilities(state["load"]["image"])
            names = self.classifier.class_names
            i = int(np.argmax(probs))
            label, p = names[i], float(probs[i])
            data = {"label": label, "display_label": DISPLAY_LABELS[label], "confidence": round(p, 4),
                    "confidence_words": confidence_words(p),
                    "probabilities": {c: round(float(v), 4) for c, v in zip(names, probs)},
                    "calibrated": self.classifier.calibration is not None,
                    "calibration_status": self.classifier.calibration_status,
                    "temperature": self.classifier.calibration.temperature if self.classifier.calibration else None,
                    "model": f"{self.classifier.info['name']} ({self.classifier.info['experiment_id']})",
                    "statement": STATEMENT}
            return f"{DISPLAY_LABELS[label]} · model confidence {p:.0%} ({data['confidence_words']})", data

        def detect() -> tuple[str, dict[str, Any]]:
            found = detect_regions(self.bundle.region_detector, state["preprocess"]["rgb"])
            regions = [r.to_dict() for r in found["regions"]]
            rows = [r.to_dict() for r in found["rows"]]
            return (f"{len(regions)} synthetic inscription region(s), {len(rows)} glyph row(s)",
                    {"regions": regions, "rows": rows, "_rows": found["rows"], "_regions": found["regions"]})

        def segment_stage() -> tuple[str, dict[str, Any]]:
            rows = state["detect"]["_rows"]
            if not rows:
                return "no glyph row to segment", {"glyphs": [], "box": None}
            gray = state["preprocess"]["gray"]
            H, W = gray.shape
            x0, y0, x1, y1 = ocr_crop(rows[0], state["detect"]["_regions"], W, H)
            pad = round(0.1 * (y1 - y0))
            x0, y0, x1, y1 = max(0, x0 - pad), max(0, y0 - pad), min(W, x1 + pad), min(H, y1 + pad)
            glyphs = segment(self.bundle.strategy, gray[y0:y1, x0:x1], self.bundle.glyph_centers)
            boxes = [{"x": round((x0 + g.cx - g.side / 2) / W, 5), "y": round((y0 + g.cy - g.side / 2) / H, 5),
                      "width": round(g.side / W, 5), "height": round(g.side / H, 5), "word": g.word} for g in glyphs]
            return f"{len(glyphs)} glyph(s) segmented ({self.bundle.strategy})", {"glyphs": glyphs, "boxes": boxes,
                                                                                   "box": (x0, y0, x1, y1)}

        def ocr() -> tuple[str, dict[str, Any]]:
            glyphs = state["segment"]["glyphs"]
            if not glyphs:
                return "no synthetic glyph transcription", {"status": "no_reading", "reason": "no glyph row detected or segmented",
                                                             "words": [], "transcription": "", "glyph_count": 0,
                                                             "mean_glyph_score": 0.0, "segmentation": self.bundle.strategy}
            words, scores = read_glyphs(self.bundle.glyph_classifier, glyphs)
            text = WORD_SEPARATOR.join(" ".join(w) for w in words)
            data = {"status": "read", "label": TRANSCRIPTION_LABEL, "words": words, "transcription": text,
                    "glyph_count": len(scores), "glyph_scores": [round(s, 4) for s in scores],
                    "mean_glyph_score": round(float(np.mean(scores)), 4), "segmentation": self.bundle.strategy,
                    "glyph_boxes": state["segment"]["boxes"],
                    "statement": "Synthetic glyph codes: no sound, no reading, not a transcription of any script."}
            return f"{TRANSCRIPTION_LABEL}: {text}", data

        def interpret_stage() -> tuple[str, dict[str, Any]]:
            lang = decode_language(state["ocr"]["words"]).to_dict()          # predicted codes only
            state["language"] = lang
            it = grammatical_interpretation(lang)
            said = f"'{lang['translation']}'" if lang["translation"] else "no translation"
            return (f"synthetic language ({lang['spec']}): {it['summary']}; translation {said} "
                    f"[{lang['status']}]"), it

        def reason() -> tuple[str, dict[str, Any]]:
            o = state["ocr"]
            chron = chronology(words=o["words"], synthetic_class=state["classify"]["label"],
                               class_confidence=state["classify"]["confidence"],
                               ocr_score=o["mean_glyph_score"] if o["status"] == "read" else None,
                               surface=(record or {}).get("synthetic_surface")).to_dict()
            return f"synthetic chronology: {chron['display']}", chron

        stage("load", load)
        stage("preprocess", preprocess)
        stage("classify", classify)
        stage("detect", detect)
        stage("segment", segment_stage)
        stage("ocr", ocr)
        stage("interpret", interpret_stage)
        stage("reason", reason)

        img = state["load"]["image"]
        c, det = state["classify"], state["detect"]
        consistency = []
        if c["label"] == "synthetic_tamil_brahmi_like" and not det["rows"]:
            consistency.append("the classifier says Tamil-Brahmi-like but the detector found no glyph row (disagreement kept, not resolved)")
        if det["rows"] and c["label"] in ("synthetic_none", "synthetic_graffiti_like"):
            consistency.append(f"the detector found a glyph row but the classifier says {c['label']} (disagreement kept, not resolved)")
        if c["label"] == "synthetic_none" and det["regions"]:
            consistency.append("the classifier says no mark but the detector proposed a region (disagreement kept)")
        analysis: dict[str, Any] = {
            "dataset_type": DATASET_TYPE, "warning": WARNING_CODE, "banner": UI_BANNER, "statement": STATEMENT,
            "marker": MARKER, "purpose": PURPOSE, "label_warning": LABEL_WARNING,
            "input": {"width_px": img.size[0], "height_px": img.size[1],
                      "image_id": (record or {}).get("image_id"), "artifact_id": (record or {}).get("artifact_id"),
                      "generator_version": (record or {}).get("synthetic_generator_version")},
            "classification": {k: v for k, v in c.items()},
            "inscription": {"regions": det["regions"], "rows": det["rows"], "class": "synthetic_inscription_region"},
            "ocr": {k: v for k, v in state["ocr"].items()},
            "interpretation": state["interpret"],
            "synthetic_language": state["language"],
            "chronology": state["reason"],
            "consistency": consistency,
        }
        analysis["summary"] = (f"SYNTHETIC: {c['label']} ({c['confidence']:.2f}) · "
                               + (f"{TRANSCRIPTION_LABEL.lower()} '{state['ocr']['transcription']}' · "
                                  if state["ocr"]["status"] == "read" else "no synthetic glyph transcription · ")
                               + f"{state['interpret']['summary']} · {state['reason']['display']}")
        analysis["confidence"] = {"synthetic_model_confidence": c["confidence"], "words": c["confidence_words"],
                                  "calibration_status": c["calibration_status"],
                                  "synthetic_chronology_confidence": state["reason"]["confidence"],
                                  "note": "Model probabilities on synthetic images; never an archaeological confidence."}
        analysis["reading_results"] = synthetic_reading_results(analysis)
        analysis["reasoning"] = reasoning_lines(analysis)
        analysis["evidence_chain"] = evidence_chain(analysis)
        analysis["stages"] = stages
        cpu1, wall = proc.cpu_times(), time.perf_counter() - wall0
        analysis["performance"] = {
            "total_seconds": round(wall, 4), "stage_seconds": {s["key"]: s["seconds"] for s in stages},
            "device": self.device,
            "peak_gpu_memory_mib": round(torch.cuda.max_memory_allocated() / 2**20, 1) if cuda else None,
            "cpu_percent_of_one_core": round(100 * ((cpu1.user - cpu0.user) + (cpu1.system - cpu0.system)) / max(wall, 1e-6), 1)}
        analysis["provenance"] = self.provenance
        if record is not None:
            analysis["ground_truth_check"] = ground_truth_check(analysis, record)
        return analysis


def ground_truth_check(a: dict[str, Any], record: dict[str, Any]) -> dict[str, Any]:
    """Compare a run with the generator's ground truth (synthetic images only). Errors are kept exactly."""
    truth_words = record["synthetic_glyph_sequence"]
    pred_words = a["ocr"]["words"]
    ref = [c for w in truth_words for c in w]
    hyp = [c for w in pred_words for c in w]
    gt_regions = [r for r in record["synthetic_regions"] if r["kind"] in ("glyph_row", "mark")]
    best_iou = max((_iou((p["x"], p["y"], p["width"], p["height"]), (g["x"], g["y"], g["width"], g["height"]))
                    for p in a["inscription"]["regions"] for g in gt_regions), default=None)
    truth_interp = grammatical_interpretation(decode_language(truth_words))
    lang_truth = record.get("synthetic_language_target") or language_target(truth_words)
    lang_pred = a["synthetic_language"]
    return {
        "note": "Generator ground truth, available only because the image is synthetic. It is compared, never used.",
        "true_label": record["script_type"], "label_correct": a["classification"]["label"] == record["script_type"],
        "true_transcription": WORD_SEPARATOR.join(" ".join(w) for w in truth_words),
        "predicted_transcription": a["ocr"]["transcription"],
        "glyph_edit_distance": edit_distance(ref, hyp) if ref else None,
        "cer": round(edit_distance(ref, hyp) / len(ref), 4) if ref else None,
        "wer": round(edit_distance([tuple(w) for w in truth_words], [tuple(w) for w in pred_words]) / len(truth_words), 4) if truth_words else None,
        "exact_transcription": (pred_words == truth_words) if ref else None,
        "best_region_iou": round(best_iou, 4) if best_iou is not None else None,
        "true_regions": len(gt_regions),
        "true_interpretation": truth_interp["summary"],
        "interpretation_correct": (truth_interp["status"], truth_interp["clauses"])
                                  == (a["interpretation"]["status"], a["interpretation"]["clauses"]),
        "true_synthetic_language_status": lang_truth["status"],
        "true_synthetic_transliteration": lang_truth["transliteration"],
        "true_synthetic_translation": lang_truth["translation"],
        "predicted_synthetic_translation": lang_pred["translation"],
        "synthetic_translation_correct": (lang_pred["status"], lang_pred["translation"])
                                         == (lang_truth["status"], lang_truth["translation"]),
    }


__all__ = [
    "DISPLAY_LABELS",
    "OCR_CROP_POLICY",
    "STAGES",
    "STATEMENT",
    "TRANSCRIPTION_LABEL",
    "WARNING_CODE",
    "SyntheticPipeline",
    "SyntheticPipelineError",
    "ground_truth_check",
    "ocr_crop",
]
