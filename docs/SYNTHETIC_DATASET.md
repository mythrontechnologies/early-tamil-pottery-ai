# Synthetic engineering dataset (Milestone 9)

> **SYNTHETIC — NOT ARCHAEOLOGICAL EVIDENCE**
>
> The synthetic dataset exists solely for engineering and model-pipeline validation. It must not
> be interpreted as archaeological evidence or used to make claims about real Tamil Nadu pottery.

## 1. Purpose

The research dataset has no expert labels yet, so the training gate (G1–G11) is closed and the
model pipeline had never run end to end on images. This dataset lets every stage run —
generation, validation, artifact-level split, training, checkpoint, evaluation, robustness,
glyph-recognition benchmark, inference, HTTP API and Streamlit UI — **without** weakening a single
real-data gate and **without** inventing any archaeological fact.

It answers engineering questions only: does the code load, group, split, train, checkpoint,
evaluate, calibrate, serve and display correctly? It answers no question about pottery, scripts,
sites or dates.

## 2. What it is (and is not)

| | |
|---|---|
| Content | procedurally drawn images: an irregular "sherd" on a background, with abstract marks |
| Source | `src/synthetic/generator.py` (NumPy + OpenCV + Pillow); **no photograph is used anywhere** |
| Marks | invented glyph primitives (`SG00`–`SG15`) and abstract motifs; **no historical inscription is reproduced**, no published sign list or image was consulted |
| Location | `data/synthetic/` only (code-enforced; never `data/raw`, `data/external`, `data/interim`, `data/processed`, `data/metadata`) |
| Identifiers | `SYNTH-A0001` (object), `SYNTH-A0001-V1` (image), `SYNTH-ONLY-0001` (synthetic-only catalogue id) |
| Archaeological fields | fixed sentinels: `site`, `context`, `period`, `dating_basis`, `transcription`, `translation` are all `not_applicable` |
| Marker on every record | `dataset_type: synthetic`, `synthetic_marker: "SYNTHETIC — NOT ARCHAEOLOGICAL EVIDENCE"`, `label_warning: "Synthetic task label — not archaeological evidence."` |

There are no sites, excavations, catalogue numbers, dates, publications or named people in it.

## 3. Classes: synthetic visual task categories

| synthetic label | what the generator drew | `inscription_present` | output slot (mapping layer) |
|---|---|---|---|
| `synthetic_tamil_brahmi_like` | a left-to-right row of 3–8 synthetic glyphs on a baseline, sometimes two "words" | `yes` | slot of `tamil_brahmi` |
| `synthetic_graffiti_like` | 1–3 larger abstract motifs placed freely (burst, hatch, nested chevrons, spiral, zigzag band, concentric arcs, scribble) | `yes` | slot of `graffiti` |
| `synthetic_none` | no deliberate mark (only the scratches, cracks and pits every class has) | `no` | slot of `none` |
| `synthetic_uncertain` | marks deliberately degraded below legibility: `cut_row` (row cut by the break), `faint` (very shallow, eroded), `fragment` (isolated stroke pieces), `overscratched` (buried under dense scratches) | `uncertain` | slot of `uncertain` |

These labels mean **only** "which kind of procedural mark the generator drew". They do not mean
verified Tamil-Brahmi or verified graffiti, and "tamil_brahmi_like" says nothing about real
letterforms.

**The mapping layer** (`src.synthetic.ARCHITECTURE_SLOTS`) lets the unchanged 4-output classifier
be exercised: a synthetic label occupies the same *output index* as the real class named in the
table. That is a statement about tensor positions only. Checkpoints store the synthetic names, so
the class-list check refuses to load a synthetic model as a model of the real classes, and the
real labels (`configs/project.yaml`, `image_record.schema.json`) are untouched.

`unknown` and `uncertain` are never confused: the generator always knows what it drew, so no
record says `unknown`; `uncertain` is a class the generator produced on purpose.

## 4. The generator

Each **artifact** (object) is built once and photographed 2–3 times:

* outline: an irregular polygon with rough break edges (outlines too thin to hold any mark are
  redrawn from the same random stream, for every class alike);
