# Early Tamil Pottery AI

AI-assisted analysis of Early Historic Tamil Nadu pottery, with emphasis on Tamil-Brahmi/Tamili
inscriptions and graffiti.

> **This system provides AI-assisted archaeological analysis and is not a substitute for expert
> epigraphic or archaeological assessment.**

**Status: engineering complete; blocked on real evidence.** Everything engineering can honestly
complete is complete: acquisition, validation, preprocessing, annotation (append-only,
tamper-evident), agreement, reversible promotion, knowledge base and verification workflow,
evidence-based reasoning, an inference API/CLI/HTTP service, a Streamlit application,
evaluation and a gated training pipeline. What remains is **real archaeological evidence**:
expert annotation, reference verification, enough labelled artifacts per class, then training.
The project holds **30 openly licensed photographs (17 artifacts)**, **none carries an expert
label**, and there is **no trained model**. The analysis tool therefore answers most questions
with "Insufficient evidence", which is the correct answer. See
[`docs/FINAL_ENGINEERING_STATUS.md`](docs/FINAL_ENGINEERING_STATUS.md).

---

## What this is

A research prototype that, given a photograph of a pottery sherd, is intended to produce an
artifact assessment, inscription detection, script identification, an experimental transcription
and translation, an estimated chronological range, and — crucially — **the evidence and reasoning
behind each of those**, with explicit confidence and uncertainty.

## What this is not

Not an image classifier that prints `"2nd century BCE — 87%"`. The design principle throughout is
that four things are kept apart and shown separately:

| Layer | Question |
|---|---|
| **Observation** | What did the vision/OCR model actually detect? |
| **Interpretation** | What might that indicate? |
| **Historical evidence** | What do published archaeological and epigraphic sources establish? |
| **Conclusion** | What range or reading follows? |

An LLM-generated explanation is not evidence and is never presented as such.

---

## Current state

| | |
|---|---|
| Research images | **30** (17 artifacts), Wikimedia Commons, CC BY / CC BY-SA — see [`docs/PUBLIC_DATASET_AUDIT.md`](docs/PUBLIC_DATASET_AUDIT.md) |
| Expert-labelled images | **0** — every record has `script_type = unknown` pending annotation |
| Supporting images | 15 in `data/external/` (out-of-region pottery, Tamil-Brahmi rock inscriptions) |
| Verified references | **0** — verification registry built (Milestone 8); R1, S01, S03 not yet checked against the publications (`python -m src.knowledge status`) |
| Models | **no archaeological model.** Training pipeline complete (AMP, resume, fingerprints). Milestone 9 validated it end to end on a separate SYNTHETIC engineering dataset; the resulting models live in `models/synthetic/`, are marked SYNTHETIC ONLY, and are refused wherever an archaeological model is expected ([`docs/SYNTHETIC_TRAINING.md`](docs/SYNTHETIC_TRAINING.md)) |
| Synthetic engineering data | 1,000 generated objects / 2,202 images in `data/synthetic/` — **SYNTHETIC — NOT ARCHAEOLOGICAL EVIDENCE**; never counted, never gated, never annotated or promoted ([`docs/SYNTHETIC_DATASET.md`](docs/SYNTHETIC_DATASET.md)) |
| Training ready | **false** — blocked by `src/dataset/readiness.py` (gates G1–G11) |
| Annotations | **0** — annotation tool, evidence-based reasoning, expert pilot (six Keezhadi close-ups) ready ([`docs/ANNOTATION_GUIDE.md`](docs/ANNOTATION_GUIDE.md)). Pilot opened 2026-09-24: no human or expert input yet; 107/109 flagged "REVIEW REQUIRED — possible reproduction / duplicate inscription" (unconfirmed); per-sherd questions in [`docs/PILOT_ANNOTATION_CHECKLIST.md`](docs/PILOT_ANNOTATION_CHECKLIST.md) ([`docs/MILESTONE_8_PILOT_RESULTS.md`](docs/MILESTONE_8_PILOT_RESULTS.md)) |
| Label promotion | built, dry-run by default, reversible; **0 promotions** ([`docs/MILESTONE_8_REPORT.md`](docs/MILESTONE_8_REPORT.md)) |
| Tests | see `python -m pytest tests/ -q` (final count in [`docs/FINAL_ENGINEERING_STATUS.md`](docs/FINAL_ENGINEERING_STATUS.md)) |

