"""Image transformations: EXIF, colour mode, resize, pad/crop, normalisation.

Every function here is deterministic. Given the same input array and the same
parameters, the output is bit-identical - no random crops, no random flips, no
dithering, no adaptive heuristics. Augmentation, if it is ever wanted, belongs in the
training loop where its randomness is visible and seeded, not in a preprocessing step
whose output is cached to disk.

The resampling filter is pinned rather than left to a default, because a default that
changes between Pillow versions would silently change every cached image.
"""

from __future__ import annotations

from dataclasses import dataclass
from dataclasses import field as dc_field
from typing import Any, Literal

import numpy as np
from PIL import Image, ImageOps

ResizeStrategy = Literal["pad", "crop"]

#: Name -> Pillow filter. Pinned so the pipeline is reproducible across versions.
RESAMPLE_FILTERS: dict[str, Image.Resampling] = {
    "nearest": Image.Resampling.NEAREST,
    "bilinear": Image.Resampling.BILINEAR,
    "bicubic": Image.Resampling.BICUBIC,
    "lanczos": Image.Resampling.LANCZOS,
}


@dataclass
class TransformLog:
    """What was actually done to the image, for the provenance sidecar.

    Several of these steps discard information (alpha, bit depth, the area outside a
    crop). Recording them means a later reader can tell what the model saw versus what
    the photograph contained.
    """

    steps: list[str] = dc_field(default_factory=list)
    exif_transposed: bool = False
    exif_orientation: int | None = None
    original_mode: str | None = None
    alpha_flattened: bool = False
    alpha_background: tuple[int, int, int] | None = None
    bit_depth_reduced: bool = False
    resize_strategy: str | None = None
    resample: str | None = None
    scale_factor: float | None = None
    upscaled: bool = False
    pad_left: int = 0
    pad_top: int = 0
    pad_right: int = 0
    pad_bottom: int = 0
    pad_color: tuple[int, int, int] | None = None
    crop_box: tuple[int, int, int, int] | None = None
    content_box: tuple[int, int, int, int] | None = None

    def record(self, step: str) -> None:
        self.steps.append(step)

    def to_dict(self) -> dict[str, Any]:
        return {
            "steps": list(self.steps),
            "exif_transposed": self.exif_transposed,
            "exif_orientation": self.exif_orientation,
            "original_mode": self.original_mode,
            "alpha_flattened": self.alpha_flattened,
            "alpha_background": list(self.alpha_background) if self.alpha_background else None,
            "bit_depth_reduced": self.bit_depth_reduced,
            "resize_strategy": self.resize_strategy,
            "resample": self.resample,
            "scale_factor": self.scale_factor,
            "upscaled": self.upscaled,
            "padding": {
                "left": self.pad_left, "top": self.pad_top,
                "right": self.pad_right, "bottom": self.pad_bottom,
            },
            "pad_color": list(self.pad_color) if self.pad_color else None,
            "crop_box": list(self.crop_box) if self.crop_box else None,
            # Where the real image sits inside the padded output. Milestone 6 needs
            # this to map a predicted box back to original-image coordinates.
            "content_box": list(self.content_box) if self.content_box else None,
        }


# --------------------------------------------------------------------------- #
# EXIF
# --------------------------------------------------------------------------- #


def apply_exif_orientation(image: Image.Image, log: TransformLog | None = None) -> Image.Image:
    """Rotate/flip per the EXIF orientation tag, then drop the tag.

    A photograph whose orientation lives only in EXIF will be read upright by some
    libraries and sideways by others. Baking the rotation into the pixels removes that
    inconsistency before anything else looks at the image.
    """
    orientation = None
    try:
        orientation = image.getexif().get(0x0112)
    except Exception:  # noqa: BLE001 - malformed EXIF is not fatal
        orientation = None

    transposed = ImageOps.exif_transpose(image)
    # exif_transpose returns a copy when it acts, and may return None for some inputs.
    if transposed is None:
        transposed = image

    changed = isinstance(orientation, int) and orientation not in (0, 1)
    if log is not None:
        log.exif_orientation = int(orientation) if isinstance(orientation, int) else None
        log.exif_transposed = changed
        log.record(f"exif_orientation({orientation if changed else 'none'})")
    return transposed


