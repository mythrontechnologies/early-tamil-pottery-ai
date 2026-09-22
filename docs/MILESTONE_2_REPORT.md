# Milestone 2 — Completion Report

**Date:** 2026-09-22
**Scope:** dataset ingestion and validation
**Status:** complete. No model trained. No research data fabricated, scraped or downloaded.

---

## 1. What was implemented

The schema is now executable. `src/dataset/` is a self-contained layer that a real
archaeological batch can be handed to on the day one exists.

| Module | Responsibility |
|---|---|
| `src/dataset/schema.py` | Loads the JSON Schema and `configs/project.yaml`. Derives field order, field kinds and enum values **from the schema itself**, so nothing in the package hard-codes a field list and the two cannot drift apart. |
| `src/dataset/validation.py` | `E1` schema layer + `R1`–`R15` cross-field layer + `E2`–`E5` engineering checks. Reports; never repairs. |
| `src/dataset/convert.py` | Lossless, deterministic CSV ⇄ JSONL. |
| `src/dataset/ingest.py` | The nine-stage pipeline. All-or-nothing. |
| `src/dataset/audit.py` | Dataset statistics, with a hard separation between research data and fixtures. |
| `src/dataset/readiness.py` | Machine-readable training gate. Fails closed. |
| `src/dataset/__main__.py` | CLI. Forces UTF-8 output so Tamil text does not crash a cp1252 console. |

Dependencies added: **none**. The layer runs on the standard library plus `jsonschema`
and `PyYAML`, both already required by Milestone 1. `pandas` was deliberately not used —
stdlib `csv` gives exact control over quoting and line endings, which determinism needs.

## 2. Validation rules

Two layers, kept visibly distinct.

### `R1`–`R15` — from `docs/SPLIT_METHODOLOGY.md` §4

Project methodology and archaeological reasoning agreed in Milestone 1.

| Rule | Check | Severity |
|---|---|---|
| R1 | `image_id` unique across the dataset | error |
| R2 | `image_path` resolves to an existing file | error |
| R3 | all records of one artifact share one split | error |
| R4 | one photograph is not claimed by two artifacts | error |
| R5 | `inscription_present=no` ⟹ `script_type=none` | error |
| R6 | `script_type=none` ⟹ reading fields are `not_applicable` | error |
| R7 | `script_type=other_script` ⟹ `script_type_other_detail` names it | error |
| R8 | `dating_lower_year` ≤ `dating_upper_year` | error |
| R9 | a numeric date requires a `dating_source` | error |
| R10 | stratigraphic dating requires `context_reliability=excavated_stratified` | error |
| R11 | `redistributable≠yes` blocks export (`--export`) | error on export |
| R12 | `split=excluded` requires a reason | error |
| R13 | `inscription_regions` lie within the image | error |
| R14 | unverified project annotation in the test split | warning |
| R15 | recommended fields absent rather than sentinel-filled | warning |

### `E1`–`E5` — engineering checks added in Milestone 2

Data hygiene and file-system facts. **None is an archaeological claim.** The separate
namespace exists so that no one later mistakes an engineering convenience for domain truth.

| Rule | Check | Severity |
|---|---|---|
| E1 | record conforms to the JSON Schema | error |
| E2 | recorded `image_sha256` matches the file on disk | error |
| E3 | `image_path` is relative, POSIX-style, no `..` traversal | error |
| E4 | `schema_version` major version is compatible | error |
| E5 | duplicate photograph *within* one artifact | warning |

`E1` is where the brief's "invalid sentinel combinations, empty strings, year-zero errors,
unsupported view values, missing required fields, schema-invalid records" are caught — the
schema already forbids them, so re-implementing those checks by hand would have created a
second source of truth that could disagree with the first.

**Skipped ≠ passed.** When the data root does not exist, R2 and E2 are reported as
`SKIPPED` in the summary and `images_checked` is `false` in the JSON output.

`--strict` promotes warnings to failures. `--export` enables R11.

## 3. Ingestion architecture

```
input (.json / .jsonl / .csv)
   -> parse                 parse failure rejects the batch; nothing partial is kept
   -> merge context         existing records are loaded so R1/R3/R4 see the whole dataset
   -> schema validation     E1
   -> cross-field           R1-R15, E2-E5
   -> image existence       R2   (or reported as skipped)
   -> SHA-256 verification  E2   (--verify-hashes)
   -> artifact grouping     R3, R4, E5
   -> dataset report        audit over the merged set
   -> ACCEPTED / REJECTED
```

Three properties are enforced rather than intended:

1. **Never repairs.** No sentinel is filled in, no type coerced, no spelling normalised,
   no bad row dropped. `test_never_repairs_a_record` asserts a missing field stays missing
   through a committed ingest.
2. **All-or-nothing.** One invalid record rejects the batch and nothing is written. A
   partially-ingested batch would leave the dataset in a state nobody reviewed.
3. **Dry run by default.** Writing requires `--commit`.

