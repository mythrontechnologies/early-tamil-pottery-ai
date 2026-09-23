# Training Framework

**Status:** built in Milestone 5, and **never run on archaeological data**: none exists that
may be used. `python -m src.training train` stops at the readiness gate today:

```text
> python -m src.training train
Training blocked:
No authorized archaeological images are available.
```

The framework exists so that authorised data can be inserted later without redesign. Every
number in `configs/training.yaml` is an untuned engineering default.

---

## 1. Architecture

```text
configs/project.yaml ─┐  (classes, split, seed, threshold, image size, normalisation)
configs/training.yaml ┤  (model, optimiser, augmentation, runtime)
                      ▼
python -m src.training train
  └─ run.run_training()                        the ONLY path from records to a model
       1. TrainingConfig.load + check_against_project
       2. assert_training_ready()   ◄── gate G1–G11 on the canonical dataset; no bypass
       ─────────────── nothing below runs today ───────────────
       3. load_dataset()  +  SplitManifest.load  +  partition_records (leakage re-check)
       4. print class report (class / artifacts / images / %)
       5. seed_everything, select_device
       6. PotteryImageDataset + make_loader (augment train only; optional weighted sampler)
       7. build_model (pretrained backbone, new head, frozen backbone)
       8. Trainer.fit (AMP, clipping, scheduler, early stopping, unfreeze, best/last ckpt)
       9. reload best checkpoint → test partition → image- and artifact-level metrics
      10. ExperimentRecord → models/experiments/<id>/experiment.json
```

| Module | Responsibility |
|---|---|
| `src/dataset/loader.py` | Strict record loading. `L1` path containment, `L2` real hash, SHA-256 recomputed. Read-only records. Brief-name aliases. |
| `src/dataset/classes.py` | Class spec from `project.yaml`. Held-out labels are explicit, never collapsed. Per-label availability. |
| `src/dataset/splits.py` | Artifact-level split manifests and leakage verification. See [`DATASET_SPLIT.md`](DATASET_SPLIT.md). |
| `src/dataset/sampling.py` | Class counts, inverse-frequency weights, sampler weights, the pre-training class table. |
| `src/dataset/fingerprint.py` | Dataset and image-set fingerprints. |
| `src/dataset/statistics.py` | `python -m src.dataset stats`. |
| `src/dataset/readiness.py` | Gates G1–G11. |
| `src/training/config.py` | Strict typed config. Unknown keys and contradictions are errors. |
| `src/training/augmentation.py` | Conservative train transforms; deterministic eval transforms. |
| `src/training/data.py` | `PotteryImageDataset`, seeded loaders. |
| `src/training/model.py` | Backbones, head replacement, freeze/unfreeze. |
| `src/training/engine.py` | `Trainer`, `EarlyStopping`. Data-agnostic. |
| `src/training/checkpoint.py` | Checkpoint format and checks. |
| `src/training/runtime.py` | Device selection, seeding, git commit, environment. |
| `src/training/experiment.py` | JSON experiment records. |
| `src/training/run.py` | Gate, then orchestration. |
| `src/evaluation/metrics.py` | Metrics, artifact aggregation, BLOCKED reports. |

`src/classification/` (reserved in Milestone 1) is still empty. The classifier is a
configured `src/training` model, not a separate package.

### 1.1 Why the engine is data-agnostic

`Trainer` fits whatever loaders it is given. That lets the tests drive it with random
tensors on the CPU. It **cannot** be reached with research records except through
`run_training`, which:

- takes no records path, data root or relaxing flag (tested: its signature is only
  `config_path`, `manifest_path`);
- always evaluates the gate on `data/metadata/records.jsonl` + `data/raw/`.

The gate's own `permit_noncanonical_source` parameter exists only so the gate's positive
path can be unit-tested on synthetic corpora in a temporary directory. It is not exposed by
`assert_training_ready`, `run_training`, or any CLI (tested).

## 2. Configuration (`configs/training.yaml`)

