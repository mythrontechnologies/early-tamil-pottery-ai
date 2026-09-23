# Milestone 7: Annotation and Archaeological Reasoning Layer

**Date:** 2026-09-23
**Status:** complete. The annotation system and the reasoning layer are ready. **No
annotation has been made, no label assigned, and training remains BLOCKED.**

```text
Tests:              PASS (569 passed; 453 before this milestone + 116 new)
Annotation system:  READY (0 annotations; store validates; knowledge base K1-K5 PASS)
Reasoning layer:    READY (17/17 real artifacts -> "Insufficient evidence", confidence unknown)
Training:           BLOCKED (exit 3; gates G7-G11 fail: no labels)
Real artifacts:     17 (30 images)
Expert labels:      0
```

The system **cannot identify Tamil-Brahmi from images**, and does not claim to.

---

## 1. Files created and modified

**Created**
- `data/metadata/schema/annotation.schema.json`: annotation schema 1.0.0.
- `src/annotation/`:
  - `model.py`: templates, provenance roles, coordinate conversion;
  - `validate.py`: rules N1–N13;
  - `store.py`: append-only store;
  - `resolve.py`: multi-annotator resolution and disagreement;
  - `quality.py`: technical quality vs usability;
  - `form.py`: UI helpers;
  - `__main__.py`: `validate`, `summary`, `quality` and `rules` commands.
- `src/reasoning/`: `types.py`, `engine.py`, `from_annotations.py`, `__main__.py`.
- `src/dating/`: `chronology.py` (signed years, no year 0; positions and periods from
  config), `estimate.py` (evidence-based age ranges).
- `src/translation/interpret.py`: "No translation established" logic.
- `src/knowledge/base.py`: knowledge-base loader and validator (K1–K5).
- `knowledge/`:
  - `references/references.yaml` (10 references);
  - `sites/sites.yaml` (Keezhadi, Kodumanal);
  - `scripts/scripts.yaml`;
  - `inscriptions/published_readings.yaml` (4 readings transcribed from S03 and S01);
  - READMEs for the empty categories.
- `app/annotate.py`: Streamlit annotation interface.
- `tests/test_annotation.py` (59), `tests/test_reasoning.py` (47).
- `docs/ANNOTATION_GUIDE.md`, `docs/ARCHAEOLOGICAL_REASONING.md`, this report.

**Modified**
- `src/dataset/audit.py`: `dating_basis` counting fix (§2).
- `tests/test_ingest_audit_readiness.py`: +10 regression tests.
- `configs/project.yaml`: `chronology.periods`, the Early Historic label, marked unverified.
- `README.md`.

**Not modified:** `records.jsonl`, the acquisition provenance, the image-record schema, and
every training gate.

## 2. The `dating_basis` audit quirk
`["not_available"]`, `["unknown"]`, `["not_applicable"]` and sentinel-only lists no longer
count as a dating basis (`has_dating_evidence_basis`). This changes counting only; no record
was edited. The live audit now reports **0** records with a dating basis (it reported 30).
Ten regression tests cover the sentinel cases, mixed lists, absent fields, non-mutation and
the live dataset.

## 3. Schema changes
- **New: annotation schema 1.0.0.** One record per artifact, per annotator, per revision.
  It contains:
  - provenance type (`source_information` / `project_annotation` / `expert_annotation` /
    `ai_prediction`), annotator (id, role, qualification) and review state
    (`unreviewed` / `project_reviewed` / `expert_reviewed` / `disputed`);
  - `supersedes`, for revisions;
  - object;
  - inscription: presence, project-category type, script and confidence, **normalised
    regions**, characters visible, reading, transliteration, alternatives, reading
    confidence and source;
  - interpretation: type, translation, meaning, confidence, source;
  - linguistic features;
  - dating: range, confidence, basis, and evidence items with type, observation, support
    bounds, association, confidence and source;
  - per-image archaeological usability, references, uncertainty notes.
- `script_type` and `pottery_type` vocabularies are kept **identical** to the image-record
  schema by a test.
- **Image-record schema: unchanged (1.2.0).** Annotations live in their own store. Source
  metadata is never overwritten.
- `project.yaml`: `chronology.periods` added. It is a label for ranges, not a date source.

## 4. Annotation workflow
1. `streamlit run app/annotate.py`. Enter an annotator id; choose project annotator, source
   transcription or expert (experts state a qualification).
2. Select an artifact (all 17 are available). View its photographs and the source's
   caption, shown as context and never as a label.
3. Zoom by window sliders, and add the window as a normalised region. Regions are drawn on a
   copy; the original is never touched.
4. Fill in object, inscription, reading, alternatives, meaning, linguistic features, dating
   evidence, references, per-photo usability and uncertainty.
5. Save: the record is validated against the whole store (N1–N13) and **appended**. A second
   save by the same annotator supersedes their own earlier record, which is kept.
6. The Review tab shows every annotation (superseded ones marked), the resolution status,
   disagreements, and the reasoning output for the artifact.

Resolution statuses:
- `expert_label`: the **only** ground-truth-eligible status;
- `disputed`;
- `provisional`: project agreement, **not** ground truth;
- `project_disagreement`;
- `unannotated`.

AI predictions never count.

