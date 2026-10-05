"""Synthetic vision models: inscription-region detection, glyph segmentation, glyph recognition.

    SYNTHETIC ENGINEERING BENCHMARK — synthetic glyph codes, not a transcription of any script.

    python -m src.synthetic train-vision        # trains and saves a fingerprinted bundle

Models (all small enough for a 6 GB GPU, trained on the TRAIN split, selected on VAL):

* ``RegionNet`` (``RowNet`` with two output channels; stride-4 heat maps on a 256 px letterbox):
  channel 0 = glyph row, channel 1 = any synthetic inscription region (glyph row, abstract motif,
  degraded marks). Connected components of each map become boxes with a confidence (the peak
  probability); channel-1 boxes are reported as class ``synthetic_inscription_region``.
* ``GlyphCenterNet`` - a small encoder-decoder over a letterboxed row crop (96 x 384, stride 2)
  predicting a glyph-centre heat map and each glyph's width/height. This is the learned option of
  the segmentation comparison; the classical options are vertical projection (Milestone 9) and
  connected-component grouping.
* ``GlyphNet`` (Milestone 9) classifies each glyph crop into SG00-SG15.

Segmentation strategies are compared on the VALIDATION split and the best (by CER) is recorded in the
bundle manifest; the test split is only measured. Glyph codes have no sound, reading or meaning.
"""

from __future__ import annotations

import hashlib
import itertools
import json
import math
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from functools import partial
from pathlib import Path
from typing import Any

import cv2
import numpy as np
import torch
from torch import nn

from src.training.checkpoint import model_fingerprint

from . import DATASET_TYPE, MARKER, SYNTHETIC_MODELS_ROOT, assert_synthetic_model_destination
from .ocr_benchmark import (
    DET_PX,
    GlyphNet,
    RowNet,
    _iou,
    _letterbox,
    _normalise,
    _rgb,
    _row_target,
    _to_tensor,
    classify,
    deskew,
    enhanced_gray,
    glyph_crops,
    projection_boxes,
    square_crop,
    train_glyph_classifier,
)

VISION_DIR = SYNTHETIC_MODELS_ROOT / "vision"
REGION_CLASS = "synthetic_inscription_region"
ROW_CLASS = "synthetic_glyph_row"
CROP_H, CROP_W = 96, 384        # GlyphCenterNet input (letterboxed row crop)
STRATEGIES = ("projection", "components", "learned_centers")


def _device(device: str) -> torch.device:
    return torch.device("cuda" if device in ("auto", "cuda") and torch.cuda.is_available() else "cpu")


# --------------------------------------------------------------------------- #
# Ground truth
# --------------------------------------------------------------------------- #


def inscription_regions(record: Any) -> list[dict[str, Any]]:
    """Ground-truth synthetic inscription regions of an image: glyph rows and marks (not single glyphs)."""
    return [r for r in record["synthetic_regions"] if r["kind"] in ("glyph_row", "mark")]


def _region_targets(record: Any, W: int, H: int, k: float, ox: int, oy: int) -> np.ndarray:
    out = DET_PX // 4
    target = np.zeros((2, out, out), np.float32)
    target[0] = _row_target(record, W, H, k, ox, oy)
    for r in inscription_regions(record):
        if r["kind"] == "glyph_row":
            continue
        q = np.asarray(r["quad"], np.float32) * np.float32([W, H]) * k + np.float32([ox, oy])
        cv2.fillPoly(target[1], [np.round(q / 4 * 4).astype(np.int32)], 1.0, shift=2)
    target[1] = np.maximum(target[1], target[0])
    return target


# --------------------------------------------------------------------------- #
# Region detector
# --------------------------------------------------------------------------- #


