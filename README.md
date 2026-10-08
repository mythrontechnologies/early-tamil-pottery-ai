# Early Tamil Pottery AI

AI-assisted analysis of Early Historic Tamil Nadu pottery, with emphasis on Tamil-Brahmi/Tamili
inscriptions and graffiti.

> **This system provides AI-assisted archaeological analysis and is not a substitute for expert
> epigraphic or archaeological assessment.**

**Status: engineering complete; blocked on real evidence.** Everything engineering can honestly
complete is complete: licence-gated acquisition, validation, preprocessing, a dual-annotation
workflow with expert adjudication (append-only, tamper-evident), agreement and field-level
disagreement reports, reversible promotion, a knowledge base with a human verification workflow
and software pre-checks, evidence-based reasoning, an inference API/CLI/HTTP service, a Streamlit
application, gated evaluation (classification, detection, OCR, robustness) and a gated training
pipeline. What remains is **real archaeological evidence**: expert annotation, a human check of the
references, enough labelled artifacts per class, then training. The project holds **34 openly
licensed photographs (21 artifacts)**, **none carries an expert label**, and there is **no trained
archaeological model**. The analysis tool therefore answers most questions with "Insufficient
evidence", which is the correct answer. See
[`docs/FINAL_ENGINEERING_STATUS.md`](docs/FINAL_ENGINEERING_STATUS.md) and
[`docs/MILESTONE_11_REPORT.md`](docs/MILESTONE_11_REPORT.md).

---

## At a glance