| Section | Key defaults | Notes |
|---|---|---|
| `model` | `resnet18`, `pretrained: true`, `freeze_backbone: true`, unfreeze at epoch 5, dropout 0.2 | `num_classes: 4` is an **assertion** checked against `project.yaml`, not an override |
| `data` | `image_size: 224`, `batch_size: 16`, `num_workers: 2` | image size must equal `preprocessing.target_size` |
| `optimization` | AdamW, lr 3e-4 (head) / 3e-5 (backbone once unfrozen), wd 1e-4, cosine, 30 epochs, clip 1.0 | |
| `early_stopping` | monitor `balanced_accuracy`, patience 7 | balanced accuracy, not accuracy, because classes will be imbalanced |
| `imbalance` | `class_weighted_loss`, counted per **artifact** | see §5 |
| `runtime` | seed 20260923, `device: auto`, AMP on, deterministic on | |
| `checkpoint`, `experiments` | `models/checkpoints`, `models/experiments` | git-ignored |
| `augmentation` | see §4 | |

**Why these defaults fit a 6 GB RTX 4050.** ResNet18 has 11.7 M parameters (about 45 MB in
fp32). Peak allocated GPU memory, **measured** on this machine for one AdamW + fp16 autocast
step at 224 px, batch 16, using random tensors:

| Backbone | Peak allocated |
|---|---|
| frozen (head only) | 128 MiB |
| unfrozen (full network) | 383 MiB |

That leaves ample headroom for a larger batch or ResNet34 later. "Do not optimise
prematurely" applies: nothing here was tuned, because there is nothing to tune on.

Supported backbones: `resnet18`, `resnet34`, `efficientnet_b0`, `mobilenet_v3_large`. All are
torchvision models with ImageNet weights, downloaded on first real use. ImageNet weights are
a general-purpose image model, not archaeological data. Tests always use
`pretrained: false` and are checked never to touch the network.

The loader rejects: unknown keys; unsupported model, optimiser or scheduler; early-stopping
mode inconsistent with the monitor; rotation > 15°; hue > 0.02; both imbalance corrections at
once; and any disagreement with `project.yaml`.

## 3. Readiness gates

`src/dataset/readiness.py`. Each gate carries a **basis**, so an engineering requirement is
never mistaken for an archaeological claim. Unevaluated gates count as failed.

| Gate | Blocks when | Basis |
|---|---|---|
| G1 | records are not `data/metadata/records.jsonl` | engineering |
| G2 | no records | engineering |
| G3 | no image files under `data/raw/` | engineering |
| G4 | metadata validation fails (`E*`, `R*`, including R3: an artifact in two splits) | engineering |
| G5 | any record rejected by the loader: missing image, bad or absent SHA-256, path escape | engineering |
| G6 | one photograph (by hash) recorded under two artifacts (R4) | engineering |
| G7 | a training record has `label_source = unknown` | project methodology |
| G8 | a training record lacks `research_usable = yes` (**absent or `unknown` = not permitted**) | rights |
| G9 | a trainable class has zero artifacts | project methodology |
| G10 | a class is below the per-class artifact minimum: 20 for holdout, `k` for k-fold | engineering (statistical) |
| G11 | no split manifest for the current dataset fingerprint, or it fails verification (artifact or hash leakage, stale fingerprint) | engineering |

**No gate encodes an archaeological judgement.** The class list (G9) is a project
methodology decision from Milestone 1. The thresholds (G10) are statistical and are
explained in `DATASET_SPLIT.md` §4. G8 implements the Milestone 4 finding that "visible
online" is not permission, and no source is licensed for training today.

`G7` blocks only `unknown` provenance. `project_annotation_unverified` labels may be trained
on, but rule R14 warns if they reach the test split, because test labels should be
source-backed.

## 4. Augmentation

Every transformation was admitted by one question: **could it change the evidence a
specialist would use to classify this sherd?**

