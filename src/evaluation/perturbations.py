"""Photographic perturbations for robustness evaluation (shared by real and synthetic evaluation).

Each perturbation is ``f(image, rng) -> image`` and deterministic for a given generator; ``seed(name)``
derives the generator from an image id, so a re-run perturbs every image identically. They change
pixels only: lighting (exposure, contrast), blur, sensor noise, compression, rotation, scale / crop,
and partial occlusion. Background replacement needs the object's mask and therefore exists only in
the synthetic suite, where the generator can re-render a view (``src.synthetic.robustness``).

Moved here from ``src.synthetic.robustness`` in Milestone 11 so that real-data robustness evaluation
does not depend on the synthetic package. Robustness on synthetic images is not robustness on
photographs of pottery; the numbers are never mixed.
"""

from __future__ import annotations

import hashlib
import io
import math
from collections.abc import Callable

import numpy as np
from PIL import Image, ImageFilter

Perturb = Callable[[Image.Image, np.random.Generator], Image.Image]


def seed(name: str) -> np.random.Generator:
    return np.random.default_rng(int.from_bytes(hashlib.sha256(name.encode()).digest()[:8], "big"))


def blur(sigma: float) -> Perturb:
    return lambda im, rng: im.filter(ImageFilter.GaussianBlur(sigma))


def gain(factor: float) -> Perturb:
    return lambda im, rng: Image.fromarray(np.clip(np.asarray(im, np.float32) * factor, 0, 255).astype(np.uint8))


def contrast(factor: float) -> Perturb:
    def f(im: Image.Image, rng: np.random.Generator) -> Image.Image:
        a = np.asarray(im, np.float32)
        return Image.fromarray(np.clip((a - a.mean()) * factor + a.mean(), 0, 255).astype(np.uint8))
    return f


def noise(sigma: float) -> Perturb:
    def f(im: Image.Image, rng: np.random.Generator) -> Image.Image:
        a = np.asarray(im, np.float32)
        return Image.fromarray(np.clip(a + rng.normal(0, sigma, a.shape), 0, 255).astype(np.uint8))
    return f


def jpeg(quality: int) -> Perturb:
    def f(im: Image.Image, rng: np.random.Generator) -> Image.Image:
        buf = io.BytesIO()
        im.save(buf, format="JPEG", quality=quality)
        return Image.open(io.BytesIO(buf.getvalue())).convert("RGB")
    return f


def border(im: Image.Image) -> tuple[int, int, int]:
    a = np.asarray(im)
    edge = np.concatenate([a[0], a[-1], a[:, 0], a[:, -1]])
    return tuple(int(v) for v in np.median(edge, axis=0))  # type: ignore[return-value]


def rotate(deg: float) -> Perturb:
    return lambda im, rng: im.rotate(deg, resample=Image.Resampling.BILINEAR, expand=True, fillcolor=border(im))


def scale(factor: float) -> Perturb:
    def f(im: Image.Image, rng: np.random.Generator) -> Image.Image:
        w, h = im.size
        if factor < 1:     # object smaller in an unchanged frame
            small = im.resize((max(1, round(w * factor)), max(1, round(h * factor))), Image.Resampling.LANCZOS)
            canvas = Image.new("RGB", (w, h), border(im))
            canvas.paste(small, ((w - small.width) // 2, (h - small.height) // 2))
            return canvas
        cw, ch = round(w / factor), round(h / factor)   # zoom in: central crop
        left, top = (w - cw) // 2, (h - ch) // 2
        return im.crop((left, top, left + cw, top + ch))
    return f


def occlude(fraction: float) -> Perturb:
    def f(im: Image.Image, rng: np.random.Generator) -> Image.Image:
        w, h = im.size
        side_w = int(math.sqrt(fraction * w * h * rng.uniform(0.6, 1.6)))
        side_h = int(fraction * w * h / max(side_w, 1))
        x, y = int(rng.integers(0, max(1, w - side_w))), int(rng.integers(0, max(1, h - side_h)))
        out = im.copy()
        out.paste(tuple(int(v) for v in rng.integers(40, 200, 3)), (x, y, x + side_w, y + side_h))
        return out
    return f


#: name -> (family, severity, perturbation): every photographic perturbation at two severities.
PHOTOGRAPHIC: dict[str, tuple[str, str, Perturb | None]] = {
    "clean": ("clean", "none", None),
    "blur_sigma1": ("blur", "mild", blur(1.0)),
    "blur_sigma2": ("blur", "moderate", blur(2.0)),
    "exposure_0.7": ("lighting", "mild", gain(0.7)),
    "exposure_0.5": ("lighting", "moderate", gain(0.5)),
    "exposure_1.3": ("lighting", "mild", gain(1.3)),
    "exposure_1.6": ("lighting", "moderate", gain(1.6)),
    "contrast_0.7": ("lighting", "mild", contrast(0.7)),
    "contrast_0.5": ("lighting", "moderate", contrast(0.5)),
    "noise_sigma8": ("noise", "mild", noise(8.0)),
    "noise_sigma16": ("noise", "moderate", noise(16.0)),
    "jpeg_q35": ("compression", "mild", jpeg(35)),
    "jpeg_q15": ("compression", "moderate", jpeg(15)),
    "rotate_+8": ("rotation", "mild", rotate(8)),
    "rotate_-15": ("rotation", "moderate", rotate(-15)),
    "scale_0.8": ("scale", "mild", scale(0.8)),
    "scale_0.6": ("scale", "moderate", scale(0.6)),
    "crop_zoom_1.15": ("crop", "mild", scale(1.15)),
    "crop_zoom_1.4": ("crop", "moderate", scale(1.4)),
    "occlusion_8pct": ("occlusion", "mild", occlude(0.08)),
    "occlusion_16pct": ("occlusion", "moderate", occlude(0.16)),
}


__all__ = ["PHOTOGRAPHIC", "Perturb", "blur", "border", "contrast", "gain", "jpeg", "noise", "occlude", "rotate",
           "scale", "seed"]
