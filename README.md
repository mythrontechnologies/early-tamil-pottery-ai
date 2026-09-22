# Early Tamil Pottery AI

AI-assisted analysis of Early Historic Tamil Nadu pottery, with emphasis on Tamil-Brahmi/Tamili
inscriptions and graffiti.

> **This system provides AI-assisted archaeological analysis and is not a substitute for expert
> epigraphic or archaeological assessment.**

**Status: Milestone 1 of 13 complete — project structure, environment, dataset schema.**
There is **no data and no trained model.** The system cannot analyse an image yet, and no part of
it should be presented as if it could.

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
| Images | **0** — see [`docs/DATA_INVENTORY.md`](docs/DATA_INVENTORY.md) |
| Records | **0** |
| Verified references | **0** — see [`docs/CHRONOLOGICAL_SCOPE.md`](docs/CHRONOLOGICAL_SCOPE.md) |
| Models | none |
| Tests | 19 passing (schema contract) |

No dataset has been fabricated. A synthetic pottery corpus would produce a model that is confident
and baseless — the exact failure this project exists to avoid.

---

## Quickstart

```bash
cd V:\ADM\early-tamil-pottery-ai

# 1. Isolate the environment (recommended - the machine's global Python has 188 packages)
python -m venv .venv
.venv\Scripts\activate

# 2. GPU users: install CUDA torch FIRST (an RTX 4050 is present on this machine,
#    but the global torch is the CPU-only build). Check the right tag at pytorch.org.
pip install torch torchvision --index-url https://download.pytorch.org/whl/cu126

# 3. Dependencies
pip install -r requirements.txt -r requirements-dev.txt

# 4. Verify
python scripts/check_env.py
python -m pytest tests/ -q
```

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
│       └── schema/
│           ├── image_record.schema.json    ← the contract
│           └── _example_record.json        ← fictitious structural example
├── knowledge/                structured KB (Milestone 11) — dirs only, empty
├── src/
│   ├── preprocessing/  classification/  detection/  ocr/
│   ├── translation/    dating/          knowledge/  evaluation/
├── app/                      Streamlit UI (Milestone 12) — not built
├── configs/project.yaml      chronology, splits, integrity gates
├── scripts/check_env.py
├── tests/test_schema.py
├── notebooks/
├── models/                   (git-ignored)
└── docs/
    ├── CHRONOLOGICAL_SCOPE.md   chronology + references to verify
    ├── DATA_INVENTORY.md        what data exists and how to get more
    ├── SPLIT_METHODOLOGY.md     leakage prevention
    └── MILESTONE_1_REPORT.md
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

**6. Nothing is fabricated.**
No invented sites, inscriptions, translations, dates, catalogue numbers or publications. The
references currently on file are **drafted and unverified**, and are marked as such until a human
checks them against the physical publications.

---

## Milestones

| # | Milestone | Status |
|---|---|---|
| 1 | Project structure, environment, dataset schema | ✅ **complete** |
| 2 | Dataset ingestion and validation | next — tooling buildable now, ingestion blocked on data |
| 3 | Preprocessing pipeline | |
| 4 | Tamil-Brahmi / graffiti / no-inscription classifier | blocked on data |
| 5 | Evaluation and error analysis | blocked |
| 6 | Inscription-region detection | blocked |
| 7 | Character recognition | blocked |
| 8 | Transcription + transliteration | blocked |
| 9 | Translation | blocked |
| 10 | Chronological reasoning engine | partly unblocked (structure) |
| 11 | Knowledge base + retrieval | partly unblocked (structure) |
| 12 | Streamlit integration | shell buildable; must not display fabricated results |
| 13 | End-to-end testing | blocked |

Milestones are not skipped to make the UI look finished.

---

## Environment

Verified on this machine, 2026-09-22:

| | |
|---|---|
| Python | 3.13.7 (3.10 also available) |
| GPU | NVIDIA RTX 4050 Laptop, 6 GiB |
| torch | 2.9.1**+cpu** — CPU-only build; reinstall from the CUDA index to use the GPU |
| Present globally | numpy, pandas, opencv, pillow, scikit-learn, matplotlib, jsonschema, pytest, PyYAML, transformers |
| Missing | **streamlit** |

6 GiB of VRAM comfortably fits ResNet18 / EfficientNet-B0 / ConvNeXt-Tiny at 224 px. CPU is fine
through Milestone 3.
