"""Training augmentation and deterministic evaluation transforms.

Every augmentation here was admitted by asking one question: *could it change the
evidence a specialist would use to classify the sherd?* The full reasoning is in
``docs/TRAINING_FRAMEWORK.md`` §4. In short:

======================  =======  ====================================================
transformation          default  why
======================  =======  ====================================================
small rotation (±5°)    on       a photographer's hand; applied with ``expand=True``
                                 before letterboxing, so no corner of the sherd is cut
letterbox resize        on       same geometry as Milestone 3 preprocessing (pad, not crop)
scale-and-shift         on       shrink within the letterbox, shift only into the freed
                                 margin: provably never crops the sherd
brightness / contrast   on, mild lighting varies between photographs
saturation              tiny     surface colour distinguishes wares
hue                     0        ditto; a hue shift can turn red ware into something else
horizontal flip         OFF      mirrors letter forms; a mirrored Tamil-Brahmi glyph is
                                 not a valid character, and some mirror onto another one
vertical flip           absent   not offered
random resized crop     absent   can cut off an inscription at a break or rim
perspective / elastic   absent   distorts letter morphology
cutout / erasing / blur absent   can erase or soften the marks being classified
======================  =======  ====================================================

Evaluation transforms are deterministic: letterbox, tensor, normalise. Nothing random.
"""

from __future__ import annotations

import warnings
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any

import torch
from PIL import Image
from torchvision.transforms import v2
from torchvision.transforms.v2 import functional as F

from src.dataset.schema import load_config
from src.preprocessing.transforms import resize_preserving_aspect

from .config import AugmentationConfig


class HorizontalFlipWarning(UserWarning):
    """Emitted when horizontal flipping is enabled for script-bearing images."""


@dataclass(frozen=True)
class ImageGeometry:
    size: int
    pad_color: tuple[int, int, int]
    resample: str
    mean: tuple[float, float, float]
    std: tuple[float, float, float]

    @classmethod
    def from_project(cls, size: int | None = None, project: dict[str, Any] | None = None
                     ) -> ImageGeometry:
        pre = (project or load_config()).get("preprocessing", {})
        norm = pre.get("normalization", {})
        return cls(
            size=int(size or pre.get("target_size", 224)),
            pad_color=tuple(pre.get("pad_color", (0, 0, 0))),
            resample=str(pre.get("resample", "lanczos")),
            mean=tuple(norm.get("mean", (0.485, 0.456, 0.406))),
            std=tuple(norm.get("std", (0.229, 0.224, 0.225))),
        )


def _uniform(low: float, high: float) -> float:
    """Draw from torch's RNG so worker seeding makes augmentation reproducible."""
    if high <= low:
        return float(low)
    return float(torch.empty(1).uniform_(low, high).item())


class Letterbox:
    """Aspect-preserving resize onto a square canvas. Deterministic."""

    def __init__(self, geometry: ImageGeometry) -> None:
        self.g = geometry

    def __call__(self, image: Image.Image) -> Image.Image:
        return resize_preserving_aspect(image.convert("RGB"), self.g.size, strategy="pad",
                                        resample=self.g.resample, pad_color=self.g.pad_color)


class SmallRotation:
    """Rotate by a small random angle with ``expand=True`` (nothing leaves the frame)."""

    def __init__(self, max_degrees: float, fill: tuple[int, int, int]) -> None:
        self.max_degrees = float(max_degrees)
        self.fill = fill

    def __call__(self, image: Image.Image) -> Image.Image:
        if self.max_degrees <= 0:
            return image
        angle = _uniform(-self.max_degrees, self.max_degrees)
        return image.rotate(angle, resample=Image.Resampling.BILINEAR, expand=True, fillcolor=self.fill)


class SafeScaleShift:
    """Shrink the letterboxed square by ``s`` in ``[min_scale, 1]`` and place it inside
    the canvas. The offset is drawn from the margin the shrink frees up, so the whole
    original canvas, and with it the whole sherd, stays inside the frame."""

    def __init__(self, min_scale: float, translate: bool, fill: tuple[int, int, int]) -> None:
        self.min_scale = float(min_scale)
        self.translate = translate
        self.fill = fill

    def __call__(self, image: Image.Image) -> Image.Image:
        size = image.size[0]
        scale = _uniform(self.min_scale, 1.0)
        new = max(1, min(size, round(size * scale)))
        if new == size:
            return image
        shrunk = image.resize((new, new), Image.Resampling.BILINEAR)
        margin = size - new
        if self.translate:
            ox, oy = round(_uniform(0, margin)), round(_uniform(0, margin))
        else:
            ox = oy = margin // 2
        canvas = Image.new("RGB", (size, size), self.fill)
        canvas.paste(shrunk, (ox, oy))
        return canvas


class ToNormalizedTensor:
    def __init__(self, mean: Sequence[float], std: Sequence[float]) -> None:
        self.mean, self.std = list(mean), list(std)

    def __call__(self, image: Image.Image) -> torch.Tensor:
        tensor = F.to_dtype(F.to_image(image), torch.float32, scale=True)
        return F.normalize(tensor, self.mean, self.std)


class Compose:
    def __init__(self, steps: Sequence[Callable[[Any], Any]], deterministic: bool) -> None:
        self.steps = list(steps)
        self.deterministic = deterministic

    def __call__(self, image: Image.Image) -> torch.Tensor:
        out: Any = image
        for step in self.steps:
            out = step(out)
        return out

    def describe(self) -> list[str]:
        return [type(s).__name__ for s in self.steps]


def build_eval_transform(geometry: ImageGeometry) -> Compose:
    """Letterbox -> tensor -> normalise. No randomness, ever."""
    return Compose([Letterbox(geometry), ToNormalizedTensor(geometry.mean, geometry.std)],
                   deterministic=True)


def build_train_transform(aug: AugmentationConfig, geometry: ImageGeometry) -> Compose:
    """Conservative training augmentation. See the module docstring for the rationale."""
    if not aug.enabled:
        return Compose(build_eval_transform(geometry).steps, deterministic=True)
    steps: list[Callable[[Any], Any]] = []
    if aug.rotation_degrees > 0:
        steps.append(SmallRotation(aug.rotation_degrees, geometry.pad_color))
    steps.append(Letterbox(geometry))
    if aug.min_scale < 1.0:
        steps.append(SafeScaleShift(aug.min_scale, aug.translate, geometry.pad_color))
    if any((aug.brightness, aug.contrast, aug.saturation, aug.hue)):
        steps.append(v2.ColorJitter(brightness=aug.brightness, contrast=aug.contrast,
                                    saturation=aug.saturation, hue=aug.hue))
    if aug.horizontal_flip:
        warnings.warn(
            "horizontal_flip is enabled: mirrored images contain mirror-image letter forms "
            "that do not occur in Tamil-Brahmi. Use only with a documented justification.",
            HorizontalFlipWarning, stacklevel=2)
        steps.append(v2.RandomHorizontalFlip(p=0.5))
    steps.append(ToNormalizedTensor(geometry.mean, geometry.std))
    return Compose(steps, deterministic=False)


__all__ = [
    "Compose",
    "HorizontalFlipWarning",
    "ImageGeometry",
    "Letterbox",
    "SafeScaleShift",
    "SmallRotation",
    "ToNormalizedTensor",
    "build_eval_transform",
    "build_train_transform",
]
