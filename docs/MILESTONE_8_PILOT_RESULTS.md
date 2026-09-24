# Milestone 8: Six-Artifact Annotation Pilot, First Processing Run

**Date:** 2026-09-24
**Status:** pilot **opened, not completed.** No human project annotation, no expert annotation
and no reference verification has been supplied. An AI-prepared draft of the project-annotator
worksheet exists. It is quarantined as an AI draft and has **not** been entered into the
annotation store. One provenance problem was found in the pilot set itself (§3).

```text
Human project annotations:  0 / 6
Expert annotations:         0 / 6          expert labels = 0
AI-prepared draft:          6 / 6          outputs/pilot_handoff/ (git-ignored), NOT in the store
Agreement:                  not computable (0 pairs)
References verified:        0 / 10 claims  (checklist returned blank)
Citation questions:         R3 / R5 partly answered from the repository, not resolved (§7)
Promotion dry run:          0 candidates; 6 rejected (P1: no human annotation)
Training:                   BLOCKED (exit 3; gates G7-G11)
Tests:                      686 passed
Pilot set problem:          107 and 109 appear to be painted reproductions of 106 and 108
```

---

## 1. The six pilot artifacts and their data sources

| Artifact | Image id | SHA-256 (records.jsonl) | Hash re-checked | Commons file |
|---|---|---|---|---|
| `WMC_KEELADI_MUS_SHERD_105` | `wmc_157308858` | `1352aa85…235900` | ✅ match | Keeladi-archeological-site-photos 105.jpg |
| `WMC_KEELADI_MUS_SHERD_106` | `wmc_157308869` | `2e19d952…840568` | ✅ match | … 106.jpg |
| `WMC_KEELADI_MUS_SHERD_107` | `wmc_157308866` | `eebf1582…7066be` | ✅ match | … 107.jpg |
| `WMC_KEELADI_MUS_SHERD_108` | `wmc_157308870` | `61039359…2b2da` | ✅ match | … 108.jpg |
| `WMC_KEELADI_MUS_SHERD_109` | `wmc_157308868` | `1043f139…c91537` | ✅ match | … 109.jpg |
| `WMC_KEELADI_MUS_SHERD_110` | `wmc_157308873` | `ee1f1049…d7d9f5` | ✅ match | … 110.jpg |

All six photographs are 6000 × 4000 px, by Rajeshodayanchal, CC BY-SA 4.0, via Wikimedia Commons.
Identity comes from the acquisition provenance, not from the filenames. The project holds no
excavation context, trench, layer, catalogue number or publication for any of them. The raw
images were only read: viewing crops were made in a temporary directory and nothing under
`data/raw/` was written.

## 2. Worksheet status on arrival

| File | State found |
|---|---|
| `outputs/pilot_handoff/pilot_worksheet_project_annotator.csv` | all judgement columns blank |
| `outputs/pilot_handoff/pilot_worksheet_expert.csv` | all judgement columns blank |
| `outputs/pilot_handoff/verification_checklist.csv` | all 10 verification rows blank |
| `data/metadata/annotations/annotations.jsonl` | does not exist (0 annotations of any tier) |
| `knowledge/verification/reference_verifications.jsonl` | does not exist (0 verifications) |

## 3. Finding: two pilot "artifacts" appear to be reproductions

Full-resolution inspection of the photographs shows the following. This is a **project
observation**, not a museum or expert confirmation.

| Photographed object | Evidence visible in the photograph | Appears to reproduce |
|---|---|---|
| `…_107` | flat opaque paint with brush strokes; grooves filled with white paste; screwed to a wall by four metal screws | `…_106`: same outline, same black-over-red layout, the **same six signs in the same order and forms** |
| `…_109` | opaque orange-red paint with brush strokes; white-filled grooves; wall-mounted with screws; moulded join line | `…_108`: same outline, same break between two parts, the **same sign sequence** on both parts |

Consequences, if confirmed:

