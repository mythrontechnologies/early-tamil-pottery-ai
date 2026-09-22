# Milestone 3 — Completion Report

**Date:** 2026-09-23
**Scope:** image preprocessing pipeline
**Status:** complete. No model trained. No archaeological images downloaded, scraped or fabricated.

---

## 0. Environment (prerequisite)

| | |
|---|---|
| Interpreter | `.venv\Scripts\python.exe` — Python 3.13.7 |
| torch | `2.14.0+cu126` |
| CUDA available | **True** — NVIDIA RTX 4050 Laptop, 6.0 GiB |
| PyYAML / jsonschema / pytest | 6.0.3 / 4.26.0 / 9.1.1 |
| Also present | numpy 2.5.2, pillow 12.3.0, opencv 5.0.0, pandas 3.0.6, scikit-learn 1.9.1, matplotlib 3.11.2, streamlit 1.64.0 |

`pip install -r requirements.txt -r requirements-dev.txt` left the CUDA wheel in place, as
expected: `torch>=2.2` was already satisfied by `2.14.0+cu126`, so pip had no reason to
pull the CPU build from PyPI. Verified after the install, not assumed.

All 255 tests now run from `.venv`, not the global interpreter.

---

## 1. Architecture

`src/preprocessing/` is a four-module layer with a CLI. It depends only on Pillow and
NumPy — deliberately not OpenCV, which is in the project's requirements but is a heavy
import for what amounts to one 5-point stencil (see §4).

| Module | Responsibility |
|---|---|
| `loader.py` | File and image validation, safe decoding, SHA-256. Checks `P1`–`P7`. |
| `transforms.py` | EXIF orientation, colour-mode conversion, resize, pad/crop, normalisation. All deterministic. |
| `quality.py` | Image-quality metrics and flags. Carries its own disclaimer. |
| `pipeline.py` | Orchestration, provenance sidecar, raw-immutability guard (`P8`). |
| `__main__.py` | CLI: `inspect`, `run`, `checks`. |

```
input image
  -> file/image validation      loader.load_image            P1-P7
  -> EXIF orientation           apply_exif_orientation
  -> RGB conversion             to_rgb
  -> integrity + resolution     loader (P3/P5)
  -> quality metrics            quality.assess               measured at FULL size
  -> aspect-preserving resize   resize_preserving_aspect
  -> padding / cropping         (same call, strategy-dependent)
  -> model-ready normalisation  to_model_array               in memory, on demand
  -> processed PNG + JSON sidecar
```

Quality is measured **after** EXIF and colour conversion but **before** resizing, so the
numbers describe the photograph as taken rather than the 224 px copy. A test asserts this.

## 2. Validation checks

`P*` codes, parallel to the `E*` engineering checks in `src/dataset/validation.py` and
equally **not archaeological claims**. `python -m src.preprocessing checks` lists them.

| Code | Check | Severity |
|---|---|---|
| P1 | file exists, is a regular file, is non-empty | error |
| P2 | format is recognised and supported | error |
| P3 | image decodes without error (not corrupted or truncated) | error |
| P4 | image is within the decompression-bomb pixel limit | error |
| P5 | smallest dimension ≥ `min_dimension_px` (32) | error |
| P5 | image had to be upscaled to reach target size | warning |
| P6 | colour mode is convertible to RGB | error |
| P7 | extension matches the actual file format | warning |
| P8 | output path is not inside `data/raw` | raises |

A record-aware run adds one more: if the dataset record carries an `image_sha256` and the
file on disk disagrees, preprocessing **stops**. Silently preprocessing a file that is not
the one the record describes would corrupt the link between image and provenance.

## 3. Transformations

| Stage | Behaviour | Information lost? |
|---|---|---|
| **EXIF orientation** | `ImageOps.exif_transpose`, then the tag is dropped | no — baked into pixels |
| **Grayscale → RGB** | channel replication | no |
| **RGBA/LA → RGB** | composited onto `alpha_background` (default white), then flattened | **yes** — alpha discarded; recorded as `alpha_flattened` |
| **Palette (P/PA)** | expanded via RGBA so palette transparency is honoured | no |
| **CMYK / YCbCr / 1** | `Image.convert("RGB")` | colour-space approximation |
| **16-bit / float (`I;16`, `F`)** | rescaled to 8-bit by the image's own min/max | **yes** — recorded as `bit_depth_reduced` |
| **Resize** | aspect-preserving, LANCZOS, pinned filter | no (pad) / edges (crop) |
| **Pad** | letterbox to square, constant colour | no |
| **Crop** | centre crop after fill-resize | **yes** — edges discarded |
| **Normalisation** | `(x/255 − mean) / std`, CHW float32 | no |