No archaeological dataset has been fabricated. A synthetic pottery corpus used as research data would
produce a model that is confident and baseless — the exact failure this project exists to avoid. The
synthetic engineering dataset of Milestone 9 is therefore kept apart in code: it validates the
pipeline, it cannot pass the training gate, and nothing trained on it is a model of Tamil-Brahmi,
graffiti or any archaeological category.

---

## Run it

```powershell
.\scripts\setup.ps1                 # once (add -Cpu for CPU-only); Linux: scripts/setup.sh
.\scripts\start_app.ps1             # http://localhost:8501  (analysis page + annotation tool)
python -m src.inference analyze photo.jpg     # the same analysis on the command line
python -m src.workflow status                 # every stage, raw data -> evaluation, and the next step
```
Guides: [`USER_GUIDE`](docs/USER_GUIDE.md) · [`ARCHITECTURE`](docs/ARCHITECTURE.md) ·
[`ANNOTATION_GUIDE`](docs/ANNOTATION_GUIDE.md) · [`DATASET_POLICY`](docs/DATASET_POLICY.md) ·
[`MODEL_CARD`](docs/MODEL_CARD.md) · [`REPRODUCIBILITY`](docs/REPRODUCIBILITY.md) ·
[`LIMITATIONS`](docs/LIMITATIONS.md) · [`DEPLOYMENT`](docs/DEPLOYMENT.md).

## Quickstart

```bash
cd V:\ADM\early-tamil-pottery-ai

# 1. Isolate the environment (recommended - the machine's global Python has 188 packages)
python -m venv .venv
.venv\Scripts\activate

# 2. GPU users: install CUDA torch FIRST, before anything pulls in the CPU wheel.
#    Already done in this project's .venv (torch 2.14.0+cu126, RTX 4050 detected).
#    Check the right CUDA tag for your driver at pytorch.org.
pip install torch torchvision --index-url https://download.pytorch.org/whl/cu126

# 3. Dependencies
pip install -r requirements.txt -r requirements-dev.txt

# 4. Verify
python scripts/check_env.py
python -m pytest tests/ -q
```

### Dataset commands

```bash
python -m src.dataset rules                       # list all validation rules
python -m src.dataset validate <file>             # validate .jsonl / .csv / .json
python -m src.dataset ingest   <file> --commit    # default is a dry run
python -m src.dataset audit                       # what is in the dataset
python -m src.dataset readiness                   # may training proceed? (no)
python -m src.dataset convert  in.jsonl out.csv   # CSV <-> JSONL, lossless
python -m src.dataset stats                       # artifacts, images, classes, splits, readiness
python -m src.dataset split                       # artifact-level split manifest (refused: no data)
```

### Acquisition commands

```bash
python -m src.acquisition rules                   # licence allow-list, blocked sources, A1-A9
python -m src.acquisition plan configs/acquisition/milestone6_wikimedia_commons.yaml           # dry run
python -m src.acquisition plan configs/acquisition/milestone6_wikimedia_commons.yaml --commit  # acquire
python -m src.acquisition registry                # what has been acquired, by licence and scope
```

### Annotation and reasoning commands

```bash
streamlit run app/main.py                         # the application (7 pages; annotation is append-only)
python -m src.annotation validate                 # rules N1-N15 + knowledge base K1-K5
python -m src.annotation summary                  # per-artifact status, disagreements
python -m src.annotation quality                  # technical quality vs archaeological usability
python -m src.reasoning analyze <artifact_id>     # evidence-based identification / reading / age
python -m src.annotation pilot                    # Milestone 8 expert pilot progress
python -m src.annotation agreement                # inter-annotator agreement (never resolves)
python -m src.annotation promote --pilot          # DRY RUN of expert-label promotion
python -m src.annotation promote --execute --approve <digest> --approver <id>   # human-approved write
python -m src.annotation promote --revert <promotion_id>                       # reversal (dry run)
python -m src.knowledge status                    # reference verification (R1, S01, S03)
python -m src.knowledge claim-report              # per claim: publication, status, verifier (R3/R5 unresolved)
python -m src.knowledge verify ... [--commit]     # record a human check (dry run by default)
python -m src.annotation handoff                  # blank pilot worksheets + verification checklist
python -m src.knowledge import-checklist <csv> [--commit]   # import a filled checklist (all-or-nothing)
```