1. 107 and 109 are not archaeological objects and cannot carry archaeological labels.
2. Each would duplicate its original's inscription under a different `artifact_id`. The
   project's leakage control (one artifact, one split: R3, G6) cannot catch this, because the
   ids differ. In a split, the same inscription would sit on both sides.
3. The reproductions' signs are bolder and cleaner than the originals'. Whoever made them may
   have interpreted the strokes, so they are **not** evidence for how the originals read.
4. The pilot then has **four** original sherds, not six.

**Not changed:** `records.jsonl` and the provenance registry. The records correctly state what
the source says. The reproduction question is for the expert, or the Keezhadi site museum, to
answer. `docs/PILOT_HANDOFF.md` §1 now asks it.

## 4. Project annotation (AI-prepared draft, not a human annotation)

The brief asked for the project-annotator worksheet to be prepared if blank. It was prepared
by the AI assistant (Claude Opus 5.5) from the photographs. A human project annotator did not
prepare it, so it is recorded honestly as an AI draft:

- worksheet: `outputs/pilot_handoff/pilot_worksheet_project_annotator.csv`, with
  `annotator_id = ai_draft_claude-opus-5-5` and an "AI-PREPARED DRAFT" flag in every row;
- machine-readable copy: `outputs/pilot_handoff/ai_draft_annotations.jsonl`, with
  `provenance_type = ai_prediction`. It passes N1–N14 (schema, regions within the image,
  unknown vs uncertain, no reading means no interpretation, no date without evidence).

**It was not appended to `data/metadata/annotations/annotations.jsonl`.** Entering it there as
`project_annotation` would put AI output under a human provenance tier. That is the blurring
the project exists to prevent. A human project annotator should treat it as notes, check
every field against the photographs, and enter **their own** annotation in `app/annotate.py`.

| Artifact | Inscription present | Script | Regions (normalised x, y, w, h) | Signs counted | Usable |
|---|---|---|---|---|---|
| 105 | yes | uncertain (low) | 0.26, 0.43, 0.44, 0.38: 3 signs, 4th cut by break | 3 | yes |
| 106 | yes | uncertain (low) | 0.453, 0.52, 0.28, 0.15: one row | ~6 | yes |
| 107 | yes (on the reproduction) | uncertain (low) | 0.387, 0.31, 0.413, 0.26 | 6 | **no** (probable reproduction) |
| 108 | yes | uncertain (low) | 0.19, 0.465, 0.183, 0.095 (left); 0.42, 0.44, 0.36, 0.21 (right) | not counted | yes |
| 109 | yes (on the reproduction) | uncertain (low) | 0.26, 0.29, 0.14, 0.10; 0.467, 0.19, 0.44, 0.15 | not counted | **no** (probable reproduction) |
| 110 | yes | uncertain (low) | 0.367, 0.665, 0.2, 0.055 (left); 0.587, 0.69, 0.307, 0.08 (right, faint) | not counted | uncertain (glass, glare, oblique) |

Every region is labelled `possible_inscription`, not `inscription` or `graffiti`. The regions
were drawn over the photographs and checked visually before they were recorded.

**Why "uncertain" for script, although deliberate signs are clearly present.** Deciding between
Tamil-Brahmi, non-script graffiti, and both needs palaeographic judgement at the level of
individual strokes. An AI reading of letterforms is exactly the "LLM-hallucinated reading"
this pilot must not produce. The site name (Keezhadi) is not evidence of script and was not
used.

| Field | Draft value (all six) |
|---|---|
| Reading | `No reliable transcription established.` |
| Alternative readings | none recorded |
| Inscription type | `uncertain` |
| Interpretation type | `not_applicable` (no reading) |
| Translation | `No translation established.` |
| Linguistic observations | none |
| Dating | `Insufficient evidence`. No range, no evidence items. |
| References | none |

## 5. Expert annotation

**None.** The expert worksheet is blank and no expert annotation exists in the store. None
was fabricated. `expert labels = 0`.

## 6. Inter-annotator agreement

