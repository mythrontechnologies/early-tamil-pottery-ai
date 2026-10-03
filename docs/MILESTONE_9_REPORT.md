# Milestone 9: Synthetic Dataset + Full ML Pipeline Validation

**Date:** 2026-10-03
**Status:** complete. The whole pipeline ran end to end on an isolated SYNTHETIC engineering
dataset. **No archaeological model exists, no archaeological metric was produced, the research
data is byte-for-byte unchanged, and real training remains BLOCKED.**

> The synthetic dataset exists solely for engineering and model-pipeline validation. It must not
> be interpreted as archaeological evidence or used to make claims about real Tamil Nadu pottery.

```text
SYNTHETIC ENGINEERING RESULTS (generated images; not archaeological performance)
  Dataset:          1,000 artifacts / 2,202 images, 4 x 250 artifacts, 37.2 MiB (29.2 MiB images)
  Split:            700 / 152 / 148 artifacts (1,538 / 338 / 326 images); 0 leakage
  Fingerprint:      d61e25c6dfe07878fd3a8d9bf47b434417691fefcf7ddb15f3e913855bc14240
  Model:            ResNet18 (ImageNet init), RTX 4050 + AMP, 467 s, best epoch 8 of 16
  Test (artifact):  accuracy 0.885, balanced accuracy 0.885, macro F1 0.882
  Calibration:      ECE 0.085 (artifact) / 0.108 (image); Brier 0.195 / 0.232; overconfident
  Glyph benchmark:  oracle glyph accuracy 0.991; learned row detection F1 0.787; end-to-end CER 0.475

REAL ARCHAEOLOGICAL STATE (unchanged)
  Research data:    30 images / 17 artifacts, all script_type = unknown; 70 files byte-identical
  Workflow:         stage 6 annotations WAITING (human action); 7 agreement WAITING; 10 training and
                    11 evaluation WAITING / blocked
  Training:         BLOCKED (exit 3; G7-G11 fail); readiness report identical to before the milestone
  Evaluation:       BLOCKED ("NO REAL DATA — EVALUATION BLOCKED", exit 3)
  Tests:            898 passed (825 before this milestone + 73 new)
```

---

## 1. Objective

Validate synthetic data → training → evaluation → checkpoint → inference → API → UI → metrics →
reproducibility, while keeping every real-data gate intact and never representing synthetic data
as archaeological.

## 2. What was built

| component | files |
|---|---|
| constants, label mapping, separation guards | `src/synthetic/__init__.py` |
| invented glyph alphabet (SG00–SG15) and abstract motifs | `src/synthetic/glyphs.py` |
| procedural generator (class-blind conditions) | `src/synthetic/generator.py`, `configs/synthetic_dataset.yaml`, `src/synthetic/config.py` |
| records, provenance, fingerprint, loader, split | `src/synthetic/dataset.py`, `src/synthetic/synthetic_record.schema.json` |
| stats and 14-check verification | `src/synthetic/audit.py` |
| CLI | `src/synthetic/__main__.py` (`generate`, `split`, `stats`, `verify`, `robustness`, `ocr-benchmark`) |
| synthetic training | `src/synthetic/train.py`, `configs/synthetic_training.yaml`, `python -m src.training train --dataset synthetic` |
| synthetic evaluation | `src/synthetic/evaluate.py`, `python -m src.evaluation evaluate --dataset synthetic` |
| robustness suite | `src/synthetic/robustness.py` |
| glyph recognition benchmark | `src/synthetic/ocr_benchmark.py` |
| inference identity + synthetic classifier | `src/synthetic/inference.py`, `src/inference/*` |
| UI indicator | `app/analyze.py`, `app/ui/components.py`, `app/ui/data.py`, `app/ui/theme_v3.css`, `app/views/dataset.py` |
| tests | `tests/test_synthetic.py` (34), `tests/test_synthetic_separation.py` (39) |
| docs | `docs/SYNTHETIC_DATASET.md`, `docs/SYNTHETIC_TRAINING.md`, this report, `data/synthetic/README.md` |

**Reused, not rewritten:** the research `DatasetRecord`/`LoadedDataset`, `make_split`,
`verify_manifest`/`partition_records`, fingerprints, `Trainer`, `build_model`, transforms and
augmentation, `PotteryImageDataset`/`make_loader`, checkpoint format, metrics and calibration,
`ExperimentRecord`, `analyze()`, `Region`/`OCRResult`/`screen_ocr`, the HTTP server and the design
system. The research path's code is unchanged except where a guard was added.

