# Final Engineering Status

**Date:** 2026-09-24
**Verdict:** everything engineering can honestly complete is complete. What remains is real
archaeological evidence (expert annotation and reference verification), enough labelled
artifacts per class, and then training. None of it can be engineered.

```text
Tests:              799 passed (23 test files)            ruff lint: clean
Research data:      17 artifacts / 30 images (Wikimedia Commons, CC BY / CC BY-SA), provenance 30/30
Labels:             0   (tamil_brahmi 0 | graffiti 0 | none 0 | uncertain 0)
Human annotations:  0 project, 0 expert                   Verified references: 0
Training:           BLOCKED (exit 3; G1-G6 pass, G7-G11 fail)   Evaluation: BLOCKED (exit 3)
Workflow:           stages 1-5 PASS; stage 6 (annotations) WAITING - HUMAN ACTION REQUIRED
```

Legend: **done** = implemented and tested · **blocked (data)** · **blocked (expert)** · **future**.

## Final engineering checklist

| # | Phase | Item | State |
|---|---|---|---|
| 1 | Audit | explicit ruff config incl. security rules; codebase lints clean | done |
| 1 | Audit | duplicated CLI console code → `src/console.py`; UTC dates; no absolute paths (tested) | done |
| 1 | Audit | unsafe checkpoint unpickling → `weights_only=True` + weight fingerprint | done |
| 1 | Audit | acquisition host allow-list (defence in depth) | done |
| 1 | Audit | static type checking | future (not configured) |
| 2 | Tests | +91 tests: hardening, integrity/KB, inference, evaluation, reasoning rules, workflow, training smoke, UI, deployment | done |
| 3 | Annotation | separate project/expert workflows; append-only; N11 no overwrite; object/reproduction status; references; mandatory provenance | done |
| 3 | Annotation | AI drafts stay AI (N15); tamper-evident ledger (N16); dry-run, reversible, logged promotion (P1-P10) | done |
| 3 | Annotation | real annotations | blocked (expert) |
| 4 | Reasoning | 11 rules each pinned by a test (insufficient evidence, AI never used, conflicts not averaged, no invented translation, names untranslated, no year 0, unverified caps confidence, insecure association, script = outer bound, disputes, determinism) | done |
| 5 | OCR pipeline | quality → regions → enhancement → mark analysis → OCR → screening → reasoning; OCR kept apart from epigraphy | done (null engines) |
| 5 | OCR pipeline | a validated Tamil-Brahmi/graffiti OCR or detector | blocked (data) |
| 6 | Knowledge base | every claim: id, source, provenance, status, scope, locator, notes, uncertainty (`knowledge entries`); K7/K8/V9 | done |
| 6 | Knowledge base | R3, R5 as explicit UNRESOLVED placeholders | done (identity blocked (expert)) |
| 6 | Knowledge base | any reference verified | blocked (expert) |
| 7 | Inference | `analyze(image)` Python API, CLI, HTTP API; human evidence only for hash-registered photos | done |
| 8 | UI | analysis page (13 sections, layers drawn apart) + annotation tool | done |
| 9 | Evaluation | accuracy, balanced accuracy, P/R/F1, per class, confusion, top-k, artifact-level, ECE/MCE/Brier, confidence analysis, CER/WER, reproducibility report, blocked path | done |
| 9 | Evaluation | any metric on real data | blocked (data) |
| 10 | Dataset | `python -m src.workflow status`: 11 stages in order with next command | done |
| 11 | Training | CUDA+AMP, checkpoint, **resume**, deterministic mode, early stopping, imbalance, artifact splits, leakage checks, experiment/config/dataset/model fingerprints, environment capture; smoke-tested on noise (CPU + RTX 4050) | done |
| 11 | Training | training on research data | blocked (data) |
| 12 | Deployment | requirements, setup/start scripts (PowerShell + bash), Dockerfile, compose, `.dockerignore`, LF pinning | done |
| 12 | Deployment | Docker image build | not run (Docker engine not running); `docker compose config` validates |
| 13 | Security | path traversal (E3), arbitrary file loading (API takes bytes only), oversized/bomb/truncated/corrupt images, unsafe pickle, command injection (no shell), URL hosts, provenance/annotation tampering, raw-data immutability | done (tested) |
| 13 | Security | API authentication | future (localhost-only by default; see DEPLOYMENT.md) |
| 14 | Docs | ARCHITECTURE, USER_GUIDE, ANNOTATION_GUIDE, DATASET_POLICY, MODEL_CARD, REPRODUCIBILITY, LIMITATIONS, DEPLOYMENT, this file | done |

## A. What is complete

Acquisition with licence and host gating; dataset validation, ingestion, audit, splits and the
readiness gate; deterministic preprocessing; the annotation system (UI, append-only
ledger-chained store, N1-N16, pilot, agreement, reversible promotion P1-P10); the knowledge
base and verification workflow (K1-K8, V1-V10, claim reports); evidence-based reasoning,
dating and translation; the inscription pipeline and classifier/detector/OCR interfaces;
`analyze(image)` with CLI and HTTP API; the Streamlit application; evaluation (incl.
calibration, OCR metrics, reproducibility); the training pipeline (incl. resume, safe
fingerprinted checkpoints); deployment files; documentation.