`python -m src.annotation agreement` → **0 pairs**. Every field reports `no_data`.

| Field | Compared | Agree | Disagree | Statistic |
|---|---|---|---|---|
| inscription_present | 0 | – | – | κ n/a |
| script_type | 0 | – | – | κ n/a |
| inscription_type | 0 | – | – | κ n/a |
| interpretation_type | 0 | – | – | κ n/a |
| regions | 0 | – | – | IoU n/a |
| reading | 0 | – | – | similarity n/a |
| dating_evidence_types | 0 | – | – | Jaccard n/a |

The AI draft cannot stand in as rater A: `agreement.py` excludes `ai_prediction` by design.
Even at completion, the pilot has **n = 6** items (n = 4 if 107/109 are excluded). The project
flags κ as not interpretable below 30 items. With n ≤ 6, one changed item moves raw agreement
by 17–25 percentage points, and κ is undefined whenever a rater uses a single category
throughout. The pilot's value is the **item-by-item disagreement list**, not a statistic.
Agreement is not archaeological truth.

## 7. Reference verification and the two citation questions

**Checklist:** `python -m src.knowledge import-checklist …` (dry run) → *rows with a status: 0;
blank rows skipped: 10*. Nothing was imported. All 10 claims (R1: 1, S01: 3, S03: 6) remain
unverified.

| Ref | Claims | Effective status | Why unchanged |
|---|---|---|---|
| R1 | 1 | bibliographic_only | No authorised copy. The only online copy found is unauthorised (DATA_SOURCE_AUDIT S06) and does not count. |
| S01 | 3 | transcribed_unverified | Read via Tamil Digital Library in Milestone 4, but no named human verifier has checked the claims and locators. |
| S03 | 6 | transcribed_unverified | Same. Two claims have no transcribed locator (`not_available`). None was invented. |

The AI assistant did not fill the checklist. Rule V3 requires a named human verifier (role
`project_member` or `expert`) who consulted a physical, authorised or open-access copy, and an
AI is neither. Marking rows `source_unavailable` would also need a human verifier record.

**Citation question 1: does position B's `R3` mean `R3a`?** The repository answers this in
part. In `docs/CHRONOLOGICAL_SCOPE.md` §6, `R3` is an **author-level placeholder**: "Rajan, K.
— publications on early writing, Porunthal and Kodumanal", flagged 🔶 (least certain). It is
not one work. Two candidate titles were later located. `R3a` (Rajan & Yatheeskumar 2013,
*Prāgdhārā* 21–22: 280–295) is `bibliographic_only`: it exists, and it has not been read. The
other is S01 (Rajan & Sivanantham 2026), whose ch. 10 argues the chronology. So `R3` is **not
established to mean `R3a`**. Either work, or another Rajan publication, could be the source
for position B's −500 to −400 range. **Unresolved: requires source verification.**

**Citation question 2: what is `R5`?** In `docs/CHRONOLOGICAL_SCOPE.md` §6, `R5` is "Falk,
Harry — publications on the origins of Brahmi", again an author-level placeholder flagged 🔶,
with "exact titles unverified". It is absent from `knowledge/references/references.yaml`
because no title has been established. The repository therefore records the **intended
author** (Harry Falk) but no specific work. That attribution was itself drafted by an assistant
and is unverified. **Unresolved: the specific work requires source verification.** No title
was guessed.

## 8. Dating and translation evidence

| Level | What exists | Used for an object date? |
|---|---|---|
| Site / deposit | Uploader's caption: Keeladi deposit "6th century BCE – 1st century CE" | **No.** It is a site-level statement from a non-specialist caption. |
| Published site chronology | S03 (ASI: inscribed sherds c. 2nd c. BCE – 1st c. CE) vs R6 (TNSDA: 6th c. BCE beginning). Disputed, unverified. | **No.** Not linked to these objects. |
| Stratigraphy / layer | none recorded | – |
| Absolute dating | none linked to these objects | – |
| Palaeography | none (no reading, no script identification) | – |
| Linguistics | none (no reading) | – |
| Pottery typology | none recorded (106 shows a two-tone black/red surface; the ware was not identified) | – |
| Published attribution | none (no catalogue number connects any photograph to a publication) | – |

