# Final Engineering Status

**Date:** 2026-10-08 (Milestone 11; previous status 2026-09-24)
**Verdict:** everything engineering can honestly complete is complete, including the dual-annotation and
adjudication workflow, worksheet round trip, software pre-checks of the key references, a near-duplicate
leakage guard, gated real-data evaluation for every task, and a type-checked codebase. What remains is real
archaeological evidence: a human check of the references, expert annotation, enough labelled artifacts per
class, and then training. None of it can be engineered, and none of it has been fabricated.

```text
Tests:              1093 passed, 5 browser tests deselected, 1 expected warning (a hardening test feeds a raw pickle to the safe loader); 31 test files (2026-10-09, synthetic language, grammatical interpretation, near-duplicate grouping; 981 at Milestone 11)
Browser:            5 passed (phone-width overflow at 100-200 % text; keyboard, fallbacks, reduced motion, timing; every page at phone / tablet / desktop width, text 100-200 %; one session through every page with the app's navigation, Research and Presentation; language / reading results at phone / tablet / desktop)
Static checks:      ruff clean; mypy clean (127 files: src, app, scripts)
Research data:      21 artifacts / 34 images (Wikimedia Commons, CC BY / CC BY-SA), provenance 34/34, raw files unchanged
Labels:             0   (tamil_brahmi 0 | graffiti 0 | none 0 | uncertain 0)
Human annotations:  0 project, 0 expert, 0 adjudications
References:         0 verified; R1, S01, S03 bibliographically confirmed + 10 claims pre-checked by software (not verification)
Training:           BLOCKED (exit 3; G1-G6 pass, G7-G11 fail)   Evaluation: BLOCKED (exit 3), detection / OCR: BLOCKED
Workflow:           stages 1-5 PASS; stage 6 (annotations) WAITING - HUMAN ACTION REQUIRED
Synthetic system:   verify 14/14 PASS (byte-identical re-render); demo, CLI, API, UI working; SYNTHETIC only
```

Legend: **done** = implemented and tested · **blocked (data)** · **blocked (expert)** · **future**.

## Final engineering checklist

