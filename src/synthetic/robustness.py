"""Robustness of a synthetic checkpoint to photographic perturbations.

    python -m src.synthetic robustness --checkpoint <best.pt> [--partition test] [--json]

    Synthetic robustness is not archaeological robustness.

Every perturbation is applied to the held-out synthetic images at two severities and the model
re-scored (image and artifact level). The perturbations are deterministic (seeded by image id).
``background`` re-renders the very same view through the generator with a different background,
so object pixels are unchanged and only the surroundings differ, which a post-hoc filter cannot do.
"""

from __future__ import annotations

import hashlib
import io
import math
from collections.abc import Callable
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image, ImageFilter

from src.dataset.loader import DatasetRecord
from src.training.augmentation import ImageGeometry, build_eval_transform
from src.training.data import PotteryImageDataset, load_rgb, make_loader

from . import DATASET_TYPE, EVALUATION_BANNER, MARKER, PURPOSE, ROBUSTNESS_NOTE, SYNTHETIC_LABELS
from .config import SyntheticDatasetConfig
from .dataset import synthetic_class_spec
from .evaluate import checkpoint_records, load_synthetic_model, save_report
from .generator import BACKGROUNDS, build_artifact, generate_view

Perturb = Callable[[Image.Image, np.random.Generator], Image.Image]


def _seed(name: str) -> np.random.Generator:
    return np.random.default_rng(int.from_bytes(hashlib.sha256(name.encode()).digest()[:8], "big"))


def _blur(sigma: float) -> Perturb:
    return lambda im, rng: im.filter(ImageFilter.GaussianBlur(sigma))


def _gain(factor: float) -> Perturb:
    return lambda im, rng: Image.fromarray(np.clip(np.asarray(im, np.float32) * factor, 0, 255).astype(np.uint8))


def _contrast(factor: float) -> Perturb:
    def f(im: Image.Image, rng: np.random.Generator) -> Image.Image:
        a = np.asarray(im, np.float32)
        return Image.fromarray(np.clip((a - a.mean()) * factor + a.mean(), 0, 255).astype(np.uint8))
    return f


def _noise(sigma: float) -> Perturb:
    def f(im: Image.Image, rng: np.random.Generator) -> Image.Image:
        a = np.asarray(im, np.float32)
        return Image.fromarray(np.clip(a + rng.normal(0, sigma, a.shape), 0, 255).astype(np.uint8))
    return f


def _jpeg(quality: int) -> Perturb:
    def f(im: Image.Image, rng: np.random.Generator) -> Image.Image:
        buf = io.BytesIO()
        im.save(buf, format="JPEG", quality=quality)
        return Image.open(io.BytesIO(buf.getvalue())).convert("RGB")
    return f


def _border(im: Image.Image) -> tuple[int, int, int]:
    a = np.asarray(im)
    edge = np.concatenate([a[0], a[-1], a[:, 0], a[:, -1]])
    return tuple(int(v) for v in np.median(edge, axis=0))  # type: ignore[return-value]


def _rotate(deg: float) -> Perturb:
    return lambda im, rng: im.rotate(deg, resample=Image.BILINEAR, expand=True, fillcolor=_border(im))


