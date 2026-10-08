# Milestone 10 Report: Synthetic End-to-End AI Demonstration

> **SYNTHETIC — NOT ARCHAEOLOGICAL EVIDENCE.** Milestone 10 demonstrates the complete AI pipeline on the
> procedurally generated engineering dataset of Milestone 9. Every number below measures software on
> generated images. Real archaeological training stayed blocked throughout.

**Commit:** `b0c7174` (2026-10-05) · **Full technical description:**
[`SYNTHETIC_END_TO_END.md`](SYNTHETIC_END_TO_END.md) · **Benchmark reports:**
`models/synthetic/reports/benchmark/` (git-ignored; regenerate with `python -m src.evaluation synthetic`).

*This report was written in Milestone 11: the README linked it, but the file had not been committed. Its
content is taken from `SYNTHETIC_END_TO_END.md`, the commit and the recorded benchmark reports; nothing
was re-measured for it.*

## 1. What was built

| Part | Module | Result |
|---|---|---|
| Calibrated classifier | `src/synthetic/calibration.py` | temperature `T = 2.967` fitted on synthetic val, bound to the checkpoint's `model_fingerprint` |
| Region detector | `src/synthetic/vision.py` (RegionNet) | glyph rows and synthetic inscription regions from a stride-4 heat map |
| Glyph segmentation | `vision.py` (GlyphCenterNet) | learned glyph centres in a deskewed row crop (strategy chosen on val) |
| Glyph recognition | `vision.py` / `ocr_benchmark.py` (GlyphNet) | 16 invented glyph classes → a *Synthetic glyph transcription* |
| Interpretation | `src/synthetic/interpretation.py` | an invented rule table → `synthetic_*_like` categories (never a real person or word) |
| Chronology reasoning | `src/synthetic/reasoning.py` | three synthetic evidence sources combined by intersection; conflicts reported, never averaged; categories `SYNTH_CAT_01`–`04`, never BCE/CE |
| Pipeline | `src/synthetic/pipeline.py` | 8 timed stages, refuses any image whose SHA-256 is not in the synthetic dataset |
| CLI / API / UI | `src/synthetic/demo.py`, `src/inference`, `app/ui/synthetic_demo.py`, `app/ui/synthetic3d.py` | `demo`, `inference synthetic`, `POST /synthetic/analyze`, Analysis → Synthetic Demonstration with a step-by-step replay |
| Benchmark | `src/synthetic/benchmark.py` | classification, detection, OCR, calibration, robustness, timings in one report |

## 2. Results (SYNTHETIC ENGINEERING BENCHMARK, test split)

| | |
|---|---|
| Classification, artifact level | accuracy 0.885 · balanced accuracy 0.885 · macro F1 0.882 |
| Calibration | ECE 0.108 → 0.060 after temperature scaling |
| Region detection (IoU ≥ 0.5) | F1 0.619; glyph rows F1 0.785 |
| Glyph recognition (true glyph boxes) | accuracy 0.989 |
| End-to-end OCR (detected rows) | CER 0.080 · WER 0.223 |
| Pipeline time | mean 26.5 ms per image on an RTX 4050, peak GPU memory 68 MiB |

These are accuracies on the synthetic engineering benchmark. A model that does well here has learned the
generator, not pottery; none of these numbers forecasts archaeological performance.

## 3. Separation (unchanged and tested)

Synthetic models run only on images registered in the synthetic dataset (real photographs: "REAL RESEARCH
PHOTO DETECTED", CLI exit 3, API 422); synthetic models are written only under `models/synthetic/`; rules
E6, N17 and P0 keep synthetic data out of the research records, the annotation store and promotion; Real
Research is the default mode and never loads a synthetic model.

## 4. Tests

The suite stood at **928 passed** (2 opt-in browser tests deselected) when Milestone 11 began, measured on
2026-10-08 before any Milestone 11 change. The browser tests covered phone-width overflow at 100–200 % text,
keyboard operation of both modes, the WebGL and reduced-motion fallbacks, and pipeline timing.

## 5. Limitations

See [`SYNTHETIC_END_TO_END.md`](SYNTHETIC_END_TO_END.md) §Limitations: modest region recall on graffiti-like
and uncertain marks, robustness drops under noise and occlusion, invented interpretation and chronology
tables, and an illustrative (not reconstructed) replay.