* surface: one of five neutral colour families (`reddish`, `buff`, `grey`, `dark`, `two_tone`),
  multi-octave texture, temper speckles, slip wear, pale broken edges, curvature shading;
* marks: drawn into a groove (depth) map, so they render as incisions with relief that responds
  to the light direction;
* distractors on **every** class: scratches, cracks, pits.

Each **view** (photograph) draws its own: canvas size (300–420 px), background (studio paper,
cloth, soil, wood, grey card), scale, rotation (±20°), perspective, light direction and relief,
light gradient, cast shadow, exposure, contrast, white balance, vignetting, Gaussian or motion
blur, sensor noise, optional occluder (card or blob, ≤12 % of the frame) and JPEG quality (60–95).

**No leakage by construction.** Every random draw comes from
`numpy.random.default_rng([seed, artifact, stream])`. Only the `marks` stream sees the class; the
object, distractor, view-count and per-view streams never do. A test
(`test_photographic_conditions_never_see_the_class`) builds the same artifact index under all four
labels and checks that outline, surface, distractors and every view parameter are identical. So
colour, blur, framing or exposure cannot act as a label signature; classes share broad conditions.

Configuration: [`configs/synthetic_dataset.yaml`](../configs/synthetic_dataset.yaml) (strict loader,
unknown keys are errors).

## 5. Size and storage

> **Update 2026-10-09 — generator 1.1.0 (synthetic language).** The dataset was regenerated so that every Tamil-Brahmi-like row is a sentence of the invented synthetic language ([`SYNTHETIC_LANGUAGE.md`](SYNTHETIC_LANGUAGE.md); SYNTHETIC LANGUAGE — NOT TAMIL-BRAHMI); other classes are byte-identical and the split assignment is unchanged. The models were retrained. Current: records `4e6eb6684b50…`, synthetic `c57c6fb985433fae…`, split `a96ed8d18770…`; classifier `synthetic_20261009T065459Z_4e6eb668_s20261003_resnet18` (test artifact accuracy 0.872, balanced 0.872, macro F1 0.861; T = 2.886, ECE 0.114 → 0.021); vision bundle `vision_20261009T071624Z_4e6eb668_s20261003` (regions F1 0.627, rows F1 0.732, segmentation F1 0.967, end-to-end CER 0.091, WER 0.277); synthetic-language exact translation 0.826 on 86 held-out images (`benchmark_20261009T071739Z_test`). The tables below record the 2026-10-03 run (generator 1.0.0) and are kept as history.

Generated 2026-10-03 with generator 1.0.0, seed 20261003:

| | |
|---|---|
| Artifacts | **1,000** (250 per class) |
| Images | **2,202** (798 artifacts × 2 views, 202 × 3) |
| Images per class | brahmi-like 544 · graffiti-like 549 · none 562 · uncertain 547 |
| Uncertain modes | cut_row 120 · faint 133 · fragment 165 · overscratched 129 (images) |
| Storage | 37.2 MiB in total; 29.2 MiB of JPEG images |
| Duplicates / hash collisions | 0 / 0 |
| Generation time | 252 s on one CPU core |

## 6. Metadata, provenance, fingerprint

Files under `data/synthetic/`:

| file | content | in git |
|---|---|---|
| `images/SYNTH-A0001-V1.jpg` … | the images | no (regenerable) |
| `metadata/records.jsonl` | one record per image ([schema](../src/synthetic/synthetic_record.schema.json)) | no (regenerable) |
| `manifests/provenance.jsonl` | per image: generator version, seed, the five random-stream seeds, every artifact and view parameter, image SHA-256, config digest | no (regenerable) |
| `manifests/generation_run.json` | when, which git commit, which environment | no (not fingerprinted) |
| `manifests/dataset_lock.json` | counts and every fingerprint (deterministic) | **yes** |
| `splits/split_holdout_*.json` | the artifact-level split manifest | **yes** |

Every record carries `artifact_id`, `image_id`, `image_sha256`, `dataset_type`,
`synthetic_generator_version`, `generation_seed`, `source`, `site`, `period`, `dating_basis`,
`script_type`, `inscription_present`, `inscription_type`, `transcription`, `translation`, `view`,
`label_source` (`synthetic_ground_truth`), `label_confidence` (`high`: certainty that the generator
drew this category, not archaeological confidence), the ground-truth regions (row, glyph and mark
boxes with rotation-aware quads and visible fraction) and the glyph sequence.