def train_region_detector(train: list[Any], val: list[Any], *, epochs: int = 24, seed: int = 20261003,
                          device: str = "auto", log: Callable[[str], None] | None = None) -> tuple[RowNet, dict[str, Any]]:
    torch.manual_seed(seed)
    rng = np.random.default_rng(seed)
    dev = _device(device)

    def load(recs: list[Any]) -> tuple[np.ndarray, np.ndarray]:
        xs, ys = [], []
        for r in recs:
            rgb = _rgb(r.image_path)
            lb, k, ox, oy = _letterbox(rgb)
            xs.append(lb)
            ys.append(_region_targets(r.record, rgb.shape[1], rgb.shape[0], k, ox, oy))
        return np.stack(xs), np.stack(ys)

    xt, yt = load(train)
    xv, yv = load(val)
    net = RowNet(out_channels=2).to(dev)
    opt = torch.optim.AdamW(net.parameters(), lr=2e-3, weight_decay=1e-4)
    sched = torch.optim.lr_scheduler.CosineAnnealingLR(opt, T_max=epochs)
    pos = [max(1.0, float((1 - yt[:, c].mean()) / max(yt[:, c].mean(), 1e-6)) ** 0.5) for c in range(2)]
    bce = nn.BCEWithLogitsLoss(pos_weight=torch.tensor(pos, device=dev)[:, None, None])
    best, best_state, history = -1.0, None, []
    for epoch in range(epochs):
        net.train()
        order = rng.permutation(len(xt))
        for start in range(0, len(order), 32):
            idx = order[start:start + 32]
            xb = _to_tensor(xt[idx]).to(dev) * float(rng.uniform(0.8, 1.2)) + float(rng.uniform(-0.2, 0.2))
            yb = torch.from_numpy(yt[idx]).to(dev)
            logits = net(xb)
            prob = torch.sigmoid(logits)
            dice = 1 - (2 * (prob * yb).sum((0, 2, 3)) + 1) / (prob.sum((0, 2, 3)) + yb.sum((0, 2, 3)) + 1)
            loss = bce(logits, yb) + dice.mean()
            opt.zero_grad(set_to_none=True)
            loss.backward()
            opt.step()
        sched.step()
        net.eval()
        with torch.no_grad():
            pv = torch.cat([torch.sigmoid(net(_to_tensor(xv[i:i + 64]).to(dev))).cpu() for i in range(0, len(xv), 64)]).numpy()
        ious = []
        for c in range(2):
            pred, true = pv[:, c] > 0.5, yv[:, c] > 0.5
            union = float((pred | true).sum())
            ious.append(float((pred & true).sum()) / union if union else 0.0)
        score = float(np.mean(ious))
        history.append({"epoch": epoch, "val_pixel_iou_row": round(ious[0], 4), "val_pixel_iou_region": round(ious[1], 4)})
        if log:
            log(f"  region detector epoch {epoch:>2}  val pixel IoU row {ious[0]:.3f} region {ious[1]:.3f}")
        if score > best:
            best, best_state = score, {k: v.detach().cpu().clone() for k, v in net.state_dict().items()}
    assert best_state is not None
    net.load_state_dict(best_state)
    return net.cpu().eval(), {"best_val_mean_pixel_iou": round(best, 4), "history": history, "device": dev.type,
                              "train_images": len(xt), "val_images": len(xv)}


@dataclass
class DetectedRegion:
    x: float               # normalised to the image
    y: float
    width: float
    height: float
    confidence: float      # peak heat-map probability in the region (a model score, not evidence)
    kind: str              # synthetic_inscription_region | synthetic_glyph_row

    @property
    def box_px(self) -> tuple[float, float, float, float]:
        return self.x, self.y, self.width, self.height

    def pixels(self, W: int, H: int) -> tuple[int, int, int, int]:
        return (max(0, round(self.x * W)), max(0, round(self.y * H)),
                min(W, round((self.x + self.width) * W)), min(H, round((self.y + self.height) * H)))

    def to_dict(self) -> dict[str, Any]:
        return {"x": round(self.x, 5), "y": round(self.y, 5), "width": round(self.width, 5),
                "height": round(self.height, 5), "confidence": round(self.confidence, 4), "class": self.kind}


#: Region-channel post-processing, selected on the VALIDATION split (region F1 0.630, vs 0.561 at
#: threshold 0.5 without erosion): a higher threshold and one erosion step separate neighbouring motifs.
REGION_THRESHOLD, REGION_ERODE = 0.7, 1
ROW_THRESHOLD = 0.5


def _components(prob: np.ndarray, threshold: float, erode: int, k: float, ox: int, oy: int, W: int, H: int,
                kind: str) -> list[DetectedRegion]:
    mask = (prob > threshold).astype(np.uint8)
    if erode:
        mask = cv2.erode(mask, np.ones((3, 3), np.uint8), iterations=erode)
    n, labels, stats, _ = cv2.connectedComponentsWithStats(mask, connectivity=8)
    found = []
    for i in range(1, n):
        if stats[i][4] < (1 if erode else 3):
            continue
        x, y, w, h = (float(v) for v in stats[i][:4])
        x, y, w, h = x - erode, y - erode, w + 2 * erode, h + 2 * erode          # undo the erosion on the box
        x0, y0 = max(0.0, (x * 4 - ox) / k), max(0.0, (y * 4 - oy) / k)
        x1, y1 = min(float(W), ((x + w) * 4 - ox) / k), min(float(H), ((y + h) * 4 - oy) / k)
        if x1 - x0 < 2 or y1 - y0 < 2:
            continue
        found.append(DetectedRegion(x0 / W, y0 / H, (x1 - x0) / W, (y1 - y0) / H, float(prob[labels == i].max()), kind))
    return sorted(found, key=lambda r: -r.confidence)


