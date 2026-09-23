"""Preprocessing tests (Milestone 3).

All images are synthetic geometric patterns from ``tests/fixtures/images/``. None
depicts pottery or any archaeological object.

The properties under test, in order of importance:

1. raw source images are never modified;
2. the same input produces byte-identical output;
3. corrupted and unsupported files are rejected, never repaired;
4. provenance (artifact_id, image_id, SHA-256) survives preprocessing.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from src.preprocessing import (
    PreprocessConfig,
    RawImmutabilityError,
    apply_exif_orientation,
    assess,
    load_image,
    map_box_to_original,
    preprocess_image,
    preprocess_to_disk,
    resize_preserving_aspect,
    save_result,
    sha256_file,
    to_model_array,
    to_rgb,
)
from src.preprocessing.pipeline import RAW_ROOT, _assert_not_raw
from src.preprocessing.transforms import TransformLog

IMAGES = "images"


@pytest.fixture(scope="session")
def images_dir(fixtures_dir):
    return fixtures_dir / IMAGES


@pytest.fixture
def cfg() -> PreprocessConfig:
    return PreprocessConfig.from_config()


def img(images_dir, name: str):
    return images_dir / name


# --------------------------------------------------------------------------- #
# Raw immutability - the single most important property here
# --------------------------------------------------------------------------- #


class TestRawImmutability:
    def test_source_bytes_and_mtime_unchanged(self, images_dir, tmp_path, cfg):
        source = tmp_path / "source.png"
        shutil.copy(img(images_dir, "rgb_gradient.png"), source)
        before_hash = sha256_file(source)
        before_mtime = source.stat().st_mtime_ns

        result = preprocess_image(source, config=cfg)
        save_result(result, tmp_path / "out" / "processed.png")

        assert sha256_file(source) == before_hash
        assert source.stat().st_mtime_ns == before_mtime

    def test_writing_into_data_raw_is_refused(self):
        with pytest.raises(RawImmutabilityError, match="raw research directory"):
            _assert_not_raw(RAW_ROOT / "site" / "anything.png")

    def test_writing_to_data_raw_itself_is_refused(self):
        with pytest.raises(RawImmutabilityError):
            _assert_not_raw(RAW_ROOT)

    def test_save_result_refuses_raw_destination(self, images_dir, cfg):
        result = preprocess_image(img(images_dir, "rgb_gradient.png"), config=cfg)
        with pytest.raises(RawImmutabilityError):
            save_result(result, RAW_ROOT / "escaped.png")

    def test_ordinary_output_path_is_allowed(self, tmp_path):
        _assert_not_raw(tmp_path / "interim" / "x.png")  # must not raise


# --------------------------------------------------------------------------- #
# Determinism
# --------------------------------------------------------------------------- #


class TestDeterminism:
    def test_same_input_gives_identical_bytes(self, images_dir, tmp_path, cfg):
        source = img(images_dir, "rgb_gradient.jpg")
        a = save_result(preprocess_image(source, config=cfg), tmp_path / "a.png")
        b = save_result(preprocess_image(source, config=cfg), tmp_path / "b.png")
        assert (tmp_path / "a.png").read_bytes() == (tmp_path / "b.png").read_bytes()
        assert a.processed_sha256 == b.processed_sha256

    def test_pixel_arrays_are_identical(self, images_dir, cfg):
        source = img(images_dir, "noise_sharp.png")
        a = preprocess_image(source, config=cfg)
        b = preprocess_image(source, config=cfg)
        assert np.array_equal(np.asarray(a.image), np.asarray(b.image))

    def test_normalised_arrays_are_identical(self, images_dir, cfg):
        source = img(images_dir, "rgb_gradient.png")
        a = preprocess_image(source, config=cfg).to_array()
        b = preprocess_image(source, config=cfg).to_array()
        assert np.array_equal(a, b)

    def test_quality_metrics_are_identical(self, images_dir, cfg):
        source = img(images_dir, "rgb_gradient.png")
        a = preprocess_image(source, config=cfg).quality.to_dict()
        b = preprocess_image(source, config=cfg).quality.to_dict()
        assert a == b

    def test_no_augmentation_randomness(self, images_dir, cfg):
        """Ten runs, one result. Any randomness would show up here."""
        source = img(images_dir, "rgb_gradient.png")
        hashes = {
            preprocess_image(source, config=cfg).image.tobytes()
            for _ in range(10)
        }
        assert len(hashes) == 1


# --------------------------------------------------------------------------- #
# Colour modes
# --------------------------------------------------------------------------- #


class TestColourModes:
    @pytest.mark.parametrize("name", [
        "rgb_gradient.png", "rgb_gradient.jpg", "rgb_gradient.tif", "rgb_gradient.bmp",
        "grayscale_checker.png", "rgba_transparent.png", "palette.png", "cmyk.jpg",
        "grayscale_16bit.tif", "bilevel.png",
    ])
    def test_everything_becomes_rgb(self, images_dir, cfg, name):
        result = preprocess_image(img(images_dir, name), config=cfg)
        assert result.ok, [str(i) for i in result.errors]
        assert result.image.mode == "RGB"
        assert result.image.size == (cfg.target_size, cfg.target_size)

    def test_grayscale_channels_are_replicated(self):
        gray = Image.new("L", (8, 8), 137)
        rgb = to_rgb(gray)
        array = np.asarray(rgb)
        assert rgb.mode == "RGB"
        assert np.array_equal(array[:, :, 0], array[:, :, 1])
        assert np.array_equal(array[:, :, 1], array[:, :, 2])
        assert array[0, 0, 0] == 137

    def test_rgba_is_composited_not_dropped(self):
        """A transparent pixel must take the background colour, not the raw RGB."""
        rgba = Image.new("RGBA", (4, 4), (255, 0, 0, 0))  # fully transparent red
        log = TransformLog()
        out = to_rgb(rgba, alpha_background=(255, 255, 255), log=log)
        assert np.array_equal(np.asarray(out)[0, 0], [255, 255, 255])
        assert log.alpha_flattened
        assert log.alpha_background == (255, 255, 255)

    def test_alpha_background_is_configurable_and_recorded(self):
        rgba = Image.new("RGBA", (4, 4), (255, 0, 0, 0))
        log = TransformLog()
        out = to_rgb(rgba, alpha_background=(0, 0, 0), log=log)
        assert np.array_equal(np.asarray(out)[0, 0], [0, 0, 0])
        assert log.to_dict()["alpha_background"] == [0, 0, 0]

    def test_opaque_rgba_pixels_survive_flattening(self):
        rgba = Image.new("RGBA", (4, 4), (10, 200, 30, 255))
        assert np.array_equal(np.asarray(to_rgb(rgba))[0, 0], [10, 200, 30])

    def test_16bit_is_scaled_and_flagged(self, images_dir, cfg):
        result = preprocess_image(img(images_dir, "grayscale_16bit.tif"), config=cfg)
        assert result.ok
        assert result.transform_log.bit_depth_reduced is True

    def test_rgb_input_is_not_needlessly_copied(self):
        rgb = Image.new("RGB", (4, 4), (1, 2, 3))
        assert to_rgb(rgb) is rgb

    def test_to_model_array_rejects_non_rgb(self):
        with pytest.raises(ValueError, match="expected an RGB image"):
            to_model_array(Image.new("L", (4, 4)))


# --------------------------------------------------------------------------- #
# EXIF orientation
# --------------------------------------------------------------------------- #


class TestExifOrientation:
    def test_orientation_6_rotates(self, images_dir, cfg):
        """Stored landscape, displayed portrait."""
        stored = Image.open(img(images_dir, "exif_orientation_6.jpg"))
        assert stored.size == (64, 48)

        result = preprocess_image(img(images_dir, "exif_orientation_6.jpg"), config=cfg)
        assert result.transform_log.exif_transposed is True
        assert result.transform_log.exif_orientation == 6
        assert result.quality.width_px == 48
        assert result.quality.height_px == 64

    def test_orientation_1_is_a_no_op(self, images_dir, cfg):
        result = preprocess_image(img(images_dir, "exif_orientation_1.jpg"), config=cfg)
        assert result.transform_log.exif_transposed is False
        assert result.quality.width_px == 64

    def test_no_exif_is_a_no_op(self):
        log = TransformLog()
        image = Image.new("RGB", (6, 4), (1, 2, 3))
        out = apply_exif_orientation(image, log)
        assert out.size == (6, 4)
        assert log.exif_transposed is False

    def test_malformed_exif_does_not_crash(self):
        image = Image.new("RGB", (4, 4))
        image.info["exif"] = b"garbage-not-exif"
        apply_exif_orientation(image, TransformLog())  # must not raise


# --------------------------------------------------------------------------- #
# Geometry
# --------------------------------------------------------------------------- #


class TestResize:
    @pytest.mark.parametrize("size", [(100, 50), (50, 100), (64, 64), (400, 40)])
    def test_pad_preserves_aspect_ratio(self, size):
        log = TransformLog()
        image = Image.new("RGB", size, (200, 100, 50))
        out = resize_preserving_aspect(image, 224, strategy="pad", log=log)

        assert out.size == (224, 224)
        left, top, right, bottom = log.content_box
        content_w, content_h = right - left, bottom - top
        original_ratio = size[0] / size[1]
        # Relative, not absolute: the content box is whole pixels, so a 10:1 image
        # scaled to a 22px short side carries ~2% quantisation error by construction.
        assert abs(content_w / content_h - original_ratio) / original_ratio < 0.03

    def test_pad_does_not_lose_content(self):
        """Every non-background pixel of the original survives the letterbox."""
        image = Image.new("RGB", (100, 20), (255, 0, 0))
        log = TransformLog()
        out = resize_preserving_aspect(
            image, 224, strategy="pad", pad_color=(0, 0, 0), log=log
        )
        array = np.asarray(out)
        left, top, right, bottom = log.content_box
        content = array[top:bottom, left:right]
        assert (content[:, :, 0] > 200).all()

    def test_pad_colour_fills_the_letterbox(self):
        image = Image.new("RGB", (100, 20), (255, 255, 255))
        out = resize_preserving_aspect(image, 224, strategy="pad", pad_color=(0, 0, 0))
        assert np.array_equal(np.asarray(out)[0, 0], [0, 0, 0])

    def test_crop_fills_the_square(self):
        log = TransformLog()
        image = Image.new("RGB", (400, 100), (255, 0, 0))
        out = resize_preserving_aspect(image, 224, strategy="crop", log=log)
        assert out.size == (224, 224)
        assert (np.asarray(out)[:, :, 0] > 200).all()
        assert log.crop_box is not None

    def test_square_input_needs_no_padding(self):
        log = TransformLog()
        resize_preserving_aspect(Image.new("RGB", (64, 64)), 224, strategy="pad", log=log)
        assert (log.pad_left, log.pad_top, log.pad_right, log.pad_bottom) == (0, 0, 0, 0)

    def test_upscaling_is_recorded(self, images_dir, cfg):
        result = preprocess_image(img(images_dir, "small_40x40.png"), config=cfg)
        assert result.transform_log.upscaled is True
        assert any(i.code == "P5" and "upscaled" in i.message for i in result.warnings)

    def test_downscaling_is_not_flagged_as_upscaling(self):
        log = TransformLog()
        resize_preserving_aspect(Image.new("RGB", (1000, 1000)), 224, log=log)
        assert log.upscaled is False

    def test_invalid_strategy_rejected(self):
        with pytest.raises(ValueError, match="unknown resize strategy"):
            resize_preserving_aspect(Image.new("RGB", (8, 8)), 224, strategy="squash")

    def test_invalid_resample_rejected(self):
        with pytest.raises(ValueError, match="unknown resample filter"):
            resize_preserving_aspect(Image.new("RGB", (8, 8)), 224, resample="magic")

    def test_invalid_target_rejected(self):
        with pytest.raises(ValueError, match="target must be positive"):
            resize_preserving_aspect(Image.new("RGB", (8, 8)), 0)

    def test_box_maps_back_to_original_coordinates(self):
        """Milestone 6 will need to report boxes against the original photograph."""
        log = TransformLog()
        resize_preserving_aspect(Image.new("RGB", (448, 224)), 224, strategy="pad", log=log)
        left, top, right, bottom = log.content_box
        mapped = map_box_to_original((left, top, right, bottom), log)
        assert mapped is not None
        assert abs(mapped[0] - 0) < 1 and abs(mapped[1] - 0) < 1
        assert abs(mapped[2] - 448) < 1 and abs(mapped[3] - 224) < 1


# --------------------------------------------------------------------------- #
# Normalisation
# --------------------------------------------------------------------------- #


class TestNormalisation:
    def test_shape_and_dtype(self, images_dir, cfg):
        array = preprocess_image(img(images_dir, "rgb_gradient.png"), config=cfg).to_array()
        assert array.shape == (3, cfg.target_size, cfg.target_size)
        assert array.dtype == np.float32

    def test_values_match_the_formula(self):
        image = Image.new("RGB", (2, 2), (128, 128, 128))
        array = to_model_array(image, mean=(0.5, 0.5, 0.5), std=(0.5, 0.5, 0.5))
        expected = (128 / 255 - 0.5) / 0.5
        assert np.allclose(array, expected, atol=1e-6)

    def test_channels_last_option(self):
        array = to_model_array(Image.new("RGB", (4, 6)), channels_first=False)
        assert array.shape == (6, 4, 3)

    def test_not_written_to_disk(self, images_dir, tmp_path, cfg):
        """The cache stores a PNG, not a float array - see the docstring rationale."""
        result = preprocess_image(img(images_dir, "rgb_gradient.png"), config=cfg)
        save_result(result, tmp_path / "out.png")
        assert not list(tmp_path.glob("*.npy"))
        assert {p.suffix for p in tmp_path.iterdir()} == {".png", ".json"}


# --------------------------------------------------------------------------- #
# Failure handling - never silently repaired
# --------------------------------------------------------------------------- #


class TestFailures:
    def test_truncated_image_is_rejected(self, images_dir, cfg):
        """A half-decoded photograph could be missing the inscription."""
        result = preprocess_image(img(images_dir, "truncated.jpg"), config=cfg)
        assert not result.ok
        assert result.image is None
        assert any(i.code == "P3" for i in result.errors)

    def test_truncated_loading_is_disabled_globally(self):
        from PIL import ImageFile

        assert ImageFile.LOAD_TRUNCATED_IMAGES is False

    def test_text_masquerading_as_jpeg_is_rejected(self, images_dir, cfg):
        result = preprocess_image(img(images_dir, "not_an_image.jpg"), config=cfg)
        assert not result.ok
        assert any(i.code == "P2" for i in result.errors)

    def test_unsupported_format_is_rejected(self, images_dir, cfg):
        result = preprocess_image(img(images_dir, "unsupported.txt"), config=cfg)
        assert not result.ok
        assert any(i.code == "P2" for i in result.errors)

    def test_empty_file_is_rejected(self, images_dir, cfg):
        result = preprocess_image(img(images_dir, "empty.png"), config=cfg)
        assert not result.ok
        assert any(i.code == "P1" for i in result.errors)

    def test_missing_file_is_rejected(self, tmp_path, cfg):
        result = preprocess_image(tmp_path / "nope.png", config=cfg)
        assert not result.ok
        assert any(i.code == "P1" for i in result.errors)

    def test_directory_is_rejected(self, tmp_path, cfg):
        result = preprocess_image(tmp_path, config=cfg)
        assert not result.ok
        assert any(i.code == "P1" for i in result.errors)

    def test_below_minimum_dimension_is_rejected(self, images_dir, cfg):
        result = preprocess_image(img(images_dir, "tiny_8x8.png"), config=cfg)
        assert not result.ok
        assert any(i.code == "P5" for i in result.errors)

    def test_small_but_above_floor_is_accepted(self, images_dir, cfg):
        result = preprocess_image(img(images_dir, "small_40x40.png"), config=cfg)
        assert result.ok

    def test_extension_mismatch_warns_but_loads(self, images_dir, cfg):
        """A .png that is really a JPEG is a data-integrity signal, not a blocker."""
        result = preprocess_image(img(images_dir, "actually_jpeg.png"), config=cfg)
        assert result.ok
        assert any(i.code == "P7" for i in result.warnings)

    def test_failed_result_cannot_be_saved(self, images_dir, tmp_path, cfg):
        result = preprocess_image(img(images_dir, "truncated.jpg"), config=cfg)
        with pytest.raises(ValueError, match="nothing to save"):
            save_result(result, tmp_path / "x.png")

    def test_hash_mismatch_against_record_is_rejected(self, images_dir, cfg):
        record = {"artifact_id": "FIXTURE_A", "image_id": "FIXTURE_A__x__1",
                  "image_sha256": "0" * 64}
        result = preprocess_image(img(images_dir, "rgb_gradient.png"),
                                  config=cfg, record=record)
        assert not result.ok
        assert any("hash does not match" in i.message for i in result.errors)


# --------------------------------------------------------------------------- #
# Quality metrics
# --------------------------------------------------------------------------- #


class TestQualityMetrics:
    def test_core_fields_populated(self, images_dir, cfg):
        q = preprocess_image(img(images_dir, "rgb_gradient.png"), config=cfg).quality
        assert q.width_px == 64 and q.height_px == 48
        assert q.file_size_bytes > 0
        assert q.detected_format == "PNG"
        assert 0 <= q.brightness_mean <= 255
        assert q.aspect_ratio >= 1.0

    def test_sharp_beats_blurry(self, images_dir, cfg):
        sharp = preprocess_image(img(images_dir, "noise_sharp.png"), config=cfg).quality
        blurry = preprocess_image(img(images_dir, "smooth_blurry.png"), config=cfg).quality
        assert sharp.sharpness_laplacian_var > blurry.sharpness_laplacian_var
        assert "possibly_blurry" in blurry.flags
        assert "possibly_blurry" not in sharp.flags

    def test_dark_and_bright_flags(self, images_dir, cfg):
        dark = preprocess_image(img(images_dir, "dark_flat.png"), config=cfg).quality
        bright = preprocess_image(img(images_dir, "bright_flat.png"), config=cfg).quality
        assert "dark" in dark.flags and "low_contrast" in dark.flags
        assert "bright" in bright.flags

    def test_extreme_aspect_ratio_flagged(self, images_dir, cfg):
        q = preprocess_image(img(images_dir, "wide_400x40.png"), config=cfg).quality
        assert q.aspect_ratio == 10.0
        assert "extreme_aspect_ratio" in q.flags

    def test_low_resolution_flagged(self, images_dir, cfg):
        q = preprocess_image(img(images_dir, "rgb_gradient.png"), config=cfg).quality
        assert "low_resolution" in q.flags

    def test_effectively_grayscale_detected(self, images_dir, cfg):
        q = preprocess_image(img(images_dir, "rgb_but_grayscale.png"), config=cfg).quality
        assert q.is_effectively_grayscale is True
        assert "effectively_grayscale" in q.flags

    def test_colour_image_not_called_grayscale(self, images_dir, cfg):
        q = preprocess_image(img(images_dir, "noise_sharp.png"), config=cfg).quality
        assert q.is_effectively_grayscale is False

    def test_clipping_detected(self):
        q = assess(Image.new("RGB", (16, 16), (0, 0, 0)),
                   thresholds={"clip_fraction": 0.05})
        assert q.shadow_clip_fraction == 1.0
        assert "shadow_clipped" in q.flags

    def test_metrics_carry_the_disclaimer(self, images_dir, cfg):
        """Quality output must never travel without its caveat."""
        data = preprocess_image(img(images_dir, "rgb_gradient.png"),
                                config=cfg).quality.to_dict()
        assert "not archaeological judgements" in data["_disclaimer"]

    def test_no_archaeological_fields_in_quality(self, images_dir, cfg):
        """Guards against a future 'authenticity' or 'date' field creeping in."""
        data = preprocess_image(img(images_dir, "rgb_gradient.png"),
                                config=cfg).quality.to_dict()
        forbidden = {"authentic", "authenticity", "date", "period", "script",
                     "inscription", "genuine", "age"}
        assert not forbidden & {k.lower() for k in data}

    def test_measured_before_resize(self, images_dir, cfg):
        """Metrics describe the photograph, not the 224px copy."""
        q = preprocess_image(img(images_dir, "wide_400x40.png"), config=cfg).quality
        assert (q.width_px, q.height_px) == (400, 40)

    def test_thresholds_come_from_config(self, cfg):
        assert cfg.quality_thresholds
        assert "blur_laplacian_var" in cfg.quality_thresholds


# --------------------------------------------------------------------------- #
# Provenance
# --------------------------------------------------------------------------- #


class TestProvenance:
    def test_identity_is_preserved(self, images_dir, tmp_path, cfg, base_record):
        source = img(images_dir, "rgb_gradient.png")
        record = dict(base_record, image_sha256=sha256_file(source))

        result = preprocess_image(source, config=cfg, record=record)
        save_result(result, tmp_path / "out.png")
        sidecar = json.loads((tmp_path / "out.json").read_text(encoding="utf-8"))

        assert sidecar["identity"]["artifact_id"] == record["artifact_id"]
        assert sidecar["identity"]["image_id"] == record["image_id"]
        assert sidecar["source"]["source_sha256"] == record["image_sha256"]

    def test_source_sha256_matches_the_file(self, images_dir, cfg):
        source = img(images_dir, "rgb_gradient.png")
        result = preprocess_image(source, config=cfg)
        assert result.provenance["source_sha256"] == sha256_file(source)

    def test_processed_hash_recorded(self, images_dir, tmp_path, cfg):
        result = preprocess_image(img(images_dir, "rgb_gradient.png"), config=cfg)
        save_result(result, tmp_path / "out.png")
        assert result.processed_sha256 == sha256_file(tmp_path / "out.png")

    def test_source_and_processed_hashes_are_distinct(self, images_dir, tmp_path, cfg):
        result = preprocess_image(img(images_dir, "rgb_gradient.png"), config=cfg)
        save_result(result, tmp_path / "out.png")
        assert result.processed_sha256 != result.provenance["source_sha256"]

    def test_transform_log_written(self, images_dir, tmp_path, cfg):
        result = preprocess_image(img(images_dir, "rgba_transparent.png"), config=cfg)
        save_result(result, tmp_path / "out.png")
        sidecar = json.loads((tmp_path / "out.json").read_text(encoding="utf-8"))
        assert sidecar["transforms"]["alpha_flattened"] is True
        assert sidecar["transforms"]["steps"]

    def test_record_metadata_subset_carried(self, images_dir, tmp_path, cfg, base_record):
        source = img(images_dir, "rgb_gradient.png")
        record = dict(base_record, image_sha256=sha256_file(source))
        result = preprocess_image(source, config=cfg, record=record)
        save_result(result, tmp_path / "out.png")
        sidecar = json.loads((tmp_path / "out.json").read_text(encoding="utf-8"))
        meta = sidecar["record_metadata"]
        assert meta["script_type"] == record["script_type"]
        assert meta["license"] == record["license"]
        assert "transcription" not in meta, "the sidecar is not a second copy of the record"

    def test_sidecar_is_valid_json_with_disclaimer(self, images_dir, tmp_path, cfg):
        result = preprocess_image(img(images_dir, "rgb_gradient.png"), config=cfg)
        save_result(result, tmp_path / "out.png")
        sidecar = json.loads((tmp_path / "out.json").read_text(encoding="utf-8"))
        assert "not archaeological judgements" in sidecar["_disclaimer"]
        assert sidecar["config"]["target_size"] == cfg.target_size

    def test_sidecar_can_be_skipped(self, images_dir, tmp_path, cfg):
        result = preprocess_image(img(images_dir, "rgb_gradient.png"), config=cfg)
        save_result(result, tmp_path / "out.png", write_sidecar=False)
        assert not (tmp_path / "out.json").exists()

    def test_directory_structure_preserved(self, images_dir, tmp_path, cfg):
        """Two sherds with the same filename in different site folders must not collide."""
        base = tmp_path / "raw_like"
        for site in ("site_a", "site_b"):
            (base / site).mkdir(parents=True)
            shutil.copy(img(images_dir, "rgb_gradient.png"), base / site / "sherd.png")

        out = tmp_path / "out"
        for site in ("site_a", "site_b"):
            preprocess_to_disk(base / site / "sherd.png", out, relative_to=base, config=cfg)

        assert (out / "site_a" / "sherd.png").exists()
        assert (out / "site_b" / "sherd.png").exists()


# --------------------------------------------------------------------------- #
# Config and loader plumbing
# --------------------------------------------------------------------------- #


class TestConfig:
    def test_loaded_from_project_yaml(self, cfg):
        assert cfg.target_size == 224
        assert cfg.resize_strategy in ("pad", "crop")
        assert cfg.resample in ("nearest", "bilinear", "bicubic", "lanczos")

    def test_pad_is_the_default_strategy(self, cfg):
        """Centre-cropping can remove a sherd's edge, where inscriptions often sit."""
        assert cfg.resize_strategy == "pad"

    def test_override_respected(self, images_dir, cfg):
        cfg.target_size = 64
        result = preprocess_image(img(images_dir, "rgb_gradient.png"), config=cfg)
        assert result.image.size == (64, 64)

    def test_loader_reports_source_facts(self, images_dir):
        loaded = load_image(img(images_dir, "rgb_gradient.jpg"))
        facts = loaded.source_facts()
        assert facts["source_format"] == "JPEG"
        assert facts["source_width_px"] == 64
        assert facts["source_sha256"]

    def test_hash_can_be_skipped(self, images_dir):
        loaded = load_image(img(images_dir, "rgb_gradient.png"), compute_hash=False)
        assert loaded.sha256 is None


