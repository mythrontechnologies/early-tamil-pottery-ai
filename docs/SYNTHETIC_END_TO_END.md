# Synthetic End-to-End AI Demonstration

> **SYNTHETIC — NOT ARCHAEOLOGICAL EVIDENCE.** Everything on this page runs on the procedurally
> generated engineering dataset of Milestone 9 ([`SYNTHETIC_DATASET.md`](SYNTHETIC_DATASET.md)).
> The glyphs are invented shapes, the interpretation categories and the chronology categories are
> invented rules, and every number measures software on generated images. Nothing here is a reading,
> a translation or a date of any real object. Real archaeological training remains **blocked**.

The demonstration exists to show that the whole AI system works end to end — image to classification,
detection, segmentation, glyph recognition, interpretation, reasoning, CLI, API and interface — before
any expert-labelled data exists. It does not imply archaeological readiness.

## Pipeline

```
synthetic image ──> 01 LOAD ──> 02 PREPROCESS ──> 03 CLASSIFY ──> 04 DETECT ──> 05 SEGMENT ──> 06 OCR
                                                                                  │
                     synthetic_analysis <── 08 REASON <── 07 INTERPRET <──────────┘
```

| Stage | Module | What it does |
|---|---|---|
| 01 LOAD | `src/synthetic/pipeline.py` | decodes the image; its SHA-256 must be in the synthetic index (`dataset_block`), or nothing runs |
| 02 PREPROCESS | `pipeline.py` | the project's evaluation transform (letterbox) for the classifier; enhanced grayscale, letterboxed to 256 px, for detection and OCR |
| 03 CLASSIFY | `inference.py`, `calibration.py` | ResNet-18 → four synthetic task classes, probabilities divided by the temperature fitted on synthetic val |
| 04 DETECT | `vision.py` (RegionNet) | 2-channel stride-4 heat map: channel 0 glyph rows (threshold 0.5), channel 1 `synthetic_inscription_region` (threshold 0.7, erosion 1) → boxes with confidence |
| 05 SEGMENT | `vision.py` (GlyphCenterNet) | each row is cropped as *row ∪ the region box containing it* (`ocr_crop`), deskewed to 96×384, and glyph centres are found by a CenterNet-lite (stride 2) |
| 06 OCR | `ocr_benchmark.py` (GlyphNet) | each glyph box → one of 16 invented glyph classes `SG00`–`SG15` → a **Synthetic glyph transcription** |
| 07 INTERPRET | `interpretation.py` | invented grammar `synthetic-grammar-1` (rules R0–R4) → `synthetic_personal_name_like`, `synthetic_name_and_title_like`, `synthetic_ownership_formula_like`, `synthetic_numeral_like`, `synthetic_symbolic_mark_like`, `synthetic_no_reading` |
| 08 REASON | `reasoning.py` | synthetic chronology from three independent sources (glyph form, mark type, recorded surface) combined by intersection; a conflict is reported, never averaged; no source → insufficient. Output is a category `SYNTH_CAT_01`–`04`, never a BCE/CE date. Also the reasoning lines and the 8-node synthetic evidence chain |

Every stage is timed (`torch.cuda.synchronize` on GPU); the result carries per-stage seconds, peak GPU
memory and CPU use. There are no artificial delays anywhere — the interface replays the measured stages.

## Models

Trained with `python -m src.training train --dataset synthetic` (classifier),
`python -m src.synthetic calibrate` and `python -m src.synthetic train-vision` (bundle in
`models/synthetic/vision/<run>/`: `region_detector.pt`, `glyph_centers.pt`, `glyph_classifier.pt`,
`manifest.json`).

| Model | Selection | Training |
|---|---|---|
| ResNet-18 classifier | best val balanced accuracy | Milestone 9 checkpoint |
| Temperature `T = 2.967374` | LBFGS on val log-probabilities | bound to the checkpoint's `model_fingerprint` |
| RegionNet | best val mean pixel IoU (0.673) | 24 epochs, 1,538 train / 338 val images |
| GlyphCenterNet | best val segmentation F1 (0.969) | 40 epochs, focal loss on the integer cell, size head |
| GlyphNet | best val glyph accuracy (0.990) | 20 epochs |

Choices made on the **validation** split and recorded in the manifest: segmentation strategy
(`learned_centers` over `projection` and `components`, by CER), region threshold and erosion
(F1 0.630 vs 0.561 at the defaults), and the OCR crop policy (val CER 0.095 row ∪ region vs 0.125 row
only). The test split was scored once afterwards.

The pipeline refuses to start when the classifier and the bundle were trained on different data
(dataset fingerprint or split digest differ). Every file loads with `weights_only=True` and its SHA-256
and `model_fingerprint` are re-checked against the manifest; they are written only under `models/synthetic/`
(`assert_synthetic_model_destination`).

## Results — SYNTHETIC ENGINEERING BENCHMARK (test split)

`python -m src.evaluation synthetic` (report in `models/synthetic/reports/benchmark/`).

