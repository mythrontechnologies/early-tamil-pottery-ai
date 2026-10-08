# Limitations

## Blocked by data
* **No trained model.** 0 expert-labelled artifacts (21 artifacts / 34 photographs held, all unlabelled);
  the `none` class has no candidate an annotator could judge from both faces.
  Six pilot photographs could yield at most 4-6 labels; ≥20 per class are needed for holdout.
* **No evaluation metric on real data**, and none will exist until the gate passes.
* All 21 artifacts come from museum/site photographs with **no excavation context**; no object can
  be dated from its own evidence today.

## Blocked by expert verification
* 0 human project annotations, 0 expert annotations.
* 0 references verified against their source. Software pre-checks (Milestone 11) confirmed the
  bibliographic details of R1, S01 and S03 and found S01's 3 and S03's 6 claims at exact pages (one S03
  discrepancy, one claim only partly S03's), but a pre-check is not verification. R1's claim needs a library
  copy. R3 and R5 are unresolved author-level placeholders; R5's candidate work is now confirmed to exist
  (publisher's contents) but not identified as R5.
* 107 and 109 look like reproductions of 106 and 108 (unconfirmed; P10 blocks their promotion).

## Engineering limits
* The OCR, mark-analysis and detector stages are null implementations: no validated model
  exists. Every transcription today is "No reliable transcription established."
* Image-quality thresholds are uncalibrated heuristics (`possibly_blurry` fires on most
  6000×4000 museum photographs).
* The HTTP API has no authentication; it binds to localhost by default.
* Open sources are exhausted for this purpose: the Keezhadi Commons category holds no further individually
  photographed marked sherds; Target 1 (≥ 5 artifacts per class) needs an institutional permission.
* The near-duplicate guard catches copies of one photograph, not two different photographs of one object
  filed under two ids (that needs a human; review flag + P10 cover the known case).
* Detection and OCR evaluation exist but have nothing to score: no real detector or transcriber, no
  expert-promoted regions or readings.
* The ledger detects tampering but cannot prevent someone who rewrites a store *and* its ledger;
  that leaves a different chain head, recorded in promotion entries and git history.
* Agreement statistics are not interpretable below 30 paired items.
* The Docker image build was not executed on this machine (Docker engine not running);
  `docker compose config` validates.
* Static typing is checked by mypy with `ignore_missing_imports` (torchvision, cv2 and streamlit ship partial
  stubs), so calls into those libraries are only partly checked.
* Chronology positions (A-D) are unverified and contested; the tool reports them, it does not choose.
* Synthetic engineering results (Milestone 9) measure the pipeline on generated images. A model
  that does well on them has learned the generator, not pottery; synthetic accuracy, robustness
  and glyph-recognition scores are not forecasts of archaeological performance
  ([`SYNTHETIC_DATASET.md`](SYNTHETIC_DATASET.md) §10).
