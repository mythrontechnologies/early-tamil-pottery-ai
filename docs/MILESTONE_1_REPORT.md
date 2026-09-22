# Milestone 1 — Completion Report

**Date:** 2026-09-22
**Scope:** project structure, environment, dataset schema
**Status:** complete. No model trained, no data fabricated.

---

## 1. Pre-flight inspection

| Check | Result |
|---|---|
| Existing project or repository? | **None.** `V:\ADM` is not a git repository and contains no prior code for this project. |
| Existing pottery/epigraphy code or data? | **None.** Filename search for `*pottery*`, `*brahmi*`, `*tamil*`, `*sherd*` returned 0 matches. |
| Unrelated contents of `V:\ADM` | Coursework PDFs/PPTX; `VIDURA_THE_WARNING` (animation pre-production); `simulator` (JS/Python app). **None modified.** |
| Python | 3.13.7 primary, 3.10 also installed; pip 25.2 |
| GPU | NVIDIA RTX 4050 Laptop, 6 GiB |
| torch | 2.9.1**+cpu** — CPU-only build despite the GPU being present |
| Missing | streamlit |

Full survey: [`DATA_INVENTORY.md`](DATA_INVENTORY.md).

## 2. Deliverables

| Brief §18 requirement | Where |
|---|---|
| 1. Inspect existing project | §1 above; `DATA_INVENTORY.md` §1 |
| 2. Determine whether code exists | §1 — none |
| 3. Identify Python environment | §1; `scripts/check_env.py` |
| 4. Create project structure | `../README.md` §Layout |
| 5. Create dataset schema | `../data/metadata/schema/image_record.schema.json` |
| 6. Dataset README explaining every field | `../data/metadata/README.md` |
| 7. Identify available data | `DATA_INVENTORY.md` — **zero** |
| 8. Do not fabricate a dataset | Honoured. Only a flagged fictitious structural example exists. |
| 9. Do not train | Honoured. |
| 10. Report | this file |

## 3. The schema

59 fields, 10 required, JSON Schema draft 2020-12, validated. Field-by-field documentation in
[`../data/metadata/README.md`](../data/metadata/README.md).

Design decisions worth recording:

| Decision | Rationale |
|---|---|
| **One record per photograph, `artifact_id` as split key** | Multiple views of one sherd are near-duplicates. Grouping is the only defence against a flattering, meaningless accuracy figure. |
| **Three sentinels, not one** | `unknown` / `not_available` / `not_applicable` mean different things. Collapsing them destroys auditability later. Empty strings rejected outright. |
| **`dating_text` verbatim *and* signed integer bounds** | Converting "c. 2nd century BCE" to `(-200, -101)` silently discards the hedge. The verbatim text is the record; the integers are a derived convenience for range-overlap evaluation. |
| **`dating_basis` is mandatory and non-empty** | A date with no recorded basis is precisely what the brief forbids. The schema makes it unrepresentable. |
| **`label_source` separate from `label_confidence`** | *Who* assigned a label determines whether it is ground truth; *how sure they were* is a different axis. |
| **`uncertain` is a legitimate label** | For both `script_type` and `inscription_present`. Annotators are never forced to guess. The `graffiti`/`tamil_brahmi` boundary is contested in the scholarship for some marks, not merely visually hard. |
| **`image_sha256`** | Catches the same photograph entering twice under different ids — a leakage route `artifact_id` grouping alone misses. |
| **`view` distinguishes `rubbing`/`drawing` from photographs** | Scholarly renderings are high-contrast and idealised. A model trained on them does not transfer to worn sherds. |
| **`redistributable`, with `unknown` ⇒ no** | Most excavation-report plates and museum photographs are rights-reserved. |
| **`additionalProperties: false`** | A misspelled field fails loudly instead of vanishing. |
| **CSV for annotators, JSONL as canonical** | Archaeologists work in spreadsheets. The conversion contract is specified in the dataset README §3. |

## 4. Chronology

Per brief §1, **no date range is hard-coded in source.** The scope lives in
`configs/project.yaml` under `chronology:`, and records **four competing positions** on the
earliest Tamil-Brahmi rather than selecting one. Fallback policy is
`union_of_cited_positions` — never a midpoint, never a bare percentage.

⚠️ **Every reference currently on file is unverified.** They were drafted from an AI assistant's
general knowledge and have not been checked against the physical publications. All carry
`verification_status: unverified`, which the Milestone 11 retrieval layer will filter on, so they
cannot reach a user as evidence. [`CHRONOLOGICAL_SCOPE.md`](CHRONOLOGICAL_SCOPE.md) §7 sets out
the verification procedure; §8 lists the questions only a domain expert can answer.

## 5. Tests

19 passing. They assert the schema is valid, and that it encodes the project's integrity rules:
split key required, rights fields required, label provenance required, year 0 rejected, empty
strings rejected, `dating_basis` non-empty, `uncertain` available, config split proportions sum to
1, chronology not presented as verified, competing positions recorded.

These are contract tests. If someone later relaxes one of these rules, a test fails.

## 6. Known gaps

1. **No data.** The blocking dependency. It is a research-access problem, not an engineering one —
   [`DATA_INVENTORY.md`](DATA_INVENTORY.md) §3.
2. **No domain expert.** Without one, `label_source` cannot exceed `project_annotation_unverified`
   and metrics measure agreement with an untrained annotator.
3. **No verified references.** See §4.
4. **CUDA torch not installed.** CPU-only build present; fine through Milestone 3.
5. **Cross-field validation rules are specified but not implemented** —
   [`SPLIT_METHODOLOGY.md`](SPLIT_METHODOLOGY.md) §4 lists 15 rules for Milestone 2.

## 7. Recommended next step

**Milestone 2, tooling first.** Build and test the ingestion + validation layer against synthetic
*fixtures* (clearly marked, kept in `tests/fixtures/`, never in `data/`). That makes the schema
executable, encodes the 15 cross-field rules, and means real data can be ingested the day it
arrives rather than starting the pipeline then.

Milestone 2 ingestion of real data remains blocked until images exist.
