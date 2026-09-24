# Next Data Acquisition: the Fastest Legitimate Path to a Trainable Dataset

**Date:** 2026-09-24
**Status:** plan. No data has been acquired under it. No training gate, class list or
threshold is changed by it.

## 1. Where we are

| | Count |
|---|---|
| Research artifacts / images | 17 / 30 (Wikimedia Commons, CC BY / CC BY-SA) |
| Labelled artifacts per class (`tamil_brahmi`, `graffiti`, `none`, `uncertain`) | 0 / 0 / 0 / 0 |
| Pilot artifacts that could become labels | at most 6. 107 and 109 may be reproductions (P10), which would leave **4**, and every one shows a marked sherd, so the `none` class gets nothing |
| Supporting images (`data/external/`, not training data) | 15 |

The gates stay as configured (`configs/project.yaml`):

| Target | Rule | Minimum labelled artifacts |
|---|---|---|
| **1. Grouped cross-validation** | `fallback_strategy: grouped_k_fold`, `k_folds: 5`: every class needs at least one artifact per fold | **≥ 5 per class × 4 = 20** |
| **2. 70/15/15 holdout** | `min_artifacts_per_class_for_holdout: 20` | **≥ 20 per class × 4 = 80** |

Counted in **artifacts**, not photographs. Extra photographs of one artifact help the model but
never raise the count. They stay under one `artifact_id` and one split (R3, G6).

## 2. What does *not* count

- Photographs or plates from copyrighted books and reports (S01, S03, S04, S06–S12, S14),
  and unauthorised mirrors (Internet Archive, Scribd, pdfcoffee). They may be **cited** as
  references for an expert's reading. They are never training images.
- Labels inferred from a site name, a caption, an image's appearance or any AI output.
- Commons captions or site date ranges used as object dates.
- Duplicated or augmented copies counted as new artifacts. Reproductions or replicas of an
  object already in the set (see 107/109) are not new artifacts either.
- GAN or synthetic images (e.g. Zenodo "BrahmiGAN").

## 3. Sources, in priority order

### Priority 1: openly licensed archaeological photographs (fast; few labels)

| Lead | Licence | Likely classes | Action |
|---|---|---|---|
| Remaining Keezhadi site-museum photos by Rajeshodayanchal (Commons, 18 acquired; category S15 has 174 files) | CC BY-SA 4.0 | graffiti, tamil_brahmi, uncertain | Screen the remaining files for **individually photographed** sherds. Acquire through the existing pipeline (`src.acquisition`) with provenance. Expert labels only. |
| "Adichanallur archaeological site 01–27" (Perumalism) | CC BY-SA 4.0 | none (unmarked urns), if an expert confirms | Currently rejected as near-duplicates of acquired pits. Acquire only the files showing a **different** vessel; group by vessel. |
| Pattanam (Kerala) and Tissamaharama (Sri Lanka) sherds already in `data/external/` | CC BY-SA 4.0 | tamil_brahmi (per source) | Out of the Tamil Nadu scope. They may enter a **separately flagged** comparison set only by an explicit scope decision. Not in the primary training set. |

Realistic yield: perhaps 5–15 usable **marked** sherds. Almost nothing for `none`.

### Priority 2: museum photographs with explicit reuse permission (medium; the main route to Target 2)

| Holder | What to ask for |
|---|---|
| Keeladi Heritage Museum / TNSDA (S17) | Photography permission for displayed inscribed and **uninscribed** sherds, plus the **catalogue numbers** that link each object to its publication (this also settles 107/109). |
| Government Museum, Chennai (S18) | Permission to photograph or reuse images of inscribed sherds already credited in S01. |
| TNSDA documentation database behind S01 (S02) | Research access to catalogue photographs **with** context fields and published readings. This is the single largest legitimate pool: 1,109 Tamiḻi and 2,622 graffiti sherds from Kodumanal alone, per S01. |
| Tamil University / Pondicherry University Kodumanal collections (S21) | Access to TU-PU sherds (551 Tamiḻi + 598 graffiti per S01) for photography under an agreement. |

A written permission is recorded in the acquisition provenance (`rights_notes`, `research_usable`,
`redistributable`) **before** any image is stored. `DATA_SOURCE_AUDIT.md` has the rights matrix.

### Priority 3: expert-labelled objects

The fastest way to 20 artifacts per class is **one expert working with one collection**.
Published catalogue readings, cited by page or plate, can support the expert's annotation
(`source_information` tier plus expert review). The photograph must still be one the project has
the right to use.

### Priority 4: controlled photographs of uninscribed sherds (`none` class)

`none` is the class that open sources will not supply. Photographs of pottery seldom show
the side without marks, and captions rarely say "no mark".

- Ask the holding institution for a **controlled session**: the same camera, lighting and
  scale bar for inscribed and uninscribed sherds from the same excavated contexts. The
  classifier then cannot learn "museum lighting = inscription".
- Photograph **both faces**. An expert records `inscription_present = no` only after examining the
  whole visible surface.
- Target: ≥ 20 uninscribed sherds from the same sites and wares as the inscribed ones.

### Priority 5: several photographs per artifact

Useful for model robustness: other faces, angles, raking light. Each set is **one artifact
id** and one split. The count per class does not change.

## 4. Fastest path to each target

| Step | Target 1 (20 artifacts) | Target 2 (80 artifacts) |
|---|---|---|
| 1 | Finish the six-artifact pilot (human + expert); resolve 107/109 | same |
| 2 | Screen and acquire more CC-licensed individual-sherd photos (Priority 1) | same |
| 3 | One permission request: Keeladi museum or TNSDA, for ~10 inscribed + ~10 uninscribed objects with catalogue numbers | Research-access agreement for S02 / S21 |
| 4 | Expert annotates, including `uncertain` where honest | Expert (or a small panel) annotates; agreement measured on an overlapping subset of ≥ 30 items, where κ becomes interpretable |
| 5 | Promotion dry run → human approval | same |
| 6 | `python -m src.dataset readiness`: grouped 5-fold if every class ≥ 5 | holdout if every class ≥ 20 |

**Limiting factor:** Target 1 is plausible with a handful of open photographs plus **one**
institutional permission. Target 2 is not reachable from open sources and needs an
institutional agreement.

## 5. Class balance watch

| Class | Likely sources | Risk |
|---|---|---|
| `tamil_brahmi` | S02 / S21 collections, museum permission | Readings must come from the expert or a cited publication |
| `graffiti` | Same collections (graffiti outnumber Tamiḻi in S01) | Distinguishing graffiti from script is itself the expert question |
| `none` | Controlled photography only | Hardest to obtain; highest priority for the permission request |
| `uncertain` | Arises naturally from honest annotation | Must not become a dumping ground: the expert states **why** |

## 6. Not changed

The gates G1–G11, the four classes, `min_artifacts_per_class_for_holdout: 20`, grouped 5-fold
fallback, split protection, and the provenance requirements.
