# Milestone 5: Completion Report

**Date:** 2026-09-23
**Scope:** dataset and training framework
**Status:** complete. **No model trained. No archaeological data used, downloaded or
fabricated. The training gate remains BLOCKED.**

Design detail is in [`DATASET_SPLIT.md`](DATASET_SPLIT.md) and
[`TRAINING_FRAMEWORK.md`](TRAINING_FRAMEWORK.md). This report records what was built, what
changed, and what was verified.

---

## 1. Final validation

Run from `.venv` on 2026-09-23:

```text
> python -m pytest tests/ -q
398 passed

CUDA available: True
GPU: NVIDIA GeForce RTX 4050 Laptop GPU (6.0 GiB), AMP enabled
Training readiness: BLOCKED
Real artifacts: 0
Real images: 0
```

```text
> python -m src.training train
Training blocked:
No authorized archaeological images are available.            (exit code 3, no traceback)

> python -m src.evaluation evaluate
NO REAL DATA — EVALUATION BLOCKED                              (exit code 3)

> python -m src.dataset split
SPLIT REFUSED
  - no records: there is nothing to split, and a split will not be fabricated for an empty dataset

> python -m src.dataset stats
Artifacts: 0
Images: 0
...
Training readiness: BLOCKED
```

`data/raw/` and `models/` contain only `.gitkeep`. No split manifest, checkpoint or
experiment record exists. Tests assert all of this.

## 2. What was built

### 2.1 Dataset layer (`src/dataset/`, extended, not duplicated)

| Module | New / changed | Purpose |
|---|---|---|
| `loader.py` | new | Strict loading: full validation with SHA-256 recomputation, plus `L1` (path stays inside `data/raw`, which defeats symlinks) and `L2` (real hash required). Records are rejected whole, with every reason; never repaired. Read-only records. Brief-name aliases (`dating_start` → `dating_lower_year`, and so on). `period` raises an explicit "not in schema" error. |
| `classes.py` | new | Class spec from `project.yaml`. Every schema label must be explicitly trainable or held out. Held-out labels are never collapsed. Per-label availability. |
| `fingerprint.py` | new | Order-independent dataset fingerprint (every field) and image-set fingerprint (ids + hashes). |
| `splits.py` | new | Artifact-level holdout / grouped k-fold / adopt-existing; deterministic; refuses rather than mislead; manifest with a tamper-evident digest; `verify_manifest` / `verify_partitions` leakage checks. |
| `sampling.py` | new | Class counts (per artifact or image), inverse-frequency weights, sampler weights, one-strategy-only check, the pre-training class table. |
| `statistics.py` | new | `python -m src.dataset stats`. |
| `readiness.py` | rewritten, API kept | Gates G1–G11, each with a category and a basis (engineering / project_methodology / rights). |
| `__main__.py` | extended | `stats` and `split` commands; `rules` lists the `L*` checks. |

`src/preprocessing/transforms.py` already existed. Training augmentation therefore lives in
`src/training/augmentation.py`, which reuses the Milestone 3 letterbox, rather than in a
second `src/dataset/transforms.py`.

### 2.2 Training framework (`src/training/`, new)

`config.py` (strict typed config), `augmentation.py`, `data.py`, `model.py` (ResNet18/34,
EfficientNet-B0, MobileNetV3-L; configurable classes; pretrained weights; freeze and unfreeze),
`runtime.py` (device selection with CPU fallback, seeding, git commit), `engine.py`
(AdamW/Adam/SGD; cosine/step/plateau; AMP; clipping; label smoothing; weighted loss; early
stopping; best/last checkpoints; scheduled backbone unfreeze), `checkpoint.py`,
`experiment.py`, `run.py` (gate, then orchestration), `__main__.py`.

### 2.3 Evaluation (`src/evaluation/`, new)

`metrics.py`: accuracy, balanced accuracy, macro and weighted P/R/F1, per-class metrics,
confusion matrix, top-k, artifact-level aggregation, and BLOCKED reports. Undefined metrics
stay undefined rather than becoming zeros. `__main__.py`: `evaluate`, gated.

### 2.4 Configuration

- `configs/training.yaml` (new): model, data, optimisation, early stopping, imbalance,
  runtime, checkpoint, experiments, augmentation. Conservative, untuned defaults for 6 GB.
- `configs/project.yaml`: `schema_version` 1.1.0; `split.balance_secondary:
  [inscription_present, site]`; `split.manifest_dir`.

## 3. Schema change (documented, not silent)

**1.0.0 → 1.1.0: two optional fields added**, `research_usable` and `commercially_usable`
(`yes`/`no`/`unknown`).

- **Why it was necessary.** The brief requires training to be blocked when rights are
  insufficient for the intended use. The only rights fields were free-text `license` and
  `redistributable`. Permission to republish is not permission to train, and neither can
  be tested by code. Milestone 4 (`MILESTONE_4_REPORT.md` §5.1) had already recommended
  separate rights fields.
- **Effect.** Gate G8 requires `research_usable = yes` on every training record. Absent or
  `unknown` counts as not permitted, matching the project rule that unknown rights are
  restrictive.
- **Compatibility.** Both fields are optional. The validator's `E4` checks only the major
  version, so 1.0.0 records stay valid (tested).