| Transformation | Default | Reasoning |
|---|---|---|
| Small rotation ±5° | on | Simulates a photographer's hand. Applied with `expand=True` **before** letterboxing, so no corner of the sherd is cut. Capped at 15° by the config loader: beyond that it reorients the text rather than the camera. |
| Letterbox to 224 | on | Same `pad` geometry as Milestone 3. A centre crop can remove the edge of a sherd, and inscriptions often sit near a break or rim. |
| Scale-and-shift | on, scale 0.90–1.0 | Shrinks the letterboxed square and shifts it **only within the margin the shrink frees**. It provably never crops (tested). Replaces random cropping. |
| Brightness / contrast | ±0.15 | Lighting varies between photographs; the evidence does not. |
| Saturation | ±0.05 | Kept tiny. Surface colour distinguishes wares (black-and-red, red, black). |
| Hue | **0** | A hue shift can turn one ware's colour into another's. Capped at 0.02 by the loader. |
| **Horizontal flip** | **off** | Mirroring reverses letter forms. Tamil-Brahmi is written left to right; a mirrored glyph is not a valid character, and some mirror onto a *different* character. Graffiti signs are orientation-bearing too. Enabling it emits a `HorizontalFlipWarning`, and should need a written justification. |
| Vertical flip | not offered | As above, more so. |
| Random resized crop | not offered | Can cut off the inscription. |
| Perspective / elastic / grid | not offered | Distorts letter morphology. |
| Cutout / random erasing | not offered | Can erase the very marks being classified. |
| Blur / sharpen | not offered | Softens incised strokes; worn inscriptions are already faint. |

**Evaluation and test transforms** are letterbox → tensor → normalise, with no randomness
(tested: two passes give identical tensors). Normalisation uses the ImageNet statistics
already recorded in `project.yaml`, appropriate for ImageNet-pretrained backbones. They are
to be recomputed from the training split once real data exists.

Randomness comes from torch's RNG, so DataLoader worker seeding makes augmentation
reproducible.

## 5. Class imbalance

- `imbalance.strategy`: `none` | `class_weighted_loss` | `weighted_sampler`. **One only.**
  Using both double-corrects, so the config loader and `check_strategy` both reject it.
- `count_unit: artifact` (default). Class frequencies are counted per artifact, matching the
  evaluation unit, so one heavily photographed sherd cannot dominate the weights.
- Weighted loss: inverse-frequency weights normalised to mean 1. A class with zero examples
  raises an error rather than receiving a silent zero weight.
- Weighted sampler: each class gets equal sampling mass. With `equalise_artifacts`, each
  artifact within a class also gets equal mass, spread across its photographs. The sampler
  is seeded.
- Before training, `run_training` prints the class table required by the brief:

  ```text
      class                       status      artifacts   images  % artifacts
      tamil_brahmi                trainable          ..       ..         ..
      ...
      other_script                held_out           ..       ..     held out
  ```

## 6. Evaluation (`src/evaluation/metrics.py`)

- Accuracy, **balanced accuracy**, macro and weighted precision/recall/F1, per-class
  metrics, the confusion matrix (rows = true, columns = predicted), and top-k accuracy for
  `1 < k < n_classes`.
- Computed from the confusion matrix, **not** with `zero_division=0`:
  - recall for a class with no true examples is **undefined** (`None`), not 0;
  - precision for a class never predicted is 0 if the class has examples (the model missed
    all of them) and undefined otherwise;
  - macro averages cover **classes with support**, and the report lists the classes
    excluded for having none.

  With full support these match scikit-learn exactly (tested).
- **Artifact-level metrics are the headline.** `aggregate_by_artifact` averages class
  probabilities over all photographs of each sherd before scoring. Image-level metrics are
  reported alongside them, but over-weight heavily photographed sherds.
- **Blocked evaluation:** empty input gives a `BLOCKED` report reading
  `NO REAL DATA — EVALUATION BLOCKED`, never a zero score. `python -m src.evaluation evaluate`
  checks the gate first and prints the same message today (exit code 3).