Every one of these is written into the sidecar's `transforms` block. A later reader can
always tell what the model saw versus what the photograph contained.

**Why `pad` is the default.** A centre crop removes the edges of the frame. On a sherd
that is exactly where the break, the rim, and frequently part of an inscription sit.
Letterboxing keeps the whole fragment at the cost of some wasted canvas, which is the
right trade for this material. `crop` remains available via config or `--strategy`.

**Why alpha flattening is recorded rather than silent.** A cut-out sherd flattened onto
white and the same sherd flattened onto black are different images to a model. The choice
is a parameter, and the sidecar records which value was used.

**Why the normalised array is not written to disk.** A float32 224×224×3 array is roughly
25× the size of the PNG it came from, and the arithmetic is trivial at load time. Caching
it would also freeze the normalisation constants into the cache — and those constants
should change once they can be computed from a real training split, rather than borrowed
from ImageNet. `PreprocessResult.to_array()` computes it on demand.

## 4. Quality metrics

> **These describe the photograph, never the object.** A `possibly_blurry` flag means the
> pixels are soft. It says nothing about the sherd, its authenticity, its date, whether an
> inscription is present, or how it should be read.

The disclaimer is not just documentation: it is embedded in `QualityMetrics.to_dict()`, so
it travels into every sidecar, and two tests enforce it — one checks the text is present,
the other asserts no field named `authentic`, `date`, `period`, `script`, `inscription`,
`genuine` or `age` ever appears in the quality block.

| Metric | Meaning |
|---|---|
| `width_px`, `height_px`, `megapixels` | dimensions |
| `aspect_ratio` | long side / short side, always ≥ 1 |
| `file_size_bytes`, `color_mode`, `detected_format` | file facts |
| `brightness_mean`, `brightness_median` | exposure, 0–255 (BT.601 luma) |
| `contrast_std` | standard deviation of luma |
| `dynamic_range` | p99 − p1, robust to stray pixels |
| `sharpness_laplacian_var` | variance of the discrete Laplacian |
| `shadow_clip_fraction`, `highlight_clip_fraction` | pixels pinned at 0 / 255 |
| `saturation_mean` | max(RGB) − min(RGB), the HSV definition |
| `is_effectively_grayscale` | RGB mode but identical channels — a grayscale scan |

Flags raised against configured thresholds: `low_resolution`, `possibly_blurry`, `dark`,
`bright`, `low_contrast`, `shadow_clipped`, `highlight_clipped`, `extreme_aspect_ratio`,
`effectively_grayscale`. **All are warnings.** None blocks processing.

The Laplacian variance is the standard blur indicator; the 5-point stencil is written
directly in NumPy rather than importing OpenCV for one function.

**The thresholds are uncalibrated.** They were chosen a priori and have never been
compared against a real pottery photograph, because none exists. They live in
`configs/project.yaml` precisely so they can be revised without touching code, and the
config block says so in a comment.

## 5. Determinism

Same input plus same config gives a byte-identical PNG. Guaranteed by:

- the resampling filter is **pinned** (`lanczos`), never left to a Pillow default that
  could change between versions and silently invalidate a cache;
- no augmentation — no random crop, flip, or jitter. Augmentation belongs in the training
  loop where its randomness is seeded and visible, not in a cached preprocessing step;
- `optimize=False` on PNG save, and PNG carries no timestamp;
- the fixture generator uses a fixed seed.

Five tests cover this, including one that runs the pipeline ten times and asserts a single
distinct result.

## 6. Raw immutability

The strongest guarantee in this milestone.

- Source files are opened read-only and never written.
- `_assert_not_raw()` raises `RawImmutabilityError` for any path equal to or beneath
  `data/raw`. It guards `save_result`, `preprocess_to_disk` and the output root.