**Changed in existing modules (all additive):**

* `checkpoint.py` — `dataset_type` + `synthetic` block; loaders can require a type; synthetic
  checkpoints need the marker and synthetic names; save locations enforced; `_plain` now stores
  str/int/float subclasses as built-ins (a real bug: `torch.__version__` made checkpoints
  unloadable under `weights_only=True`).
* `engine.py` — passes dataset type/metadata into checkpoints; stores train/val loss with
  checkpoint metrics; resume demands the same dataset type.
* `experiment.py` — `dataset_type`; filing guard.
* `validation.py` — rule **E6** (synthetic record = error). `annotation/validate.py` — rule **N17**.
  `annotation/promote.py` — **P0**.
* `evaluation/metrics.py` — `synthetic` provenance prints "SYNTHETIC DATA ONLY — NOT
  ARCHAEOLOGICAL PERFORMANCE". `evaluation/ocr.py` — public `edit_distance`.
* `classification` — the research classifier requires a research checkpoint.
* `inference` — `dataset_type`/`dataset` on every result (schema 1.1.0); synthetic identity by
  SHA-256; `synthetic_classifier` applied to synthetic images only; API/CLI `--synthetic-checkpoint`.
* `training/__main__.py`, `evaluation/__main__.py` — the explicit `--dataset synthetic` switch.

**Not changed:** `readiness.py` (G1–G11), `loader.py`, `splits.py`, `classes.py`, `run.py`,
`configs/project.yaml`, `configs/training.yaml`, `image_record.schema.json`, the annotation schema,
the workflow.

## 3. Synthetic dataset

See [`SYNTHETIC_DATASET.md`](SYNTHETIC_DATASET.md). Four synthetic visual task categories
(`synthetic_tamil_brahmi_like`, `synthetic_graffiti_like`, `synthetic_none`, `synthetic_uncertain`),
250 artifacts each, 2–3 views per artifact. Sherd outlines, surfaces, lighting, shadows, scratches,
texture, backgrounds, scale, blur, exposure, contrast, perspective, rotation, occlusion and JPEG
compression vary; all of them come from random streams that never see the class (tested). Archaeological
fields are `not_applicable`; ids are `SYNTH-…`; every record carries `dataset_type: synthetic` and
the marker. Generation: 252 s, deterministic; `verify` re-renders samples byte-identically.

## 4. Separation from the archaeological data (required tests 1–10)

| # | guarantee | how it is enforced | tests |
|---|---|---|---|
| 1 | synthetic files cannot enter `data/raw` | destination guard; E6 in the research validator; research loader rejects | 11 |
| 2 | synthetic data cannot satisfy readiness | gate reads only canonical paths; synthetic records fail G1/G4; research train/evaluate still exit 3 | 3 |
| 3 | synthetic checkpoints cannot be mistaken | `dataset_type` + marker; research classifier/evaluation refuse; save-location guard; weights-only loadable | 6 |
| 4 | synthetic metrics stay out of archaeological history | experiments/reports filed by type; config refuses research dirs; banner on reports; workflow unaffected | 5 |
| 5 | synthetic labels cannot be promoted | promotion P0 (plan blocked / artifact rejected) | 2 |
| 6 | synthetic annotations cannot enter the store | annotation rule N17 (+ N2) | 2 |
| 7 | provenance preserved | every image re-renders from its recorded streams; lock holds every fingerprint | 2 |
| 8 | dataset type always explicit | records, provenance, checkpoint, experiment, inference (research / synthetic / unregistered) | 2 |
| 9 | removing synthetic data changes nothing real | readiness identical before / during / after; gate code never references synthetic locations | 2 |
| 10 | real gates unchanged | G1–G11 table pinned; no relaxing parameter; class list and thresholds unchanged; live gate blocks | 4 |

## 5. Training, evaluation, robustness, OCR

Full numbers in [`SYNTHETIC_TRAINING.md`](SYNTHETIC_TRAINING.md). In brief (**synthetic only**):

* **Training:** ResNet18, 467 s on the RTX 4050 with AMP, early stop after 16 epochs (best 8).
* **Test, artifact level (n = 148):** accuracy 0.885, balanced accuracy 0.885, macro F1 0.882,
  top-2 0.986, ECE 0.085, MCE 0.508, Brier 0.195. The hard boundary is uncertain → none (11/37).
* **Calibration finding:** overconfident — image-level mean confidence 0.978 vs accuracy 0.877;
  34 of 40 errors above 0.9 confidence. A real-data model will need post-hoc calibration.