def detect_regions(net: RowNet, rgb: np.ndarray, threshold: float = ROW_THRESHOLD) -> dict[str, list[DetectedRegion]]:
    """Regions (channel 1) and glyph rows (channel 0), each sorted by confidence."""
    H, W = rgb.shape[:2]
    lb, k, ox, oy = _letterbox(rgb)
    dev = next(net.parameters()).device
    with torch.no_grad():
        prob = torch.sigmoid(net(_to_tensor(lb[None]).to(dev)))[0].cpu().numpy()
    return {"rows": _components(prob[0], threshold, 0, k, ox, oy, W, H, ROW_CLASS),
            "regions": _components(prob[1], REGION_THRESHOLD, REGION_ERODE, k, ox, oy, W, H, REGION_CLASS)}


def match_boxes(pred: list[tuple[float, ...]], gt: list[tuple[float, ...]], thr: float = 0.5) -> list[tuple[int, int, float]]:
    """Greedy one-to-one matching by IoU (highest first)."""
    pairs = sorted(((_iou(p, g), i, j) for i, p in enumerate(pred) for j, g in enumerate(gt)), reverse=True)
    used_p, used_g, out = set(), set(), []
    for iou, i, j in pairs:
        if iou < thr or i in used_p or j in used_g:
            continue
        used_p.add(i)
        used_g.add(j)
        out.append((i, j, iou))
    return out


# --------------------------------------------------------------------------- #
# Segmentation
# --------------------------------------------------------------------------- #


@dataclass
class Glyph:
    """A segmented glyph in CROP pixel coordinates."""

    cx: float
    cy: float
    side: float
    u: tuple[float, float] = (1.0, 0.0)      # row direction
    word: int = 0
    crop: np.ndarray | None = field(default=None, repr=False)


def _inverse(rot: np.ndarray, x: float, y: float) -> tuple[float, float]:
    m = cv2.invertAffineTransform(rot)
    return float(m[0, 0] * x + m[0, 1] * y + m[0, 2]), float(m[1, 0] * x + m[1, 1] * y + m[1, 2])


def segment_projection(gray: np.ndarray) -> list[Glyph]:
    """Milestone 9: deskew, then split the row at empty columns of the ink projection."""
    d = deskew(gray)
    if d is None:
        return []
    out = []
    for x0, y0, x1, y1, word in projection_boxes(d):
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        side = max(x1 - x0, y1 - y0) * 1.5
        g = Glyph(*_inverse(d.rot, cx, cy), side=side / 1.24, word=word)
        g.crop = square_crop(d.gray, (cx, cy), np.array([1.0, 0]), np.array([0, 1.0]), side)
        out.append(g)
    return out


def segment_components(gray: np.ndarray) -> list[Glyph]:
    """Deskew, then group ink connected components whose extents along the row overlap into glyphs."""
    d = deskew(gray)
    if d is None:
        return []
    n, _, stats, _ = cv2.connectedComponentsWithStats(d.ink, connectivity=8)
    comps = sorted((tuple(int(v) for v in stats[i][:4]) for i in range(1, n) if stats[i][4] >= 5), key=lambda b: b[0])
    h = d.height
    groups: list[list[int]] = []                   # [x0, y0, x1, y1]
    for x, y, w, hh in comps:
        box = [x, y, x + w, y + hh]
        if groups:
            g = groups[-1]
            overlap = min(g[2], box[2]) - max(g[0], box[0])
            if (overlap > -0.1 * h and max(g[2], box[2]) - min(g[0], box[0]) < 1.1 * h):
                groups[-1] = [min(g[0], box[0]), min(g[1], box[1]), max(g[2], box[2]), max(g[3], box[3])]
                continue
        groups.append(box)
    groups = [g for g in groups if (g[2] - g[0]) >= 0.12 * h or (g[3] - g[1]) >= 0.3 * h]
    gaps = [b[0] - a[2] for a, b in itertools.pairwise(groups)]
    split = max(0.7 * h, 2.0 * float(np.median(gaps))) if gaps else math.inf
    out, word = [], 0
    for i, (x0, y0, x1, y1) in enumerate(groups):
        if i and gaps[i - 1] > split:
            word += 1
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        side = max(x1 - x0, y1 - y0) * 1.5
        g = Glyph(*_inverse(d.rot, cx, cy), side=side / 1.24, word=word)
        g.crop = square_crop(d.gray, (cx, cy), np.array([1.0, 0]), np.array([0, 1.0]), side)
        out.append(g)
    return out