- The CLI exits `2` rather than writing there. Verified: `--out data/raw` is refused, and
  `data/raw` still contains only `.gitkeep`.
- A test copies a source, preprocesses it, and asserts both the SHA-256 **and the mtime**
  are unchanged.

Outputs go to `data/interim/preprocessed/` by default, mirroring the source directory
structure so two sherds named `sherd.png` in different site folders cannot collide.

## 7. Provenance

Every processed image gets a JSON sidecar beside it:

```json
{
  "_disclaimer": "Image-quality indicators only. ...",
  "pipeline_version": "1.0.0",
  "identity":  { "artifact_id": "...", "image_id": "..." },
  "source":    { "source_sha256": "...", "source_format": "PNG", "source_mode": "RGBA", ... },
  "processed": { "path": "...", "sha256": "...", "width_px": 224, ... },
  "config":    { "target_size": 224, "resize_strategy": "pad", ... },
  "transforms":{ "steps": [...], "alpha_flattened": true, "content_box": [0, 28, 224, 196] },
  "quality":   { ... },
  "issues":    [ ... ],
  "record_metadata": { "script_type": "...", "license": "...", ... }
}
```

`record_metadata` carries a **fixed subset** of the dataset record (`PROVENANCE_FIELDS`),
not the whole thing. The sidecar is a traceability link, not a second copy of the dataset
that could drift out of sync with `records.jsonl`. A test asserts `transcription` is
absent.

`content_box` records where the real image sits inside the padded square. Milestone 6 will
predict inscription regions on the processed image and needs to report them against the
original photograph; `map_box_to_original()` inverts the mapping and is already tested.

## 8. Supported formats

| Container | Read | Notes |
|---|---|---|
| JPEG | ✅ | including CMYK JPEG and EXIF orientation |
| PNG | ✅ | including palette transparency |
| TIFF | ✅ | including 16-bit grayscale |
| BMP | ✅ | |
| WEBP | ✅ | configured; no fixture yet |

Colour modes handled: `1`, `L`, `LA`, `P`, `PA`, `RGB`, `RGBA`, `CMYK`, `YCbCr`, `I`,
`I;16`, `I;16B`, `F`. Anything else is rejected by `P6` rather than guessed at.

Output is always 8-bit RGB PNG — lossless, so preprocessing never adds a second round of
JPEG artefacts on top of whatever the source already carries.

**Format is detected from content, not extension.** A `.png` that is really a JPEG loads
correctly and raises a `P7` warning, because an extension that lies is a data-integrity
signal worth surfacing rather than a reason to fail.

## 9. Corruption is never repaired

`ImageFile.LOAD_TRUNCATED_IMAGES = False` is set explicitly at import, and a test asserts
it. Pillow's default would be to return a partially-decoded image with the missing region
filled grey. For this project that is the wrong behaviour: a half-decoded photograph that
*looks* fine could be missing exactly the region carrying the inscription.

Verified against a deliberately halved JPEG:

```
FAIL tests/fixtures/images/truncated.jpg
     [ERROR  ] P3: image is corrupted or truncated (OSError: Truncated File Read)
```

Rejected, reported with the exact reason, nothing written.

## 10. Fixtures

**26 synthetic images**, ~43 KB total, generated by `tests/fixtures/_generate_images.py`.
They are gradients, checkerboards and seeded noise. **None depicts pottery, an inscription
or any archaeological object.** `images/MANIFEST.json` states this and lists what each file
is for; a test asserts the manifest covers every file on disk, and another asserts every
fixture carries a `FIXTURE` or `SYNTHETIC` marker.

Coverage: four containers; ten colour modes; EXIF orientations 1 and 6; sizes from 8×8 to
400×40; aspect ratios to 10:1; deliberately dark, bright, sharp and smooth images; and six
failure cases (truncated, text-as-JPEG, unsupported extension, zero bytes, below-floor
dimensions, extension/content mismatch).

A test asserts no image file has appeared under `data/raw`, `data/interim`,
`data/processed` or `data/external`.

## 11. CLI

