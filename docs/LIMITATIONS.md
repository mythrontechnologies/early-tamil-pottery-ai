# Limitations

## Blocked by data
* **No trained model.** 0 expert-labelled artifacts; the `none` class has no candidate at all.
  Six pilot photographs could yield at most 4-6 labels; ≥20 per class are needed for holdout.
* **No evaluation metric on real data**, and none will exist until the gate passes.
* 17 artifacts come from museum/site photographs with **no excavation context**; no object can
  be dated from its own evidence today.

## Blocked by expert verification
* 0 human project annotations, 0 expert annotations.
* 0 references verified against their source (R1 bibliographic only; S01, S03 transcribed,
  unverified). R3 and R5 are unresolved author-level placeholders; R5's candidate work was
  identified from a secondary source only.
* 107 and 109 look like reproductions of 106 and 108 (unconfirmed; P10 blocks their promotion).

## Engineering limits
* The OCR, mark-analysis and detector stages are null implementations: no validated model
  exists. Every transcription today is "No reliable transcription established."
* Image-quality thresholds are uncalibrated heuristics (`possibly_blurry` fires on most
  6000×4000 museum photographs).
* The HTTP API has no authentication; it binds to localhost by default.
* The ledger detects tampering but cannot prevent someone who rewrites a store *and* its ledger;
  that leaves a different chain head, recorded in promotion entries and git history.
* Agreement statistics are not interpretable below 30 paired items.
* The Docker image build was not executed on this machine (Docker engine not running);
  `docker compose config` validates.
* No static type checker is configured (ruff lint only).
* Chronology positions (A-D) are unverified and contested; the tool reports them, it does not choose.
* Synthetic engineering results (Milestone 9) measure the pipeline on generated images. A model
  that does well on them has learned the generator, not pottery; synthetic accuracy, robustness
  and glyph-recognition scores are not forecasts of archaeological performance
  ([`SYNTHETIC_DATASET.md`](SYNTHETIC_DATASET.md) §10).
