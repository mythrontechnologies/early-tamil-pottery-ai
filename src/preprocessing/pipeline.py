"""The preprocessing pipeline.

    input image
        -> file/image validation        loader.load_image   (P1-P7)
        -> EXIF orientation             transforms.apply_exif_orientation
        -> RGB conversion               transforms.to_rgb
        -> integrity + resolution       loader + quality
        -> quality metrics              quality.assess      (on the full-size image)
        -> aspect-preserving resize     transforms.resize_preserving_aspect
        -> padding / cropping           (same call; strategy-dependent)
        -> model-ready normalisation    transforms.to_model_array (in memory)
        -> processed image + sidecar

Three guarantees:

**Raw is never touched.** The pipeline opens source files read-only and refuses to
write anywhere under ``data/raw`` (``P8``). A test asserts that source bytes and mtime
are unchanged after a run.

**Deterministic.** Same input plus same config gives a byte-identical PNG. The
resampling filter is pinned, no augmentation is applied, and no timestamp is written
into the output image.

**Provenance travels with the image.** Every processed image gets a JSON sidecar
carrying ``artifact_id``, ``image_id``, the source SHA-256, the processed SHA-256, the
full transform log and the quality metrics. A processed image is never an anonymous
array: it can always be traced back to the photograph and the record it came from.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field as dc_field
from datetime import date
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image

from .loader import Issue, LoadedImage, load_image, sha256_file
from .quality import DISCLAIMER, QualityMetrics, assess
from .transforms import (
    TransformLog,
    apply_exif_orientation,
    resize_preserving_aspect,
    to_model_array,
    to_rgb,
)

ROOT = Path(__file__).resolve().parents[2]
RAW_ROOT = ROOT / "data" / "raw"

DEFAULT_OUTPUT_ROOT = ROOT / "data" / "interim" / "preprocessed"


class RawImmutabilityError(RuntimeError):
    """Raised when an operation would write into ``data/raw``."""


def _assert_not_raw(path: Path) -> None:
    """P8 - refuse to write anywhere under the raw research directory."""
    try:
        resolved = path.resolve()
    except OSError:  # pragma: no cover - unresolvable path
        resolved = path
    raw = RAW_ROOT.resolve() if RAW_ROOT.exists() else RAW_ROOT
    if resolved == raw or raw in resolved.parents:
        raise RawImmutabilityError(
            f"refusing to write inside the raw research directory: {resolved}\n"
            "Raw images are the primary record and are never modified or overwritten."
        )


@dataclass
class PreprocessConfig:
    """Preprocessing parameters, normally loaded from ``configs/project.yaml``."""

    pipeline_version: str = "1.0.0"
    target_size: int = 224
    resize_strategy: str = "pad"
    resample: str = "lanczos"
    pad_color: tuple[int, int, int] = (0, 0, 0)
    alpha_background: tuple[int, int, int] = (255, 255, 255)
    output_format: str = "png"
    min_dimension_px: int = 32
    max_pixels: int | None = 178_956_970
    supported_formats: frozenset[str] = frozenset({"JPEG", "PNG", "TIFF", "BMP", "WEBP"})
    norm_mean: tuple[float, float, float] = (0.485, 0.456, 0.406)
    norm_std: tuple[float, float, float] = (0.229, 0.224, 0.225)
    quality_thresholds: dict[str, float] = dc_field(default_factory=dict)

    @classmethod
    def from_config(cls, config: dict[str, Any] | None = None) -> PreprocessConfig:
        if config is None:
            from src.dataset.schema import load_config

            config = load_config()
        section = dict(config.get("preprocessing", {}))
        norm = dict(section.get("normalization", {}))
        return cls(
            pipeline_version=str(section.get("pipeline_version", "1.0.0")),
            target_size=int(section.get("target_size", 224)),
            resize_strategy=str(section.get("resize_strategy", "pad")),
            resample=str(section.get("resample", "lanczos")),
            pad_color=tuple(section.get("pad_color", (0, 0, 0))),
            alpha_background=tuple(section.get("alpha_background", (255, 255, 255))),
            output_format=str(section.get("output_format", "png")),
            min_dimension_px=int(section.get("min_dimension_px", 32)),
            max_pixels=section.get("max_pixels"),
            supported_formats=frozenset(
                section.get("supported_formats", ["JPEG", "PNG", "TIFF", "BMP", "WEBP"])
            ),
            norm_mean=tuple(norm.get("mean", (0.485, 0.456, 0.406))),
            norm_std=tuple(norm.get("std", (0.229, 0.224, 0.225))),
            quality_thresholds=dict(section.get("quality_thresholds", {})),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "pipeline_version": self.pipeline_version,
            "target_size": self.target_size,
            "resize_strategy": self.resize_strategy,
            "resample": self.resample,
            "pad_color": list(self.pad_color),
            "alpha_background": list(self.alpha_background),
            "output_format": self.output_format,
            "min_dimension_px": self.min_dimension_px,
            "normalization": {"mean": list(self.norm_mean), "std": list(self.norm_std)},
        }


@dataclass
class PreprocessResult:
    source_path: str
    ok: bool
    issues: list[Issue] = dc_field(default_factory=list)
    image: Image.Image | None = None
    quality: QualityMetrics | None = None
    transform_log: TransformLog | None = None
    provenance: dict[str, Any] = dc_field(default_factory=dict)
    output_path: str | None = None
    sidecar_path: str | None = None
    processed_sha256: str | None = None

    @property
    def errors(self) -> list[Issue]:
        return [i for i in self.issues if i.severity == "error"]

    @property
    def warnings(self) -> list[Issue]:
        return [i for i in self.issues if i.severity == "warning"]

    def to_array(
        self, mean: tuple[float, ...] | None = None, std: tuple[float, ...] | None = None
    ) -> np.ndarray:
        """Normalised CHW float32 array. Computed on demand, never cached to disk."""
        if self.image is None:
            raise ValueError("no processed image available")
        kwargs: dict[str, Any] = {}
        if mean is not None:
            kwargs["mean"] = mean
        if std is not None:
            kwargs["std"] = std
        return to_model_array(self.image, **kwargs)

    def sidecar(self) -> dict[str, Any]:
        """The full provenance + quality record written next to the processed image."""
        return {
            "_disclaimer": DISCLAIMER,
            "pipeline_version": self.provenance.get("pipeline_version"),
            "processed_utc_date": self.provenance.get("processed_utc_date"),
            "identity": {
                "artifact_id": self.provenance.get("artifact_id"),
                "image_id": self.provenance.get("image_id"),
            },
            "source": {
                k: v for k, v in self.provenance.items() if k.startswith("source_")
            },
            "processed": {
                "path": self.output_path,
                "sha256": self.processed_sha256,
                "width_px": self.image.size[0] if self.image else None,
                "height_px": self.image.size[1] if self.image else None,
                "mode": self.image.mode if self.image else None,
            },
            "config": self.provenance.get("config"),
            "transforms": self.transform_log.to_dict() if self.transform_log else None,
            "quality": self.quality.to_dict() if self.quality else None,
            "issues": [i.to_dict() for i in self.issues],
            "record_metadata": self.provenance.get("record_metadata"),
        }

    def render(self) -> str:
        lines = [f"source : {self.source_path}", f"status : {'OK' if self.ok else 'FAILED'}"]
        if self.output_path:
            lines.append(f"output : {self.output_path}")
        if self.quality:
            lines.append("quality:")
            lines.append(self.quality.render())
        if self.transform_log:
            lines.append("transforms:")
            lines += [f"  {s}" for s in self.transform_log.steps]
        if self.issues:
            lines.append("issues:")
            lines += [f"  {i}" for i in self.issues]
        return "\n".join(lines)


#: Metadata fields copied from a dataset record into the sidecar, so a processed
#: image never loses its provenance. Deliberately a fixed list: the sidecar is not a
#: second copy of the dataset, only enough to trace the image back to its record.
PROVENANCE_FIELDS = (
    "artifact_id",
    "image_id",
    "image_sha256",
    "image_path",
    "source",
    "source_reference",
    "site",
    "catalogue_reference",
    "license",
    "redistributable",
    "script_type",
    "label_source",
    "verification_status",
)


def preprocess_image(
    source: Path | str,
    *,
    config: PreprocessConfig | None = None,
    record: dict[str, Any] | None = None,
    compute_hash: bool = True,
) -> PreprocessResult:
    """Run the full pipeline on one image. Does not write anything."""
    cfg = config or PreprocessConfig()
    source = Path(source)
    result = PreprocessResult(source_path=source.as_posix(), ok=False)

    loaded: LoadedImage = load_image(
        source,
        supported_formats=set(cfg.supported_formats),
        min_dimension_px=cfg.min_dimension_px,
        max_pixels=cfg.max_pixels,
        compute_hash=compute_hash,
    )
    result.issues.extend(loaded.issues)

    provenance: dict[str, Any] = {
        "pipeline_version": cfg.pipeline_version,
        "processed_utc_date": date.today().isoformat(),
        "config": cfg.to_dict(),
        **loaded.source_facts(),
    }
    if record:
        provenance["artifact_id"] = record.get("artifact_id")
        provenance["image_id"] = record.get("image_id")
        provenance["record_metadata"] = {
            k: record[k] for k in PROVENANCE_FIELDS if k in record
        }
        # If the record carries a hash, the file on disk must agree with it.
        declared = record.get("image_sha256")
        if (
            compute_hash
            and loaded.sha256
            and isinstance(declared, str)
            and len(declared) == 64
            and declared != loaded.sha256
        ):
            result.issues.append(
                Issue("P3", "error",
                      "file hash does not match the hash recorded in the dataset",
                      f"record={declared[:12]}... file={loaded.sha256[:12]}...")
            )
            result.provenance = provenance
            return result
    result.provenance = provenance

    if not loaded.ok or loaded.image is None:
        return result

    log = TransformLog()
    image = apply_exif_orientation(loaded.image, log)
    image = to_rgb(image, alpha_background=cfg.alpha_background, log=log)

    # Quality is measured on the full-size, orientation-corrected image, so the
    # numbers describe the photograph rather than the downscaled copy.
    result.quality = assess(
        image,
        file_size_bytes=loaded.file_size_bytes,
        detected_format=loaded.detected_format,
        color_mode=loaded.original_mode,
        thresholds=cfg.quality_thresholds,
    )

    processed = resize_preserving_aspect(
        image,
        cfg.target_size,
        strategy=cfg.resize_strategy,
        resample=cfg.resample,
        pad_color=cfg.pad_color,
        log=log,
    )

    if log.upscaled:
        result.issues.append(
            Issue("P5", "warning",
                  "image was upscaled to reach the target size",
                  f"scale factor {log.scale_factor:.3f}; upscaling invents no detail")
        )

    result.image = processed
    result.transform_log = log
    result.ok = True
    return result


def save_result(
    result: PreprocessResult,
    output_path: Path | str,
    *,
    write_sidecar: bool = True,
) -> PreprocessResult:
    """Write the processed image and its sidecar. Refuses to write into ``data/raw``."""
    if result.image is None:
        raise ValueError("nothing to save: preprocessing did not produce an image")

    output_path = Path(output_path)
    _assert_not_raw(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # optimize=False keeps output stable across Pillow builds; PNG carries no
    # timestamp, so repeated runs are byte-identical.
    result.image.save(output_path, format="PNG", optimize=False)

    result.output_path = output_path.as_posix()
    result.processed_sha256 = sha256_file(output_path)

    if write_sidecar:
        sidecar_path = output_path.with_suffix(".json")
        _assert_not_raw(sidecar_path)
        sidecar_path.write_text(
            json.dumps(result.sidecar(), indent=2, ensure_ascii=False, sort_keys=False) + "\n",
            encoding="utf-8",
        )
        result.sidecar_path = sidecar_path.as_posix()

    return result


def preprocess_to_disk(
    source: Path | str,
    output_root: Path | str | None = None,
    *,
    relative_to: Path | str | None = None,
    config: PreprocessConfig | None = None,
    record: dict[str, Any] | None = None,
) -> PreprocessResult:
    """Preprocess one image and write it under ``output_root``.

    The source's directory structure is preserved beneath ``output_root`` so that two
    sherds with the same filename in different site folders cannot collide.
    """
    source = Path(source)
    out_root = Path(output_root) if output_root else DEFAULT_OUTPUT_ROOT
    _assert_not_raw(out_root)

    result = preprocess_image(source, config=config, record=record)
    if not result.ok:
        return result

    base = Path(relative_to) if relative_to else source.parent
    try:
        relative = source.relative_to(base)
    except ValueError:
        relative = Path(source.name)

    return save_result(result, out_root / relative.with_suffix(".png"))


__all__ = [
    "DEFAULT_OUTPUT_ROOT",
    "PROVENANCE_FIELDS",
    "PreprocessConfig",
    "PreprocessResult",
    "RawImmutabilityError",
    "preprocess_image",
    "preprocess_to_disk",
    "save_result",
]