| | |
|---|---|
| Classification (artifact level) | accuracy 0.8851 · balanced accuracy 0.8851 · macro F1 0.8820 |
| Classification (image level) | accuracy 0.8773 · balanced accuracy 0.8763 · macro F1 0.8753 |
| Per-class F1 (artifact level) | synthetic_tamil_brahmi_like 0.960 · synthetic_graffiti_like 0.986 · synthetic_none 0.843 · synthetic_uncertain 0.738 |
| Calibration (T = 2.967) | ECE 0.1078 → 0.0598 · MCE 0.1658 → 0.1689 · Brier 0.2322 → 0.2206 · mean confidence 0.978 → 0.863 at accuracy 0.877 |
| Detection, regions (IoU ≥ 0.5) | precision 0.6891 · recall 0.5616 · F1 0.6189 · mean IoU 0.7227 |
| Detection, glyph rows | precision 0.7143 · recall 0.8721 · F1 0.7853 · mean IoU 0.7421 |
| False alarms on no-mark images | 0.012 |
| Glyph recognition accuracy on the synthetic glyph benchmark | 0.9888 (446 glyphs, true glyph boxes) |
| Segmentation (true rows) | learned centres F1 0.9685 · components 0.7277 · projection 0.6475 |
| End-to-end OCR (detected rows) | CER 0.0799 · WER 0.2232 · exact rows 0.7791 (Milestone 9: CER 0.475) |
| Synthetic interpretation | agreement with the generator's rules 0.9419 |
| Synthetic chronology reasoning test | agreement 0.9509 |
| Robustness (image balanced accuracy) | clean 0.876 · blur 0.790 · noise 0.694 · occlusion 0.634 · scale 0.6 0.746 · exposure 0.858 · contrast 0.839 |
| Performance | complete pipeline mean 26.5 ms, p95 36.4 ms on an RTX 4050; peak GPU memory 68 MiB |

## Interfaces

**CLI**

```powershell
python -m src.synthetic demo [--image-id SYNTH-A0007-V1] [--json] [--no-record]
python -m src.inference synthetic --image data/synthetic/images/SYNTH-A0007-V1.jpg [--device cpu] [--json]
python -m src.evaluation synthetic [--partition val] [--skip-robustness] [--json]
```
`synthetic --image` on a real or unregistered photograph exits with code 3 and says the command runs
only on images of the synthetic engineering dataset. `demo` writes a run record to
`models/synthetic/runs/` (dataset fingerprint, split digest, model fingerprints, git commit, environment,
seed, ground-truth check, timings).

**API** — `python -m src.inference serve --synthetic`

| | |
|---|---|
| `GET /health` | adds `synthetic_pipeline_loaded` |
| `POST /synthetic/analyze` | synthetic image → 200 `{"dataset_type": "synthetic", "warning": "synthetic_not_archaeological", "dataset": …, "synthetic_analysis": …}`; any other image → 422; pipeline not loaded → 503 |
| `POST /analyze` | unchanged; a synthetic image also gets `synthetic_analysis`; a real image never does |

GPU calls are serialised with a lock; the upload size limit and path rules are unchanged.

**Interface** — Analysis → *Data mode* → **Synthetic Demonstration** (or Overview → *Run synthetic
demonstration*). Real Research is the default. The page shows the mode banner, a choice of held-out
synthetic test images, *Run analysis*, live stage progress, the result banner, the **pipeline replay**,
the photograph viewer with synthetic detector boxes (purple dotted, "Synthetic detector — not
evidence"), the findings, the synthetic evidence chain (each node badged *Synthetic*), the reasoning,
the ground-truth check, timings and, in Research presentation, provenance.

**Pipeline replay (2.5D).** An illustrative CSS-3D sherd — *Illustrative visualization · not a scan of
the input image · SYNTHETIC* — with the eight stages around it lit in their measured proportions and a
synthetic region callout. Play/Pause, Skip, Replay and 2D buttons; an `aria-live` region announces each
stage; reduced motion shows all eight stages at once without animation; the 2D list is used
automatically when 3D transforms are unavailable. Values are inserted with `textContent` only.

## Separation guarantees

| Guarantee | Enforced by |
|---|---|
| Synthetic models run only on images whose SHA-256 is in the synthetic dataset | `dataset_block`, `analyze`, `/synthetic/analyze` (422), CLI (exit 3) |
| A real photograph says **REAL RESEARCH PHOTO DETECTED** and gets `synthetic_models_applied: false` | `dataset_block`; Real Research mode never loads a synthetic model |
| The two modes never merge | the data-mode switch renders one mode; a synthetic upload in Real mode is refused |
| Synthetic models are written only under `models/synthetic/` | `assert_synthetic_model_destination` |
| Synthetic data never enters the research store, gate or promotion | rules E6, N17, P0 (Milestone 9), unchanged |
| Real training stays blocked | `python -m src.training train` → exit 3 (gates G1–G11 unchanged) |
| Wording: "Synthetic glyph transcription", "Synthetic Tamil-Brahmi-like class", `*_like` categories, "Synthetic demonstration — not archaeological dating." | constants in `pipeline.py`, `reasoning.py`; tests assert no BCE/CE, no "Tamil-Brahmi transcription" |

## Limitations

* Every number above is synthetic. It says the software works, not that it would work on real sherds.
* Region detection is modest for the graffiti-like and uncertain classes (recall 0.56); the stride-4 heat
  map merges or misses small marks. Row detection is better (F1 0.79).
* Robustness falls under noise (−0.18) and occlusion (−0.24) — the classifier was not trained with
  those perturbations.
* The interpretation grammar and chronology tables are invented; "agreement" means the pipeline
  recovers the generator's own rules.
* The pipeline replay is illustrative; it is not a 3D reconstruction of the input image.