### Training and evaluation commands

```bash
python -m src.training device                     # CUDA / GPU / AMP report
python -m src.training config                     # validated training configuration
python -m src.training train                      # gate first; exit 3 "Training blocked" today
python -m src.evaluation evaluate --checkpoint P  # "NO REAL DATA — EVALUATION BLOCKED" today
```

### Synthetic engineering commands (Milestone 9 — SYNTHETIC, NOT ARCHAEOLOGICAL EVIDENCE)

```bash
python -m src.synthetic generate [--force]        # data/synthetic/: 1,000 objects, 2,202 images (deterministic)
python -m src.synthetic stats | verify            # counts, fingerprint; 14 integrity/separation/reproducibility checks
python -m src.training train --dataset synthetic  # "SYNTHETIC TRAINING — NOT ARCHAEOLOGICAL MODEL EVALUATION"
python -m src.evaluation evaluate --dataset synthetic --checkpoint models/synthetic/checkpoints/<run>/best.pt
python -m src.synthetic robustness --checkpoint <best.pt>   # blur, exposure, noise, JPEG, rotation, scale, occlusion, background
python -m src.synthetic ocr-benchmark             # "Synthetic glyph recognition benchmark" (not transcription)
python -m src.inference serve --synthetic-checkpoint latest # applied to synthetic images only
```

### Preprocessing commands

```bash
python -m src.preprocessing checks                # list the P1-P8 checks
python -m src.preprocessing inspect <image|dir>   # report only, writes nothing
python -m src.preprocessing run <image|dir> --out DIR
```

Deterministic, and it refuses to write anywhere under `data/raw`.

Exit codes: `0` success, `1` validation failure, `2` usage error.

`check_env.py` installs nothing; it reports what is present, whether CUDA is usable, whether the
schema is valid, and how much data exists.

---

## Layout

