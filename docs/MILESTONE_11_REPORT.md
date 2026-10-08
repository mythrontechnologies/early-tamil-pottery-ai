# Milestone 11 Report: Reference Pre-checks, Annotation Completion, Leakage Guard, Real Evaluation, Typed Codebase

**Date:** 2026-10-08 · **Status:** engineering complete for everything that does not need a human expert.
Real training remains **blocked**, correctly: there are still no expert labels.

```text
Research data:     21 artifacts / 34 images (was 17 / 30); all unlabelled; provenance 34/34; raw files unchanged
References:        R1, S01, S03 bibliographically confirmed and pre-checked by software; 0 verified (only a human can)
Annotations:       0 (no human or expert input exists yet); the full dual-annotation + adjudication workflow is built
Training:          BLOCKED (G7-G11)      Evaluation: BLOCKED (exit 3), detection/OCR scoring BLOCKED (no expert truth)
Static checks:     ruff clean; mypy clean (127 files, newly configured)
Tests:             981 passed (+ 3 browser tests passed); was 928
```

## 1. Audit (start of milestone)

| Check | Result |
|---|---|
| `pytest` | 928 passed, 2 browser tests deselected (5 min 12 s) |
| `ruff` | clean |
| `src.annotation validate / integrity`, `src.knowledge validate`, `src.dataset audit / readiness`, `src.workflow status` | all PASS; stages 1-5 PASS, 6-11 WAITING / BLOCKED |
| Gaps found | `MILESTONE_10_REPORT.md` linked but missing; no adjudication; worksheets could not be imported; no glyph-level regions; no near-duplicate leakage check; no real-data detection/OCR/robustness scoring; no type checker; stale counts in README and requirements |

## 2. Reference verification (R1, S01, S03)

A software agent cannot verify a reference: the project's rules (V1-V10) require a named human, and this
milestone keeps that rule. What a software agent *can* do is find each claim in a copy the project may
consult and record exactly where. That is now a separate, schema-checked layer:
`knowledge/verification/source_prechecks.json` (`checked_by: software_agent`, `effect: none`, rules PC1-PC8,
`src/knowledge/precheck.py`). It never changes a status; `verify-from-precheck` lets the human verifier
confirm a claim in about a minute.