- **Updated:** schema file; `_example_record.json` and `tests/fixtures/valid/base_record.json`
  (now 61 fields; the example sets `research_usable: unknown`, the fixture `yes`);
  `data/metadata/README.md` (field table plus a "Schema changes" table);
  `tests/fixtures/README.md`; new schema tests in `TestRightsFields`.

**Not added:** the other three rights fields from Milestone 4 (`viewable_online`,
`downloadable`, and so on). They describe a *source*, not a training decision, and belong in
`DATA_SOURCE_AUDIT.md`. `period` and `inscription_type` were also **not** added: a
periodisation is an unmade archaeological decision, and `inscription_technique` already
covers how a mark was made. The loader and statistics say so explicitly.

## 4. Leakage protection, as verified by tests

| Property | Test |
|---|---|
| train ∩ val = train ∩ test = val ∩ test = ∅ (artifacts) | `test_holdout_is_artifact_disjoint` |
| all photographs of an artifact share a partition | `test_all_photographs_of_an_artifact_share_a_partition` |
| no image hash in two partitions | `test_hashes_do_not_cross_partitions`, `test_verify_partitions_catches_artifact_and_hash_leaks` |
| same photograph under two artifacts is rejected | `test_duplicate_hash_across_artifacts_is_rejected`, gate `G6` |
| artifact across two splits blocks training | `test_artifact_across_splits_blocks` |
| `image_id` grouping rejected | `test_manifest_never_uses_image_level_grouping` |
| stale manifest (dataset changed) rejected | `test_manifest_for_a_changed_dataset_fails_verification`, `test_stale_manifest_blocks` |
| hand-edited manifest rejected | `test_manifest_roundtrip_and_tamper_detection` |
| deterministic, order-independent | `test_deterministic`, `test_record_order_does_not_matter` |
| no re-split once a test set exists | `test_preassigned_splits_are_not_resplit` |

## 5. Readiness gates, as verified by tests

Each gate has a failing test on a synthetic corpus in `tmp_path`: zero data, missing class,
too few artifacts, invalid metadata, bad hash, duplicate photograph, artifact across splits,
unknown label source, rights unknown or absent, missing manifest, stale manifest, no images.

`test_synthetic_corpus_can_satisfy_every_gate_when_permitted` shows the gate **can** open on
a complete synthetic corpus, when a test-only parameter permits a non-canonical path. That
matters: a gate that could never pass would prove nothing by blocking. The same corpus is
blocked without that parameter. `TestNoBypass` checks that the parameter is not reachable
from `assert_training_ready`, `run_training`, or any CLI.

## 6. Tests

| File | Tests | Covers |
|---|---:|---|
| `test_dataset_layer.py` | 62 | loader, schema 1.1.0 rights fields, classes, fingerprints, splits, sampling, statistics, CLI |
| `test_readiness_gates.py` | 24 | live blocking, every gate failure, positive path, gate bases, no bypass |
| `test_training_framework.py` | 43 | config, model creation and class counts, CPU fallback, CUDA selection, seeding, augmentation safety, data, engine, checkpoints, AMP on CUDA, blocked training |
| `test_evaluation_metrics.py` | 14 | metrics vs scikit-learn, undefined-not-zero, top-k, artifact aggregation, BLOCKED reports and command |
| existing (Milestones 1–3) | 255 | unchanged, all passing |
| **Total** | **398** | all passing from `.venv` |

**Synthetic data used in tests:** a `synthetic_corpus` fixture generates flat-colour PNG
squares and `FIXTURE_`-marked records **in pytest's `tmp_path`**, never under `data/`. The
engine tests use random tensors. No test output is a result. The CUDA test runs one AMP step
on random tensors, and confirmed the GPU path works on the RTX 4050.

## 7. Decisions worth reviewing

1. **The split manifest, not `records.jsonl`, holds the assignment.** This differs from
   `SPLIT_METHODOLOGY.md` §5 as written in Milestone 1 (now annotated). Reason: writing
   splits into records changes the fingerprint the split depends on. See
   `DATASET_SPLIT.md` §7.
2. **Class frequencies are counted per artifact by default** for imbalance correction.
3. **Artifact-level metrics are the headline.** Image-level metrics are reported alongside.
4. **Held-out labels are excluded, not modelled.** `tamil_brahmi_and_graffiti` might suit
   multi-label modelling once examples exist.
5. **Augmentation** omits horizontal flip and all crop/distortion/erasing operations, and
   fixes hue at 0. This is reasoning, not validation. An epigraphist should review the
   rotation range and the photometric strengths.
6. **The 20-artifact holdout threshold** is carried over from Milestone 1 as a documented
   statistical requirement. No new archaeological threshold was introduced.

## 8. Current data limitations

Unchanged from Milestone 4: 0 authorised images, 0 records, no `research_usable = yes` on
any source, no source for the `none` class, and published sherd images too small for
character-level work. The framework makes these limits enforceable. It does not reduce them.

## 9. Next blocker

**Authorised data.** Specifically: a written TNSDA and author permission covering the
2026 corpus and ideally its documentation database (`DATA_SOURCE_AUDIT.md` §6, Step 1), and
an institutional route to photograph uninscribed sherds for the `none` class. Once records
exist, the path is:

```powershell
python -m src.dataset ingest <batch> --commit   # validate + append
python -m src.dataset split                     # artifact-level manifest
python -m src.dataset stats                     # review class table, leakage, readiness
python -m src.training train                    # runs only if G1–G11 all pass
```
