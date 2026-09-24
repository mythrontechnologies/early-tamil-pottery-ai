# Model Card

## Status: no trained model exists

| | |
|---|---|
| Trained models | **none** |
| Why | the readiness gate (G1-G11) fails: 0 expert-labelled artifacts in every class |
| What runs today | `NoModelClassifier`, `NoDetector`, `NullMarkAnalyzer`, `NullTranscriber` (honest null stages) |
| Metrics | **none**. "Evaluation blocked — insufficient expert-labelled archaeological data." |

Nothing in this repository reports an accuracy, a calibration or an OCR error rate for real data.
The numbers produced by the test suite come from synthetic noise tensors and exist only to
exercise code.

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