**Object dating: `Insufficient evidence` for all six.** No range was averaged, no midpoint was
taken, and no range was copied from the site.
**Translation: `No translation established.` for all six.** There is no reading to translate.

## 9. Reasoning results

`python -m src.reasoning analyze` on the real store gives the same for each of the six:

| Section | Output |
|---|---|
| Observation | Script not determined by any human annotator or source |
| Interpretation | No reading established; nothing can be translated |
| Evidence | none: no human-sourced evidence, no verified reference |
| Dating | Insufficient evidence; basis none; confidence unknown |
| Translation | No translation established |
| Uncertainty | No secure context recorded; no expert-reviewed label |

Run against a **scratch copy** of the store holding the AI draft, the output is identical,
plus a section "AI PREDICTIONS (reported only; not evidence)" listing the draft. The draft
changed no conclusion. The quarantine works as designed.

## 10. Pilot report

| Artifact | Inscription | Script | Reading | Translation | Dating | Evidence | Confidence | Status |
|---|---|---|---|---|---|---|---|---|
| 105 | **Observed:** 3 incised signs (+1 cut by break). **AI draft:** yes. **Expert:** – | **AI draft:** uncertain. **Expert:** – | none established | none established | Insufficient evidence | none verified | unknown | unannotated (human); awaiting project + expert |
| 106 | **Observed:** ~6 incised signs in one row. **AI draft:** yes. **Expert:** – | **AI draft:** uncertain. **Expert:** – | none established | none established | Insufficient evidence | none verified | unknown | unannotated (human); awaiting project + expert |
| 107 | **Observed:** 6 signs on a **probable painted reproduction of 106**. **AI draft:** yes; unusable. **Expert:** – | **AI draft:** uncertain. **Expert:** – | none established | none established | Insufficient evidence | none verified | unknown | **reproduction status unresolved**; should not be a training artifact |
| 108 | **Observed:** line of signs across two joined fragments. **AI draft:** yes. **Expert:** – | **AI draft:** uncertain. **Expert:** – | none established | none established | Insufficient evidence | none verified | unknown | unannotated (human); awaiting project + expert |
| 109 | **Observed:** signs on a **probable painted reproduction of 108**. **AI draft:** yes; unusable. **Expert:** – | **AI draft:** uncertain. **Expert:** – | none established | none established | Insufficient evidence | none verified | unknown | **reproduction status unresolved**; should not be a training artifact |
| 110 | **Observed:** row of signs below the rim; right part faint; under glass. **AI draft:** yes; usability uncertain. **Expert:** – | **AI draft:** uncertain. **Expert:** – | none established | none established | Insufficient evidence | none verified | unknown | unannotated (human); awaiting project + expert |

"Observed" is what is visible in the photograph. "AI draft" is the quarantined project-worksheet
draft. There is no expert annotation, no verified evidence, and every archaeological question
is unresolved.

## 11. Promotion dry run

```text
python -m src.annotation promote --dry-run          candidates 0, rejected 0 (no annotated artifacts to consider)
python -m src.annotation promote --dry-run --pilot  candidates 0, rejected 6
    105-110: P1 no human annotation (AI predictions are never labels)
With the AI draft in a scratch store:                candidates 0, rejected 6
    105-110: P1 no human annotation ... (1 AI prediction(s) ignored)
```

| Requirement | 105 | 106 | 107 | 108 | 109 | 110 |
|---|---|---|---|---|---|---|
| Expert-reviewed | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ |
| Not disputed | n/a | n/a | n/a | n/a | n/a | n/a |
| Valid provenance / image hash | ✓ | ✓ | ✓ (but object provenance doubtful) | ✓ | ✓ (but object provenance doubtful) | ✓ |
| Schema valid | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| Evidence / references verified | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ |
| **Training label candidate** | none | none | none | none | none | none |

