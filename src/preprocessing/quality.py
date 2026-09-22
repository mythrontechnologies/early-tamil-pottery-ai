"""Image-quality metrics.

> **These are properties of the photograph, never of the object.**
>
> A "blurry" flag means the pixels are soft. It says nothing about the sherd, its
> authenticity, its date, whether an inscription is present, or how it should be read.
> Nothing in this module may be used, directly or indirectly, as archaeological
> evidence, and the flags carry that statement with them into the output sidecar.

The metrics are deliberately simple, cheap and interpretable. Each one answers a
question a photographer would recognise: is it sharp, is it well exposed, is it big
enough. Thresholds live in ``configs/project.yaml`` rather than here, and are
**provisional** - they were chosen a priori and have never been calibrated against real
pottery photographs, because none exist yet.

Implemented with NumPy alone. The Laplacian variance below is the standard blur
indicator; writing the 5-point stencil directly avoids pulling OpenCV into what is
otherwise a Pillow + NumPy layer.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field as dc_field
from typing import Any

import numpy as np
from PIL import Image

DISCLAIMER = (
    "Image-quality indicators only. These describe the photograph, not the artifact. "
    "They are not archaeological judgements and must not be used as evidence about "
    "authenticity, date, or the presence or reading of an inscription."
)

#: Luminance weights (ITU-R BT.601), the usual basis for a perceptual grayscale.
_LUMA = np.array([0.299, 0.587, 0.114], dtype=np.float64)


@dataclass
class QualityMetrics:
    # Geometry
    width_px: int = 0
    height_px: int = 0
    megapixels: float = 0.0
    aspect_ratio: float = 0.0          # long side / short side, always >= 1
    is_portrait: bool = False

    # File
    file_size_bytes: int = 0
    color_mode: str = "unknown"
    detected_format: str | None = None

    # Exposure and tone, all on a 0-255 scale
    brightness_mean: float = 0.0
    brightness_median: float = 0.0
    contrast_std: float = 0.0
    dynamic_range: float = 0.0         # p99 - p1, robust to a few stray pixels

    # Focus
    sharpness_laplacian_var: float = 0.0

    # Clipping
    shadow_clip_fraction: float = 0.0  # pixels at 0
    highlight_clip_fraction: float = 0.0  # pixels at 255

    # Colour
    saturation_mean: float = 0.0       # 0-255
    is_effectively_grayscale: bool = False

    # Flags raised against the configured thresholds
    flags: list[str] = dc_field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["_disclaimer"] = DISCLAIMER
        return data

    def render(self) -> str:
        lines = [
            f"  dimensions        : {self.width_px} x {self.height_px} "
            f"({self.megapixels:.2f} MP, aspect {self.aspect_ratio:.2f}:1)",
            f"  file size         : {self.file_size_bytes:,} bytes",
            f"  colour mode       : {self.color_mode} ({self.detected_format})",
            f"  brightness (mean) : {self.brightness_mean:.1f} / 255",
            f"  contrast (std)    : {self.contrast_std:.1f}",
            f"  dynamic range     : {self.dynamic_range:.1f}",
            f"  sharpness (lap var): {self.sharpness_laplacian_var:.1f}",
            f"  shadow clipping   : {self.shadow_clip_fraction * 100:.2f}%",
            f"  highlight clipping: {self.highlight_clip_fraction * 100:.2f}%",
            f"  saturation (mean) : {self.saturation_mean:.1f}",
            f"  effectively gray  : {self.is_effectively_grayscale}",
        ]
        if self.flags:
            lines.append(f"  flags             : {', '.join(self.flags)}")
        else:
            lines.append("  flags             : none")
        return "\n".join(lines)


def laplacian_variance(gray: np.ndarray) -> float:
    """Variance of the discrete Laplacian - the standard blur indicator.

    A sharp image has strong second derivatives at edges and therefore high variance;
    a soft one has little. The absolute value is scene-dependent, so it is only
    meaningful compared against other photographs of similar subjects - which is why
    the threshold is configurable and currently uncalibrated.
    """
    if gray.shape[0] < 3 or gray.shape[1] < 3:
        return 0.0
    centre = gray[1:-1, 1:-1]
    lap = (
        4.0 * centre
        - gray[:-2, 1:-1]
        - gray[2:, 1:-1]
        - gray[1:-1, :-2]
        - gray[1:-1, 2:]
    )
    return float(np.var(lap))


def assess(
    image: Image.Image,
    *,
    file_size_bytes: int = 0,
    detected_format: str | None = None,
    color_mode: str | None = None,
    thresholds: dict[str, float] | None = None,
) -> QualityMetrics:
    """Compute quality metrics for an image.

    ``image`` should be the RGB image *after* EXIF and colour conversion but *before*
    resizing, so the metrics describe the photograph as taken rather than the
    downscaled copy.
    """
    thresholds = thresholds or {}
    rgb = image if image.mode == "RGB" else image.convert("RGB")
    array = np.asarray(rgb, dtype=np.float64)

    height, width = array.shape[0], array.shape[1]
    gray = array @ _LUMA

    long_side, short_side = max(width, height), max(1, min(width, height))

    metrics = QualityMetrics(
        width_px=width,
        height_px=height,
        megapixels=round(width * height / 1_000_000, 4),
        aspect_ratio=round(long_side / short_side, 4),
        is_portrait=height > width,
        file_size_bytes=file_size_bytes,
        color_mode=color_mode or image.mode,
        detected_format=detected_format,
        brightness_mean=round(float(gray.mean()), 3),
        brightness_median=round(float(np.median(gray)), 3),
        contrast_std=round(float(gray.std()), 3),
        sharpness_laplacian_var=round(laplacian_variance(gray), 3),
    )

    p1, p99 = np.percentile(gray, [1, 99])
    metrics.dynamic_range = round(float(p99 - p1), 3)

    total = array.shape[0] * array.shape[1]
    metrics.shadow_clip_fraction = round(float((gray <= 0.5).sum()) / total, 5)
    metrics.highlight_clip_fraction = round(float((gray >= 254.5).sum()) / total, 5)

    # Saturation as max(RGB) - min(RGB), the HSV definition scaled to 0-255.
    channel_max = array.max(axis=2)
    channel_min = array.min(axis=2)
    saturation = channel_max - channel_min
    metrics.saturation_mean = round(float(saturation.mean()), 3)
    # A "colour" photograph whose channels are identical is really a grayscale scan;
    # worth knowing before drawing conclusions from colour features.
    metrics.is_effectively_grayscale = bool(saturation.max() <= 1.0)

    metrics.flags = _flags(metrics, thresholds)
    return metrics


def _flags(m: QualityMetrics, t: dict[str, float]) -> list[str]:
    """Raise warning flags against the configured thresholds. Warnings only."""
    flags: list[str] = []

    min_dim_warn = t.get("min_dimension_warn")
    if min_dim_warn and min(m.width_px, m.height_px) < min_dim_warn:
        flags.append("low_resolution")

    blur = t.get("blur_laplacian_var")
    if blur is not None and m.sharpness_laplacian_var < blur:
        flags.append("possibly_blurry")

    dark = t.get("dark_mean")
    if dark is not None and m.brightness_mean < dark:
        flags.append("dark")

    bright = t.get("bright_mean")
    if bright is not None and m.brightness_mean > bright:
        flags.append("bright")

    low_contrast = t.get("low_contrast_std")
    if low_contrast is not None and m.contrast_std < low_contrast:
        flags.append("low_contrast")

    clip = t.get("clip_fraction")
    if clip is not None:
        if m.shadow_clip_fraction > clip:
            flags.append("shadow_clipped")
        if m.highlight_clip_fraction > clip:
            flags.append("highlight_clipped")

    max_aspect = t.get("max_aspect_ratio")
    if max_aspect is not None and m.aspect_ratio > max_aspect:
        flags.append("extreme_aspect_ratio")

    if m.is_effectively_grayscale and m.color_mode == "RGB":
        flags.append("effectively_grayscale")

    return flags


__all__ = ["DISCLAIMER", "QualityMetrics", "assess", "laplacian_variance"]
