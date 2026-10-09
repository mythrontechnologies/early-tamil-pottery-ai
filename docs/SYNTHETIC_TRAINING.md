# Synthetic training, evaluation, robustness and glyph benchmark (Milestone 9)

> **Update 2026-10-09 — generator 1.1.0 (synthetic language).** The dataset was regenerated so that every Tamil-Brahmi-like row is a sentence of the invented synthetic language ([`SYNTHETIC_LANGUAGE.md`](SYNTHETIC_LANGUAGE.md); SYNTHETIC LANGUAGE — NOT TAMIL-BRAHMI); other classes are byte-identical and the split assignment is unchanged. Later the same day the split was corrected so that no near-duplicate component crosses a partition ([`SYNTHETIC_DATASET.md`](SYNTHETIC_DATASET.md) §7) and the models were retrained on it. Current: records `4e6eb6684b50…`, synthetic `e999614b37e1eeea…`, split `1201fe36c1f0…`; classifier `synthetic_20261009T105815Z_4e6eb668_s20261003_resnet18` (test artifact accuracy 0.892, balanced 0.892, macro F1 0.891; T = 1.614, ECE 0.071 → 0.050); vision bundle `vision_20261009T111151Z_4e6eb668_s20261003` (regions F1 0.621, rows F1 0.794, segmentation F1 0.962, end-to-end CER 0.079, WER 0.206); synthetic-language exact translation 0.821 and grammatical-role agreement 0.821 on 84 held-out images (`benchmark_20261009T111257Z_test`). The tables below record the 2026-10-03 run (generator 1.0.0) and are kept as history.

> **SYNTHETIC TRAINING — NOT ARCHAEOLOGICAL MODEL EVALUATION**
>
> Every number on this page was measured on generated images (see
> [`SYNTHETIC_DATASET.md`](SYNTHETIC_DATASET.md)). They show that the pipeline trains, checkpoints,
> evaluates, calibrates and serves correctly. They are **not** archaeological performance and must
> not be quoted as the accuracy of a Tamil-Brahmi, graffiti or pottery classifier. No
> archaeological model exists; the research training path is still blocked by the readiness gate.

## 1. Commands

```bash
python -m src.training train --dataset synthetic [--model resnet18] [--epochs N] [--resume CKPT]
python -m src.evaluation evaluate --dataset synthetic --checkpoint models/synthetic/checkpoints/<run>/best.pt
python -m src.synthetic robustness --checkpoint <best.pt>
python -m src.synthetic ocr-benchmark
python -m src.inference analyze IMAGE --synthetic-checkpoint latest
python -m src.inference serve --synthetic-checkpoint latest
```

Without `--dataset synthetic`, `python -m src.training train` is exactly the research command it
was: readiness gate first, exit code 3, "Training blocked". `--model/--epochs` are refused there.

## 2. Configuration — [`configs/synthetic_training.yaml`](../configs/synthetic_training.yaml)

A separate file. It repeats every value explicitly instead of inheriting `configs/training.yaml`,
and is validated by the same strict `TrainingConfig` loader plus synthetic rules (`dataset_type`
must be `synthetic`; checkpoint, experiment and report directories must lie in `models/synthetic/`;
four classes; image size equal to the project geometry).

| setting | value | why |
|---|---|---|
| model | ResNet18, ImageNet weights (torchvision), new 4-way head, dropout 0.2 | the project's baseline |
| backbone | frozen for epochs 0–1, then fine-tuned | strokes are small; ImageNet features alone are not enough |
| input | 224 px letterbox, ImageNet normalisation | identical to the research pipeline |
| batch / workers | 32 / 0 | fits 6 GB with AMP; worker start-up on Windows costs more than it saves |
| optimiser | AdamW, lr 1e-3 (head), 2e-4 (backbone), weight decay 1e-4, grad clip 1.0 | |
| schedule | cosine over 30 epochs | |
| early stopping | balanced accuracy, patience 7, min delta 0.001 | |
| imbalance | class-weighted loss, artifact counts | classes are balanced; kept to exercise the research code path |
| augmentation | ±5° rotation, safe scale-shift ≥ 0.9, brightness/contrast 0.15, saturation 0.05, no flip, no hue | the research augmentation, unchanged |
| runtime | seed 20261003, AMP fp16 on CUDA, deterministic algorithms (warn-only) | |

## 3. What a synthetic run writes

