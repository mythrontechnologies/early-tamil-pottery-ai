# data/synthetic — SYNTHETIC ENGINEERING DATASET

> **SYNTHETIC — NOT ARCHAEOLOGICAL EVIDENCE**
>
> The synthetic dataset exists solely for engineering and model-pipeline validation. It must not
> be interpreted as archaeological evidence or used to make claims about real Tamil Nadu pottery.

Everything here is drawn by `src/synthetic/generator.py`. No image is a photograph, no mark is a
historical inscription, and no record names a site, date, excavation, publication or person.
This folder is never read by the research loader, the readiness gate, the annotation store or
label promotion; synthetic data placed anywhere else under `data/` is refused.

Regenerate (deterministic: identical metadata; byte-identical images with the same Pillow build):

```bash
python -m src.synthetic generate --force     # images/, metadata/records.jsonl, manifests/, splits/
python -m src.synthetic verify               # must print RESULT: PASS
```

Tracked in git: this README, `manifests/dataset_lock.json` (every fingerprint) and
`splits/split_*.json`. Images and per-image JSONL are git-ignored. See
[`docs/SYNTHETIC_DATASET.md`](../../docs/SYNTHETIC_DATASET.md).