The merge step matters: a batch that is valid alone can still be invalid against the
existing dataset (a re-used `image_id`, a photograph already filed under another artifact).
Validating the batch in isolation would miss exactly the leakage R1/R3/R4 exist to catch.

## 4. CSV ⇄ JSONL

Both round trips are the identity, verified on every valid fixture:

- `JSONL → CSV → JSONL` — records compare equal
- `CSV → JSONL → CSV` — files compare **byte-identical**

Encoding contract (full table in `data/metadata/README.md` §3):

| JSON | CSV |
|---|---|
| key absent | empty cell |
| `null` (int field) | `null` token |
| `[]` | `[]` token |
| enum array | `a;b` |
| free-text array | compact JSON |
| region array | compact JSON, keys sorted |

Two decisions worth recording:

- **Empty cell means "absent", not "empty string".** The schema forbids empty strings, so
  a blank cell has exactly one possible meaning. `null` and `[]` therefore need literal
  tokens, which is what keeps *absent*, *null* and *empty list* three distinct states
  across a round trip.
- **`alternative_readings` is JSON-encoded, not semicolon-joined.** This **changes the
  Milestone 1 draft convention**, which specified semicolons for both array fields.
  `dating_basis` holds enum values that cannot contain a semicolon, so joining is safe
  there. `alternative_readings` holds free text that can — and a competing epigraphic
  reading containing a semicolon would have been silently cut in half on the round trip.
  `data/metadata/README.md` §3 has been updated; a test asserts the behaviour.

Output is UTF-8 without BOM, `\n` line endings, columns in schema order. Reading accepts a
BOM because spreadsheets add one.

## 5. CLI

```bash
python -m src.dataset validate  <file> [--data-root P] [--no-images] [--verify-hashes]
                                       [--export] [--strict] [--json]
python -m src.dataset ingest    <file> [--commit] [--no-merge] [--destination P] [...]
python -m src.dataset audit     [--records P] [--json]
python -m src.dataset readiness [--records P] [--data-root P] [--out P] [--json]
python -m src.dataset convert   <in> <out>
python -m src.dataset rules
```

Exit codes: `0` success, `1` validation/ingestion failure, `2` usage or I/O error — so
these compose in a shell script or CI job.

A small but real fix: the CLI forces UTF-8 on stdout/stderr. Windows consoles default to
cp1252, which cannot encode Tamil; printing a record containing it raised
`UnicodeEncodeError` mid-report. Since Tamil text will be routine in this dataset, a
report that dies halfway through is worse than one with replacement characters.

## 6. Audit

`python -m src.dataset audit` reports every count the brief asks for: total records,
unique artifacts, unique image hashes, breakdowns by `script_type`, `inscription_present`,
`site`, `label_source`, `verification_status` and `split`, records carrying transcription,
transliteration, translation, dating bounds, dating basis, dating source, publication,
hash and regions, plus validation failures.

Two additions that are more useful than the raw record counts:

- **`artifacts_by_script_type`** — the count that determines whether a split is viable.
  Twenty photographs of one sherd is one artifact's worth of evidence, not twenty.
- **`photos_per_artifact_max`** — makes over-representation of a single object visible.

**Fixtures are never counted as research data.** Any source other than
`data/metadata/records.jsonl` prints:

```
!!  SOURCE IS NOT THE RESEARCH DATASET.
!!  These counts describe test fixtures or an ad-hoc file.
```

The real dataset prints `REAL DATASET: 0 records`.

## 7. Readiness gate

`python -m src.dataset readiness` writes `data/metadata/readiness.json`:

```json
{
  "research_data_present": false,
  "record_count": 0,
  "unique_artifacts": 0,
  "validation_status": "PASS",
  "training_ready": false,
  "reason": "No real archaeological images are currently available",
  "image_files_present": 0,
  "min_artifacts_per_class_required": 20,
  "blockers": [
    "data/metadata/records.jsonl does not exist - no records have been ingested",
    "See docs/DATA_INVENTORY.md for acquisition routes"
  ]
}
```

The gate fails closed: any error reading the dataset reports *not ready*. It checks four
things — records exist, images exist on disk, validation passes, and each class has at
least `min_artifacts_per_class_for_holdout` (20, from `configs/project.yaml`) **artifacts**.

**Enforcement.** Every training entry point from Milestone 4 onward must open with:

```python
from src.dataset.readiness import assert_training_ready
assert_training_ready()     # raises NotTrainingReadyError until real data exists
```

A test asserts this raises today, and another asserts that a validating fixture set still
cannot make it pass.

## 8. Fixtures

24 files under `tests/fixtures/`, generated by `tests/fixtures/_generate.py` from one base
record so each invalid fixture carries exactly one defect and a failure points at one rule.

Quarantine rules, stated in `tests/fixtures/README.md` and enforced in code:

- never under `data/` — a test asserts the path relationship;
- every fixture carries a `FIXTURE` marker — a test asserts it on every file;
- identifiers are `FIXTURE_SITE_A`, not real Tamil Nadu sites; transcriptions are
  `FIXTURE_TRANSCRIPTION_PLACEHOLDER`, not Tamil-Brahmi readings; dates are labelled
  placeholders. A fixture must not be mistakable for a genuine record if it escapes.