```
early-tamil-pottery-ai/
├── data/
│   ├── raw/                  images, as received          (git-ignored)
│   ├── interim/              intermediate products        (git-ignored)
│   ├── processed/            model-ready data             (git-ignored)
│   ├── external/             third-party datasets, e.g. character sets for OCR
│   │                         pretraining — kept strictly separate from our pottery data
│   └── metadata/
│       ├── README.md         ← every field, explained
│       ├── records.jsonl     research image records (30, all unlabelled)
│       ├── acquisition/      provenance registry, dataset manifests, ingested batches
│       ├── splits/           split manifests (tracked; none yet)
│       ├── annotations/      append-only annotation store (created on first save)
│       ├── promotions/       promotion audit log (created on first promotion)
│       └── schema/
│           ├── image_record.schema.json    ← the contract
│           └── _example_record.json        ← fictitious structural example
├── knowledge/                referenced knowledge base (references, sites, scripts, published readings)
│   └── verification/         human reference-verification registry (empty)
├── src/
│   ├── dataset/              ingestion, validation, loader, splits, sampling, stats, gate
│   ├── preprocessing/        loader, transforms, quality, pipeline
│   ├── acquisition/          licence policy, Commons adapter, provenance, acquisition pipeline
│   ├── annotation/           annotation rules, store, resolution, pilot, agreement, promotion
│   ├── reasoning/            deterministic evidence-based analysis (engine, inputs, CLI)
│   ├── dating/               signed-year chronology (no year 0), evidence-based age ranges
│   ├── translation/          interpretation: "no translation established" unless sourced
│   ├── knowledge/            knowledge-base loader/validator, reference verification
│   ├── training/             config, augmentation, model, engine, checkpoints, experiments
│   ├── evaluation/           metrics, artifact aggregation, blocked reports
│   ├── classification/  detection/  ocr/
│   ├── translation/     dating/     knowledge/
├── app/                      Streamlit application: main.py, analyze.py, annotate.py, views/, ui/
├── configs/project.yaml      chronology, classes, splits, integrity gates
├── configs/training.yaml     model, optimiser, augmentation, runtime (untuned defaults)
├── configs/acquisition/      curated acquisition plans (no licences: those are read from the source)
├── scripts/check_env.py
├── tests/
│   ├── fixtures/             SYNTHETIC test data — never research data
│   │   └── images/           26 generated patterns, not photographs
│   ├── test_schema.py        test_validation.py
│   ├── test_conversion.py    test_ingest_audit_readiness.py
│   ├── test_preprocessing.py test_dataset_layer.py
│   ├── test_readiness_gates.py
│   └── test_training_framework.py  test_evaluation_metrics.py
├── notebooks/
├── models/                   (git-ignored)
└── docs/
    ├── CHRONOLOGICAL_SCOPE.md   chronology + references to verify
    ├── DATA_INVENTORY.md        what data exists and how to get more
    ├── SPLIT_METHODOLOGY.md     leakage prevention + the 15 validation rules
    ├── MILESTONE_1_REPORT.md
    ├── MILESTONE_2_REPORT.md
    ├── MILESTONE_3_REPORT.md
    ├── DATA_SOURCE_AUDIT.md     where defensible data can come from, and on what terms
    ├── MILESTONE_4_REPORT.md    source audit (research only)
    ├── DATASET_SPLIT.md         the artifact-level split algorithm
    ├── TRAINING_FRAMEWORK.md    training, augmentation, gates, evaluation, reproducibility
    ├── MILESTONE_5_REPORT.md
    ├── DATA_ACQUISITION.md      acquisition procedure, policy A1-A9, provenance
    ├── PUBLIC_DATASET_AUDIT.md  every source searched, accepted and rejected, with reasons
    ├── MILESTONE_6_REPORT.md
    ├── ANNOTATION_GUIDE.md      what to label and what not to
    ├── ARCHAEOLOGICAL_REASONING.md  evidence hierarchy, dating, confidence, translation limits
    ├── MILESTONE_7_REPORT.md
    ├── MILESTONE_8_REPORT.md    expert pilot, agreement, verification, promotion
    ├── PILOT_HANDOFF.md         brief for the expert, the annotator and the reference verifier
    ├── MILESTONE_8_PILOT_RESULTS.md  first processing run of the six-artifact pilot
    ├── PILOT_ANNOTATION_CHECKLIST.md one-page question list per pilot sherd
    └── NEXT_DATA_ACQUISITION.md      fastest legitimate path to 5 and 20 artifacts per class
```

Data files are git-ignored; **the metadata describing them is committed**, so the dataset is
reproducible by anyone who can legitimately obtain the images.

---

## Design rules

These are enforced in the schema, the config and the tests — not left to good intentions.

**1. Splits are grouped by physical artifact, never by image.**
Every photograph of one sherd lands in one split. With few objects and many near-duplicate views,
image-level splitting produces a high accuracy figure that means nothing. Enforced by
`split.group_key: artifact_id`; see [`docs/SPLIT_METHODOLOGY.md`](docs/SPLIT_METHODOLOGY.md).

**2. Missing information is explicit and typed.**
`unknown` (exists, undetermined), `not_available` (not recorded by the source), `not_applicable`
(field does not apply). Empty strings are rejected by the schema. Nothing is inferred to fill a gap.

**3. Every claim carries its provenance.**
`label_source` records who assigned a label; `dating_basis` records *why* a date is claimed;
`verification_status` records whether a human has checked the record against its source.
Records below `verified_against_source` cannot surface in the UI as evidence.

**4. Uncertainty is a first-class value.**
`uncertain` is an available label for both `script_type` and `inscription_present`. An annotator is
never forced to guess. `alternative_readings` exists so competing readings are shown rather than
one being invented.

**5. No date is hard-coded.**
The chronological scope lives in `configs/project.yaml` with citations attached. The earliest date
of Tamil-Brahmi is **contested**; the config records competing positions and the system reports the
disagreement rather than resolving it. See
[`docs/CHRONOLOGICAL_SCOPE.md`](docs/CHRONOLOGICAL_SCOPE.md).