# --------------------------------------------------------------------------- #
# Fixture hygiene
# --------------------------------------------------------------------------- #


class TestFixtureHygiene:
    def test_images_live_outside_data(self, images_dir):
        from src.dataset.schema import ROOT

        assert not images_dir.is_relative_to(ROOT / "data")

    def test_every_image_under_data_is_accounted_for(self, images_dir):
        """Milestone 6: data/ may hold real acquired images, but only registered ones.

        raw/ and external/ -> each file is in the acquisition provenance registry with the
        same SHA-256; interim/ -> empty (staging is cleared); processed/ -> each image has a
        sidecar naming a registered source hash. No synthetic fixture image may appear.
        """
        import hashlib

        from src.acquisition.provenance import read_registry
        from src.dataset.schema import ROOT

        suffixes = {".jpg", ".jpeg", ".png", ".tif", ".tiff", ".bmp", ".webp"}
        registry = {p["local_path"]: p["image_sha256"] for p in read_registry()}
        registered_hashes = set(registry.values())
        fixture_hashes = {hashlib.sha256(p.read_bytes()).hexdigest()
                          for p in images_dir.rglob("*") if p.suffix.lower() in suffixes}

        def images(directory: str) -> list[Path]:
            return [p for p in (ROOT / "data" / directory).rglob("*")
                    if p.is_file() and p.suffix.lower() in suffixes]

        for directory in ("raw", "external"):
            for p in images(directory):
                rel = p.relative_to(ROOT).as_posix()
                digest = hashlib.sha256(p.read_bytes()).hexdigest()
                assert registry.get(rel) == digest, f"unregistered or altered image: {rel}"
                assert digest not in fixture_hashes, f"fixture image leaked: {rel}"
        assert not images("interim"), "acquisition staging was not cleared"
        for p in images("processed"):
            sidecar = p.with_suffix(".json")
            assert sidecar.exists(), f"processed image without sidecar: {p}"
            text = sidecar.read_text(encoding="utf-8")
            assert any(h in text for h in registered_hashes), f"untraceable derivative: {p}"

    def test_manifest_marks_images_synthetic(self, images_dir):
        manifest = json.loads((images_dir / "MANIFEST.json").read_text(encoding="utf-8"))
        assert "SYNTHETIC" in manifest["_WARNING"]
        assert "never research data" in manifest["_WARNING"].lower()

    def test_manifest_covers_every_image(self, images_dir):
        manifest = json.loads((images_dir / "MANIFEST.json").read_text(encoding="utf-8"))
        on_disk = {p.name for p in images_dir.iterdir() if p.name != "MANIFEST.json"}
        assert on_disk == set(manifest["files"])


class TestMpoSupport:
    """Milestone 6: many cameras write MPO (a JPEG plus extra preview frames)."""

    def test_mpo_is_read_as_jpeg_primary_frame(self, tmp_path):
        from PIL import Image

        from src.preprocessing.loader import load_image

        primary = Image.new("RGB", (64, 48), (200, 40, 40))       # SYNTHETIC
        secondary = Image.new("RGB", (64, 48), (40, 200, 40))
        path = tmp_path / "synthetic_mpo.jpg"
        primary.save(path, format="MPO", save_all=True, append_images=[secondary])
        loaded = load_image(path)
        assert loaded.ok, [str(i) for i in loaded.issues]
        assert loaded.detected_format == "MPO"
        assert loaded.image.size == (64, 48)
        r, g, _ = loaded.image.getpixel((10, 10))
        assert r > g                                   # primary (red) frame, not the preview
        assert any(i.code == "P2" and i.severity == "info" for i in loaded.issues)
        assert not any(i.code == "P7" for i in loaded.issues)