# --------------------------------------------------------------------------- #
# Colour mode
# --------------------------------------------------------------------------- #


def to_rgb(
    image: Image.Image,
    *,
    alpha_background: tuple[int, int, int] = (255, 255, 255),
    log: TransformLog | None = None,
) -> Image.Image:
    """Convert any supported mode to 8-bit RGB.

    Alpha is composited onto ``alpha_background`` and discarded. That choice changes
    pixel values, so it is recorded: a cut-out sherd flattened onto white and the same
    sherd flattened onto black are different images to a model.

    High-bit-depth modes (``I;16``, ``F``) are scaled to 8 bits by their own min/max
    range. This loses precision and is recorded as ``bit_depth_reduced``.
    """
    mode = image.mode
    if log is not None:
        log.original_mode = mode

    if mode == "RGB":
        if log is not None:
            log.record("to_rgb(already_rgb)")
        return image

    # High bit depth: scale to 8 bits before anything else.
    if mode in {"I", "I;16", "I;16B", "I;16L", "F"}:
        array = np.asarray(image).astype(np.float64)
        lo, hi = float(array.min()), float(array.max())
        if hi > lo:
            scaled = (array - lo) / (hi - lo) * 255.0
        else:
            scaled = np.zeros_like(array)
        image = Image.fromarray(scaled.round().astype(np.uint8), mode="L")
        if log is not None:
            log.bit_depth_reduced = True
            log.record(f"bit_depth_reduce({mode}->L, range=[{lo:g},{hi:g}])")
        mode = "L"

    # Palette images must go through RGBA to honour palette transparency.
    if mode in {"P", "PA"}:
        image = image.convert("RGBA")
        mode = "RGBA"
        if log is not None:
            log.record("palette_expand(P->RGBA)")

    if mode in {"RGBA", "LA"}:
        rgba = image.convert("RGBA")
        canvas = Image.new("RGBA", rgba.size, (*alpha_background, 255))
        flattened = Image.alpha_composite(canvas, rgba).convert("RGB")
        if log is not None:
            log.alpha_flattened = True
            log.alpha_background = alpha_background
            log.record(f"flatten_alpha(background={alpha_background})")
        return flattened

    converted = image.convert("RGB")
    if log is not None:
        log.record(f"to_rgb({mode}->RGB)")
    return converted


# --------------------------------------------------------------------------- #
# Geometry
# --------------------------------------------------------------------------- #


