# Data Splitting and Leakage Prevention

**Status:** specified in Milestone 1, implemented in Milestone 2.
This document is the methodology statement that must be reproduced in any write-up of this project.

---

## 1. The rule

> **Train/validation/test splits are assigned by physical artifact (`artifact_id`), never by image.**

Every photograph of a given sherd lands in exactly one split. No exceptions, including for
rubbings, drawings and composite plates of that sherd.

```
artifact_id = KDM_0041
  ├── KDM_0041__exterior__1.jpg   ┐
  ├── KDM_0041__closeup__1.jpg    ├─ all → train   (or all → val, or all → test)
  └── KDM_0041__rubbing__1.jpg    ┘
```

## 2. Why this is not optional

An archaeological photo set is close to a worst case for naive image-level splitting:

1. **Near-duplicate photographs.** Two shots of the same sherd under the same lighting are almost
   the same image. Split them across train and test and the test set measures memorisation.
2. **Small object counts.** This domain yields hundreds of *objects*, not hundreds of thousands.
   With many photographs per object, image-level splitting can put a relative of nearly every test
   image into training.
3. **The failure is invisible and flattering.** It does not crash. It produces a high accuracy
   number that will not survive contact with a new excavation — which is precisely the situation
   the prototype is meant to be useful in.

A reported accuracy from an image-level split on this kind of data is not a weak result. It is a
meaningless one.

## 3. Secondary leakage routes

`artifact_id` grouping is necessary but not sufficient. Milestone 2 also checks:

| Route | Check | Action |
|---|---|---|
| **Same photo, two ids** | `image_sha256` collision across different `artifact_id`s | Hard error. Merge the artifacts or remove the duplicate. |
| **Uncertain identity** | Annotator cannot tell whether two photos show the same sherd | Assign the **same** `artifact_id` (conservative merge) and record it in `notes`. Over-merging loses a little data; under-merging corrupts the evaluation. |
| **Joining sherds** | Fragments that physically refit into one vessel | Same `artifact_id`, or a recorded `refit_group` — decide before splitting, not after. |
| **Plate-level correlation** | All sherds from one excavation-report plate photographed together under identical conditions | Not leakage in the strict sense, but it inflates within-source similarity. Report per-site and per-source performance separately. |
| **Site-level confound** | A site whose sherds are nearly all one class | Report the per-site breakdown so a "site detector" masquerading as a script classifier is visible. |

## 4. Cross-field validation rules (Milestone 2)

JSON Schema cannot express these; the ingestion validator will.

| # | Rule | Severity |
|---|---|---|
| 1 | `image_id` unique across the dataset | error |
| 2 | Every `image_path` resolves to an existing file under `data/raw/` | error |
| 3 | All records sharing an `artifact_id` share the same `split` | error |
| 4 | Same `image_sha256` under two different `artifact_id`s | error |
| 5 | `inscription_present = no` ⟹ `script_type = none` | error |
| 6 | `script_type = none` ⟹ `transcription`, `transliteration`, `translation_*` are `not_applicable` | error |
| 7 | `script_type = other_script` ⟹ `script_type_other_detail` is not a sentinel | error |
| 8 | `dating_lower_year` ≤ `dating_upper_year` when both are non-null | error |
| 9 | Either numeric dating bound non-null ⟹ `dating_source` is not a sentinel | error |
| 10 | `dating_basis` includes `stratigraphy` ⟹ `context_reliability` ∈ {`excavated_stratified`} | error |
| 11 | `redistributable = unknown` treated as `no` for any export | error on export |
| 12 | `split = excluded` ⟹ `split_exclusion_reason` is not a sentinel | error |
| 13 | A non-empty `inscription_regions` entry lies within `image_width_px` × `image_height_px` | error when dimensions known |
| 14 | `label_source = project_annotation_unverified` present in the **test** split | warning — test labels should be source-backed |
| 15 | Recommended fields missing rather than sentinel-filled | warning |

Rule 10 deserves a note: a date cannot rest on stratigraphy if the object is a surface find or
unprovenanced, no matter what a catalogue entry asserts.

## 5. Split proportions

Provisional target, to be revisited once the real artifact count is known (Milestone 2):

| Split | Share of **artifacts** | Purpose |
|---|---|---|
| train | ~70% | model fitting |
| val | ~15% | model selection, early stopping, threshold choice |
| test | ~15% | reported once, at the end |

Constraints:

- Stratify by `script_type` **at the artifact level** so every class appears in every split.
- If the artifact count is small enough that a 15% test split contains only a handful of objects
  per class, **report grouped k-fold cross-validation instead of a single split**, and say so. A
  test set of six objects does not support a quoted accuracy figure.
- The split assignment is written into `data/metadata/records.jsonl` and committed, so results are
  reproducible. It is generated from a fixed seed recorded in `configs/project.yaml`.
- **The test split is not looked at during development.** Re-splitting after seeing test results
  invalidates them.

## 6. Reporting requirement

Any report, paper or presentation arising from this project must state:

> Splits were assigned at the level of the physical artifact rather than the photograph: all
> images of a given sherd were placed in the same partition, preventing near-duplicate views of one
> object from spanning training and evaluation. Splits were stratified by script class at the
> artifact level. Duplicate photographs were detected by file hash. [Where applicable:] Owing to
> the limited number of distinct artifacts, results are reported as grouped k-fold
> cross-validation rather than from a single held-out partition.

Also report: number of **artifacts** (not only images) per split and per class, and per-site
performance.