**6. Training is gated, not merely discouraged.**
`assert_training_ready()` raises until real data exists, passes validation, is split by
artifact without leakage, carries `research_usable = yes` for every training image, and clears
the per-class artifact threshold (gates G1–G11). It has no relaxing parameter and only
evaluates the canonical dataset, so fixtures cannot satisfy it. `python -m src.training train`
calls it before anything else.

**7. Raw images are never modified.**
Preprocessing opens sources read-only and raises `RawImmutabilityError` on any attempt to
write under `data/raw`. Output is deterministic, and every processed image carries a
sidecar with its source hash, transform log and provenance.

**8. Image quality is not archaeology.**
Quality metrics describe the photograph, never the object. The disclaimer is embedded in
the metrics themselves, and a test forbids any field named for authenticity, date or script
from appearing in the quality block.

**9. Nothing is fabricated.**
No invented sites, inscriptions, translations, dates, catalogue numbers or publications. The
references currently on file are **drafted and unverified**, and are marked as such until a human
checks them against the physical publications.

---

## Milestones

| # | Milestone | Status |
|---|---|---|
| 1 | Project structure, environment, dataset schema | ✅ **complete** |
| 2 | Dataset ingestion and validation | ✅ **complete** — tooling built and tested; ingestion of real data blocked |
| 3 | Preprocessing pipeline | ✅ **complete** — deterministic, tested on synthetic fixtures |
| 4 | Research data acquisition & source audit | ✅ **complete** — no data acquired; permission request is the next action |
| 5 | Dataset & training framework | ✅ **complete** — loader, splits, gates, trainer, metrics; never run on data |
| 6 | Public dataset acquisition | ✅ **complete** — 30 research + 15 supporting images, all openly licensed, none labelled |
| 7 | Annotation + archaeological reasoning layer | ✅ **complete** — annotation UI, multi-annotator store, evidence-based reasoning; 0 annotations |
| 8 | Expert annotation pilot + verification + reversible promotion | ✅ **complete** — workflow built; awaiting an expert; 0 expert labels, 0 verified references |
| 9 | Synthetic dataset + full ML pipeline validation | ✅ **complete** — isolated synthetic data; pipeline validated end to end; real training still blocked ([`docs/MILESTONE_9_REPORT.md`](docs/MILESTONE_9_REPORT.md)) |
| — | Classifier training *(originally M4)* | blocked on authorised data |
| — | Evaluation and error analysis *(originally M5)* | infrastructure built; blocked on data |
| — | Inscription-region detection *(originally M6)* | blocked |
| — | Character recognition *(originally M7)* | blocked |
| — | Transcription + transliteration *(originally M8)* | blocked |
| — | Translation *(originally M9)* | blocked |
| — | Chronological reasoning engine *(originally M10)* | partly unblocked (structure) |
| — | Knowledge base + retrieval *(originally M11)* | partly unblocked (structure) |
| — | Streamlit integration *(originally M12)* | shell buildable; must not display fabricated results |
| — | End-to-end testing *(originally M13)* | blocked |

Milestones are not skipped to make the UI look finished. Remaining milestones keep their
original numbers in brackets because code comments and earlier reports refer to them.

---

## Environment

Verified on this machine, 2026-09-23:

| | |
|---|---|
| Python | 3.13.7 (3.10 also available) |
| GPU | NVIDIA RTX 4050 Laptop, 6 GiB |
| torch | `2.14.0+cu126` in `.venv` — **CUDA available: True** |
| `.venv` | fully provisioned; all 686 tests run from it |

Use `.venv\Scripts\python.exe`, not the global interpreter. The dataset layer needs only
the standard library plus `jsonschema` and `PyYAML`; preprocessing adds Pillow and NumPy.
Measured: one ResNet18 training step at 224 px, batch 16, fp16 autocast peaks at 383 MiB of
GPU memory with the backbone unfrozen (random tensors; see `docs/TRAINING_FRAMEWORK.md` §2).
