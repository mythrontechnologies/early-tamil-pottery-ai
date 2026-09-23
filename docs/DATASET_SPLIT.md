# Dataset Split Algorithm

**Status:** implemented in Milestone 5 (`src/dataset/splits.py`). Tested in
`tests/test_dataset_layer.py::TestSplits` and `tests/test_readiness_gates.py`.
**Methodology it implements:** [`SPLIT_METHODOLOGY.md`](SPLIT_METHODOLOGY.md). That document
says *what* must hold. This one says *how* the code makes it hold.

Today the split command refuses to run, because there are no records:

```text
> python -m src.dataset split
SPLIT REFUSED
  - no records: there is nothing to split, and a split will not be fabricated for an empty dataset
No split manifest was written.
```

---

## 1. The invariants

For every split the code produces or accepts:

```text
train artifacts ∩ validation artifacts = ∅
train artifacts ∩ test artifacts       = ∅
validation artifacts ∩ test artifacts  = ∅
no image_sha256 appears in two partitions
no image_id appears in two partitions
every eligible artifact is in exactly one partition; every other artifact is excluded with a reason
```

The unit is `artifact_id`. `image_id` is never a split key: `verify_manifest` rejects a
manifest whose `group_key` is anything else.

## 2. Pipeline

```text
records.jsonl ──► load_dataset() ──► check_splittable() ──► make_split() ──► verify_manifest() ──► manifest.json
                  (validate, verify   (refuse or choose     (deal whole       (re-check every
                   hashes, reject)     holdout / k-fold)     artifacts)        invariant)
```

### 2.1 Load (`src/dataset/loader.py`)

The loader runs the full Milestone 2 validator (`E1`–`E5`, `R1`–`R15`) with the image root
and **SHA-256 recomputation on**, plus two loader checks:

| Code | Check |
|---|---|
| `L1` | The resolved image path stays inside `data/raw/`. Catches symlink escape, which `E3` (no `..`) cannot. |
| `L2` | `image_sha256` is a real hash, not a sentinel. Without a hash, a duplicate photograph under two ids cannot be detected. |

A record with any error is rejected whole, with every reason attached. **The splitter
refuses to run while any record is rejected.** Nothing is repaired or defaulted.

### 2.2 Preconditions (`check_splittable`)

Each of these is a refusal, and all of them are reported together:

| Condition | Why |
|---|---|
| no records | a split of nothing is not a split |
| any rejected record | a split of a partially valid dataset hides the invalid part |
| records already carry `train`/`val`/`test` | re-splitting after a test set exists invalidates results measured on it (`SPLIT_METHODOLOGY.md` §5). Use `--adopt-existing`. |
| an artifact's photographs disagree on `script_type` | the label describes the sherd, not the photograph |
| an artifact is partly eligible, partly excluded | eligibility is per artifact |
| a trainable class has **zero** artifacts | a class with no examples cannot be trained or evaluated |
| holdout with fewer than `min_artifacts_per_class_for_holdout` (20) artifacts in some class | see §4 |
| k-fold with fewer than `k` (5) artifacts in some class | every class must be able to appear in every fold |

### 2.3 Eligibility

An artifact takes part if all its records have a **trainable** label (`tamil_brahmi`,
`graffiti`, `none`, `uncertain`) and none is `split=excluded`. Otherwise it goes into the
manifest's `excluded` map with a reason:

- `held_out_label:other_script`, `held_out_label:tamil_brahmi_and_graffiti`. These labels
  are real categories. They are retained, counted and reported, and **never relabelled**
  into a trainable class.
- `split=excluded (<split_exclusion_reason>)`.

### 2.4 Assignment (`make_split`)

For each trainable class separately:

1. **Group by secondary key.** Artifacts are grouped by the values of
   `split.balance_secondary` (default `inscription_present`, `site`), read from the
   artifact's first photograph.
2. **Shuffle each group** with a seed derived by SHA-256 from `(seed, class, group key)`.
   Python's `hash()` is not used, because it is salted per process and would break
   determinism.
3. **Interleave** the groups round-robin, largest group first. Consecutive positions now
   alternate between sites, so any contiguous stretch is approximately site-balanced.
4. **Deal** the interleaved list to partitions. First, one artifact is dealt to each
   partition (largest ratio first), which guarantees every class appears in every
   partition. After that, each artifact goes to the partition furthest below its target
   share (`ratio × dealt-so-far − count`), with ties broken towards the earlier partition.

Whole artifacts are dealt. The secondary keys change only the **order** of dealing, so
secondary balance can never override artifact grouping. When a secondary group is too
small to spread evenly, it simply ends up less balanced. That is reported in the manifest
summary (`artifacts_by_site`, `artifacts_by_inscription_present` per partition), never
"fixed" by moving part of an artifact.

### 2.5 Verification

`verify_manifest(manifest, dataset)` runs after generation, again whenever a manifest is
loaded for training (gate `G11`), and again inside `partition_records`. It checks:

- the manifest's `dataset_fingerprint` equals the current dataset's (§6);
- `group_key == "artifact_id"`;
- every partition name is valid;
- every listed artifact exists, with exactly the listed images;
- no artifact is both assigned and excluded, and none is unaccounted for;
- no record's own `split` field contradicts the manifest;
- `verify_partitions`: pairwise disjointness of artifacts, image ids **and image hashes**.

`verify_partitions` is also exported on its own, so any future code that assembles
training sets differently can apply the same leakage check to what it actually uses.

## 3. Strategies

| `--strategy` | When it runs | Partitions |
|---|---|---|
| `holdout` | every class has ≥ 20 artifacts | `train` / `val` / `test` at 0.70 / 0.15 / 0.15 of **artifacts** |
| `grouped_kfold` | every class has ≥ `k` (5) artifacts | `fold_0` … `fold_4`. For fold *i*: train = all other folds, val = fold *i*. **There is no untouched test set**, and the manifest carries a warning saying so. |
| `auto` (default) | | holdout if possible, else k-fold if possible, else refuse |
| `--adopt-existing` | records already carry a complete train/val/test assignment | builds a manifest from it after full verification |

## 4. Why 20, and what kind of number it is

`min_artifacts_per_class_for_holdout: 20` was set in Milestone 1 (`configs/project.yaml`).
It is an **engineering and statistical** requirement, not an archaeological one. At a 15%
test share, 20 artifacts in a class give about 3 test artifacts for that class. Below
that, a per-class test figure is one or two sherds, and a quoted accuracy is noise. The
number says nothing about how many sherds exist, or how many a specialist needs. It should
be revisited, with a statistician, once real counts are known. The k-fold minimum of `k`
per class is a purely mechanical requirement: each class must be able to appear in each
fold.

## 5. Stratification fields, and what is deliberately absent

| Field | Status |
|---|---|
| `script_type` | **primary**, enforced per class |
| `inscription_present` | secondary, approximate |
| `site` | secondary, approximate. It also protects against a "site detector" posing as a script classifier (`SPLIT_METHODOLOGY.md` §3). |
| **period** | **not available.** The schema has no period field. A periodisation (for example, which date ranges count as "Early Historic phase I") is an archaeological decision that has not been made, and the Keeladi dates are disputed (`DATA_SOURCE_AUDIT.md` §2). Deriving a period from `dating_lower_year` would be exactly the kind of invented assumption the project forbids. When an agreed period field exists, add it to `balance_secondary`; no code change is needed. |

Any schema field can be added to `balance_secondary`. Adding many fields with few
artifacts only makes the secondary balance coarser; it never breaks grouping.

## 6. Determinism and the dataset fingerprint

- **Seed:** `split.seed` in `configs/project.yaml` (`20260922`), overridable with `--seed`,
  and recorded in the manifest.
- **Order independence:** artifacts are sorted before shuffling, so reordering
  `records.jsonl` does not change the split (tested).
- **Digest:** `SplitManifest.digest` is a SHA-256 over strategy, seed, `k`, ratios, dataset
  fingerprint, assignments and exclusions. It excludes the creation timestamp. Identical
  inputs give an identical digest (tested). A hand-edited manifest fails to load.
- **Dataset fingerprint** (`src/dataset/fingerprint.py`): a SHA-256 over the canonical JSON
  of **every field of every record**, sorted by `image_id`. Any change to the records, even
  a corrected note, produces a new fingerprint. A manifest for an older fingerprint then
  fails verification, so a model can never be trained or evaluated against a split made
  for different data. A second **image-set fingerprint** covers only
  `(image_id, artifact_id, image_sha256)`, to separate "pixels changed" from "metadata
  edited".

Manifests are written to `data/metadata/splits/split_<strategy>_<fingerprint12>_seed<seed>.json`.
That directory is tracked by git, like the rest of `data/metadata/`.

## 7. Relationship to the `split` field in records

`SPLIT_METHODOLOGY.md` §5 originally said splits would be written back into
`records.jsonl`. Milestone 5 keeps records **unmodified** and makes the **manifest** the
authoritative assignment instead:

- writing the split into records would change the dataset fingerprint the split depends on;
- a manifest can be regenerated, diffed and verified independently of the records.

The `split` field still works. `excluded` is honoured. Pre-existing `train`/`val`/`test`
values are either adopted (`--adopt-existing`) or cause a refusal. They are never silently
overwritten, and a record whose `split` contradicts the manifest fails verification.

## 8. Commands

```powershell
python -m src.dataset split                        # validate, then split (auto)
python -m src.dataset split --strategy holdout     # or grouped_kfold
python -m src.dataset split --dry-run              # print the split, write nothing
python -m src.dataset split --adopt-existing       # adopt train/val/test already in records
python -m src.dataset stats                        # counts, splits, leakage checks, readiness
```

Exit code 1 means the split was refused. The reasons are printed, and no manifest is written.