| Question | Answer |
|---|---|
| **What does the system do?** | Given a photograph of a pottery sherd, it reports image quality, the human evidence recorded for that object (who said what), an evidence-based script / reading / meaning / date assessment with explicit uncertainty, and — separately, never as evidence — any AI observation. It also runs the whole annotation → agreement → adjudication → promotion → training → evaluation workflow. |
| **What works now?** | Everything above, on real photographs, with the honest result "Insufficient evidence" because no expert has annotated yet. The full AI pipeline (classify → detect → segment → OCR → interpret → reason) works end to end in **Synthetic Demonstration** mode. |
| **What is synthetic mode?** | A procedurally generated engineering dataset (1,000 objects, 2,202 images; invented glyphs, invented rules) used only to prove the software works. Every synthetic output says **SYNTHETIC — NOT ARCHAEOLOGICAL EVIDENCE**; synthetic models never see a real photograph and real mode never runs one. |
| **What is real mode?** | The default. Real photographs from openly licensed sources, with provenance and SHA-256; human annotations in provenance tiers (project / expert / adjudication); AI output only ever as an `ai_prediction`. |
| **What is blocked, and why?** | Real training and real evaluation: the readiness gate (G1-G11) requires expert-promoted labels in all four classes (`tamil_brahmi`, `graffiti`, `none`, `uncertain`), ≥ 5 artifacts per class for grouped CV (≥ 20 for holdout), and a verified artifact-level split. Today there are 0 labels. Reference *verification* needs a named human; software has pre-checked where each claim is. |
| **What must a human do next?** | Annotate the six pilot sherds (project annotator + expert, independently); confirm the pre-checked references; obtain photographs of uninscribed sherds. Exact steps: [Annotate real data](#annotate-real-data) and [`docs/FINAL_ENGINEERING_STATUS.md`](docs/FINAL_ENGINEERING_STATUS.md) §E. |

An LLM-generated explanation is not evidence and is never presented as such.

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

---

## Current state

| | |
|---|---|
| Research images | **34** (21 artifacts), Wikimedia Commons, CC BY / CC BY-SA, provenance and SHA-256 for every file — see [`docs/PUBLIC_DATASET_AUDIT.md`](docs/PUBLIC_DATASET_AUDIT.md) |
| Expert-labelled images | **0** — every record has `script_type = unknown` pending annotation |
| Supporting images | 15 in `data/external/` (out-of-region pottery, Tamil-Brahmi rock inscriptions) |
| Verified references | **0** — only a named human verifies. Milestone 11 **pre-checked** R1, S01, S03 by software: bibliographic details confirmed for all three; S01 3/3 and S03 5/6 claims found at exact pages in authorised / open-access copies (one S03 discrepancy recorded); R1's claim needs a library copy (`python -m src.knowledge prechecks`) |
| Models | **no archaeological model.** Training pipeline complete (AMP, resume, fingerprints). Milestone 9 validated it end to end on a separate SYNTHETIC engineering dataset; the resulting models live in `models/synthetic/`, are marked SYNTHETIC ONLY, and are refused wherever an archaeological model is expected ([`docs/SYNTHETIC_TRAINING.md`](docs/SYNTHETIC_TRAINING.md)). Milestone 10 added a complete SYNTHETIC demonstration pipeline (detector, glyph OCR, synthetic reasoning) that runs on synthetic images only ([`docs/SYNTHETIC_END_TO_END.md`](docs/SYNTHETIC_END_TO_END.md)) |
| Synthetic engineering data | 1,000 generated objects / 2,202 images in `data/synthetic/` — **SYNTHETIC — NOT ARCHAEOLOGICAL EVIDENCE**; never counted, never gated, never annotated or promoted ([`docs/SYNTHETIC_DATASET.md`](docs/SYNTHETIC_DATASET.md)) |
| Training ready | **false** — blocked by `src/dataset/readiness.py` (gates G1–G11) |
| Annotations | **0** — annotation tool (with expert adjudication, glyph regions, worksheets and a queue), evidence-based reasoning, expert pilot (six Keezhadi close-ups) ready ([`docs/ANNOTATION_GUIDE.md`](docs/ANNOTATION_GUIDE.md)). Pilot opened 2026-09-24: no human or expert input yet; 107/109 flagged "REVIEW REQUIRED — possible reproduction / duplicate inscription" (unconfirmed); per-sherd questions in [`docs/PILOT_ANNOTATION_CHECKLIST.md`](docs/PILOT_ANNOTATION_CHECKLIST.md) ([`docs/MILESTONE_8_PILOT_RESULTS.md`](docs/MILESTONE_8_PILOT_RESULTS.md)) |
| Label promotion | built, dry-run by default, reversible; **0 promotions** ([`docs/MILESTONE_8_REPORT.md`](docs/MILESTONE_8_REPORT.md)) |
| Tests / static checks | `python -m pytest tests/ -q`; `ruff` and `mypy` clean (counts in [`docs/FINAL_ENGINEERING_STATUS.md`](docs/FINAL_ENGINEERING_STATUS.md)) |

No archaeological dataset has been fabricated. A synthetic pottery corpus used as research data would
produce a model that is confident and baseless — the exact failure this project exists to avoid. The
synthetic engineering dataset of Milestone 9 is therefore kept apart in code: it validates the
pipeline, it cannot pass the training gate, and nothing trained on it is a model of Tamil-Brahmi,
graffiti or any archaeological category.

---

## Run it

```powershell
.\scripts\setup.ps1                 # once (add -Cpu for CPU-only); Linux: scripts/setup.sh
.\scripts\start_app.ps1             # http://localhost:8501  (all seven pages)
.\scripts\start_api.ps1             # http://127.0.0.1:8765  (GET /health, POST /analyze)
python -m src.inference analyze photo.jpg     # the same analysis on the command line
python -m src.workflow status                 # every stage, raw data -> evaluation, and the next step
python -m src.annotation queue                # every artifact's annotation state and next human step
```
Guides: [`USER_GUIDE`](docs/USER_GUIDE.md) · [`ARCHITECTURE`](docs/ARCHITECTURE.md) ·
[`ANNOTATION_GUIDE`](docs/ANNOTATION_GUIDE.md) · [`DATASET_POLICY`](docs/DATASET_POLICY.md) ·
[`MODEL_CARD`](docs/MODEL_CARD.md) · [`EVALUATION`](docs/EVALUATION.md) ·
[`REPRODUCIBILITY`](docs/REPRODUCIBILITY.md) · [`LIMITATIONS`](docs/LIMITATIONS.md) ·
[`DEPLOYMENT`](docs/DEPLOYMENT.md) · [`TROUBLESHOOTING`](docs/TROUBLESHOOTING.md).

## Annotate real data

1. `python -m src.annotation queue` — what needs annotating; pilot artifacts first.
2. **App:** `streamlit run app/main.py` → Annotation. Set your id and role in the sidebar (project annotator or
   expert, with qualification), choose the artifact, zoom, mark regions (one `character` region per sign if you
   read signs), answer only what the photograph supports (`uncertain` / `unknown` are good answers), save.
   Saving appends; nothing is overwritten. One-page brief: [`docs/PILOT_ANNOTATION_CHECKLIST.md`](docs/PILOT_ANNOTATION_CHECKLIST.md).
   **Offline:** `python -m src.annotation handoff --all` writes blank worksheets to `outputs/pilot_handoff/`;
   fill them in Excel, then `python -m src.annotation import-worksheet <file.csv> --role project|expert`
   (dry run) and add `--commit` when it says the records are valid.
3. Project annotator and expert work **independently**; then `python -m src.annotation disagreements`. An expert
   resolves a disagreement by recording an **adjudication** (Annotation → sidebar "I am ADJUDICATING").
4. `python -m src.annotation promote --pilot` (dry run) → a human approves with
   `--execute --approve <digest> --approver <id>`. Every promotion is logged and reversible.

## Train a real model once the gates pass

```powershell
python -m src.dataset near-duplicates      # no near-copy photographs across artifacts
python -m src.dataset split                # artifact-level, seeded, fingerprinted manifest (refuses when data are insufficient)
python -m src.dataset readiness            # G1-G11 must all PASS
python -m src.training train               # runs only if they do; otherwise exit 3, nothing trained
python -m src.evaluation evaluate --checkpoint models\checkpoints\<run>\best.pt --robustness
python -m src.evaluation reproducibility   # commit, environment, data / split / config fingerprints
```
Nothing here can be forced: the gate has no bypass flag and evaluates only the canonical dataset.

## Quickstart

```bash
git clone https://github.com/mythrontechnologies/early-tamil-pottery-ai
cd early-tamil-pottery-ai

# 1. Isolate the environment (recommended - the machine's global Python has 188 packages)
python -m venv .venv
.venv\Scripts\activate

# 2. Install torch for your hardware FIRST, before anything pulls in another wheel.
#    Check the right CUDA tag for your driver at pytorch.org; CPU: .../whl/cpu
pip install torch torchvision --index-url https://download.pytorch.org/whl/cu126

# 3. Dependencies
pip install -r requirements.txt -r requirements-dev.txt

# 4. Verify
python scripts/check_env.py
python -m pytest tests/ -q
python -m pytest -m browser    # opt-in: real app in Chromium (needs playwright-cli + the synthetic dataset)
# Exact reproduction of a recorded result: pip install -r requirements-lock.txt (see its header)
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
python -m src.annotation validate                 # rules N1-N20 + knowledge base K1-K8
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
python -m src.knowledge prechecks                 # SOFTWARE pre-checks: where each claim was found (not verification)
python -m src.knowledge verify-from-precheck <PC-id> --verifier <id> --role project_member --date YYYY-MM-DD --i-opened-the-source [--commit]
python -m src.annotation queue                    # every artifact: state + next human step
python -m src.annotation disagreements [--all]    # field by field, who said what (never resolved here)
python -m src.annotation export                   # current annotations, tier-labelled (JSONL + CSV)
python -m src.annotation handoff --all            # blank worksheets for every research photograph
python -m src.annotation import-worksheet <csv> --role project|expert [--revise] [--commit]
```

### Training and evaluation commands

```bash
python -m src.training device                     # CUDA / GPU / AMP report
python -m src.training config                     # validated training configuration
python -m src.training train                      # gate first; exit 3 "Training blocked" today
python -m src.evaluation evaluate --checkpoint P [--robustness]  # "NO REAL DATA — EVALUATION BLOCKED" today
python -m src.evaluation detection --predictions regions.jsonl   # vs expert-promoted regions (blocked today)
python -m src.evaluation ocr --predictions readings.jsonl        # vs expert-promoted readings (blocked today)
python -m src.dataset near-duplicates             # near-copy photographs across artifacts (split leakage)
```

### Quality checks

```bash
python -m pytest tests/ -q                        # unit, integration, UI (AppTest), static checks
python -m pytest -m browser                       # opt-in: every page in Chromium at phone/tablet/desktop width, text 100-200 %
python -m ruff check src app scripts tests
python -m mypy                                    # configured in pyproject.toml (src, app, scripts)
python -m src.synthetic verify                    # 14 synthetic integrity / separation / reproducibility checks
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

### Synthetic end-to-end demonstration (Milestone 10 — SYNTHETIC, NOT ARCHAEOLOGICAL EVIDENCE)

```bash
python -m src.synthetic calibrate                 # temperature scaling on the synthetic VAL split
python -m src.synthetic train-vision              # region detector, glyph-centre segmenter, glyph classifier
python -m src.synthetic demo                      # load → preprocess → classify → detect → segment → OCR → interpret → reason
python -m src.inference synthetic --image data/synthetic/images/SYNTH-A0007-V1.jpg [--json]  # exit 3 for a real photo
python -m src.inference serve --synthetic         # POST /synthetic/analyze (synthetic images only; 422 otherwise)
python -m src.evaluation synthetic                # "SYNTHETIC ENGINEERING BENCHMARK": classification, detection, OCR, calibration, robustness
```
In the app: Analysis → *Data mode* → **Synthetic Demonstration** (Real Research is the default).
See [`docs/SYNTHETIC_END_TO_END.md`](docs/SYNTHETIC_END_TO_END.md).

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
│   └── verification/         human reference-verification registry (empty) + software pre-checks (not verification)
├── src/
│   ├── dataset/              ingestion, validation, loader, splits, sampling, stats, gate
│   ├── preprocessing/        loader, transforms, quality, pipeline
│   ├── acquisition/          licence policy, Commons adapter, provenance, acquisition pipeline
│   ├── annotation/           annotation rules, store, resolution (incl. adjudication), pilot, agreement,
│   │                         promotion, worksheets / queue / disagreement report / export
│   ├── reasoning/            deterministic evidence-based analysis (engine, inputs, CLI)
│   ├── dating/               signed-year chronology (no year 0), evidence-based age ranges
│   ├── translation/          interpretation: "no translation established" unless sourced
│   ├── knowledge/            knowledge-base loader/validator, reference verification, software pre-checks
│   ├── training/             config, augmentation, model, engine, checkpoints, experiments
│   ├── evaluation/           metrics, calibration, OCR, detection / error / robustness tasks, perturbations
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
    ├── NEXT_DATA_ACQUISITION.md      fastest legitimate path to 5 and 20 artifacts per class
    ├── MILESTONE_9_REPORT.md / SYNTHETIC_*.md   synthetic engineering dataset and pipeline
    ├── MILESTONE_10_REPORT.md        synthetic end-to-end demonstration
    ├── MILESTONE_11_REPORT.md        pre-checks, adjudication, worksheets, leakage guard, real evaluation, typing
    ├── EVALUATION.md                 evidence tiers and every metric
    └── TROUBLESHOOTING.md
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
| 10 | Synthetic end-to-end AI demonstration | ✅ **complete** — calibrated classifier, region detector, glyph segmentation + OCR, synthetic interpretation and chronology reasoning, CLI/API/UI with live pipeline replay; SYNTHETIC only; real training still blocked ([`docs/MILESTONE_10_REPORT.md`](docs/MILESTONE_10_REPORT.md)) |
| 11 | Reference pre-checks, annotation completion, leakage guard, real evaluation | ✅ **complete** — R1/S01/S03 pre-checked (0 verified: a human must); +4 licensed artifacts (21/34); adjudication, glyph regions, worksheets, queue; near-duplicate split guard; gated detection / OCR / robustness evaluation; mypy clean ([`docs/MILESTONE_11_REPORT.md`](docs/MILESTONE_11_REPORT.md)) |
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

Verified on this machine, 2026-10-08:

| | |
|---|---|
| Python | 3.13.7 (the code targets ≥ 3.10) |
| GPU | NVIDIA RTX 4050 Laptop, 6 GiB (optional: everything runs on CPU, training and the synthetic demonstration more slowly) |
| torch | `2.14.0+cu126` in `.venv` — **CUDA available: True** |
| Exact versions | `requirements-lock.txt` (`pip freeze` of the tested `.venv`) |

Use `.venv\Scripts\python.exe`, not the global interpreter. The dataset layer needs only
the standard library plus `jsonschema` and `PyYAML`; preprocessing adds Pillow and NumPy.
Measured: one ResNet18 training step at 224 px, batch 16, fp16 autocast peaks at 383 MiB of
GPU memory with the backbone unfrozen (random tensors; see `docs/TRAINING_FRAMEWORK.md` §2).