The one piece of real Tamil is *சோதனை* ("test") in the conversion fixture, present only to
prove UTF-8 survives the CSV round trip. It is not a transcription or translation.

## 9. Tests

**164 passing**, up from 19.

| File | Tests | Covers |
|---|---:|---|
| `test_schema.py` | 19 | schema contract (Milestone 1) |
| `test_validation.py` | 78 | R1–R15, E1–E5, valid records, determinism, non-mutation |
| `test_conversion.py` | 33 | round trips, encoding rules, determinism, loud failure |
| `test_ingest_audit_readiness.py` | 34 | pipeline, audit, gate, research-data hygiene |

Beyond per-rule coverage, the suite asserts some properties worth naming:

- `test_validator_never_mutates_input` — validation reports, never repairs
- `test_findings_are_deterministic` — same input, same output, same order
- `test_skipped_checks_are_reported_not_passed`
- `test_sentinel_hashes_do_not_collide` — two records with `image_sha256="not_available"`
  are not the same photograph
- `test_fixtures_cannot_make_the_gate_pass`
- `test_every_fixture_is_marked_synthetic`
- `test_research_dataset_is_empty` / `test_no_images_under_data`

## 10. Current dataset status

| | |
|---|---|
| Images in `data/raw/` | **0** |
| Records in `data/metadata/records.jsonl` | **0** (file does not exist) |
| Unique artifacts | **0** |
| Verified references | **0** |
| Models | none |
| Training ready | **false** |

Nothing was fabricated, scraped or downloaded. No web search for pottery images was made.

## 11. Known limitations

1. **The validator has never seen a real record.** Every rule is exercised against
   synthetic fixtures. Fixtures test the code; they cannot test whether the *rules* match
   archaeological practice. That needs a domain expert and a real batch.
2. **R10 may be too strict.** It requires `context_reliability=excavated_stratified` for
   any stratigraphy-based date. If published practice admits stratigraphic dating from
   `excavated_unstratified` contexts in some circumstances, this will produce false
   errors. Flagged for expert review rather than loosened on a guess.
3. **R15's recommended-field list is an engineering judgement**, not a domain standard. It
   reflects what seems useful for research reuse and should be revisited with an
   archaeologist.
4. **No `refit_group` field.** `docs/SPLIT_METHODOLOGY.md` §3 raises physically refitting
   sherds as a grouping question; the schema has no field for it yet. Currently handled by
   assigning the same `artifact_id`. Worth revisiting when real material appears.
5. **Image existence is checked; image *validity* is not.** A zero-byte file named `.jpg`
   passes R2. Decoding belongs in Milestone 3 preprocessing.
6. **No split-assignment tool yet.** The methodology and the `R3` check exist, but nothing
   *assigns* splits. That is Milestone 2's natural sequel and is blocked on having
   artifacts to split.
7. **`.venv` is incomplete.** It has CUDA torch but not `jsonschema`, `PyYAML` or `pytest`,
   so the suite currently runs against the global interpreter. See §13.

## 12. Exact blocker for ML training

> **There are zero real archaeological images.**

Training is blocked in code by `assert_training_ready()`, which currently raises. It will
keep raising until all four conditions hold:

| Condition | Now | Needed |
|---|---|---|
| Records ingested | 0 | ≥ 1 batch passing validation |
| Image files on disk | 0 | one per record |
| Validation status | PASS (vacuously) | PASS over real records |
| Artifacts per class | 0 | ≥ 20 each for `tamil_brahmi`, `graffiti`, `none`, `uncertain` |

The last row is the real bar: **≥ 20 distinct artifacts per class, ~150–200 artifacts
total**. Below that, a 15% test split holds single-digit counts per class and a quoted
accuracy figure is noise — the gate then directs the project to grouped k-fold reporting
instead.

This is a research-access problem, not an engineering one. `docs/DATA_INVENTORY.md` §3
sets out six acquisition routes. The non-data dependency remains an epigraphist: without
one, `label_source` cannot rise above `project_annotation_unverified`, and any metric
measures agreement with an untrained annotator rather than with the field.

## 13. Environment note

`.venv` holds the CUDA build (`torch 2.14.0+cu126`, `torch.cuda.is_available() == True`,
RTX 4050 detected) but not `jsonschema`, `PyYAML` or `pytest`. The suite was run against
the global interpreter, which has them. To make `.venv` the working environment:

```powershell
.venv\Scripts\activate
pip install -r requirements.txt -r requirements-dev.txt
python -m pytest tests/ -q
```

No packages were installed during this milestone.

## 14. Recommended next step

**Milestone 3 — preprocessing.** Buildable now against any images, tuned later on real
sherds. The split-assignment tool (§11.6) is the other candidate, but it needs artifacts
to split, so preprocessing is the better use of the blocked period.