No `--execute` was run. The promotion log is empty.

## 12. Training status

`python -m src.training train` → **BLOCKED, exit 3.** G1–G6 pass; G7–G11 fail. No gate,
class list or threshold was changed. Even a fully successful pilot would add at most 4–6
labelled artifacts, against ≥ 5 per class for grouped cross-validation and ≥ 20 per class for
holdout. The `none` class (sherds with no mark) has **no** candidate in this pilot, because
every pilot photograph shows a marked sherd. It needs deliberate acquisition.

## 13. Checks run

| Check | Result |
|---|---|
| `python -m pytest tests/ -q` | 686 passed |
| `python -m src.dataset audit` | PASS; 30 records, all `script_type = unknown` |
| `python -m src.dataset validate data/metadata/records.jsonl --strict --verify-hashes` | PASS, no findings |
| `python -m src.preprocessing inspect` on the six pilot images | OK. Flag `possibly_blurry` on all six (an uncalibrated technical heuristic; it rejects nothing). |
| `python -m src.annotation validate` | PASS (0 annotations) |
| `python -m src.knowledge status` | R1 bibliographic_only; S01, S03 transcribed_unverified; 0 verified |
| `python -m src.training train` | BLOCKED (exit 3) |

## 14. Limitations

- The only "project annotation" is an AI draft. It is not a substitute for the independent
  human project annotator the pilot design requires.
- The reproduction finding rests on the photographs alone.
- The annotation schema has no field for "modern reproduction". The draft uses `object_type =
  other`, `usable_for_annotation = no` and notes.
- One photograph per artifact, no scale bar, and 110 is taken through display glass.
- n ≤ 6: no agreement statistic will be interpretable.

## 15. Next steps

1. **Ask the Keezhadi site museum or the expert** whether 107 and 109 are reproductions. If
   they are, exclude them from the pilot and from any split, record why, and add two original
   sherds (or run the pilot on four).
2. A **human project annotator** annotates the six in `app/annotate.py` under their own id,
   using the AI draft only as notes.
3. The **expert** annotates independently, with a review state of `expert_reviewed` or
   `disputed`.
4. Run `python -m src.annotation agreement` and resolve the item-by-item disagreements in the
   expert's own annotation.
5. A **human verifier** works through `verification_checklist.csv` against authorised copies,
   then runs `import-checklist` (dry run, then `--commit`).
6. Resolve R3 (which Rajan work supports position B) and R5 (which Falk work supports
   position D) from the publications.
7. `python -m src.annotation promote --pilot` (dry run), then human approval.
8. Acquire unmarked sherds for the `none` class.

---

## Addendum (2026-09-24, later): pilot prepared for completion

- **107/109** are now carried as review flags in `configs/project.yaml`
  (`annotation_pilot.review_flags`): "REVIEW REQUIRED — possible reproduction / duplicate
  inscription", `confirmed: false`. Artifact identity and `records.jsonl` are unchanged.
  Promotion rule **P10** refuses a flagged artifact until every expert states
  `object_status = original`.
- Annotation schema **1.1.0** (additive): `object.object_status`
  (original/reproduction/uncertain/unknown), `object.object_notes`,
  `dating.unresolved_conflict`.
- Rule **N15**: an AI-marked record can only be an `ai_prediction`. The AI draft is shown
  read-only in the UI (off by default) under "AI-generated observation. Not archaeological
  evidence."
- The project-annotator worksheet was regenerated **blank**, so the AI-filled draft copy is
  gone. The AI draft remains only in `ai_draft_annotations.jsonl`.
- Agreement now also compares `object_status` and the proposed date ranges, and prints an
  item-level review. κ is withheld from the text below 30 items.
- `python -m src.knowledge claim-report`: per-claim verification state; R3 and R5 are UNRESOLVED.
  Web-found candidates are recorded in `PILOT_HANDOFF.md` §3 as secondary information only.
