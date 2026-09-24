# Dataset Policy

## What may enter the research dataset

1. **Rights first.** An image enters `data/raw` only through `src.acquisition` from an
   approved source, under an allowed licence (A1-A9), from an approved host, with a
   provenance record (source URL, licence, attribution, SHA-256). Or through written
   permission recorded in the provenance *before* the file is stored.
2. **Never:** copyrighted book or report plates, unauthorised mirrors (Scribd, pdfcoffee,
   unofficial Internet Archive uploads), synthetic/GAN images, duplicates or augmented copies
   counted as new artifacts, reproductions/replicas counted as separate artifacts.
3. **Identity** comes from provenance, not filenames. One physical object = one `artifact_id`;
   every photograph of it shares that id and one split (R3, G6).

## What may become a label

Only an **expert annotation**, `expert_reviewed`, agreeing with every other current expert
annotation, passing P1-P10, promoted through a dry run that a named human approves by digest,
written atomically, logged, and reversible. Never: AI output, project-only annotations,
disputed items, reproductions (P10), captions, site dates, anything inferred from appearance.

## Integrity

* `records.jsonl` and the provenance registry are changed only by acquisition and promotion.
* The annotation store, verification registry and promotion log are append-only and
  ledger-chained (`python -m src.annotation integrity`).
* `data/raw` is never written by preprocessing, inference, the UI or tests.
* Test fixtures live in `tests/fixtures/` or `tmp_path`, never in `data/`.

## Current state (2026-09-24)

17 research artifacts, 30 research images (CC BY / CC BY-SA, Wikimedia Commons), 0 labels,
0 human annotations, 0 verified references. 107 and 109 carry an unconfirmed
"possible reproduction" review flag. The `none` class has no candidate.