- **Provenance stamp:** a report built from non-research data carries
  `SYNTHETIC_TEST DATA - NOT AN ARCHAEOLOGICAL RESULT`.
- For a k-fold manifest there is no test partition. Each fold's validation metrics are
  recorded in its own experiment file and must be reported as cross-validation.

## 7. Reproducibility

| What | How |
|---|---|
| Seeds | `seed_everything` seeds `random`, NumPy, torch CPU and CUDA. The DataLoader has a seeded generator and `worker_init_fn`; the weighted sampler is seeded. |
| Determinism | `cudnn.deterministic = True`, `benchmark = False`, `use_deterministic_algorithms(True, warn_only=True)`, `CUBLAS_WORKSPACE_CONFIG=:4096:8`. Bitwise GPU determinism is not guaranteed for every kernel. `warn_only` makes an op without a deterministic implementation warn instead of abort, and the seed state is recorded. |
| Split | Deterministic manifest with a content digest; see `DATASET_SPLIT.md` §6. |
| Dataset | `dataset_fingerprint` in the manifest, the checkpoint and the experiment record. A checkpoint evaluated against a different fingerprint is refused. |
| Config | The full resolved config is stored in every checkpoint and experiment record. |
| Code | `git rev-parse HEAD` plus a dirty-tree flag, in every checkpoint and experiment record. |
| Environment | Python, torch, torchvision, CUDA runtime and cuDNN versions, and platform, in every experiment record. |

## 8. Checkpoints and experiment records

A **checkpoint** (`models/checkpoints/<experiment_id>/best.pt` and `last.pt`) contains
`format_version`, `model_name`, `num_classes`, `class_names`, `state_dict`,
optimiser/scheduler state, `epoch`, `metrics`, `monitor`, `config`, `dataset_fingerprint`,
`split_digest`, `git` and `created_utc`. `load_checkpoint` refuses a missing key, an
incompatible format, or a class list that differs from the expected one. Writes are atomic
(temporary file, then rename).

An **experiment record** (`models/experiments/<experiment_id>/experiment.json`) contains
`experiment_id` (`<UTC timestamp>_<fingerprint8>_s<seed>[_fold<i>]`), `timestamp`, `status`,
`git_commit`, `git_dirty`, `dataset_version`, `config`, `model` (name and parameter
counts), `seed`, `device`, `environment`, `split` (strategy, digest, manifest, fold),
`training_split`/`validation_split`/`test_split` (artifact and image counts, artifact ids),
`metrics` (full per-epoch history, and image- and artifact-level test metrics),
`checkpoint`, and a `readiness` snapshot of the gate. A blocked run writes no experiment
record: nothing was trained.

No tracking server is used. JSON files are enough for a prototype and diff cleanly.

## 9. Commands

```powershell
python -m src.dataset stats          # what is in the dataset; readiness
python -m src.dataset split          # artifact-level split manifest (refused today)
python -m src.dataset readiness      # full gate report
python -m src.training device        # CUDA / GPU / AMP report
python -m src.training config        # validated, resolved training config
python -m src.training train         # gate first; exit code 3 when blocked
python -m src.evaluation evaluate --checkpoint models/checkpoints/<id>/best.pt
```

## 10. Current limitations

- **No authorised data.** Nothing here has been run on a sherd photograph. Every default is a
  priori.
- **Normalisation statistics** are ImageNet's, not computed from sherds.
- **Augmentation strengths** were chosen by reasoning, not validated. The *choice* of
  transformations should be reviewed by an epigraphist, particularly the rotation range
  and whether any photometric change can hide a faint incision.
- **No calibration and no uncertainty.** The softmax outputs are not calibrated
  probabilities. Calibration belongs in the evaluation milestone, once there is a
  validation set to fit it on.
- **Single-label.** `tamil_brahmi_and_graffiti` is held out rather than modelled as
  multi-label. Revisit when examples exist.
- **Bitwise reproducibility on GPU** is best-effort (§7).