**Fingerprints** (all in the lock):

* `records_fingerprint` — every field of every record (the same algorithm as the research data);
  split manifests are tied to it;
* `image_set_fingerprint` — `(image_id, artifact_id, image_sha256)` only;
* `metadata_fingerprint` — records without image hashes, so it is identical on any platform;
* `synthetic_fingerprint` — image hashes + metadata hash + generator version + configuration digest
  + split digest. Changing any meaningful component changes it (tested component by component).

Current values: records `52004dd5aca4…`, synthetic `d61e25c6dfe07878fd3a8d9bf47b434417691fefcf7ddb15f3e913855bc14240`,
config `bc4431587d87…`, split `6c1e3cab8bf3962f…`.

**Reproducibility.** Same seed + generator version + configuration → identical metadata and
parameters everywhere, and byte-identical JPEGs with the same Pillow/libjpeg build.
`python -m src.synthetic verify` re-renders a sample from seed alone and compares SHA-256 (V14).

## 7. Split

The research splitter (`src.dataset.splits.make_split`) is reused unchanged, with the synthetic
class list: artifact-level hold-out 70/15/15, stratified by label, secondarily balanced by
surface family, seed 20261003.

| partition | artifacts | images | per class |
|---|---|---|---|
| train | 700 | 1,538 | 175 each |
| val | 152 | 338 | 38 each |
| test | 148 | 326 | 37 each |

No artifact, image id or image hash appears in two partitions (checked by `verify_manifest`, by
`verify` V11 and by tests).

## 8. Commands

```bash
python -m src.synthetic generate [--force]      # data/synthetic/ + split (deterministic, ~4 min)
python -m src.synthetic split                   # re-split (same digest for the same data)
python -m src.synthetic stats [--json]
python -m src.synthetic verify [--regenerate N] # 14 checks incl. separation and reproducibility
```

`verify` checks: no synthetic file under the research data folders (V1), no synthetic record in
`data/metadata/records.jsonl` (V2), no synthetic annotation in the store (V3), schema/markers (V4),
ids (V5), files and hashes (V6), duplicates (V7), labels (V8), configured counts (V9), image folder
completeness (V10), split leakage (V11), lock (V12), generator version and seed (V13),
regeneration (V14).

## 9. Separation from archaeological data

| guard | where |
|---|---|
| synthetic files refused under `data/raw`, `external`, `interim`, `processed`, `metadata` | `assert_synthetic_destination` |
| research validator rule **E6**: a synthetic record is an error, even dressed in research fields | `src/dataset/validation.py` |
| readiness gate never reads `data/synthetic/`; a synthetic records file fails G1 and G4 | `src/dataset/readiness.py` (unchanged) |
| annotation rule **N17**: no annotation of a synthetic artifact, image or label | `src/annotation/validate.py` |
| promotion **P0**: synthetic records block a plan; synthetic artifacts are rejected | `src/annotation/promote.py` |
| checkpoints carry `dataset_type`; synthetic ones must carry the marker; loaders can demand a type | `src/training/checkpoint.py` |
| synthetic checkpoints/experiments/reports only under `models/synthetic/` | `assert_synthetic_model_destination` |
| inference: identity by SHA-256; synthetic images get only the synthetic model; real images never | `src/inference/__init__.py` |

Deleting `data/synthetic/` changes nothing about the research dataset or its readiness (tested).

## 10. Limitations

* The images are not photographs; a model that does well on them has learned the generator, not
  pottery. Synthetic accuracy is **not** a forecast of archaeological accuracy.
* The glyphs are invented, compound geometric shapes; recognising them says nothing about reading
  Tamil-Brahmi.
* `synthetic_uncertain` is defined by the generator's degradation modes; real uncertainty has
  other causes (wear patterns, partial knowledge, disputed readings) that are not modelled.
* JPEG bytes depend on the Pillow/libjpeg build; on another build the image hashes (and therefore
  `records_fingerprint`) can differ while `metadata_fingerprint` stays identical.