| artefact | location | carries |
|---|---|---|
| checkpoints `best.pt`, `last.pt` | `models/synthetic/checkpoints/<experiment>/` | `dataset_type: synthetic`; `synthetic` block: SYNTHETIC ONLY marker, banner, generator version, generation seed, dataset-config digest, synthetic fingerprint, label/slot mapping, seed, environment; plus dataset fingerprint, split digest, git commit, full config, model fingerprint (re-checked on load), validation metrics with train/val loss |
| experiment record | `models/synthetic/experiments/<experiment>/experiment.json` | `dataset_type: synthetic`, banner and purpose in `notes`, readiness "not consulted" |
| reports | `models/synthetic/reports/<experiment>/evaluation_test.json`, `robustness_test.json`; `models/synthetic/reports/ocr_benchmark/` | banner, fingerprints, per-image predictions |

All of `models/` is git-ignored. The research directories `models/checkpoints/` and
`models/experiments/` are refused for synthetic artefacts (and `models/synthetic/` for research
ones), so synthetic metrics can never enter the archaeological evaluation history.

## 4. Training run (2026-10-03)

| | |
|---|---|
| experiment | `synthetic_20261003T093220Z_52004dd5_s20261003_resnet18` |
| device | NVIDIA GeForce RTX 4050 Laptop GPU, CUDA 12.6, AMP on, torch 2.14.0 |
| data | 1,538 train / 338 val / 326 test images (700 / 152 / 148 artifacts) |
| epochs | 16 of 30 (early stop); best epoch **8** (val balanced accuracy 0.8455) |
| training time | **467 s** (~29 s per epoch) |
| parameters | 11,178,564 |
| best checkpoint | `models/synthetic/checkpoints/synthetic_20261003T093220Z_52004dd5_s20261003_resnet18/best.pt` (128 MiB incl. optimiser state) |
| model fingerprint | `9e1d6213353c6206…` |
| dataset fingerprint | records `52004dd5aca4…`, synthetic `d61e25c6dfe07878…`, split `6c1e3cab8bf3962f…` |

Training loss fell to ~0.01 while validation loss rose after epoch 5: the model overfits the
training artifacts. Early stopping on balanced accuracy selected epoch 8.

## 5. Evaluation on the held-out test split

