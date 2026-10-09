# Model Card

## Status: no trained model exists

| | |
|---|---|
| Trained models | **none** |
| Why | the readiness gate (G1-G11) fails: 0 expert-labelled artifacts in every class |
| What runs today | `NoModelClassifier`, `NoDetector`, `NullMarkAnalyzer`, `NullTranscriber` (honest null stages) |
| Metrics | **none**. "Evaluation blocked — insufficient expert-labelled archaeological data." |

Nothing in this repository reports an accuracy, a calibration or an OCR error rate for real data. When
expert labels exist, `python -m src.evaluation evaluate` reports artifact-level metrics, calibration, an
error analysis and (`--robustness`) perturbation robustness, under the evidence tier `real_expert_labelled`
([`EVALUATION.md`](EVALUATION.md)).
The numbers produced by the test suite come from synthetic noise tensors and exist only to
exercise code.

### Synthetic engineering models (Milestone 9) are not this model

`models/synthetic/` holds models trained on the SYNTHETIC engineering dataset
([`SYNTHETIC_TRAINING.md`](SYNTHETIC_TRAINING.md)). They classify four *synthetic visual task
categories* drawn by a procedural generator; they are **not** models of Tamil-Brahmi, graffiti or
any archaeological category, and their metrics are **SYNTHETIC DATA ONLY — NOT ARCHAEOLOGICAL
PERFORMANCE**. Every such checkpoint carries `dataset_type: synthetic` and the SYNTHETIC ONLY
marker; the research classifier, research evaluation and resume refuse it, and the inference
pipeline applies it to synthetic images only.

### Synthetic demonstration models (Milestone 10) are not this model either

> **Update 2026-10-09 — generator 1.1.0 (synthetic language).** The dataset was regenerated so that every Tamil-Brahmi-like row is a sentence of the invented synthetic language ([`SYNTHETIC_LANGUAGE.md`](SYNTHETIC_LANGUAGE.md); SYNTHETIC LANGUAGE — NOT TAMIL-BRAHMI); other classes are byte-identical and the split assignment is unchanged. The models were retrained. Current: records `4e6eb6684b50…`, synthetic `c57c6fb985433fae…`, split `a96ed8d18770…`; classifier `synthetic_20261009T065459Z_4e6eb668_s20261003_resnet18` (test artifact accuracy 0.872, balanced 0.872, macro F1 0.861; T = 2.886, ECE 0.114 → 0.021); vision bundle `vision_20261009T071624Z_4e6eb668_s20261003` (regions F1 0.627, rows F1 0.732, segmentation F1 0.967, end-to-end CER 0.091, WER 0.277); synthetic-language exact translation 0.826 on 86 held-out images (`benchmark_20261009T071739Z_test`). The tables below record the 2026-10-03 run (generator 1.0.0) and are kept as history.

| Model | Task (SYNTHETIC) | Synthetic test result |
|---|---|---|
| ResNet-18 + temperature `T = 2.967` (fitted on synthetic val) | 4 synthetic task classes | artifact accuracy 0.885, balanced 0.885, macro F1 0.882; ECE 0.108 → 0.060 |
| RegionNet (2-channel heat map, stride 4) | synthetic inscription regions; glyph rows | regions F1 0.619 (IoU ≥ 0.5); rows F1 0.785 |
| GlyphCenterNet (CenterNet-lite, stride 2) | glyph centres in a row crop | segmentation F1 0.969 |
| GlyphNet (16-way) | synthetic glyph classes SG00–SG15 | glyph accuracy 0.989; end-to-end CER 0.080, WER 0.223 |

These are **accuracy on the synthetic engineering benchmark**, *glyph recognition accuracy on the
synthetic glyph benchmark* and a *synthetic chronology reasoning test* — never archaeological
performance. The glyphs are invented shapes; the interpretation categories and the chronology
categories are invented rules. The vision bundle (`models/synthetic/vision/<run>/`) has a
manifest with SHA-256 and `model_fingerprint` per file, the dataset fingerprint and split digest
(the pipeline refuses a classifier and bundle trained on different data), git commit and
environment; files load with `weights_only=True`. Calibration files are bound to the checkpoint's
`model_fingerprint`. See [`SYNTHETIC_END_TO_END.md`](SYNTHETIC_END_TO_END.md).

## Intended model (when data exists)

| | |
|---|---|
| Task | 4-class artifact-level script category: `tamil_brahmi`, `graffiti`, `none`, `uncertain` |
| Architectures | ResNet-18 / EfficientNet-B0 / ConvNeXt-Tiny (torchvision), ImageNet-initialised, new head |
| Training data | expert-promoted labels only; artifact-level grouped splits (5-fold CV at ≥5/class, 70/15/15 at ≥20/class) |
| Imbalance | class-weighted loss (default) or weighted sampler |
| Reporting | artifact-level metrics as the headline; per-class P/R/F1, balanced accuracy, confusion matrix, top-k, ECE/MCE/Brier |
| Provenance | every checkpoint carries dataset fingerprint, split digest, git commit, config and a weight fingerprint |

## Use and misuse

* **Output is an AI observation.** A class probability is not archaeological confidence and
  never sets the script, a reading or a date. It is shown under the amber AI banner only.
* Not for: dating a sherd, reading an inscription, deciding authenticity, or any claim about
  an object without expert review.
* Known risk to control when data arrives: shortcut learning (museum lighting, display glass,
  photographer) because sources cluster by class. Controlled photography of uninscribed sherds
  from the same contexts is required (docs/NEXT_DATA_ACQUISITION.md).