## B. What is tested

799 tests. Final audit (2026-09-24), all run live:

| Check | Result |
|---|---|
| `pytest tests/ -q` | 799 passed |
| `ruff check src app scripts tests` | clean |
| type checks | not configured |
| `python -m src.dataset audit` | PASS, 30 records, 0 missing hashes |
| provenance (`src.acquisition registry`, workflow stage 2) | 30/30 research records with provenance; 0 SHA-256 mismatches |
| `src.dataset validate ... --strict --verify-hashes` | PASS, hashes checked |
| preprocessing inspect (pilot image) | OK (`possibly_blurry`, uncalibrated) |
| `src.annotation validate` / `integrity` | PASS / all stores EMPTY (intact) |
| reasoning tests (`-k reason`) | 79 passed |
| `src.knowledge validate` | PASS (12 references, 0 verifications) |
| `src.annotation promote --dry-run --pilot` | 0 candidates, 6 rejected (P1: no human annotation) |
| `src.dataset readiness` / `src.training train` | not ready / exit 3 |
| `src.evaluation evaluate` | blocked, exit 3 |
| `src.inference analyze` (image 109) | registered, "Insufficient evidence", review flag shown |
| HTTP API `/health`, `/analyze` | ok; "Insufficient evidence" |
| `streamlit run app/main.py` (headless) | `/_stcore/health` ok |
| CUDA mixed-precision smoke test | passed (RTX 4050, synthetic noise) |

## C. Current dataset status

| | |
|---|---|
| Research artifacts | 17 |
| Research images | 30 |
| Supporting images (not training data) | 15 |
| Human annotations | 0 |
| Expert annotations | 0 |
| Verified references | 0 |
| Tamil-Brahmi / graffiti / none / uncertain | 0 / 0 / 0 / 0 |
| Review flags | 107 and 109: possible reproductions of 106 and 108 (unconfirmed) |

## D. Current training status

**BLOCKED** by gates G7-G11 (no training-eligible labels, no class present, no split
manifest). No model exists. No gate, class list or threshold was changed.

## E. Remaining human actions

1. **HUMAN:** confirm with the Keezhadi site museum or an expert whether 107/109 are reproductions, and get catalogue numbers for 105-110.
2. **HUMAN:** close `outputs/pilot_handoff/pilot_worksheet_expert.csv` in Excel, then `python -m src.annotation handoff` (it could not be regenerated while open).
3. **HUMAN (project annotator):** annotate the six pilot sherds independently.
4. **HUMAN (expert):** annotate them independently; `expert_reviewed` or `disputed`.
5. **HUMAN (verifier):** check the 10 key claims (R1, S01, S03) against authorised copies; identify the exact works behind R3 and R5.
6. **HUMAN (approver):** approve promotion by digest after the dry run.

## F. Remaining data acquisition

See `docs/NEXT_DATA_ACQUISITION.md`: ≥5 labelled artifacts per class for grouped CV (20 in
total), ≥20 per class for holdout (80). The `none` class needs controlled photography of
uninscribed sherds; Target 2 needs an institutional agreement (TNSDA / museum / university
collections).

## G. Known limitations

See `docs/LIMITATIONS.md`. In short: no model, no labels, no verified references, null OCR and
detector, uncalibrated quality flags, no API authentication, Docker image build not executed,
no type checker.

## H. Run the project

```powershell
.\scripts\setup.ps1                                     # once (-Cpu for CPU only)
.\scripts\start_app.ps1                                 # UI: http://localhost:8501
.\scripts\start_api.ps1                                 # API: http://127.0.0.1:8765
.venv\Scripts\python -m src.inference analyze photo.jpg
.venv\Scripts\python -m src.workflow status
.venv\Scripts\python -m pytest tests/ -q
```

## I. Resume once expert data arrives

```powershell
python -m src.workflow status                              # where you are
streamlit run app/main.py                                  # annotators and experts annotate
python -m src.annotation integrity                         # stores intact?
python -m src.annotation pilot
python -m src.annotation agreement                         # item-level disagreements
python -m src.knowledge import-checklist outputs\pilot_handoff\verification_checklist.csv            # dry run
python -m src.knowledge import-checklist outputs\pilot_handoff\verification_checklist.csv --commit   # verifier
python -m src.annotation promote --pilot                   # dry run
python -m src.annotation promote --execute --approve <digest> --approver <id>
python -m src.dataset split                                # once every class has labels
python -m src.dataset readiness
python -m src.training train                               # runs only if G1-G11 pass
python -m src.evaluation evaluate --checkpoint <best.pt>
python -m src.evaluation reproducibility
```
New images: `python -m src.acquisition plan <plan.yaml>` (dry run) then `--commit`; or, with
written permission, record the rights in the provenance before storing any file.
