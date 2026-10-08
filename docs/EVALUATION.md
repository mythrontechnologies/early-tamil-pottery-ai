# Evaluation

Evaluation is **gated**: on the research dataset it runs only after the readiness gate (G1-G11) passes, and it
scores only against labels that experts promoted. Today every real-data evaluation prints
`NO REAL DATA — EVALUATION BLOCKED` and exits with code 3. That is the correct result, not a failure.

## Evidence tiers (never mixed in one headline)

| Tier | Where | May be called |
|---|---|---|
| `real_expert_labelled` | `python -m src.evaluation evaluate / detection / ocr` | a real-data validation result |
| `synthetic_engineering` | `python -m src.evaluation synthetic`, `python -m src.synthetic …` | "accuracy on the synthetic engineering benchmark" only |
| `test_fixture` | the test suite | nothing; it exercises code |

## Classification (real, gated)

```powershell
python -m src.evaluation evaluate --checkpoint models\checkpoints\<run>\best.pt [--partition test] [--robustness] [--json]
```

Headline at **artifact level** (photographs of one sherd are averaged first): accuracy, balanced accuracy,
macro precision / recall / F1, weighted F1, per-class metrics, confusion matrix, top-k, calibration (ECE, MCE,
Brier), plus an **error analysis** (every misclassified artifact with its model confidence, the high-confidence
errors first, accuracy by confidence bin). `--robustness` re-scores under lighting (exposure, contrast), blur,
noise, JPEG compression, rotation, scale, crop and occlusion at two severities
(`src/evaluation/perturbations.py`, seeded per image). The checkpoint must carry `dataset_type: research` and
the current dataset fingerprint; grouped k-fold runs are evaluated per fold during training.

## Detection and OCR (real, gated)

Any region detector or transcriber, whatever produced it, is scored from a JSONL file:

```powershell
python -m src.evaluation detection --predictions regions.jsonl   # {"image_id": ..., "regions": [[x, y, w, h], ...]}
python -m src.evaluation ocr --predictions readings.jsonl        # {"image_id": ..., "reading": "..."}
```

Ground truth is what experts promoted into `data/metadata/records.jsonl` (`label_source = expert_annotation`):
inscription / graffiti regions in pixels for detection, undisputed transcriptions for OCR. Without it the
commands are BLOCKED (exit 3).

* Detection: greedy one-to-one IoU matching; precision, recall, F1 at IoU 0.5 and 0.75; mean IoU of matches;
  the images with missed regions. An image an expert marked as having no region turns any prediction into a
  false positive.
* OCR: CER, WER, exact-reading accuracy, coverage, and failures split into *no output*, *partial*
  (CER < 0.5) and *wrong*. A reading the expert recorded as illegible is excluded, never scored against the model.

## What the numbers are not

A model probability is not archaeological confidence; a high score on few artifacts is fragile (report
grouped-CV variance); agreement statistics are uninterpretable below ~30 paired items; synthetic scores say
nothing about real sherds. Shortcut learning (museum lighting, display glass, photographer) is the main risk once
data exist: inspect the high-confidence errors first.

Code: `src/evaluation/metrics.py`, `calibration.py`, `ocr.py`, `tasks.py`, `perturbations.py`,
`reproducibility.py`.