```bash
python -m src.preprocessing inspect <image|dir> [--json] [--size N] [--strategy pad|crop]
python -m src.preprocessing run     <image|dir> --out DIR [--no-sidecar] [...]
python -m src.preprocessing checks
```

`inspect` writes nothing. `run` writes images and sidecars, and refuses `data/raw`.
Exit codes `0` / `1` / `2` (success / image failures / usage), verified.

## 12. Tests

**255 passing**, up from 164. Preprocessing contributes 91.

| Group | Tests | Covers |
|---|---:|---|
| Raw immutability | 5 | bytes and mtime unchanged, guard on every write path |
| Determinism | 5 | byte-identical output, identical arrays, ten-run stability |
| Colour modes | 18 | RGB/grayscale/RGBA/palette/CMYK/16-bit/bilevel, compositing |
| EXIF orientation | 4 | orientation 6 rotates, 1 is a no-op, malformed EXIF survives |
| Geometry | 12 | aspect preservation, pad/crop, upscaling flags, box inversion |
| Normalisation | 4 | shape, dtype, formula, not written to disk |
| Failure handling | 12 | truncated, text-as-JPEG, unsupported, empty, tiny, hash mismatch |
| Quality metrics | 12 | each flag, disclaimer present, no archaeological fields |
| Provenance | 8 | identity, hashes, transform log, sidecar shape, no collisions |
| Config / loader | 6 | values from `project.yaml`, overrides, source facts |
| Fixture hygiene | 5 | outside `data/`, manifest complete, markers present |

## 13. Known limitations

1. **Thresholds are uncalibrated.** Every quality threshold was chosen a priori. On the
   synthetic fixtures nearly everything trips `low_resolution`, which tells you the
   fixtures are small, not that the thresholds are right. They must be re-tuned on real
   pottery photographs.
2. **No sherd segmentation.** The pipeline processes the whole frame. A photograph with a
   large background, a scale bar or a colour chart is passed through as-is, so a
   meaningful fraction of the 224 px may not be sherd. Background removal is a plausible
   Milestone 3.5, but it needs real images to develop against.
3. **The `pad`/`crop` choice is an assumption.** `pad` is reasoned, not measured. Which
   performs better is an empirical question that cannot be answered without data.
4. **ImageNet normalisation constants are borrowed.** They should be recomputed from the
   training split once one exists.
5. **16-bit scaling is per-image.** Each image is scaled by its own min/max, so two images
   of the same object under different exposures normalise differently. Correct for display,
   possibly wrong for comparison. Flagged but not solved.
6. **No WEBP fixture**, though the format is configured and supported.
7. **No colour management.** ICC profiles are ignored; an AdobeRGB photograph is treated as
   sRGB. This shifts colour in a way that matters for ware identification. Worth revisiting
   if colour features are ever used.
8. **`P4` is untested by fixture.** Testing the decompression-bomb limit would require
   committing a very large image; the code path exists and the limit is configurable.
9. **Quality metrics are global.** A photograph that is sharp on the sherd and blurred in
   the background scores as middling. Region-aware metrics would be better once there are
   regions to be aware of (Milestone 6).

## 14. Current status

| | |
|---|---|
| Real archaeological images | **0** |
| Records in `data/metadata/records.jsonl` | **0** |
| Processed research images | **0** |
| Synthetic fixture images | 26 (in `tests/fixtures/images/`, never in `data/`) |
| Models | none |
| Training ready | **false** |

`python -m src.dataset readiness` still reports
`"No real archaeological images are currently available"`, and
`assert_training_ready()` still raises.

## 15. Next blocker

Unchanged, and now the only thing standing between the project and Milestone 4:

> **Acquisition of trustworthy, properly sourced archaeological images.**

The gate needs ≥ 20 distinct **artifacts** per class across `tamil_brahmi`, `graffiti`,
`none` and `uncertain` — roughly 150–200 artifacts in total. `docs/DATA_INVENTORY.md` §3
sets out six acquisition routes and the non-data dependency: without an epigraphist,
`label_source` cannot rise above `project_annotation_unverified`, and any metric would
measure agreement with an untrained annotator rather than with the field.

Milestones 1–3 have built everything that can honestly be built without data. The pipeline
is ready to receive real photographs; it cannot invent them.