def resize_preserving_aspect(
    image: Image.Image,
    target: int,
    *,
    strategy: ResizeStrategy = "pad",
    resample: str = "lanczos",
    pad_color: tuple[int, int, int] = (0, 0, 0),
    log: TransformLog | None = None,
) -> Image.Image:
    """Resize to a ``target`` x ``target`` square while preserving aspect ratio.

    ``pad``  - fit the whole image inside the square and letterbox the remainder.
               Nothing is lost. This is the default, because a sherd's edge often
               carries the break, the rim, or part of an inscription.
    ``crop`` - fill the square and centre-crop the overflow. Nothing is distorted,
               but the edges are discarded.
    """
    if target <= 0:
        raise ValueError(f"target must be positive, got {target}")
    if strategy not in ("pad", "crop"):
        raise ValueError(f"unknown resize strategy {strategy!r} (use 'pad' or 'crop')")
    if resample not in RESAMPLE_FILTERS:
        raise ValueError(
            f"unknown resample filter {resample!r} "
            f"(use one of {', '.join(sorted(RESAMPLE_FILTERS))})"
        )

    filt = RESAMPLE_FILTERS[resample]
    width, height = image.size

    if log is not None:
        log.resize_strategy = strategy
        log.resample = resample

    if strategy == "pad":
        scale = min(target / width, target / height)
        new_w = max(1, min(target, round(width * scale)))
        new_h = max(1, min(target, round(height * scale)))
        resized = image.resize((new_w, new_h), filt)

        canvas = Image.new("RGB", (target, target), pad_color)
        left = (target - new_w) // 2
        top = (target - new_h) // 2
        canvas.paste(resized, (left, top))

        if log is not None:
            log.scale_factor = scale
            log.upscaled = scale > 1.0
            log.pad_left, log.pad_top = left, top
            log.pad_right = target - new_w - left
            log.pad_bottom = target - new_h - top
            log.pad_color = pad_color
            log.content_box = (left, top, left + new_w, top + new_h)
            log.record(
                f"resize_pad({width}x{height}->{new_w}x{new_h}, scale={scale:.6f}, "
                f"pad=({left},{top},{log.pad_right},{log.pad_bottom}))"
            )
        return canvas

    # crop
    scale = max(target / width, target / height)
    new_w = max(target, round(width * scale))
    new_h = max(target, round(height * scale))
    resized = image.resize((new_w, new_h), filt)

    left = (new_w - target) // 2
    top = (new_h - target) // 2
    box = (left, top, left + target, top + target)
    cropped = resized.crop(box)

    if log is not None:
        log.scale_factor = scale
        log.upscaled = scale > 1.0
        log.crop_box = box
        log.content_box = (0, 0, target, target)
        log.record(
            f"resize_crop({width}x{height}->{new_w}x{new_h}, scale={scale:.6f}, crop={box})"
        )
    return cropped


# --------------------------------------------------------------------------- #
# Model-ready normalisation
# --------------------------------------------------------------------------- #


def to_model_array(
    image: Image.Image,
    *,
    mean: tuple[float, float, float] = (0.485, 0.456, 0.406),
    std: tuple[float, float, float] = (0.229, 0.224, 0.225),
    channels_first: bool = True,
) -> np.ndarray:
    """Convert an RGB image to a normalised float32 array.

    Returns CHW by default, matching torch's convention. This is *not* written to disk
    by the pipeline: a float32 224x224x3 array is roughly 25x the size of the PNG it
    came from, and the operation is cheap enough to do at load time. Storing it would
    also freeze the normalisation constants into the cache, which is exactly what we
    want to be able to change once statistics can be computed from real training data.
    """
    if image.mode != "RGB":
        raise ValueError(f"expected an RGB image, got mode {image.mode!r}")

    array: np.ndarray = np.asarray(image, dtype=np.float32) / 255.0
    array = (array - np.asarray(mean, dtype=np.float32)) / np.asarray(std, dtype=np.float32)
    return np.transpose(array, (2, 0, 1)).copy() if channels_first else array


def map_box_to_original(
    box: tuple[float, float, float, float], log: TransformLog
) -> tuple[float, float, float, float] | None:
    """Map a box in processed-image coordinates back to the original image.

    Milestone 6 will predict inscription regions on the processed image and needs to
    report them against the original photograph. Returns ``None`` when the transform
    log lacks the information to invert the mapping.
    """
    if log.scale_factor is None or log.content_box is None:
        return None

    x0, y0, x1, y1 = box
    scale = log.scale_factor

    if log.resize_strategy == "pad":
        left, top = log.content_box[0], log.content_box[1]
        return ((x0 - left) / scale, (y0 - top) / scale,
                (x1 - left) / scale, (y1 - top) / scale)

    if log.resize_strategy == "crop" and log.crop_box is not None:
        left, top = log.crop_box[0], log.crop_box[1]
        return ((x0 + left) / scale, (y0 + top) / scale,
                (x1 + left) / scale, (y1 + top) / scale)

    return None


__all__ = [
    "RESAMPLE_FILTERS",
    "TransformLog",
    "apply_exif_orientation",
    "map_box_to_original",
    "resize_preserving_aspect",
    "to_model_array",
    "to_rgb",
]