* **Robustness:** lighting and background changes cost ≤ 0.02 balanced accuracy; JPEG q15 and
  blur σ2 about 0.08; 0.6× scale 0.13; σ16 noise 0.18; 16 % occlusion 0.24.
* **Synthetic glyph recognition benchmark:** oracle glyph accuracy 0.991 (CER 0.045); learned row
  detector F1 0.787 (classical baseline 0.383); end-to-end CER 0.475, WER 0.786. Segmentation of a
  row into glyphs is the bottleneck. Through `analyze()` the reliability screen kept 5 of 60 outputs
  (all correct) and abstained on 55.

## 6. Inference, API, UI

* CLI: `python -m src.inference analyze <synthetic image> --synthetic-checkpoint latest` →
  "DATASET SYNTHETIC DEMONSTRATION", synthetic prediction labelled as such, "Insufficient evidence"
  for every archaeological question.
* HTTP API (live): synthetic image → `dataset_type: synthetic`, banner, prediction; real
  CC-BY-4.0 research photograph → `dataset_type: research`, registered, licence intact,
  classification `no_model` — the loaded synthetic model is never applied to a real image.
* Streamlit (Chromium via playwright-cli, 1440 px and 390 px): synthetic mode shows the hatched
  "Synthetic demonstration — not archaeological evidence" banner, the SYNTHETIC DEMONSTRATION badge,
  generator ground truth vs model prediction and a "GENERATED synthetic image" caption; no real-data
  badge appears. Research photographs show REAL RESEARCH DATA and no synthetic element. The Dataset
  page states it counts research data only. Badges carry text and a
  glyph, never colour alone; the banner is a labelled `role="note"` region.

**Correction (follow-up fix).** This report originally said "no horizontal scroll at 390 px". That check
measured only the document at the default text size. With phone-enlarged text (125 % and above) the
synthetic analysis page was 41 px (390 px wide) to 71 px (360 px wide) wider than the screen, inside
Streamlit's scroll container: status badges could not wrap, flex headings did not wrap, the 2D/2.5D
control did not wrap, and long tokens (`synthetic_tamil_brahmi_like`, ids, hashes) could not break.
Fixed in `app/ui/theme_v3.css` (wrap, never shrink text or hide content); every page and analysis state
now reflows at 390x844 and 360x800 with text at 100-200 %. Regression tests:
`python -m pytest -m browser` (`tests/test_browser_mobile.py`).

## 7. Real data unchanged (verified at the end of the milestone)

* SHA-256 of all 70 files under `data/raw`, `data/external`, `data/metadata` (including
  `records.jsonl`, the acquisition provenance and schemas) and `knowledge/`: identical to the
  snapshot taken before any change.
* Annotation store (`data/metadata/annotations/`): still absent (0 annotations). Verification
  registry: still absent (0 verifications).
* `python -m src.dataset readiness --json`: identical to the pre-milestone report.
* `python -m src.workflow status`: stages 1–5 PASS; 6 annotations WAITING (human action);
  7 expert agreement WAITING; 8 promotion WAITING; 9 split WAITING; 10 training BLOCKED by the gate;
  11 evaluation blocked.
* `python -m src.training train`: exit 3, "Training blocked" (G7–G11).

## 8. Reproduce

```bash
python -m src.synthetic generate --force && python -m src.synthetic verify
python -m src.training train --dataset synthetic
python -m src.evaluation evaluate --dataset synthetic --checkpoint models/synthetic/checkpoints/<run>/best.pt
python -m src.synthetic robustness --checkpoint <best.pt>
python -m src.synthetic ocr-benchmark
python -m pytest tests/ -q
```

Generated images, per-image JSONL, checkpoints and reports are git-ignored; the generator, both
configs, the schema, the dataset lock (all fingerprints) and the split manifest are committed, so
the dataset can be regenerated and checked against the lock.

## 9. Limitations

* Everything in §5 measures the generator, not pottery. None of it predicts archaeological accuracy.
* The model overfits and is overconfident on synthetic data; neither was "fixed", because tuning to
  synthetic data would optimise the wrong thing.
* The glyph benchmark's segmentation is classical and weak on touching or rotated glyphs.
* Image hashes depend on the Pillow/libjpeg build; the metadata fingerprint does not.
* The dataset was generated from the working tree of this milestone before its commit
  (`generation_run.json` records base commit `2c74c04`, dirty); regenerating after the commit
  yields byte-identical data.