**SYNTHETIC DATA ONLY — NOT ARCHAEOLOGICAL PERFORMANCE.** Artifact level (the headline; class
probabilities averaged over each artifact's views), n = 148 artifacts:

| metric | artifact level | image level (n = 326) |
|---|---|---|
| accuracy | **0.885** | 0.877 |
| balanced accuracy | **0.885** | 0.876 |
| macro precision / recall | 0.891 / 0.885 | 0.881 / 0.876 |
| macro F1 / weighted F1 | **0.882** / 0.882 | 0.875 / 0.875 |
| top-2 accuracy | 0.986 | 0.976 |
| ECE / MCE (10 bins) | 0.085 / 0.508 | 0.108 / 0.166 |
| Brier (multiclass) | 0.195 | 0.232 |

Per class (artifact level, precision / recall / F1):

| class | P | R | F1 |
|---|---|---|---|
| synthetic_tamil_brahmi_like | 0.947 | 0.973 | 0.960 |
| synthetic_graffiti_like | 1.000 | 0.973 | 0.986 |
| synthetic_none | 0.761 | 0.946 | 0.843 |
| synthetic_uncertain | 0.857 | 0.649 | 0.739 |

Confusion matrix (artifact level; rows true, columns predicted; order brahmi-like, graffiti-like,
none, uncertain): `[36,0,0,1] [0,36,0,1] [0,0,35,2] [2,0,11,24]`.

Reading it:

* The marks-present classes are easy for the model; the hard boundary is **uncertain vs none**:
  11 of 37 uncertain artifacts are called "none". That is the boundary the generator made hard on
  purpose (faint, eroded, fragmentary marks).
* **The model is overconfident.** Image-level mean confidence is 0.978 against 0.877 accuracy;
  34 of the 40 errors were made with confidence above 0.9 and no prediction fell below 0.5.
  Model probabilities are not trustworthy as confidence even here; a real-data model will need
  calibration (temperature scaling on a validation split) before any probability is displayed
  as more than an AI observation. The UI already never presents a model probability as
  archaeological confidence.

## 6. Robustness (test split)

*Synthetic robustness is not archaeological robustness.* Balanced accuracy, image level (clean
0.876); artifact-level values in the report.

| perturbation | severity | image bal. acc. | Δ |
|---|---|---|---|
| Gaussian blur σ 1 / σ 2 | mild / moderate | 0.864 / 0.790 | −0.012 / −0.087 |
| exposure ×0.7 / ×0.5 | mild / moderate | 0.868 / 0.858 | −0.009 / −0.018 |
| exposure ×1.3 / ×1.6 | mild / moderate | 0.882 / 0.860 | +0.006 / −0.016 |
| contrast ×0.7 / ×0.5 / ×1.4 | mild / moderate / mild | 0.864 / 0.839 / 0.830 | −0.013 / −0.037 / −0.046 |
| sensor noise σ 8 / σ 16 | mild / moderate | 0.834 / 0.694 | −0.042 / **−0.182** |
| JPEG q 35 / q 15 | mild / moderate | 0.852 / 0.795 | −0.025 / −0.081 |
| rotation +8° / −8° / +15° | mild / mild / moderate | 0.846 / 0.852 / 0.837 | −0.030 / −0.024 / −0.039 |
| scale 0.8 / 0.6 / zoom 1.15 | mild / moderate / mild | 0.846 / 0.746 / 0.855 | −0.031 / **−0.131** / −0.021 |
| occlusion 8 % / 16 % | mild / moderate | 0.790 / 0.634 | −0.086 / **−0.243** |
| background swap (re-rendered) | mild | 0.855 | −0.022 |

Lighting changes barely matter; occlusion, heavy noise and small objects hurt most, and
calibration degrades under every perturbation (ECE up to 0.32). The background swap re-renders
the same view with a different background through the generator, so the object pixels are
identical; its small effect suggests the model is not relying on the background.

## 7. Synthetic glyph recognition benchmark

*Synthetic glyph codes; not a transcription of any script.* Glyph codes `SG00`–`SG15` have no
sound, reading or meaning; nothing here is Tamil-Brahmi OCR.

Pipeline: region detection → CLAHE/black-hat enhancement (the project's `src.ocr` viewing aid
technique) → deskew and projection segmentation → `GlyphNet` (5 conv layers, trained on 1,981
glyph crops from the TRAIN split only; best validation glyph accuracy 0.990) → word split at wide
gaps → `src.ocr.screen_ocr` reliability screen.

Test split: 446 glyphs in 86 rows, 240 images without a row.

| mode | result |
|---|---|
| oracle segmentation (ground-truth glyph regions) | glyph accuracy **0.991**; CER 0.045, WER 0.089, exact rows 0.907 (glyphs less than half visible are left unread and count as errors) |
| row detection, learned (`RowNet` heat map; val pixel IoU 0.69) | P **0.742**, R **0.837**, F1 **0.787**, mean IoU 0.739; false alarms on row-free images 5.8 % |
| row detection, classical baseline (ink components; linking tuned on val) | P 0.491, R 0.314, F1 0.383; false alarms 8.3 % |
| reader on ground-truth rows | CER 0.464, WER 0.768, exact 0.256, glyph count right 0.454 |
| end to end (learned detector + reader) | CER **0.475**, WER 0.786, exact 0.221 |
| through `src.inference.analyze` (60 rows) | 5 kept as OCR candidates by the ≥ 0.9 screen (all 5 exact), 55 abstained ("No reliable transcription established.") |

Error budget: with correct glyph regions recognition is nearly perfect; detection costs little
(end-to-end CER 0.475 vs 0.464 on ground-truth rows); **segmenting a row into glyphs is the
bottleneck** (glyph-count accuracy 0.45). The reliability screen behaves as designed: it lets
through only high-scoring output, and that output was correct. CER is the edit distance over glyph
codes divided by the reference length; WER is over words (1–2 per row), so it is coarse.

## 8. Inference, API and UI on synthetic images

* `analyze()` identifies an image by SHA-256: research record → `dataset_type: research`
  (REAL RESEARCH DATA); synthetic record → `synthetic` (SYNTHETIC DEMONSTRATION); neither →
  `unregistered`. A synthetic image gets the warning "Synthetic demonstration — not archaeological
  evidence", no human evidence, and only the synthetic model; reasoning still answers
  "Insufficient evidence" for script, reading, translation, date and period.
* The HTTP API (`--synthetic-checkpoint`) returns `dataset_type` on every result. Verified live:
  a synthetic test image → `synthetic`, `synthetic_graffiti_like` 0.999997, banner in the summary;
  a real CC-BY-4.0 research photograph → `research`, registered, licence intact, classification
  `no_model` (the loaded synthetic model is not applied to it).
* Streamlit Analysis page: a third source, "A synthetic demonstration image" (held-out test split),
  a hatched violet banner, a SYNTHETIC DEMONSTRATION badge (text + glyph, never colour alone),
  generator ground truth beside the synthetic model's prediction, and a caption stating the image
  is generated. Research photographs carry REAL RESEARCH DATA; the Dataset page states that it
  counts research data only. Reflows without horizontal scrolling at 390x844 and 360x800 with text at
  100-200 % (regression-tested in Chromium: `python -m pytest -m browser`).

## 9. What this does and does not show

Shows: the data path, artifact grouping, split, training loop (freeze/unfreeze, AMP, early
stopping, deterministic seeding), checkpoint format and safe loading, evaluation (image and
artifact level, calibration, confidence), robustness harness, OCR plumbing, inference identity,
API and UI all work together on 2,202 images, and none of it can leak into the research data.

Does not show: anything about real pottery. The synthetic model learned the generator.
