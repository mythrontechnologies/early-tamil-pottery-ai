# Milestone 8: Expert Annotation Pilot, Evidence Verification, Reversible Label Promotion

**Date:** 2026-09-23
**Status:** complete. The workflow is built and tested. **No expert has annotated yet, no
reference has been verified, no label has been promoted, and training remains BLOCKED.**

```text
Tests:              PASS (679 passed; 569 before this milestone + 110 new)
Pilot:              READY (6 Keezhadi close-ups; 0 / 6 complete; both annotator tiers missing)
Agreement:          READY (0 pairs; nothing to measure yet)
Verification:       READY (registry empty; R1, S01, S03 unverified)
Promotion:          READY (dry run: 0 candidates; 0 promotions in the log)
Reasoning:          17/17 real artifacts -> "Insufficient evidence", confidence unknown
Training:           BLOCKED (exit 3; gates G7-G11 fail)
Real artifacts:     17 (30 images), all script_type = unknown
Expert labels:      0
```

The software is an **assistive research tool**. It keeps observed evidence, expert annotation,
project annotation, AI suggestion, published evidence and inferred interpretation apart. It
never merges them into one "truth" field.

---

## 1. Objectives

1. An expert annotation pilot for the six Keezhadi incised-sherd photographs (site photos
   105–110), **without assuming they are Tamil-Brahmi**.
2. Inter-annotator agreement (project annotator vs expert), per field, honest about sample size.
3. A controlled reference-verification workflow for R1, S01, S03 (and every other reference).
4. A reversible, audited, human-approved promotion from expert annotation to training record.
5. Preserved uncertainty: insufficient evidence, disputes and alternative readings stay visible.
6. A dating output of "estimated period / basis / confidence / important uncertainty", with the
   evidence separated into its kinds, and no date copied from a site.
7. A translation output that keeps translation apart from interpretation.
8. Only the UI changes these require.

## 2. Implementation

**Reused, not replaced:** annotation schema 1.0.0 (unchanged: it already had every field the
pilot needs, including `tamil_brahmi_and_graffiti`, regions, alternative readings, image
usability and review states), the append-only store, N1–N13, `resolve_artifact`, the
reasoning engine, the dating estimator and the translation module.

**Created**
- `src/annotation/pilot.py`: pilot definition (from config), per-annotation checklist, status.
- `src/annotation/agreement.py`: pairing, Cohen's κ, IoU, reading similarity, Jaccard, report.
- `src/annotation/promote.py`: plan (P1–P9) → dry-run report → approval → atomic write +
  audit log; plan/execute revert.
- `src/knowledge/verification.py`: verification registry, rules V1–V8 and K6, claim list,
  effective reference status.
- `src/knowledge/__main__.py`: `validate`, `claims`, `status`, `verify` (dry run unless
  `--commit`), `rules`.
- `data/metadata/schema/reference_verification.schema.json` (1.0.0).
- `knowledge/verification/README.md` (the registry itself is created on the first committed check).
- `tests/test_expert_pilot.py` (110 tests).
- This report.

**Modified**
- `src/annotation/validate.py`: rule **N14**. A cited reference may claim
  `verified_against_source` only if the registry verified it.
- `src/annotation/store.py`: passes registry-verified ids to validation (N14) by default.
- `src/annotation/__main__.py`: `pilot`, `agreement`, `promote` commands; `validate` runs N14.
- `src/reasoning/types.py`, `from_annotations.py`, `engine.py`: effective (registry) reference
  status; per-annotator dating positions; status statements; dating summary; translation vs
  interpretation in the text output.
- `app/annotate.py`: pilot filter, photo gallery, verification-status table, Pilot & agreement tab.
- `configs/project.yaml`: `annotation_pilot`, `agreement`, `verification`, `promotion` sections.
- Docs: `ANNOTATION_GUIDE.md` (§7–9), `ARCHAEOLOGICAL_REASONING.md` (§3.5–3.7, 6, 8, 9),
  `DATA_ACQUISITION.md` (§10), `README.md`.

**Not modified:** `records.jsonl`, `readiness.json`, the acquisition provenance registry, the
image-record schema, the annotation schema, the knowledge-base YAML, and every training gate,
class list and threshold.

## 3. Pilot workflow

Pilot `keezhadi_incised_sherds_m8` (`configs/project.yaml`): `WMC_KEELADI_MUS_SHERD_105` …
`_110`, one photograph each (6000 × 4000). Required tiers: `project_annotation` and
`expert_annotation`.