class GlyphCenterNet(nn.Module):
    """Glyph-centre heat map + glyph (width, height) / CROP_H, at stride 2 of a 96 x 384 row crop."""

    def __init__(self) -> None:
        super().__init__()

        def block(i: int, o: int, d: int = 1) -> nn.Sequential:
            return nn.Sequential(nn.Conv2d(i, o, 3, padding=d, dilation=d, bias=False), nn.BatchNorm2d(o),
                                 nn.ReLU(inplace=True))

        self.f1 = nn.Sequential(block(1, 32), block(32, 32), nn.MaxPool2d(2))        # 48 x 192
        self.f2 = nn.Sequential(block(32, 64), block(64, 64), nn.MaxPool2d(2))       # 24 x 96
        self.ctx = nn.Sequential(block(64, 96, 2), block(96, 96, 4), block(96, 96, 8))
        self.fuse = block(96 + 32, 64)
        self.heat = nn.Conv2d(64, 1, 1)
        self.size = nn.Conv2d(64, 2, 1)
        nn.init.constant_(self.heat.bias, -2.2)

    def forward(self, x: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor]:
        f1 = self.f1(x)
        f3 = self.ctx(self.f2(f1))
        f = self.fuse(torch.cat([nn.functional.interpolate(f3, size=f1.shape[-2:], mode="bilinear",
                                                           align_corners=False), f1], dim=1))
        return self.heat(f), self.size(f)


def _crop_letterbox(gray: np.ndarray) -> tuple[np.ndarray, float, int, int]:
    h, w = gray.shape
    s = min(CROP_H / max(h, 1), CROP_W / max(w, 1))
    nh, nw = max(1, round(h * s)), max(1, round(w * s))
    canvas = np.full((CROP_H, CROP_W), int(np.median(gray)), np.uint8)
    oy, ox = (CROP_H - nh) // 2, (CROP_W - nw) // 2
    canvas[oy:oy + nh, ox:ox + nw] = cv2.resize(gray, (nw, nh), interpolation=cv2.INTER_AREA)
    return canvas, s, ox, oy


def glyph_targets(record: Any, W: int, H: int, box: tuple[int, int, int, int]) -> list[dict[str, Any]]:
    """Ground-truth glyphs of a row in the coordinates of the crop ``box`` (x0, y0, x1, y1 in pixels)."""
    out = []
    for g in sorted((r for r in record["synthetic_regions"] if r["kind"] == "glyph"), key=lambda r: r["glyph_index"]):
        q = np.asarray(g["quad"], np.float32) * np.float32([W, H]) - np.float32([box[0], box[1]])
        u, v = q[1] - q[0], q[3] - q[0]
        out.append({"cx": float(q.mean(axis=0)[0]), "cy": float(q.mean(axis=0)[1]), "w": float(np.linalg.norm(u)),
                    "h": float(np.linalg.norm(v)), "token": g["token"], "word": g["word_index"],
                    "visible": g["visible_fraction"]})
    return out


def row_box(record: Any, W: int, H: int, rng: np.random.Generator | None = None) -> tuple[int, int, int, int] | None:
    """The ground-truth row box in pixels, optionally jittered as a detector would be."""
    rows = [r for r in record["synthetic_regions"] if r["kind"] == "glyph_row"]
    if not rows:
        return None
    r = rows[0]
    x0, y0, x1, y1 = r["x"] * W, r["y"] * H, (r["x"] + r["width"]) * W, (r["y"] + r["height"]) * H
    if rng is not None:
        m = (y1 - y0) * 0.25
        x0, y0 = x0 - rng.uniform(0, m) + rng.normal(0, m / 4), y0 - rng.uniform(0, m) + rng.normal(0, m / 4)
        x1, y1 = x1 + rng.uniform(0, m) + rng.normal(0, m / 4), y1 + rng.uniform(0, m) + rng.normal(0, m / 4)
    x0, y0, x1, y1 = (round(v) for v in (max(0, x0), max(0, y0), min(W, x1), min(H, y1)))
    return (x0, y0, x1, y1) if x1 - x0 > 4 and y1 - y0 > 4 else None