def _scale(factor: float) -> Perturb:
    def f(im: Image.Image, rng: np.random.Generator) -> Image.Image:
        w, h = im.size
        if factor < 1:     # object smaller in an unchanged frame
            small = im.resize((max(1, round(w * factor)), max(1, round(h * factor))), Image.LANCZOS)
            canvas = Image.new("RGB", (w, h), _border(im))
            canvas.paste(small, ((w - small.width) // 2, (h - small.height) // 2))
            return canvas
        cw, ch = round(w / factor), round(h / factor)   # zoom in: central crop
        left, top = (w - cw) // 2, (h - ch) // 2
        return im.crop((left, top, left + cw, top + ch))
    return f


def _occlude(fraction: float) -> Perturb:
    def f(im: Image.Image, rng: np.random.Generator) -> Image.Image:
        w, h = im.size
        side_w = int(math.sqrt(fraction * w * h * rng.uniform(0.6, 1.6)))
        side_h = int(fraction * w * h / max(side_w, 1))
        x, y = int(rng.integers(0, max(1, w - side_w))), int(rng.integers(0, max(1, h - side_h)))
        out = im.copy()
        out.paste(tuple(int(v) for v in rng.integers(40, 200, 3)), (x, y, x + side_w, y + side_h))
        return out
    return f


#: name -> (family, severity, perturbation). "background" is handled by re-rendering.
PERTURBATIONS: dict[str, tuple[str, str, Perturb | None]] = {
    "clean": ("clean", "none", None),
    "blur_sigma1": ("blur", "mild", _blur(1.0)),
    "blur_sigma2": ("blur", "moderate", _blur(2.0)),
    "exposure_0.7": ("exposure", "mild", _gain(0.7)),
    "exposure_0.5": ("exposure", "moderate", _gain(0.5)),
    "exposure_1.3": ("exposure", "mild", _gain(1.3)),
    "exposure_1.6": ("exposure", "moderate", _gain(1.6)),
    "contrast_0.7": ("contrast", "mild", _contrast(0.7)),
    "contrast_0.5": ("contrast", "moderate", _contrast(0.5)),
    "contrast_1.4": ("contrast", "mild", _contrast(1.4)),
    "noise_sigma8": ("noise", "mild", _noise(8.0)),
    "noise_sigma16": ("noise", "moderate", _noise(16.0)),
    "jpeg_q35": ("compression", "mild", _jpeg(35)),
    "jpeg_q15": ("compression", "moderate", _jpeg(15)),
    "rotate_+8": ("rotation", "mild", _rotate(8)),
    "rotate_-8": ("rotation", "mild", _rotate(-8)),
    "rotate_+15": ("rotation", "moderate", _rotate(15)),
    "scale_0.8": ("scale", "mild", _scale(0.8)),
    "scale_0.6": ("scale", "moderate", _scale(0.6)),
    "zoom_1.15": ("scale", "mild", _scale(1.15)),
    "occlusion_8pct": ("occlusion", "mild", _occlude(0.08)),
    "occlusion_16pct": ("occlusion", "moderate", _occlude(0.16)),
    "background_swap": ("background", "mild", None),
}


def _background_loader(records: list[DatasetRecord], cfg: SyntheticDatasetConfig) -> Callable[[Any], Image.Image]:
    """Re-render each view with another background kind and texture; object pixels are unchanged."""
    by_path = {Path(r.image_path).name: r for r in records}

    def load(path: Any) -> Image.Image:
        r = by_path[Path(path).name]
        rec = r.record
        state = build_artifact(cfg, rec["artifact_index"], rec["script_type"])
        from .generator import sample_view

        vp = sample_view(cfg, state, rec["view_index"])
        rng = _seed("background:" + r.image_id)
        others = [b for b in BACKGROUNDS if b != vp["background"]["kind"]]
        bg = {"kind": others[int(rng.integers(len(others)))], "hue": float(rng.uniform(0, 1)),
              "saturation": float(rng.uniform(0, 0.35)), "value": float(rng.uniform(0.25, 0.92)),
              "seed": int(rng.integers(0, 2**31 - 1))}
        gv = generate_view(cfg, state, rec["view_index"], overrides={"background": bg})
        return Image.open(io.BytesIO(gv.jpeg)).convert("RGB")
    return load


def run_robustness(checkpoint: Path | str, *, partition: str = "test", root: Path | str | None = None,
                   device: str = "auto", names: list[str] | None = None, save: bool = True,
                   config_path: Path | str | None = None) -> dict[str, Any]:
    from src.evaluation.metrics import aggregate_by_artifact, compute_metrics

    from .train import SyntheticTrainingConfig, resolve

    ckpt, _, trainer, info = load_synthetic_model(checkpoint, device)
    records = checkpoint_records(ckpt, partition, root)
    spec = synthetic_class_spec()
    cfg = trainer.cfg
    geometry = ImageGeometry.from_project(cfg.data.image_size)
    dcfg = SyntheticDatasetConfig.load(resolve(SyntheticTrainingConfig.load(config_path).dataset_config))
    if ckpt.get("synthetic", {}).get("dataset_config_digest") not in (None, dcfg.digest):
        raise ValueError("the dataset configuration differs from the one the checkpoint's dataset was made with; "
                         "background re-rendering would not reproduce its images")
    results: dict[str, Any] = {}
    for name in names or list(PERTURBATIONS):
        family, severity, fn = PERTURBATIONS[name]
        if name == "background_swap":
            loader = _background_loader(records, dcfg)
        elif fn is None:
            loader = load_rgb
        else:
            def loader(path: Any, _fn: Perturb = fn, _name: str = name) -> Image.Image:
                return _fn(load_rgb(path), _seed(f"{_name}:{Path(path).name}"))
        ds = PotteryImageDataset(records, spec, build_eval_transform(geometry), loader=loader)
        p = trainer.predict(make_loader(ds, train=False, batch_size=cfg.data.batch_size, seed=cfg.runtime.seed))
        img = compute_metrics(p.y_true, p.y_pred, SYNTHETIC_LABELS, y_prob=p.probabilities)
        aids = [records[i].artifact_id for i in p.indices]
        _, a_true, a_prob = aggregate_by_artifact(aids, p.y_true, p.probabilities)
        art = compute_metrics(a_true, list(a_prob.argmax(axis=1)), SYNTHETIC_LABELS, y_prob=a_prob)
        results[name] = {"family": family, "severity": severity, "images": img.n_samples, "artifacts": art.n_samples,
                         "image_accuracy": round(img.accuracy, 4),
                         "image_balanced_accuracy": round(img.balanced_accuracy or 0, 4),
                         "image_macro_f1": round(img.macro_f1 or 0, 4),
                         "artifact_accuracy": round(art.accuracy, 4),
                         "artifact_balanced_accuracy": round(art.balanced_accuracy or 0, 4),
                         "image_ece": img.calibration["ece"] if img.calibration else None,
                         "per_class_recall": {k: (round(v.recall, 4) if v.recall is not None else None)
                                              for k, v in img.per_class.items()}}
        print(f"  {name:<18} image bal.acc {results[name]['image_balanced_accuracy']:.4f}  "
              f"artifact bal.acc {results[name]['artifact_balanced_accuracy']:.4f}", flush=True)
    clean = results.get("clean")
    if clean:
        for r in results.values():
            r["delta_image_balanced_accuracy"] = round(r["image_balanced_accuracy"] - clean["image_balanced_accuracy"], 4)
    meta = ckpt.get("synthetic", {})
    report = {"banner": EVALUATION_BANNER, "note": ROBUSTNESS_NOTE, "dataset_type": DATASET_TYPE, "marker": MARKER,
              "purpose": PURPOSE, "checkpoint": str(checkpoint), "experiment_id": meta.get("experiment_id"),
              "model": ckpt["model_name"], "partition": partition, "device": info.device,
              "synthetic_fingerprint": meta.get("synthetic_fingerprint"), "results": results}
    if save:
        report["report_path"] = str(save_report(report, f"robustness_{partition}.json", config_path))
    return report


def render_robustness(rep: dict[str, Any]) -> str:
    L = ["#" * 72, f"#  {EVALUATION_BANNER}", f"#  {ROBUSTNESS_NOTE}", "#" * 72,
         f"checkpoint {rep['checkpoint']} (model {rep['model']}, partition {rep['partition']})", "",
         f"  {'perturbation':<18}{'family':<12}{'severity':<10}{'img bal.acc':>12}{'delta':>9}{'art bal.acc':>13}{'img ECE':>9}"]
    for name, r in rep["results"].items():
        L.append(f"  {name:<18}{r['family']:<12}{r['severity']:<10}{r['image_balanced_accuracy']:>12.4f}"
                 f"{r.get('delta_image_balanced_accuracy', 0):>+9.4f}{r['artifact_balanced_accuracy']:>13.4f}"
                 f"{(r['image_ece'] or 0):>9.4f}")
    if rep.get("report_path"):
        L.append(f"\nreport: {rep['report_path']}")
    return "\n".join(L)


__all__ = ["PERTURBATIONS", "render_robustness", "run_robustness"]
