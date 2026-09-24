# Architecture

Early Tamil Pottery AI is an **assistive research tool**. Its architecture exists to keep
four kinds of statement apart and traceable. It has no trained model yet (training is gated
on expert-labelled data), and every component works, and is tested, without one.

| Layer | Who asserts it | Can become a training label? |
|---|---|---|
| AI observation | a model or heuristic (classifier, detector, OCR, quality flags) | **never** |
| Project annotation | a project annotator | never directly (provisional only) |
| Expert annotation | a qualified expert, `expert_reviewed` | only through reviewed, reversible promotion |
| Verified evidence | a named human checked a publication (verification registry) | n/a (supports claims) |

## Packages

```
src/
  acquisition/    licence-gated download from approved sources (Wikimedia Commons) + provenance registry
  dataset/        record schema, validation (E*/R*), ingestion, audit, splits, readiness gate (G1-G11)
  preprocessing/  guarded image loading (P1-P8), EXIF/colour, letterbox, technical quality metrics
  annotation/     append-only multi-annotator store (N1-N16), pilot, agreement, promotion (P1-P10), UI helpers
  knowledge/      knowledge base (K1-K8), claim list, verification registry (V1-V10), describe()
  reasoning/      deterministic evidence-based reasoning: script, reading, meaning, age, period, limitations
  dating/         signed-year arithmetic (no year 0), evidence-tiered age estimation, chronology positions
  translation/    translation / meaning: only what a human source established
  detection/      inscription regions (human / user / AI) + detector interface (NoDetector default)
  ocr/            enhancement (viewing aid), mark-analysis and OCR interfaces (null engines default)
  classification/ script classifier interface (NoModelClassifier default; CheckpointClassifier)
  inference/      analyze(image) -> InferenceResult; CLI; stdlib HTTP API
  training/       config, data loaders, model zoo, trainer (AMP, early stopping, resume), checkpoints
  evaluation/     metrics, calibration, OCR CER/WER, reproducibility report; gated CLI
  integrity.py    hash-chained ledgers for every append-only file
  workflow.py     the 11-stage data workflow, checked in order
  console.py      UTF-8 console set-up for every CLI
app/
  main.py         Streamlit entry: analysis page + annotation tool
  analyze.py      upload / pick a photograph; all result sections; layers drawn apart
  annotate.py     annotation tool (project annotator / expert), append-only
```

## Data flow

```
Wikimedia Commons ──(acquisition: licence A1-A9, host allow-list)──> data/raw + provenance registry
                                                                   └> data/metadata/records.jsonl (script_type = unknown)
records ──(dataset validation, strict, hashes)──> readiness gate G1-G11 ──X── training (BLOCKED)
photograph ──> annotate.py ──(N1-N16, ledger)──> annotations.jsonl ──> agreement ──> promotion (P1-P10, dry run,
                                                                                   human-approved, reversible, logged)
                                                                                   └> records.jsonl labels ──> split ──> training
knowledge/*.yaml + verification registry (V1-V10, ledger) ──> effective reference status ──> reasoning
photograph ──> inference.analyze ──> quality │ regions │ classifier* │ OCR* │ reasoning(human evidence only) ──> result
                                              (* AI observation, reported, never evidence)
```

## Invariants (each enforced in code and tested)

1. **Raw data is never modified.** Preprocessing refuses to write under `data/raw` (P8); inference writes nothing.
2. **Provenance is never blurred.** `provenance_type` is mandatory; AI output can only be `ai_prediction` (N15); experts cannot be overwritten (N11).
3. **Append-only is checkable.** Every append to the annotation store, verification registry and promotion log is chained in a ledger; tampering fails N16/V10 and blocks promotion.
4. **Human evidence attaches only to a registered photograph** (SHA-256 match) in `analyze`.
5. **No label without an expert.** Only `expert_label` status, P1-P10, a digest-matched human approval and a logged write produce a label; every promotion is reversible.
6. **No date without evidence**; no year 0; conflicting dates are never averaged; a site/caption date is never an object date.
7. **No translation without a source**; a personal name has none.
8. **Unverified references cap confidence**; placeholders (R3, R5) cannot be verified until identified (K8, V9).
9. **Training is gated** (G1-G11) and the gate takes no data paths or bypass flags.
10. **Safe deserialisation.** Checkpoints load with `weights_only=True`; weights are fingerprinted; YAML uses `safe_load`.

## Extension points

A trained model plugs in without touching the reasoning layer: implement `ScriptClassifier`
(`src.classification`), `RegionDetector` (`src.detection`), `MarkAnalyzer` / `Transcriber`
(`src.ocr`) and pass it to `analyze(...)`. Its output appears under *AI observation* only.