| # | Phase | Item | State |
|---|---|---|---|
| 1 | References | R1, S01, S03: bibliographic details confirmed against the BnF record, the Tamil Digital Library imprint and the journal's own contents | done |
| 1 | References | 10 claims pre-checked in permitted copies (S01 3/3, S03 6/6 located; 1 S03 discrepancy recorded and the knowledge base corrected; R1 not accessible online); schema + rules PC1-PC8; `prechecks`, `verify-from-precheck` | done |
| 1 | References | any reference verified | blocked (expert / verifier) |
| 1 | References | identity of R3, R5 (R5 candidate's existence now confirmed) | blocked (scholar) |
| 2 | Data | second Commons screening; +4 CC BY 3.0 Adichanallur vessels via the licence-gated pipeline; rejections recorded | done |
| 2 | Data | ≥ 5 artifacts per class; the `none` class | blocked (data: institutional permission) |
| 3 | Annotation | schema 1.2.0: adjudication (N18), glyph regions (N19), reading completeness (N20); queue; worksheets + all-or-nothing import; export; tier legend; Queue tab; adjudication UI | done |
| 3 | Annotation | real annotations | blocked (expert) |
| 4 | Agreement | field-level disagreement report; `adjudicated` status, stale-adjudication detection; promotion of adjudicated labels | done |
| 5 | Split | artifact-level, seeded, fingerprinted manifests (since M5) + near-duplicate (dHash) guard and CLI | done |
| 5 | Split | a split of the real data | blocked (data) |
| 6 | Training | gated training (since M5), unchanged; refuses today | done / blocked (data) |
| 7 | Evaluation | classification + error analysis + robustness; IoU detection P/R/F1; OCR CER/WER + failure analysis; evidence tiers | done |
| 7 | Evaluation | any metric on real data | blocked (data) |
| 8 | Chronology | evidence-tiered ranges, conflicts reported, no year 0 (since M7); adjudication basis stated | done |
| 9 | Transcription | partial / fragmentary / illegible outcomes; no invented signs; no forced translation | done |
| 10 | Knowledge | every claim with source, locator, status, scope; pre-checks shown separately | done |
| 11 | Synthetic | generation, training, calibration, detection, segmentation, OCR, reasoning, replay, CLI, API, UI re-validated | done |
| 12 | UI | every page at phone / tablet / desktop width, text 100-200 %: no overflow (text-relative grids and wrapping badges fixed 9 overflow cases), no exception; keyboard, reduced motion, no-WebGL fallbacks (since M10) | done |
| 13 | Security | CSV formula-injection guard; bomb handling in the hash scan; secret scan clean; API input checks re-tested | done |
| 13 | Security | API authentication | future (localhost-only by default; DEPLOYMENT.md) |
| 14 | Docs | README rewritten (what works, synthetic vs real, blocked, annotate, train); MILESTONE_10/11 reports, EVALUATION, TROUBLESHOOTING; all guides updated | done |
| 15 | Quality | mypy configured and clean (158 errors fixed, none suppressed); static checks as tests | done |
| 16 | Reproducibility | `requirements-lock.txt`; Python / CUDA / CPU fallback documented | done |
| 12 | Deployment | Docker image build | not run (Docker engine not running); `docker compose config` validates |

## A. What is complete

Everything listed in the 2026-09-24 status (acquisition, validation, preprocessing, annotation with an
append-only ledger, agreement, reversible promotion, knowledge base and verification workflow, evidence-based
reasoning, inference API / CLI / HTTP service, Streamlit application, evaluation, gated training, deployment
files) plus Milestones 9-11: the isolated synthetic engineering dataset and complete synthetic AI pipeline, and
the Milestone 11 additions above ([`MILESTONE_11_REPORT.md`](MILESTONE_11_REPORT.md)).

## B. What is tested (final validation, 2026-10-08, run live)

| Check | Result |
|---|---|
| `pytest tests/ -q` | 1093 passed, 5 browser tests deselected, 1 expected warning (a hardening test feeds a raw pickle to the safe loader); 31 test files (re-run 2026-10-09 after the synthetic language; 981 on 2026-10-08) |
| `pytest -m browser` | 5 passed (phone-width overflow at 100-200 % text; keyboard, fallbacks, reduced motion, timing; every page at phone / tablet / desktop width, text 100-200 %; added 2026-10-09: one session through every page with the app's navigation in Research and Presentation mode; language / reading results at phone / tablet / desktop) |
| `ruff check src app scripts tests` / `mypy` | clean / no issues in 127 files |
| `src.workflow status` | stages 1-5 PASS (34 records, 34 files, 21 artifacts, provenance 34/34, 0 hash mismatches) |
| `src.dataset validate --strict --verify-hashes` / `near-duplicates` | PASS / 0 pairs |
| `src.annotation validate` / `integrity` | PASS / all stores EMPTY (intact) |
| `src.knowledge validate` | PASS (12 references, 7 entries, 0 verifications, 10 + 4 pre-checks) |
| `src.dataset readiness` / `src.training train` | not ready / exit 3 |
| `src.evaluation evaluate` / `detection` / `ocr` | blocked, exit 3 |
| `src.reasoning` on all 21 artifacts | "Insufficient evidence" (correct: no annotation exists) |
| `src.synthetic verify` | 14/14 PASS, 8 images re-rendered byte-identically |
| `src.synthetic demo` | 8 stages, 31 ms on CUDA; ground-truth check correct; synthetic warnings present |
| `src.inference synthetic` on a real photograph | refused, exit 3 |
| HTTP API | `/health` ok; real photo → "Insufficient evidence"; `/synthetic/analyze` real → 422, synthetic → 200; wrong type 415; corrupt image 422 |
| Raw data | the 30 pre-existing files byte-identical before and after acquisition |

## C. Current dataset status

| | |
|---|---|
| Research artifacts / images | 21 / 34 |
| Supporting images (not training data) | 15 |
| Human / expert annotations, adjudications | 0 / 0 / 0 |
| Verified references | 0 (10 claims pre-checked) |
| Tamil-Brahmi / graffiti / none / uncertain | 0 / 0 / 0 / 0 |
| Review flags | 107 and 109: possible reproductions of 106 and 108 (unconfirmed) |

## D. Current training status

**BLOCKED** by gates G7-G11 (no training-eligible labels, no class present, no split manifest). No model
exists. No gate, class list or threshold was changed.

## E. Remaining human actions (exact)

1. **Verifier (≈ 10 min):** `python -m src.knowledge prechecks`; for each S01 / S03 claim open the copy at the
   page shown and run `python -m src.knowledge verify-from-precheck <PC-id> --verifier <id> --role project_member --date <YYYY-MM-DD> --i-opened-the-source --commit`
   (PC-S03-05: `--status discrepancy_found --notes "..."` if you confirm the difference).
2. **Library:** check R1 position A in a physical / authorised copy (`python -m src.knowledge verify ...`).
3. **Scholar:** name the works behind R3 and R5 (add them to the knowledge base; point the positions at them).
4. **Project annotator and expert:** annotate the six pilot sherds independently (Annotation page, or
   `python -m src.annotation handoff --all` → `import-worksheet`); then `python -m src.annotation disagreements`;
   an expert adjudicates disagreements.
5. **Museum / TNSDA:** confirm whether 107 / 109 are reproductions; give catalogue numbers for 105-110.
6. **Approver:** `python -m src.annotation promote --pilot` (dry run) → `--execute --approve <digest> --approver <id>`.
7. **Data:** one institutional permission for controlled photographs of inscribed and **uninscribed** sherds
   (`NEXT_DATA_ACQUISITION.md`): open sources are exhausted.

## F. Known limitations

See [`LIMITATIONS.md`](LIMITATIONS.md): no model, no labels, no verified references, null OCR and detector for
real data, uncalibrated quality flags, no API authentication, Docker image build not executed.

## G. Run the project

```powershell
.\scripts\setup.ps1                                     # once (-Cpu for CPU only)
.\scripts\start_app.ps1                                 # UI: http://localhost:8501
.\scripts\start_api.ps1                                 # API: http://127.0.0.1:8765
.venv\Scripts\python -m src.workflow status
.venv\Scripts\python -m src.annotation queue
.venv\Scripts\python -m pytest tests/ -q ; .venv\Scripts\python -m mypy
.venv\Scripts\python -m src.synthetic demo              # SYNTHETIC demonstration
```

## H. Resume once expert data arrives

```powershell
python -m src.annotation integrity ; python -m src.annotation pilot ; python -m src.annotation disagreements
python -m src.annotation promote --pilot                   # dry run, then --execute --approve <digest> --approver <id>
python -m src.dataset near-duplicates ; python -m src.dataset split ; python -m src.dataset readiness
python -m src.training train                               # runs only if G1-G11 pass
python -m src.evaluation evaluate --checkpoint <best.pt> --robustness
python -m src.evaluation reproducibility
```