| Ref | Source consulted | Bibliographic check | Claims |
|---|---|---|---|
| **R1** Mahadevan 2003 | BnF catalogue record | matches (HOS 62; Cre-A + Harvard; 2003; ISBN 0-674-01227-5) | 1 claim **not checkable**: no authorised copy online; needs a library copy |
| **S01** Rajan & Sivanantham 2026 | Tamil Digital Library full copy (Tamil Virtual Academy) | matches (imprint: Publication No. 366, ISBN 978-81-977842-3-1, 2026) | 3/3 found as stated: Vol. I p. 80 (Kodumanal counts; *visāki*), Vol. II pp. xi-xiii and p. 1075 (Tamiḻi / Damili) |
| **S03** Ramakrishna et al. 2018 | the journal's own open-access PDF + publisher's table of contents | matches (Heritage 6: 30-72; the publisher's Archive page alone says 2019) | 4 found as stated, 1 partially (the claim also cites R6), **1 discrepancy**: the Fig. 17 reading's interpretation was transcribed as "not stated", but the article calls it the name of an individual (p. 54, p. 63) and prints the reading three ways |
| R5 (placeholder) | DAI issue contents | the candidate work (Falk 2014, ZAAK 6, from p. 45) exists | stays **unresolved**: whether R5 means it is a scholar's question |

Knowledge-base changes: exact locators for every S01 and S03 claim; the Fig. 17 entry corrected to record all
three printed spellings and the printed interpretation (still `transcribed_unverified`); notes on R1, S01, S03
and the R5 candidate. **Verified references: 0**, as before; the human step is now small.

## 3. Real data acquisition

Second screening of Wikimedia Commons (every file of the Keezhadi site, Keezhadi Museum, Sivakalai, Korkai,
Adichanallur and Government Museum (Chennai) categories, plus 31 full-text searches). Screening asked only
"does the photograph show an individual pottery object from Tamil Nadu that the project may use?"; it never
assigned a class.

* The Keezhadi category is exhausted: its individually photographed marked sherds are the six pilot sherds
  already held. The rest is trenches, coins, beads, iron tools, posters and in-situ urns.
* **Acquired:** 4 individually photographed Adichanallur vessels at the Government Museum, Chennai, by Sailko,
  **CC BY 3.0**, own work, through the licence-gated pipeline (policy A1-A9 passed; licences read from the
  Commons API; SHA-256 recorded; provenance complete). Plan:
  `configs/acquisition/milestone11_wikimedia_commons.yaml`; dataset `wmc_tamil_nadu_pottery_m11`.
* **Rejected:** Adichanallur in-situ pits 01-27 (several overlapping urns per photo, one buried face: grouping
  and leakage risk, no "none" judgement possible); Ambari (Assam) rouletted sherds (outside Tamil Nadu); gallery
  overviews; posters and panels (they reproduce the museum's own graphics).
* The uploader's caption date ("1000 ac ca.") is not copied into any date field.

Result: **21 artifacts / 34 images**, all `script_type = unknown`, queued for annotation. The pre-existing 30 raw
files were hash-checked before and after: byte-identical. The `none` class still has no candidate an annotator
could judge from both faces; that needs controlled photography (`NEXT_DATA_ACQUISITION.md`).

## 4. Annotation system

| Added | Where |
|---|---|
| Schema 1.2.0 (backwards compatible): `adjudication` block, `character` (glyph) regions with `sign_index` / `sign_reading`, `reading_completeness` | `data/metadata/schema/annotation.schema.json` |
| Rules **N18** (adjudication: reviewed, qualified expert; resolves ≥ 2 current non-AI annotations of the same artifact; `insufficient_evidence` leaves the script `uncertain`), **N19** (glyph regions), **N20** (completeness agrees with the reading) | `src/annotation/validate.py` |
| Resolution status **`adjudicated`**: the adjudication decides; the resolved annotations stay current and visible; a later annotation makes it stale (`disputed` again) | `src/annotation/resolve.py` |
| Promotion of adjudicated labels (P1-P10, source = the adjudicating annotation only); glyph regions kept as `other` + note | `src/annotation/promote.py` |
| `queue`, `disagreements`, `export`, `import-worksheet` (all-or-nothing, dry run first), `handoff --all` | `src/annotation/worksheet.py`, CLI |
| UI: Queue tab, adjudication mode (experts only), glyph region marking, reading completeness, a legend separating source metadata / project annotation / expert annotation / AI draft / promoted ground truth, field-level disagreement table | `app/annotate.py` |

## 5. Dataset splitting

New **near-duplicate leakage guard** (`src/dataset/near_duplicates.py`): a 64-bit difference hash of every
photograph; a pair across different artifacts within 6 bits blocks the split until a human merges the artifacts
or records them as distinct (`split.near_duplicate_exceptions`). Featureless images are reported, never matched.
`python -m src.dataset near-duplicates`: 34 photographs, **0 pairs**. No split was made: the data are insufficient.

## 6. Evaluation

`src/evaluation/tasks.py` (pure functions) and the gated CLI: IoU-matched detection precision / recall / F1 at
0.5 and 0.75; OCR CER / WER / exact-reading accuracy with a failure analysis (illegible references excluded);
classification error analysis (confident errors first, accuracy by confidence bin); robustness under lighting,
blur, noise, compression, rotation, scale, crop and occlusion (`src/evaluation/perturbations.py`, now shared with
the synthetic suite). Every report states its evidence tier. `evaluate --robustness`, `detection` and `ocr` are
BLOCKED (exit 3) until expert ground truth exists. See [`EVALUATION.md`](EVALUATION.md).

## 7. Reasoning and transcription

Reading completeness reaches the reasoning: "Partial transcription: some signs lost or doubtful", "Fragmentary:
only isolated signs read", "Inscription illegible: no transcription". Lost signs are never supplied; a partial
reading gets no translation unless a source gives one; a personal name has no literal translation. An
adjudicated label is used as the reasoning basis and the preserved disagreement is stated. Chronology was
already evidence-tiered, conflict-reporting and year-0-free; unchanged.

## 8. Security

CSV formula-injection guard on every worksheet and export (`safe_cell`); decompression-bomb handling in the hash
scan; no secrets, credentials or personal account data tracked (scanned); API smoke-tested: wrong media type 415,
corrupt image 422, synthetic endpoint refuses a real photograph 422.

## 9. Code quality

mypy configured (`pyproject.toml`) and **clean over src/, app/ and scripts/ (127 files)**: 158 errors fixed,
none suppressed, including real defects (loop variables re-used with another type in promotion and in the CLIs,
an unchecked `None` path in the synthetic CLI). Perturbations moved to a neutral module; the synthetic
generator still re-renders byte-identically (`python -m src.synthetic verify`, V14). `requirements-lock.txt`
records the exact environment; mypy added to `requirements-dev.txt`; static checks run as tests.

## 10. Tests

New: `tests/test_milestone11.py` (pre-checks, adjudication, glyph regions, completeness, worksheets, queue,
disagreements, export, acquisition, near-duplicates, evaluation tasks, reading outcomes, CSV guard),
`tests/test_static.py` (ruff, mypy), four UI tests, and `tests/browser/pages.js` (every page at phone, tablet and
desktop width, text 100-200 %).

| Run (2026-10-08, final) | Result |
|---|---|
| `pytest -q` | **981 passed**, 3 browser tests deselected, 1 expected warning (928 at the start of the milestone) |
| `pytest -m browser` | **3 passed** (the new every-page probe first found 9 overflow cases at tablet / desktop width with 150-200 % text; fixed with text-relative grids and wrapping badges) |
| `ruff` / `mypy` | clean / no issues in 127 files |

## 11. Remaining human actions

1. **Verifier:** open each pre-checked page and confirm (`python -m src.knowledge prechecks`, then
   `verify-from-precheck <PC-id> --verifier <you> --role project_member --date <today> --i-opened-the-source --commit`).
   About ten minutes for S01 and S03. Record the Fig. 17 discrepancy with `--status discrepancy_found` if confirmed.
2. **Library:** check R1's position A in a physical or authorised copy of Mahadevan 2003.
3. **Scholar:** identify the works behind R3 and R5.
4. **Project annotator and expert:** annotate the six pilot sherds independently (app, or
   `python -m src.annotation handoff --all` + `import-worksheet`); an expert adjudicates disagreements.
5. **Museum / TNSDA:** controlled photography of uninscribed sherds (`none`) and catalogue numbers (107/109).