1. `streamlit run app/annotate.py`. "Pilot artifacts only" is on by default.
2. Each annotator works independently, sees every photograph (gallery + zoom), marks regions,
   and decides presence (`yes`/`no`/`uncertain`) and script (`tamil_brahmi`, `graffiti`,
   `tamil_brahmi_and_graffiti`, `none`, `uncertain`, `other_script`). They then record a
   reading **only if supported**, with alternatives, interpretation/inscription type,
   linguistic observations, dating evidence, references, per-photo usability, confidence, and
   (experts) the review state.
3. `python -m src.annotation pilot` reports missing tiers and unmet checklist items. The
   checklist items: presence decided, script decided, region marked if present, usability
   assessed, and expert review state set. A reading is deliberately **not** required.
4. `python -m src.annotation agreement` measures agreement (§4).
5. Disagreements go to an expert, who resolves them by revising **their own** annotation (N11
   forbids superseding anyone else's). Agreement statistics never resolve them.
6. `python -m src.annotation promote --pilot`: the dry run (§6).

The uploader's caption for these photographs dates "the Keeladi cultural deposit". The
config, the guide and a test all record that this is a site-level statement and never a
date for these objects. The reasoning layer gives the pilot sherds no date (tested).

## 4. Agreement methodology

Two raters, each a provenance tier or an annotator id. Only current, non-superseded human
annotations are compared; AI predictions can never be a rater. If a tier has two current
annotations on one artifact, that artifact is skipped as ambiguous, and the annotator ids
must be named instead.

| Field | Metric | Notes |
|---|---|---|
| inscription_present | raw agreement, confusion matrix, Cohen's κ | `unknown` excluded and counted |
| script_type | same | |
| inscription_type | same | |
| interpretation_type | same | |
| regions | best-match IoU per region of rater A; matched at IoU ≥ 0.5 | descriptive only |
| reading | exact match after NFC/whitespace/case normalisation; mean character similarity | every non-identical pair listed as a disagreement |
| dating_evidence_types | exact set match; mean Jaccard | compares the kinds of evidence, not the dates |

**Sample size.** κ is shown beside the raw counts. Below `agreement.min_items_for_kappa` (30,
an engineering convention recorded in the config, not a statistical law) it is labelled
`insufficient_sample` / **not interpretable**. The pilot has six artifacts, so its κ will
always carry that label. When chance agreement is 1 (both raters used one category
throughout), κ is **undefined**. It is not reported as 1.0.

**Agreement never resolves disagreement.** `resolves_disagreement` is always `False`. The
module is pure: no annotation, status or record changes (tested).

## 5. Reference verification workflow

A reference is verified **only for the claims a named human checked** in the physical
publication, an authorised digital copy, or the publisher's open-access version. The
registry `knowledge/verification/reference_verifications.jsonl` is append-only. Each record
holds:

- reference id and bibliographic citation (as checked);
- the claim, and its knowledge-base claim id (`python -m src.knowledge claims`: 14 claims today,
  from the published readings, site and script assertions, and the chronology positions);
- status: `verified_against_source` / `discrepancy_found` / `source_unavailable` / `unverified`;
- verifier, and a role of `project_member` or `expert` (**there is no AI role**);
- verification date (not in the future);
- page / plate / catalogue locator;
- where the copy is held, and how it was accessed;
- notes, and the record it supersedes.

A `verified_against_source` record without a verifier, role, date, locator, copy location, or
with `not_accessed`, is rejected (V3). A `discrepancy_found` status overrides verification. A
knowledge-base entry that declares itself verified without a registry record fails K6. An
annotator declaring a reference verified fails N14. The reasoning layer uses the registry's
effective status regardless of what an annotation declares. Where a reference is verified, the
output names the verified claims, because other claims citing the same work remain
unverified.

**Current state: nothing is verified.**

| Ref | Effective status | Claims relied on | Why still unverified |
|---|---|---|---|
| R1 | `bibliographic_only` | 1 (chronology position A) | No authorised copy available to the project; only an unauthorised copy was found (DATA_SOURCE_AUDIT S06). |
| S01 | `transcribed_unverified` | 3 | Read via Tamil Digital Library in Milestone 4; not yet checked by a human verifier against the volumes. |
| S03 | `transcribed_unverified` | 6 | Transcribed in Milestone 4; not yet checked by a human verifier. |

No page number, catalogue number or verification was entered on anyone's behalf. Two
existing inconsistencies were found and left unchanged. They need a human decision:
position B cites `R3`, but the knowledge base holds `R3a`; position D cites `R5`, which is not
in the knowledge base.

## 6. Promotion architecture

```text
annotation store ─► validation (N1–N14; any failure: nothing planned)
                 ─► review: resolve_artifact == expert_label (expert_reviewed experts agree)
                 ─► candidate checks P1–P9
                 ─► DRY-RUN report: field-by-field before → after, rejections with reasons,
                    dataset validation (E*/R*, hashes) of the result, plan_digest
                 ─► human approval: --execute --approve <plan_digest> --approver <id>
                    (re-planned at execution; any drift → refused)
                 ─► atomic rewrite of records.jsonl + append-only promotion_log.jsonl
```

| Check | Rejects |
|---|---|
| P1 | disputed; provisional (project-only); project disagreement; unannotated (AI ignored) |
| P2 | a source annotation that is not a current `expert_reviewed` expert annotation with a qualification |
| P3 | experts disagreeing on inscription presence |
| P4 | `other_script` (the annotation does not name the script; R7 needs it) |
| P5 | missing artifact / photographs; unconvertible regions |
| P6 | any record whose label came from another source: **no silent overwrite** |
| P7 | an image whose SHA-256 on disk differs from the record |
| P8 | any change outside `promotion.writable_fields` (provenance, rights, path, SHA-256, site, split, record `verification_status` are protected) |
| P9 | a promoted record failing the dataset validator (e.g. R10: stratigraphic basis without a stratified context) |

One rejected artifact never blocks another. What a promoted record carries:
- `label_source = expert_annotation`; the lowest expert confidence;
- pixel regions naming annotator and annotation id;
- the annotator ids with qualifications, and a note naming the source annotations;
- a reading only if every expert gave the same one. Otherwise `reading_status = disputed`, and
  every reading is kept in `alternative_readings`;
- no translation for a personal name;
- a date range only if all experts agree (`project_estimate`, "not a published date"). Otherwise
  `disputed`, no bounds, each position in the text;
- `dating_source` listing each cited reference with its effective verification status. The
  record's own `verification_status` is left as it was.

**Reversal.** `promote --revert <id>` (dry run by default) restores each changed record's
exact pre-promotion state. It refuses if the record has changed since, or if the promotion was
already reverted. It needs the same digest-based approval and is logged as a new entry. A
promote followed by a revert restores `records.jsonl` byte for byte (tested).

**Audit entry:** promotion id, approver, UTC time, plan digest, records SHA-256 before and
after, annotation-store and registry SHA-256, artifacts, source annotation ids, and every
changed record's full before/after state with its image SHA-256.

## 7. Archaeological safeguards

- No rule of the form "looks like Tamil-Brahmi → Tamil-Brahmi". Nothing infers script,
  dynasty, site, date, reading, translation or meaning from image appearance or a language
  model.
- Fixed statements: **"Insufficient evidence"**; **"Disputed / requires expert resolution"**
  (always first when a dispute exists); **"Alternative reading(s) recorded"**; "Conflicting
  chronological positions / requires expert resolution".
- **Dating** (`dating_summary`, DATING block): "Estimated period: approximately X – Y" only
  from used evidence. It gives the basis, the confidence and the important uncertainty, sorted
  into object/context, palaeographic, linguistic, archaeological context, absolute dating,
  publication attribution and uncertainty. Annotators' ranges are shown side by side. Differing
  ranges are a conflict, capped at `low`, **never averaged**. No year 0 (a 1 BCE – 1 CE range is
  tested). The site's date is never an input.
- **Translation vs interpretation:** separate output sections. "Proper name; no literal
  translation established." / "No translation established." An AI gloss is never a translation.

## 8. Tests

| Area | Tests |
|---|---|
| Annotation creation (expert, project, all script choices), revisions, N14 | 7 |
| κ, IoU, reading similarity (known values, undefined κ, negative κ) | 6 |
| Agreement report: insufficient sample with raw counts, undefined, interpretable above threshold, unknown excluded, separate fields, no mutation / no resolution, ambiguity, AI never a rater | 9 |
| Pilot: definition, no labels on pilot records, live status, checklist, completion | 6 |
| Reference verification: V1–V8, K6, effective status, discrepancy, source unavailable, append-only, live key refs, CLI dry run | 22 |
| Unverified-reference confidence cap; verified lifts it and names the claim; annotation cannot self-verify | 3 |
| Promotion dry run: no mutation, determinism, invalid store, live CLI dry run / unapproved execute | 6 |
| Promotion rejections: disputed (×2), project-only (×2), unreviewed expert, AI (×2), qualification, presence, other_script, overwrite, SHA mismatch, validator, isolation | 14 |
| Promotion execution: success, provenance + SHA preserved, unverified evidence marked, approval, stale plan, idempotence, lowest confidence, `none` | 8 |
| Uncertainty in promotion: agreed / disagreeing readings, personal name, conflicting dates not averaged, no year 0 | 6 |
| Reversal: byte-exact, append-only audit trail, changed-since refusal, double revert, approval, unknown id | 6 |
| Training gate unchanged (thresholds, promoted small pilot still blocked, live untouched) | 3 |
| Reasoning outputs: insufficient, disputed, alternatives, personal name, no translation, AI gloss, dating shape, publication attribution, conflicting evidence, conflicting positions, no site date, live | 12 |
| Live integrity (no fabricated annotations/promotions; fixtures out of `data/`) | 2 |

```text
pytest tests/ -q                                                    679 passed
python -m src.dataset audit                                         30 records, 17 artifacts, PASS; label_source unknown: 30
python -m src.dataset validate data/metadata/records.jsonl --verify-hashes --strict   PASS, no findings
python -m src.annotation validate                                   annotations 0, PASS; knowledge base PASS
python -m src.knowledge validate                                    knowledge base PASS; verifications 0, PASS
python -m src.annotation promote --pilot                            dry run: 0 candidates, 6 rejected (unannotated)
python -m src.dataset readiness                                     Training ready: False (G7-G11 fail)
python -m src.training train                                        "Training blocked" (exit 3)
python -m src.reasoning analyze --all                               17 x "Insufficient evidence" / unknown
```

All test data is synthetic, built in `tmp_path` from `tests/fixtures/valid/base_record.json`.
Nothing is written under `data/` or `knowledge/`.

## 9. Current data status

17 research artifacts (30 images), all `script_type = unknown`, `label_source = unknown`,
`verification_status = unverified`. **0 annotations, 0 expert labels, 0 verified references,
0 promotions.** The 15 supporting images are unchanged.

## 10. Training readiness

**Blocked, correctly.** G7–G11 fail: there are no training-eligible records, every class
(`tamil_brahmi`, `graffiti`, `none`, `uncertain`) has 0 of the required 20 artifacts, and
there is no split manifest. Even if the whole pilot were annotated and promoted, six artifacts
could not meet the per-class minimum, and `none` would almost certainly stay empty, because
the pilot sherds were chosen for their marks. A test promotes six synthetic expert labels and
confirms the gate still blocks. No threshold, class or rule was relaxed.

## 11. Limitations

1. **No expert has taken part yet.** The pilot, agreement and promotion are exercised only on
   synthetic data. The first real run will be the real test of the workflow.
2. **Expert identity is self-declared.** A qualification is recorded, not verified.
   Institutional sign-off is outside the software.
3. **Verification is claim-level, but reasoning uses it at reference level.** If one claim in a
   work is verified, citations of that work count as verified for the confidence rules. The
   output lists the verified claims, so the scope stays visible. A discrepancy on any claim
   removes the verified status.
4. **Six artifacts cannot give an interpretable κ.** That is reported, not hidden.
5. **Reading agreement is string-based.** It cannot recognise equivalent transliterations in
   different schemes.
6. **Promotion writes all images of an artifact.** A per-image label, e.g. a mark visible in
   only one photograph, is represented by regions, not by different labels.
7. **An expert's unpublished reading gets `reading_status = unknown`.** The image-record schema
   has no status for "expert reading, not published".
8. **No concurrency control** on the stores or the promotion log (single annotator/reviewer
   at a time, one machine).
9. **Reference inconsistencies** R3 vs R3a and the missing R5 remain for a human to resolve.

## 12. Next recommended milestone

**Milestone 9: run the pilot with a real expert, and grow the labelled set.**
1. Recruit one qualified epigraphist or archaeologist and one project annotator. Annotate the
   six pilot sherds independently, then run `agreement` and resolve every disagreement.
2. Verify the claims the project relies on (`python -m src.knowledge claims --ref S03`,
   `--ref S01`) against the physical or authorised publications. Obtain an authorised copy of
   R1, or record it as `source_unavailable`. Resolve R3/R3a and R5.
3. Dry-run, review and approve the first promotion. Rehearse a revert.
4. Continue the data route (TNSDA permission; museum photography), including sherds **without**
   marks, because `none` needs 20 artifacts like every other class.
5. Only then generate a split manifest. Training becomes possible only once all gates pass as
   they stand.