def _center_sample(gray: np.ndarray, record: Any, rng: np.random.Generator | None) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray] | None:
    H, W = gray.shape
    box = row_box(record, W, H, rng)
    if box is None:
        return None
    crop = gray[box[1]:box[3], box[0]:box[2]]
    lb, s, ox, oy = _crop_letterbox(crop)
    heat = np.zeros((CROP_H // 2, CROP_W // 2), np.float32)
    size = np.zeros((2, CROP_H // 2, CROP_W // 2), np.float32)
    mask = np.zeros((CROP_H // 2, CROP_W // 2), np.float32)
    yy, xx = np.mgrid[0:CROP_H // 2, 0:CROP_W // 2].astype(np.float32)
    for g in glyph_targets(record, W, H, box):
        cx, cy = (g["cx"] * s + ox) / 2, (g["cy"] * s + oy) / 2
        if not (0 <= cx < CROP_W // 2 and 0 <= cy < CROP_H // 2):
            continue
        sigma = max(1.0, 0.18 * g["w"] * s / 2)
        ix, iy = min(round(cx), CROP_W // 2 - 1), min(round(cy), CROP_H // 2 - 1)
        heat = np.maximum(heat, np.exp(-((xx - ix) ** 2 + (yy - iy) ** 2) / (2 * sigma ** 2)))   # peak = 1 on its cell
        if 0 <= ix < CROP_W // 2 and 0 <= iy < CROP_H // 2:
            size[:, iy, ix] = (g["w"] * s / CROP_H, g["h"] * s / CROP_H)
            mask[iy, ix] = 1.0
    return lb, heat, size, mask


def _focal(logits: torch.Tensor, target: torch.Tensor) -> torch.Tensor:
    p = torch.sigmoid(logits).clamp(1e-4, 1 - 1e-4)
    pos = (target > 0.99).float()          # the peak cell of each glyph's Gaussian
    pos_loss = -torch.log(p) * (1 - p) ** 2 * pos
    neg_loss = -torch.log(1 - p) * p ** 2 * (1 - target) ** 4 * (1 - pos)
    return (pos_loss.sum() + neg_loss.sum()) / pos.sum().clamp(min=1)


def train_glyph_centers(train: list[Any], val: list[Any], *, epochs: int = 40, seed: int = 20261003, device: str = "auto",
                        log: Callable[[str], None] | None = None) -> tuple[GlyphCenterNet, dict[str, Any]]:
    torch.manual_seed(seed)
    rng = np.random.default_rng(seed)
    dev = _device(device)
    train_g = [(enhanced_gray(_rgb(r.image_path)), r.record) for r in train if r.script_type == "synthetic_tamil_brahmi_like"]
    val_g = [(enhanced_gray(_rgb(r.image_path)), r.record) for r in val if r.script_type == "synthetic_tamil_brahmi_like"]
    net = GlyphCenterNet().to(dev)
    opt = torch.optim.AdamW(net.parameters(), lr=2e-3, weight_decay=1e-4)
    sched = torch.optim.lr_scheduler.CosineAnnealingLR(opt, T_max=epochs)
    best, best_state, history = -1.0, None, []
    for epoch in range(epochs):
        net.train()
        order = rng.permutation(len(train_g))
        for start in range(0, len(order), 16):
            batch = [s for i in order[start:start + 16] if (s := _center_sample(*train_g[i], rng)) is not None]
            if not batch:
                continue
            x = torch.from_numpy(np.stack([_normalise(_augment_row(b[0], rng)) for b in batch])[:, None]).to(dev)
            heat_t = torch.from_numpy(np.stack([b[1] for b in batch])[:, None]).to(dev)
            size_t = torch.from_numpy(np.stack([b[2] for b in batch])).to(dev)
            mask = torch.from_numpy(np.stack([b[3] for b in batch])[:, None]).to(dev)
            heat, size = net(x)
            loss = _focal(heat, heat_t) + 2.0 * (torch.abs(size - size_t) * mask).sum() / mask.sum().clamp(min=1)
            opt.zero_grad(set_to_none=True)
            loss.backward()
            opt.step()
        sched.step()
        net.eval()
        f1 = segmentation_scores(lambda g, n=net: segment_learned(n, g), val_g)["f1"]
        history.append({"epoch": epoch, "val_segmentation_f1": f1})
        if log:
            log(f"  glyph-centre net epoch {epoch:>2}  val segmentation F1 {f1:.3f}")
        if f1 > best:
            best, best_state = f1, {k: v.detach().cpu().clone() for k, v in net.state_dict().items()}
        net.train()
    assert best_state is not None
    net.load_state_dict(best_state)
    net = net.cpu().eval()
    return net, {"best_val_segmentation_f1": round(best, 4), "history": history, "device": dev.type,
                 "train_rows": len(train_g), "val_rows": len(val_g)}


def _augment_row(gray: np.ndarray, rng: np.random.Generator) -> np.ndarray:
    out = gray.astype(np.float32)
    out = (out - out.mean()) * rng.uniform(0.75, 1.3) + out.mean() + rng.uniform(-20, 20)
    if rng.random() < 0.3:
        out = cv2.GaussianBlur(out, (0, 0), rng.uniform(0.4, 1.1))
    if rng.random() < 0.3:
        out = out + rng.normal(0, rng.uniform(2, 8), out.shape)
    return np.clip(out, 0, 255)


def segment_learned(net: GlyphCenterNet, gray: np.ndarray, threshold: float = 0.3) -> list[Glyph]:
    """Glyph centres from the heat map; row direction from the centres; words from the gaps between glyphs."""
    if gray.size == 0 or min(gray.shape) < 4:
        return []
    lb, s, ox, oy = _crop_letterbox(gray)
    dev = next(net.parameters()).device
    with torch.no_grad():
        heat, size = net(torch.from_numpy(_normalise(lb)[None, None]).to(dev))
        heat = torch.sigmoid(heat)
        peaks = (heat == nn.functional.max_pool2d(heat, 5, stride=1, padding=2)) & (heat > threshold)
    heat_np, size_np, peaks_np = heat[0, 0].cpu().numpy(), size[0].cpu().numpy(), peaks[0, 0].cpu().numpy()
    ys, xs = np.nonzero(peaks_np)
    if len(xs) == 0:
        return []
    cands = []
    for y, x in zip(ys, xs):
        cx, cy = (x * 2 + 1 - ox) / s, (y * 2 + 1 - oy) / s
        w, h = (max(float(size_np[0, y, x]), 0.05) * CROP_H / s, max(float(size_np[1, y, x]), 0.05) * CROP_H / s)
        cands.append((cx, cy, w, h, float(heat_np[y, x])))
    pts = np.array([[c[0], c[1]] for c in cands], np.float32)
    if len(cands) >= 2:
        vx, vy, _, _ = cv2.fitLine(pts, cv2.DIST_L2, 0, 0.01, 0.01).ravel()
        if vx < 0:
            vx, vy = -vx, -vy
        if abs(math.degrees(math.atan2(vy, vx))) > 40:      # not a plausible row direction: fall back to horizontal
            vx, vy = 1.0, 0.0
    else:
        vx, vy = 1.0, 0.0
    u = np.array([vx, vy], np.float32)
    v = np.array([-vy, vx], np.float32)
    order = sorted(range(len(cands)), key=lambda i: float(pts[i] @ u))
    cands = [cands[i] for i in order]
    proj = [float(np.array(c[:2]) @ u) for c in cands]
    gaps = [proj[i + 1] - proj[i] - (cands[i][2] + cands[i + 1][2]) / 2 for i in range(len(cands) - 1)]
    med_h = float(np.median([c[3] for c in cands]))
    med_gap = float(np.median(gaps)) if gaps else 0.0
    out, word = [], 0
    for i, (cx, cy, w, h, _) in enumerate(cands):
        if i and gaps[i - 1] > max(0.4 * med_h, 1.8 * max(med_gap, 0.05 * med_h)):
            word += 1
        side = max(w, h)
        g = Glyph(cx, cy, side=side, u=(float(u[0]), float(u[1])), word=word)
        g.crop = square_crop(gray, (cx, cy), u, v, side * 1.24)
        out.append(g)
    return out


def segment(strategy: str, gray: np.ndarray, center_net: GlyphCenterNet | None = None) -> list[Glyph]:
    if strategy == "projection":
        return segment_projection(gray)
    if strategy == "components":
        return segment_components(gray)
    if strategy == "learned_centers":
        if center_net is None:
            raise ValueError("learned_centers needs a GlyphCenterNet")
        return segment_learned(center_net, gray)
    raise ValueError(f"unknown segmentation strategy {strategy!r}")


def read_glyphs(glyph_net: GlyphNet, glyphs: list[Glyph]) -> tuple[list[list[str]], list[float]]:
    """Recognise segmented glyphs; returns words of codes and one model score per glyph."""
    if not glyphs:
        return [], []
    codes, conf = classify(glyph_net, [g.crop for g in glyphs])
    words: list[list[str]] = [[] for _ in range(max(g.word for g in glyphs) + 1)]
    for c, g in zip(codes, glyphs):
        words[g.word].append(c)
    return [w for w in words if w], conf


def segmentation_scores(segment_fn: Callable[[np.ndarray], list[Glyph]], rows: list[tuple[np.ndarray, Any]]) -> dict[str, Any]:
    """Segmentation precision/recall/F1 against ground-truth glyph centres on ground-truth row crops.

    A predicted glyph matches a true one when its centre lies within half the true glyph's size."""
    tp = fp = fn = exact_count = 0
    for gray, record in rows:
        H, W = gray.shape
        box = row_box(record, W, H)
        if box is None:
            continue
        crop = gray[box[1]:box[3], box[0]:box[2]]
        truth = glyph_targets(record, W, H, box)
        pred = segment_fn(crop)
        exact_count += len(pred) == len(truth)
        used = set()
        for p in pred:
            best, bj = None, None
            for j, t in enumerate(truth):
                d = math.hypot(p.cx - t["cx"], p.cy - t["cy"])
                if j not in used and d <= 0.5 * max(t["w"], t["h"]) and (best is None or d < best):
                    best, bj = d, j
            if bj is None:
                fp += 1
            else:
                tp += 1
                used.add(bj)
        fn += len(truth) - len(used)
    p = tp / (tp + fp) if tp + fp else 0.0
    r = tp / (tp + fn) if tp + fn else 0.0
    return {"precision": round(p, 4), "recall": round(r, 4), "f1": round(2 * p * r / (p + r), 4) if p + r else 0.0,
            "glyph_count_accuracy": round(exact_count / max(len(rows), 1), 4), "rows": len(rows)}


def rates(pairs: list[tuple[list[list[str]], list[list[str]]]]) -> dict[str, Any]:
    from .ocr_benchmark import _rates

    return _rates(pairs)


def reading_scores(strategy: str, glyph_net: GlyphNet, rows: list[tuple[np.ndarray, Any]],
                   center_net: GlyphCenterNet | None = None) -> dict[str, Any]:
    """CER / WER / exact rows when a strategy segments ground-truth row crops and GlyphNet reads them."""
    pairs = []
    for gray, record in rows:
        H, W = gray.shape
        box = row_box(record, W, H)
        if box is None:
            continue
        words, _ = read_glyphs(glyph_net, segment(strategy, gray[box[1]:box[3], box[0]:box[2]], center_net))
        pairs.append((record["synthetic_glyph_sequence"], words))
    return rates(pairs)


# --------------------------------------------------------------------------- #
# Persistence (fingerprinted, weights_only loadable)
# --------------------------------------------------------------------------- #

KINDS: dict[str, Callable[[], nn.Module]] = {
    "region_detector": lambda: RowNet(out_channels=2),
    "glyph_classifier": GlyphNet,
    "glyph_centers": GlyphCenterNet,
}


class VisionModelError(ValueError):
    """A synthetic vision model file is missing, foreign, tampered with or inconsistent."""


def save_model(net: nn.Module, path: Path, kind: str, meta: dict[str, Any]) -> dict[str, Any]:
    assert_synthetic_model_destination(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    state = {k: v.detach().cpu() for k, v in net.state_dict().items()}
    fp = model_fingerprint(state)
    torch.save({"dataset_type": DATASET_TYPE, "marker": MARKER, "kind": kind, "state_dict": state,
                "model_fingerprint": fp, "meta": json.loads(json.dumps(meta, default=str))}, path)
    return {"file": path.name, "sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "model_fingerprint": fp,
            "parameters": int(sum(v.numel() for v in state.values()))}


def load_model(path: Path, kind: str, expected: dict[str, Any] | None = None) -> nn.Module:
    if not path.is_file():
        raise VisionModelError(f"missing synthetic vision model: {path}")
    if expected is not None and hashlib.sha256(path.read_bytes()).hexdigest() != expected.get("sha256"):
        raise VisionModelError(f"{path.name}: file hash differs from the bundle manifest (modified file?)")
    try:
        blob = torch.load(path, map_location="cpu", weights_only=True)
    except Exception as exc:
        raise VisionModelError(f"{path.name} could not be loaded safely (weights_only): {exc}") from exc
    if blob.get("dataset_type") != DATASET_TYPE or blob.get("marker") != MARKER or blob.get("kind") != kind:
        raise VisionModelError(f"{path.name} is not a synthetic {kind}")
    if model_fingerprint(blob["state_dict"]) != blob.get("model_fingerprint"):
        raise VisionModelError(f"{path.name}: weights do not match their fingerprint")
    net = KINDS[kind]()
    net.load_state_dict(blob["state_dict"])
    return net.eval()


@dataclass
class VisionBundle:
    directory: Path
    manifest: dict[str, Any]
    region_detector: RowNet
    glyph_classifier: GlyphNet
    glyph_centers: GlyphCenterNet

    @property
    def strategy(self) -> str:
        return self.manifest["segmentation"]["selected"]

    def to(self, device: str | torch.device) -> VisionBundle:
        for m in (self.region_detector, self.glyph_classifier, self.glyph_centers):
            m.to(device)
        return self


def latest_bundle_dir(root: Path = VISION_DIR) -> Path | None:
    found = sorted((p.parent for p in root.glob("*/manifest.json")), key=lambda p: p.stat().st_mtime) if root.is_dir() else []
    return found[-1] if found else None


def load_bundle(directory: Path | str | None = None) -> VisionBundle:
    d = Path(directory) if directory else latest_bundle_dir()
    if d is None or not (d / "manifest.json").is_file():
        raise VisionModelError("no synthetic vision bundle; run `python -m src.synthetic train-vision`")
    manifest = json.loads((d / "manifest.json").read_text(encoding="utf-8"))
    if manifest.get("dataset_type") != DATASET_TYPE or manifest.get("marker") != MARKER:
        raise VisionModelError(f"{d} is not a synthetic vision bundle")
    models = {k: load_model(d / manifest["models"][k]["file"], k, manifest["models"][k]) for k in KINDS}
    return VisionBundle(d, manifest, models["region_detector"], models["glyph_classifier"], models["glyph_centers"])


# --------------------------------------------------------------------------- #
# Training the bundle
# --------------------------------------------------------------------------- #


def train_vision(*, root: Path | str | None = None, epochs_detector: int = 24, epochs_glyphs: int = 20,
                 epochs_centers: int = 40, seed: int = 20261003, device: str = "auto",
                 log: Callable[[str], None] = print, out_dir: Path | str | None = None) -> Path:
    """Train region detector, glyph classifier and glyph-centre net; select segmentation on VAL; save."""
    from src.dataset.splits import partition_records
    from src.training.runtime import environment, git_commit

    from .config import SyntheticDatasetConfig
    from .dataset import SyntheticPaths, find_manifest, load_synthetic_dataset, synthetic_fingerprint
    from .generator import GENERATOR_VERSION

    start = time.perf_counter()
    paths = SyntheticPaths.at(root)
    ds = load_synthetic_dataset(paths.root)
    split = find_manifest(ds, paths.root)
    parts = partition_records(split, ds)
    log("training synthetic region detector (glyph rows + synthetic inscription regions) ...")
    region_net, region_fit = train_region_detector(parts["train"], parts["val"], epochs=epochs_detector, seed=seed,
                                                   device=device, log=log)
    log("training synthetic glyph classifier ...")
    tr, va = glyph_crops(parts["train"]), glyph_crops(parts["val"])
    glyph_net, glyph_fit = train_glyph_classifier(tr[:2], va[:2], epochs=epochs_glyphs, seed=seed, device=device)
    log(f"  best validation glyph accuracy {glyph_fit['best_val_glyph_accuracy']}")
    log("training glyph-centre segmentation net ...")
    center_net, center_fit = train_glyph_centers(parts["train"], parts["val"], epochs=epochs_centers, seed=seed,
                                                 device=device, log=log)
    log("comparing segmentation strategies on the VALIDATION split ...")
    val_rows = [(enhanced_gray(_rgb(r.image_path)), r.record) for r in parts["val"]
                if r.script_type == "synthetic_tamil_brahmi_like"]
    comparison = {}
    for strat in STRATEGIES:
        comparison[strat] = {"segmentation": segmentation_scores(partial(segment, strat, center_net=center_net), val_rows),
                             "reading": reading_scores(strat, glyph_net, val_rows, center_net)}
        log(f"  {strat:<16} segmentation F1 {comparison[strat]['segmentation']['f1']:.3f}  "
            f"CER {comparison[strat]['reading']['cer']:.3f}")
    selected = min(STRATEGIES, key=lambda s: (comparison[s]["reading"]["cer"], -comparison[s]["segmentation"]["f1"]))
    from src.dataset.convert import read_jsonl

    raw = read_jsonl(paths.records)
    cfg = SyntheticDatasetConfig.load()
    git = git_commit()
    run_id = f"vision_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}_{ds.fingerprint[:8]}_s{seed}"
    out = Path(out_dir or VISION_DIR) / run_id
    meta = {"dataset_fingerprint": ds.fingerprint, "split_digest": split.digest, "run_id": run_id}
    models = {"region_detector": save_model(region_net, out / "region_detector.pt", "region_detector", meta | {"fit": region_fit}),
              "glyph_classifier": save_model(glyph_net, out / "glyph_classifier.pt", "glyph_classifier", meta | {"fit": glyph_fit}),
              "glyph_centers": save_model(center_net, out / "glyph_centers.pt", "glyph_centers", meta | {"fit": center_fit})}
    manifest = {
        "dataset_type": DATASET_TYPE, "marker": MARKER, "run_id": run_id,
        "created_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"), "git": git, "environment": environment(),
        "seed": seed, "dataset_fingerprint": ds.fingerprint, "split_digest": split.digest,
        "synthetic_fingerprint": synthetic_fingerprint(raw, generator_version=GENERATOR_VERSION, config_digest=cfg.digest,
                                                       split_digest=split.digest),
        "generator_version": GENERATOR_VERSION, "dataset_config_digest": cfg.digest,
        "epochs": {"region_detector": epochs_detector, "glyph_classifier": epochs_glyphs, "glyph_centers": epochs_centers},
        "models": models,
        "fit": {"region_detector": {k: v for k, v in region_fit.items() if k != "history"},
                "glyph_classifier": {k: v for k, v in glyph_fit.items() if k != "history"},
                "glyph_centers": {k: v for k, v in center_fit.items() if k != "history"}},
        "segmentation": {"selected": selected, "selected_on": "val", "selection_metric": "CER on ground-truth rows",
                         "comparison_val": comparison},
        "seconds": round(time.perf_counter() - start, 1),
    }
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8", newline="\n")
    log(f"selected segmentation strategy: {selected} (on VAL); bundle -> {out}")
    return out


__all__ = ["REGION_CLASS", "ROW_CLASS", "STRATEGIES", "VISION_DIR", "DetectedRegion", "Glyph", "GlyphCenterNet",
           "VisionBundle", "VisionModelError", "detect_regions", "inscription_regions", "latest_bundle_dir", "load_bundle",
           "load_model", "match_boxes", "read_glyphs", "reading_scores", "row_box", "save_model", "segment",
           "segment_components", "segment_learned", "segment_projection", "segmentation_scores", "train_vision"]