The UI was tested headlessly (Streamlit `AppTest`): it renders, saves to a temporary store,
records a revision chain, and rejects a save without an annotator id.

## 5. Reasoning architecture
Structured `ReasoningInputs` → `analyze_artifact` → `AnalysisResult`, built from modular,
deterministic components:
- script assessment;
- interpretation;
- evidence-based age estimation, by tier with conflict detection and no averaging;
  Position D enforced through the `association` field; no year 0;
- period labelling from config.

Confidence comes from rules, not scores. `high` requires expert, stratified, verified,
multi-type evidence. It is capped at `low` whenever evidence is project-level, conflicting,
disputed, or cites unverified references, so everything today is ≤ `low`. Script-only
evidence yields at most an outer bound ("no earlier than …", `very_low`). No evidence yields
"Insufficient evidence". Full description: `ARCHAEOLOGICAL_REASONING.md`.

## 6. Tests

| Area | Tests |
|---|---|
| Audit semantics for sentinels | 10 (in `test_ingest_audit_readiness.py`) |
| Annotation schema, vocabulary parity, year 0, empty strings | 5 |
| Provenance separation, roles, review states, AI never reviewed | 9 |
| Unknown vs uncertain, regions, normalised coordinates, reading sources | 10 |
| Translation rules (personal name, sources, symbols) | 3 |
| Dating evidence (range needs evidence, reversed, year 0, basis, association, missing) | 8 |
| References (unresolved, local, knowledge base) | 3 |
| Store (append-only, multiple annotators, revisions, cross-annotator supersede refused) | 8 |
| Resolution / conflicting annotations (incl. the brief's A / B / expert example) | 6 |
| Form, drawing without modifying originals, quality vs usability | 5 |
| Live state (no fabricated annotations; records remain unknown), UI | 3 |
| Chronology arithmetic (no year 0, centuries, ranges, config) | 11 |
| Dating engine (insufficient, outer bound, conflicts, AI excluded, Position D, confidence caps) | 16 |
| Interpretation (no reading, personal name, AI gloss ignored, sourced translation) | 5 |
| Engine (determinism, keyword interface, no fabricated evidence, disagreement, no certainty) | 8 |
| Real artifacts, expert-over-project basis | 2 |
| Knowledge base (loads, every assertion referenced, nothing evidence-grade, K3, K5) | 5 |

```text
pytest tests/ -q                                  569 passed
python -m src.dataset audit                       30 records, 17 artifacts, PASS; dating_basis: 0
python -m src.dataset validate ... --strict       PASS
python -m src.annotation validate                 annotations 0, PASS; knowledge base PASS
python -m src.dataset readiness                   Training ready: False
python -m src.training train                      "Training blocked: No expert-labelled training images ..." (exit 3)
python -m src.reasoning analyze --all             17 x insufficient_evidence / unknown
```

## 7. Dataset status
17 research artifacts (30 images), all `script_type = unknown`, **0 annotations, 0 expert
labels, 0 ground-truth-eligible artifacts**. The 15 supporting images are unchanged.

## 8. Training gate
Unchanged and blocked. Annotations do not feed the gates. The only path from an annotation
to a training label is a future, explicit promotion of `expert_label` resolutions into the
records. No gate, threshold, rights rule or split rule was relaxed.

## 9. Known limitations
1. **No annotations exist.** The system has been exercised only on synthetic annotations in
   tests.
2. **No verified references.** Every knowledge-base reference is `transcribed_unverified`,
   `bibliographic_only` or `unverified`, so reasoning confidence cannot exceed `low`.
3. **Expert identity is self-declared.** The tool records a qualification but cannot verify
   it. Institutional sign-off is outside the software.
4. **Region marking is rectangular and slider-based.** It is adequate for bounding boxes but
   not polygons, and not a drawing canvas.
5. **Reading and linguistic features are text.** There is no character-level segmentation or
   Unicode Brahmi input helper yet.
6. **The dating engine combines only what annotators supply.** It has no built-in
   palaeographic tables, because none is verified in the project.
7. **The period label** (Early Historic ≈ 300 BCE – 400 CE) is unverified.
8. **Technical quality thresholds are still uncalibrated** (29/30 images flagged
   `possibly_blurry`). They are reported beside usability and reject nothing. Calibration
   remains future work.
9. **No concurrency control** on the append-only store. It is suitable for one annotator at a
   time on one machine.

## 10. Recommended Milestone 8
**Expert annotation pilot and label promotion.**
1. Recruit one qualified epigraphist or archaeologist. Pilot-annotate the six Keezhadi
   incised-sherd close-ups (site photos 105–110), plus a project annotator for disagreement
   data.
2. Verify the first references against the physical publications (R1, S01, S03 pages). Move
   them to `verified_against_source`, with verifier and date.
3. Implement **label promotion**: `expert_label` resolutions → `records.jsonl`
   (`script_type`, `label_source = expert_annotation`, regions converted to pixels,
   readings). Do it as an audited, reversible batch through the existing ingestion
   validator, with a dry run by default.
4. Add inter-annotator agreement metrics (per field, with κ where the counts allow).
5. Continue the data route (TNSDA permission; museum photography), because the gates still
   need ≥ 5–20 labelled artifacts per class, including `none`.
