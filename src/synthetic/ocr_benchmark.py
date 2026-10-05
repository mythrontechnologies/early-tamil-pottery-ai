"""Synthetic glyph recognition benchmark.   SYNTHETIC — NOT ARCHAEOLOGICAL EVIDENCE

    python -m src.synthetic ocr-benchmark [--epochs 20] [--json]

This is NOT Tamil-Brahmi transcription and NOT OCR of any real script. It exercises the
project's inscription pipeline (region detection -> enhancement -> segmentation -> recognition ->
reliability screening) on the synthetic glyph rows, whose ground truth the generator knows
exactly: the glyph codes ``SG00``-``SG15`` (no sound, no reading, no meaning) and their regions.

Components (they implement the project's own protocols, so they plug into ``src.inference``):

* :class:`SyntheticRowDetector` (``RegionDetector``) - classical: CLAHE + black-hat ink map,
  connected components, grouping of similar, collinear components into a row. Its regions are
  ``ai_prediction`` regions, never evidence.
* :class:`GlyphNet` - a small CNN trained on glyph crops from the TRAIN split only.
* :class:`SyntheticGlyphReader` (``Transcriber``) - deskews a region, segments it by vertical
  projection, classifies each segment and splits words at wide gaps.

Measured on the TEST split:

* detection: precision / recall / F1 / mean IoU of row regions (IoU >= 0.5, the project's
  ``agreement.region_iou_match``), with false alarms counted on images that carry no row;
* recognition with ground-truth glyph regions ("oracle segmentation"): glyph accuracy, CER, WER;
* end to end (detector + reader): CER, WER, exact-sequence rate, glyph-count accuracy;
* through ``src.inference.analyze`` on a sample: how often the reliability screen keeps an output
  as a candidate and how often it abstains.

CER is the edit distance over glyph codes divided by the reference length; WER is the same over
words (groups of codes split by the wider gap). Rows have one or two words, so WER is coarse.
"""

from __future__ import annotations

import itertools
import json
import math
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import cv2
import numpy as np
import torch
from PIL import Image
from torch import nn

from src.detection import Region
from src.evaluation.ocr import edit_distance
from src.ocr import OCRResult

from . import (
    DATASET_TYPE,
    MARKER,
    OCR_BENCHMARK_NAME,
    PURPOSE,
    SYNTHETIC_MODELS_ROOT,
    assert_synthetic_model_destination,
)
from .dataset import SyntheticPaths, find_manifest, load_synthetic_dataset
from .glyphs import GLYPH_CODES

GLYPH_PX = 32
WORD_SEPARATOR = " | "
READER_ENGINE = "synthetic_glyph_reader"
NOT_A_TRANSCRIPTION = (f"{OCR_BENCHMARK_NAME}: synthetic glyph codes, not a transcription of any script and "
                       "not archaeological evidence.")
DEFAULT_MODEL_PATH = SYNTHETIC_MODELS_ROOT / "ocr" / "glyph_classifier.pt"
DEFAULT_DETECTOR_PATH = SYNTHETIC_MODELS_ROOT / "ocr" / "row_detector.pt"
LINK = 2.6          # classical detector: neighbour distance / component size (tuned on the VALIDATION split)
DET_PX = 256        # learned detector input (letterboxed); output heat map is DET_PX / 4
_CLAHE = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
_BH = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (9, 9))


# --------------------------------------------------------------------------- #
# Image helpers
# --------------------------------------------------------------------------- #


def enhanced_gray(rgb: np.ndarray) -> np.ndarray:
    return _CLAHE.apply(cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY))


def ink_map(gray: np.ndarray, *, local: bool = False) -> np.ndarray:
    """Dark, thin incision-like strokes as a 0/1 map (black-hat of the enhanced image)."""
    bh = cv2.morphologyEx(gray, cv2.MORPH_BLACKHAT, _BH)
    if local:        # inside a region crop the ink is a large share: Otsu separates it
        t, _ = cv2.threshold(bh, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        thr = max(12.0, float(t))
    else:
        thr = max(14.0, float(bh.mean() + 3 * bh.std()))
    return (bh > thr).astype(np.uint8)


def square_crop(gray: np.ndarray, center: tuple[float, float], u: np.ndarray, v: np.ndarray, side: float,
                out: int = GLYPH_PX) -> np.ndarray:
    """An ``out``x``out`` crop of a square of ``side`` px centred on ``center`` with axes u (right), v (down)."""
    u, v = u / (np.linalg.norm(u) + 1e-9), v / (np.linalg.norm(v) + 1e-9)
    c = np.asarray(center, np.float32)
    h = side / 2
    src = np.float32([c - h * u - h * v, c + h * u - h * v, c + h * u + h * v, c - h * u + h * v])
    dst = np.float32([[0, 0], [out, 0], [out, out], [0, out]])
    return cv2.warpPerspective(gray, cv2.getPerspectiveTransform(src, dst), (out, out), flags=cv2.INTER_LINEAR,
                               borderMode=cv2.BORDER_REPLICATE)


def quad_crop(gray: np.ndarray, quad_norm: list[list[float]], margin: float = 0.12) -> np.ndarray:
    """Aspect-preserving, rotation-corrected crop of a ground-truth glyph quad (TL, TR, BR, BL)."""
    H, W = gray.shape
    q = np.asarray(quad_norm, np.float32) * np.float32([W, H])
    u, v = q[1] - q[0], q[3] - q[0]
    side = max(np.linalg.norm(u), np.linalg.norm(v)) * (1 + 2 * margin)
    return square_crop(gray, tuple(q.mean(axis=0)), u, v, side)


def _normalise(crop: np.ndarray) -> np.ndarray:
    x = crop.astype(np.float32)
    return (x - x.mean()) / (x.std() + 1e-3)


# --------------------------------------------------------------------------- #
# Glyph classifier
# --------------------------------------------------------------------------- #


class GlyphNet(nn.Module):
    def __init__(self, n_classes: int = len(GLYPH_CODES)) -> None:
        super().__init__()

        def block(i: int, o: int) -> list[nn.Module]:
            return [nn.Conv2d(i, o, 3, padding=1, bias=False), nn.BatchNorm2d(o), nn.ReLU(inplace=True)]

        self.features = nn.Sequential(*block(1, 32), *block(32, 32), nn.MaxPool2d(2), *block(32, 64), *block(64, 64),
                                      nn.MaxPool2d(2), *block(64, 128), nn.AdaptiveAvgPool2d(1))
        self.head = nn.Sequential(nn.Flatten(), nn.Dropout(0.3), nn.Linear(128, n_classes))

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.head(self.features(x))


def _augment(crop: np.ndarray, rng: np.random.Generator) -> np.ndarray:
    c = GLYPH_PX / 2
    m = cv2.getRotationMatrix2D((c, c), rng.uniform(-7, 7), rng.uniform(0.82, 1.2))
    m[:, 2] += rng.uniform(-2.5, 2.5, 2)
    out = cv2.warpAffine(crop, m, (GLYPH_PX, GLYPH_PX), borderMode=cv2.BORDER_REPLICATE).astype(np.float32)
    out = (out - out.mean()) * rng.uniform(0.7, 1.3) + out.mean() + rng.uniform(-20, 20)
    if rng.random() < 0.3:
        out = cv2.GaussianBlur(out, (0, 0), rng.uniform(0.4, 1.0))
    return np.clip(out, 0, 255)


def train_glyph_classifier(train: tuple[np.ndarray, np.ndarray], val: tuple[np.ndarray, np.ndarray], *,
                           epochs: int = 20, seed: int = 20261003, device: str = "auto") -> tuple[GlyphNet, dict[str, Any]]:
    torch.manual_seed(seed)
    rng = np.random.default_rng(seed)
    dev = torch.device("cuda" if device in ("auto", "cuda") and torch.cuda.is_available() else "cpu")
    net = GlyphNet().to(dev)
    opt = torch.optim.AdamW(net.parameters(), lr=2e-3, weight_decay=1e-4)
    sched = torch.optim.lr_scheduler.CosineAnnealingLR(opt, T_max=epochs)
    loss_fn = nn.CrossEntropyLoss(label_smoothing=0.05)
    xv = torch.from_numpy(np.stack([_normalise(c) for c in val[0]])[:, None]).to(dev)
    yv = torch.from_numpy(val[1]).to(dev)
    best, best_state, history = -1.0, None, []
    for epoch in range(epochs):
        net.train()
        order = rng.permutation(len(train[0]))
        for start in range(0, len(order), 128):
            idx = order[start:start + 128]
            xb = torch.from_numpy(np.stack([_normalise(_augment(train[0][i], rng)) for i in idx])[:, None]).to(dev)
            yb = torch.from_numpy(train[1][idx]).to(dev)
            opt.zero_grad(set_to_none=True)
            loss = loss_fn(net(xb), yb)
            loss.backward()
            opt.step()
        sched.step()
        net.eval()
        with torch.no_grad():
            acc = float((net(xv).argmax(1) == yv).float().mean())
        history.append({"epoch": epoch, "val_glyph_accuracy": round(acc, 4)})
        if acc > best:
            best, best_state = acc, {k: v.detach().cpu().clone() for k, v in net.state_dict().items()}
    assert best_state is not None
    net.load_state_dict(best_state)
    return net.cpu().eval(), {"best_val_glyph_accuracy": round(best, 4), "history": history, "device": dev.type}


def classify(net: GlyphNet, crops: list[np.ndarray]) -> tuple[list[str], list[float]]:
    if not crops:
        return [], []
    with torch.no_grad():
        x = torch.from_numpy(np.stack([_normalise(c) for c in crops])[:, None]).to(next(net.parameters()).device)
        p = torch.softmax(net(x), dim=1).cpu().numpy()
    return [GLYPH_CODES[i] for i in p.argmax(1)], [float(v) for v in p.max(1)]


def save_glyph_model(net: GlyphNet, path: Path, meta: dict[str, Any]) -> Path:
    assert_synthetic_model_destination(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    torch.save({"dataset_type": DATASET_TYPE, "marker": MARKER, "codes": list(GLYPH_CODES), "glyph_px": GLYPH_PX,
                "state_dict": net.state_dict(), "meta": json.loads(json.dumps(meta, default=str))}, path)
    return path


def load_glyph_model(path: Path | str = DEFAULT_MODEL_PATH) -> GlyphNet:
    blob = torch.load(Path(path), map_location="cpu", weights_only=True)
    if blob.get("dataset_type") != DATASET_TYPE or blob.get("marker") != MARKER or blob.get("codes") != list(GLYPH_CODES):
        raise ValueError(f"{path} is not a synthetic glyph model")
    net = GlyphNet()
    net.load_state_dict(blob["state_dict"])
    return net.eval()


# --------------------------------------------------------------------------- #
# Detection
# --------------------------------------------------------------------------- #


@dataclass
class RowCandidate:
    box: tuple[float, float, float, float]       # x, y, w, h in pixels (axis-aligned)
    angle: float
    members: int


def detect_rows(rgb: np.ndarray) -> list[RowCandidate]:
    """Groups of >= 3 similar, roughly collinear, near-horizontal ink components."""
    gray = enhanced_gray(rgb)
    H, W = gray.shape
    m = min(H, W)
    ink = ink_map(gray)
    n, _labels, stats, cents = cv2.connectedComponentsWithStats(ink, connectivity=8)
    keep = []
    for i in range(1, n):
        _x, _y, w, h, area = stats[i]
        side = max(w, h)
        if area < 8 or side < 0.025 * m or side > 0.22 * m:
            continue
        if area / float(w * h) < 0.08 and side > 0.1 * m:      # long thin scratch
            continue
        keep.append(i)
    # union of near neighbours with similar size
    parent = {i: i for i in keep}

    def find(a: int) -> int:
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    for a_i, a in enumerate(keep):
        sa = max(stats[a][2], stats[a][3])
        for b in keep[a_i + 1:]:
            sb = max(stats[b][2], stats[b][3])
            if max(sa, sb) > 3.0 * min(sa, sb):
                continue
            if np.hypot(*(cents[a] - cents[b])) < LINK * max(sa, sb):
                parent[find(a)] = find(b)
    groups: dict[int, list[int]] = {}
    for i in keep:
        groups.setdefault(find(i), []).append(i)
    out = []
    for members in groups.values():
        if len(members) < 3:
            continue
        pts = cents[members].astype(np.float32)
        vx, vy, _, _ = cv2.fitLine(pts, cv2.DIST_L2, 0, 0.01, 0.01).ravel()
        angle = math.degrees(math.atan2(vy, vx))
        angle = (angle + 90) % 180 - 90
        if abs(angle) > 35:
            continue
        sizes = np.array([max(stats[i][2], stats[i][3]) for i in members], np.float32)
        normal = np.array([-vy, vx], np.float32)
        resid = np.abs((pts - pts.mean(axis=0)) @ normal)
        span = float(np.ptp(pts @ np.array([vx, vy], np.float32)))
        if resid.mean() > 0.45 * float(np.median(sizes)) or span < 1.5 * float(np.median(sizes)):
            continue
        xs = np.concatenate([[stats[i][0], stats[i][0] + stats[i][2]] for i in members])
        ys = np.concatenate([[stats[i][1], stats[i][1] + stats[i][3]] for i in members])
        x0, y0, x1, y1 = xs.min(), ys.min(), xs.max(), ys.max()
        pad = 0.15 * float(np.median(sizes))
        x0, y0, x1, y1 = max(0, x0 - pad), max(0, y0 - pad), min(W, x1 + pad), min(H, y1 + pad)
        out.append(RowCandidate((float(x0), float(y0), float(x1 - x0), float(y1 - y0)), angle, len(members)))
    return sorted(out, key=lambda r: -r.members)


class RowNet(nn.Module):
    """A small fully-convolutional heat-map network, stride 4. One output channel: P(pixel belongs to a
    glyph row). Milestone 10's region detector uses two (glyph row, any synthetic inscription region)."""

    def __init__(self, out_channels: int = 1) -> None:
        super().__init__()

        def block(i: int, o: int, d: int = 1) -> nn.Sequential:
            return nn.Sequential(nn.Conv2d(i, o, 3, padding=d, dilation=d, bias=False), nn.BatchNorm2d(o),
                                 nn.ReLU(inplace=True))

        self.s1 = nn.Sequential(block(3, 16), block(16, 16), nn.MaxPool2d(2))          # 1/2
        self.s2 = nn.Sequential(block(16, 32), block(32, 32), nn.MaxPool2d(2))         # 1/4
        self.s3 = nn.Sequential(block(32, 64), block(64, 64), nn.MaxPool2d(2))         # 1/8
        self.ctx = nn.Sequential(block(64, 64, 2), block(64, 64, 4))
        self.fuse = nn.Sequential(block(64 + 32, 32), nn.Conv2d(32, out_channels, 1))

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        f2 = self.s2(self.s1(x))
        f3 = self.ctx(self.s3(f2))
        up = nn.functional.interpolate(f3, size=f2.shape[-2:], mode="bilinear", align_corners=False)
        return self.fuse(torch.cat([up, f2], dim=1))


def _letterbox(rgb: np.ndarray, size: int = DET_PX) -> tuple[np.ndarray, float, int, int]:
    H, W = rgb.shape[:2]
    k = size / max(H, W)
    nh, nw = max(1, round(H * k)), max(1, round(W * k))
    canvas = np.zeros((size, size, 3), np.uint8)
    oy, ox = (size - nh) // 2, (size - nw) // 2
    canvas[oy:oy + nh, ox:ox + nw] = cv2.resize(rgb, (nw, nh), interpolation=cv2.INTER_AREA)
    return canvas, k, ox, oy


def _row_target(record: dict[str, Any], W: int, H: int, k: float, ox: int, oy: int) -> np.ndarray:
    out = DET_PX // 4
    mask = np.zeros((out, out), np.float32)
    quads = [g["quad"] for g in record["synthetic_regions"] if g["kind"] == "glyph"]
    if quads:
        pts = np.asarray(quads, np.float32).reshape(-1, 2) * np.float32([W, H]) * k + np.float32([ox, oy])
        hull = cv2.convexHull((pts / 4).astype(np.float32))
        cv2.fillPoly(mask, [np.round(hull * 4).astype(np.int32)], 1.0, shift=2)
    return mask


def _to_tensor(batch: np.ndarray) -> torch.Tensor:
    x = torch.from_numpy(batch).permute(0, 3, 1, 2).float() / 255.0
    return (x - 0.5) / 0.25


def train_row_detector(train: list[Any], val: list[Any], *, epochs: int = 20, seed: int = 20261003,
                       device: str = "auto") -> tuple[RowNet, dict[str, Any]]:
    """Fit RowNet on the TRAIN split (all classes: rows are positives, everything else negative)."""
    torch.manual_seed(seed)
    rng = np.random.default_rng(seed)
    dev = torch.device("cuda" if device in ("auto", "cuda") and torch.cuda.is_available() else "cpu")

    def load(recs: list[Any]) -> tuple[np.ndarray, np.ndarray]:
        xs, ys = [], []
        for r in recs:
            rgb = _rgb(r.image_path)
            lb, k, ox, oy = _letterbox(rgb)
            xs.append(lb)
            ys.append(_row_target(r.record, rgb.shape[1], rgb.shape[0], k, ox, oy))
        return np.stack(xs), np.stack(ys)

    xt, yt = load(train)
    xv, yv = load(val)
    net = RowNet().to(dev)
    opt = torch.optim.AdamW(net.parameters(), lr=2e-3, weight_decay=1e-4)
    sched = torch.optim.lr_scheduler.CosineAnnealingLR(opt, T_max=epochs)
    pos = torch.tensor([max(1.0, float((1 - yt.mean()) / max(yt.mean(), 1e-6)) ** 0.5)], device=dev)
    bce = nn.BCEWithLogitsLoss(pos_weight=pos)
    best, best_state, history = -1.0, None, []
    for epoch in range(epochs):
        net.train()
        order = rng.permutation(len(xt))
        for start in range(0, len(order), 32):
            idx = order[start:start + 32]
            xb = _to_tensor(xt[idx]).to(dev)
            xb = xb * float(rng.uniform(0.8, 1.2)) + float(rng.uniform(-0.2, 0.2))
            yb = torch.from_numpy(yt[idx])[:, None].to(dev)
            logits = net(xb)
            prob = torch.sigmoid(logits)
            dice = 1 - (2 * (prob * yb).sum() + 1) / (prob.sum() + yb.sum() + 1)
            loss = bce(logits, yb) + dice
            opt.zero_grad(set_to_none=True)
            loss.backward()
            opt.step()
        sched.step()
        net.eval()
        with torch.no_grad():
            pv = torch.cat([torch.sigmoid(net(_to_tensor(xv[i:i + 64]).to(dev))).cpu() for i in range(0, len(xv), 64)])
        pred = (pv[:, 0].numpy() > 0.5)
        inter = float((pred & (yv > 0.5)).sum())
        union = float((pred | (yv > 0.5)).sum())
        iou = inter / union if union else 0.0
        history.append({"epoch": epoch, "val_pixel_iou": round(iou, 4)})
        if iou > best:
            best, best_state = iou, {k: v.detach().cpu().clone() for k, v in net.state_dict().items()}
    assert best_state is not None
    net.load_state_dict(best_state)
    return net.cpu().eval(), {"best_val_pixel_iou": round(best, 4), "history": history, "device": dev.type,
                              "train_images": len(xt), "val_images": len(xv)}


def detect_rows_learned(net: RowNet, rgb: np.ndarray, threshold: float = 0.5) -> list[RowCandidate]:
    """The most confident row region of the heat map, as a box in image pixels (or nothing)."""
    lb, k, ox, oy = _letterbox(rgb)
    with torch.no_grad():
        prob = torch.sigmoid(net(_to_tensor(lb[None])))[0, 0].numpy()
    mask = (prob > threshold).astype(np.uint8)
    n, labels, stats, _ = cv2.connectedComponentsWithStats(mask, connectivity=8)
    if n <= 1:
        return []
    best = max(range(1, n), key=lambda i: float(prob[labels == i].sum()))
    if stats[best][4] < 3:
        return []
    x, y, w, h = (float(v) * 4 for v in stats[best][:4])
    H, W = rgb.shape[:2]
    x0, y0 = max(0.0, (x - ox) / k), max(0.0, (y - oy) / k)
    x1, y1 = min(float(W), (x + w - ox) / k), min(float(H), (y + h - oy) / k)
    if x1 - x0 < 2 or y1 - y0 < 2:
        return []
    return [RowCandidate((x0, y0, x1 - x0, y1 - y0), 0.0, int(stats[best][4]))]


def save_row_detector(net: RowNet, path: Path, meta: dict[str, Any]) -> Path:
    assert_synthetic_model_destination(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    torch.save({"dataset_type": DATASET_TYPE, "marker": MARKER, "det_px": DET_PX, "state_dict": net.state_dict(),
                "meta": json.loads(json.dumps(meta, default=str))}, path)
    return path


def load_row_detector(path: Path | str = DEFAULT_DETECTOR_PATH) -> RowNet:
    blob = torch.load(Path(path), map_location="cpu", weights_only=True)
    if blob.get("dataset_type") != DATASET_TYPE or blob.get("marker") != MARKER:
        raise ValueError(f"{path} is not a synthetic row detector")
    net = RowNet()
    net.load_state_dict(blob["state_dict"])
    return net.eval()


class SyntheticRowDetector:
    """``RegionDetector`` for synthetic glyph rows (AI proposals, never evidence).

    Uses the learned RowNet when one is given (or saved under models/synthetic/ocr/), else the
    classical ink-grouping baseline."""

    name = "synthetic_row_detector"
    statement = f"{OCR_BENCHMARK_NAME}: synthetic glyph-row detector (AI proposal, not evidence)."

    def __init__(self, net: RowNet | None = None, *, learned: bool = True) -> None:
        if net is None and learned and DEFAULT_DETECTOR_PATH.exists():
            net = load_row_detector()
        self.net = net

    def detect(self, image: Image.Image) -> list[Region]:
        rgb = np.asarray(image.convert("RGB"))
        H, W = rgb.shape[:2]
        rows = (detect_rows_learned(self.net, rgb) if self.net is not None else detect_rows(rgb))[:1]
        return [Region(x / W, y / H, min(w / W, 1 - x / W), min(h / H, 1 - y / H), "ai_prediction",
                       label="synthetic_glyph_row_candidate", note=MARKER) for x, y, w, h in (r.box for r in rows)]


# --------------------------------------------------------------------------- #
# Reading (segmentation + recognition)
# --------------------------------------------------------------------------- #


@dataclass
class Deskewed:
    """A region crop rotated so its row runs horizontally (``rot`` maps crop -> deskewed pixels)."""

    gray: np.ndarray
    ink: np.ndarray
    rot: np.ndarray
    height: float          # ink height of the row (5th-95th percentile)


def deskew(gray: np.ndarray) -> Deskewed | None:
    ink = ink_map(gray, local=True)
    n, labels, stats, _ = cv2.connectedComponentsWithStats(ink, connectivity=8)
    for i in range(1, n):
        if stats[i][4] < 5:
            ink[labels == i] = 0
    ys, xs = np.nonzero(ink)
    if len(xs) < 10:
        return None
    pts = np.stack([xs, ys], axis=1).astype(np.float32)
    vx, vy, _, _ = cv2.fitLine(pts, cv2.DIST_L2, 0, 0.01, 0.01).ravel()
    angle = (math.degrees(math.atan2(vy, vx)) + 90) % 180 - 90
    angle = float(np.clip(angle, -35, 35))
    H, W = gray.shape
    rot = cv2.getRotationMatrix2D((W / 2, H / 2), angle, 1.0)
    cos, sin = abs(rot[0, 0]), abs(rot[0, 1])
    nw, nh = int(H * sin + W * cos) + 1, int(H * cos + W * sin) + 1
    rot[0, 2] += nw / 2 - W / 2
    rot[1, 2] += nh / 2 - H / 2
    g2 = cv2.warpAffine(gray, rot, (nw, nh), borderMode=cv2.BORDER_REPLICATE)
    i2 = cv2.warpAffine(ink, rot, (nw, nh), flags=cv2.INTER_NEAREST)
    rows_with_ink = np.nonzero(i2.sum(axis=1))[0]
    if len(rows_with_ink) == 0:
        return None
    height = float(np.percentile(rows_with_ink, 95) - np.percentile(rows_with_ink, 5) + 1)
    return Deskewed(g2, i2, rot, height)


def projection_boxes(d: Deskewed) -> list[tuple[int, int, int, int, int]]:
    """Glyph boxes (x0, y0, x1, y1, word) in the deskewed frame, by vertical projection of the ink."""
    i2, height = d.ink, d.height
    cols = i2.sum(axis=0) > 0
    runs, start = [], None
    for x, on in enumerate(np.append(cols, False)):
        if on and start is None:
            start = x
        elif not on and start is not None:
            runs.append([start, x])
            start = None
    merged: list[list[int]] = []
    for r in runs:                       # rejoin pieces of one glyph split by a narrow internal gap
        if merged and r[0] - merged[-1][1] < 0.16 * height and r[1] - merged[-1][0] < 1.15 * height:
            merged[-1][1] = r[1]
        else:
            merged.append(r)
    merged = [r for r in merged if r[1] - r[0] >= 0.12 * height or i2[:, r[0]:r[1]].sum() > 8]
    gaps = [b[0] - a[1] for a, b in itertools.pairwise(merged)]
    split = max(0.7 * height, 2.0 * float(np.median(gaps))) if gaps else math.inf
    out, word = [], 0
    for k, (x0, x1) in enumerate(merged):
        if k and gaps[k - 1] > split:
            word += 1
        yy = np.nonzero(i2[:, x0:x1].sum(axis=1))[0]
        y0, y1 = (int(yy.min()), int(yy.max()) + 1) if len(yy) else (0, i2.shape[0])
        out.append((int(x0), y0, int(x1), y1, word))
    return out


def read_row(net: GlyphNet, gray: np.ndarray) -> tuple[list[list[str]], list[float]]:
    """Words of glyph codes in a (grayscale, enhanced) region crop, left to right (projection segmentation)."""
    d = deskew(gray)
    if d is None:
        return [], []
    boxes = projection_boxes(d)
    if not boxes:
        return [], []
    crops = [square_crop(d.gray, ((x0 + x1) / 2, (y0 + y1) / 2), np.array([1.0, 0]), np.array([0, 1.0]),
                         max(x1 - x0, y1 - y0) * 1.5) for x0, y0, x1, y1, _ in boxes]
    codes, conf = classify(net, crops)
    words: list[list[str]] = [[] for _ in range(boxes[-1][4] + 1)]
    for c, b in zip(codes, boxes):
        words[b[4]].append(c)
    return [w for w in words if w], conf


class SyntheticGlyphReader:
    """``Transcriber`` returning synthetic glyph codes as an OCR CANDIDATE (never a reading)."""

    name = READER_ENGINE

    def __init__(self, net: GlyphNet | None = None, path: Path | str = DEFAULT_MODEL_PATH) -> None:
        self.net = net or load_glyph_model(path)

    def transcribe(self, crop: Image.Image) -> OCRResult:
        words, conf = read_row(self.net, enhanced_gray(np.asarray(crop.convert("RGB"))))
        if not words:
            return OCRResult("no_reliable_transcription", f"{NOT_A_TRANSCRIPTION} No glyphs were segmented.",
                             engine=READER_ENGINE)
        return OCRResult("candidate", NOT_A_TRANSCRIPTION, text=WORD_SEPARATOR.join(" ".join(w) for w in words),
                         confidence=float(np.mean(conf)), engine=READER_ENGINE)


# --------------------------------------------------------------------------- #
# Benchmark
# --------------------------------------------------------------------------- #


def _iou(a: tuple[float, ...], b: tuple[float, ...]) -> float:
    ax0, ay0, aw, ah = a
    bx0, by0, bw, bh = b
    ix = max(0.0, min(ax0 + aw, bx0 + bw) - max(ax0, bx0))
    iy = max(0.0, min(ay0 + ah, by0 + bh) - max(ay0, by0))
    inter = ix * iy
    union = aw * ah + bw * bh - inter
    return inter / union if union > 0 else 0.0


def _rates(pairs: list[tuple[list[list[str]], list[list[str]]]]) -> dict[str, Any]:
    """CER over codes, WER over words, exact sequence and glyph-count agreement."""
    ref_len = sum(sum(len(w) for w in r) for r, _ in pairs)
    ref_words = sum(len(r) for r, _ in pairs)
    char_err = sum(edit_distance([c for w in r for c in w], [c for w in h for c in w]) for r, h in pairs)
    word_err = sum(edit_distance([tuple(w) for w in r], [tuple(w) for w in h]) for r, h in pairs)
    return {"n_rows": len(pairs), "cer": round(char_err / max(ref_len, 1), 4), "wer": round(word_err / max(ref_words, 1), 4),
            "exact_sequence_rate": round(sum(r == h for r, h in pairs) / max(len(pairs), 1), 4),
            "glyph_count_accuracy": round(sum(sum(map(len, r)) == sum(map(len, h)) for r, h in pairs) / max(len(pairs), 1), 4)}


def _rgb(path: Path) -> np.ndarray:
    return np.asarray(Image.open(path).convert("RGB"))


def glyph_crops(records: list[Any]) -> tuple[np.ndarray, np.ndarray, list[tuple[str, int]]]:
    crops, ys, where = [], [], []
    for r in records:
        if r.script_type != "synthetic_tamil_brahmi_like":
            continue
        gray = enhanced_gray(_rgb(r.image_path))
        for reg in r.record["synthetic_regions"]:
            if reg["kind"] == "glyph" and reg["visible_fraction"] >= 0.5:
                crops.append(quad_crop(gray, reg["quad"]))
                ys.append(GLYPH_CODES.index(reg["token"]))
                where.append((r.image_id, reg["glyph_index"]))
    return (np.stack(crops) if crops else np.zeros((0, GLYPH_PX, GLYPH_PX), np.uint8),
            np.asarray(ys, np.int64), where)


def run_benchmark(*, root: Path | str | None = None, epochs: int = 20, seed: int = 20261003, device: str = "auto",
                  pipeline_sample: int = 60, save: bool = True) -> dict[str, Any]:
    from src.dataset.splits import partition_records

    start = time.perf_counter()
    paths = SyntheticPaths.at(root)
    ds = load_synthetic_dataset(paths.root)
    manifest = find_manifest(ds, paths.root)
    parts = partition_records(manifest, ds)
    train, val, test = (glyph_crops(parts[p]) for p in ("train", "val", "test"))
    net, fit = train_glyph_classifier(train[:2], val[:2], epochs=epochs, seed=seed, device=device)
    rownet, det_fit = train_row_detector(parts["train"], parts["val"], epochs=epochs, seed=seed, device=device)

    # oracle segmentation: ground-truth glyph regions
    pred, _ = classify(net, list(test[0]))
    glyph_acc = float(np.mean([p == GLYPH_CODES[y] for p, y in zip(pred, test[1])])) if len(pred) else None
    by_img: dict[str, dict[int, str]] = {}
    for (iid, gi), p in zip(test[2], pred):
        by_img.setdefault(iid, {})[gi] = p
    test_recs = parts["test"]
    rows = [r for r in test_recs if r.script_type == "synthetic_tamil_brahmi_like"]
    oracle_pairs = []
    for r in rows:
        ref = r.record["synthetic_glyph_sequence"]
        glyphs = sorted((g for g in r.record["synthetic_regions"] if g["kind"] == "glyph"), key=lambda g: g["glyph_index"])
        hyp: list[list[str]] = [[] for _ in ref]
        for g in glyphs:
            hyp[g["word_index"]].append(by_img.get(r.image_id, {}).get(g["glyph_index"], "?"))
        oracle_pairs.append((ref, [w for w in hyp if w]))

    # detection (learned and classical) + end-to-end reading on every test image
    reader = SyntheticGlyphReader(net)
    no_row = [r for r in test_recs if not any(g["kind"] == "glyph_row" for g in r.record["synthetic_regions"])]
    detection, e2e_pairs, gt_row_pairs = {}, [], []
    for name, detect in (("learned", lambda rgb: detect_rows_learned(rownet, rgb)), ("classical", detect_rows)):
        tp = fp = fn = false_alarms = 0
        ious = []
        for r in test_recs:
            rgb = _rgb(r.image_path)
            H, W = rgb.shape[:2]
            cands = detect(rgb)[:1]
            det = cands[0] if cands else None
            gt = [g for g in r.record["synthetic_regions"] if g["kind"] == "glyph_row"]
            if not gt:
                fp += 1 if det else 0
                false_alarms += 1 if det else 0
                continue
            g = gt[0]
            gbox = (g["x"] * W, g["y"] * H, g["width"] * W, g["height"] * H)
            iou = _iou(det.box, gbox) if det else 0.0
            if det and iou >= 0.5:
                tp += 1
                ious.append(iou)
            else:
                fn += 1
                fp += 1 if det else 0
            if name == "learned":
                hyp: list[list[str]] = []
                if det:
                    x, y, w, h = (round(v) for v in det.box)
                    hyp, _ = read_row(net, enhanced_gray(rgb[y:y + h, x:x + w]))
                e2e_pairs.append((r.record["synthetic_glyph_sequence"], hyp))
                x, y, w, h = (round(v) for v in gbox)
                gt_hyp, _ = read_row(net, enhanced_gray(rgb[y:y + h, x:x + w]))
                gt_row_pairs.append((r.record["synthetic_glyph_sequence"], gt_hyp))
        precision = tp / (tp + fp) if tp + fp else None
        recall = tp / (tp + fn) if tp + fn else None
        f1 = (2 * precision * recall / (precision + recall)) if precision and recall else None
        detection[name] = {"true_positives": tp, "false_positives": fp, "false_negatives": fn,
                           "precision": round(precision, 4) if precision is not None else None,
                           "recall": round(recall, 4) if recall is not None else None,
                           "f1": round(f1, 4) if f1 is not None else None,
                           "mean_iou_of_matches": round(float(np.mean(ious)), 4) if ious else None,
                           "false_alarm_rate_on_images_without_row": round(false_alarms / max(len(no_row), 1), 4)}

    pipeline = _through_inference(rows[:pipeline_sample], reader, SyntheticRowDetector(rownet))
    report = {
        "benchmark": OCR_BENCHMARK_NAME, "dataset_type": DATASET_TYPE, "marker": MARKER, "purpose": PURPOSE,
        "statement": NOT_A_TRANSCRIPTION, "split_digest": manifest.digest, "dataset_fingerprint": ds.fingerprint,
        "glyph_alphabet": list(GLYPH_CODES),
        "data": {"train_glyphs": len(train[1]), "val_glyphs": len(val[1]), "test_glyphs": len(test[1]),
                 "test_rows": len(rows), "test_images_without_row": len(no_row)},
        "classifier": {"architecture": "GlyphNet (5 conv, 1 linear)", **fit},
        "row_detector": {"architecture": "RowNet (fully convolutional heat map, stride 4)", **det_fit,
                         "classical_baseline": f"ink components linked within {LINK} x size (tuned on validation)"},
        "oracle_segmentation": {"glyph_accuracy": round(glyph_acc, 4) if glyph_acc is not None else None,
                                **_rates(oracle_pairs)},
        "region_detection": {"iou_threshold": 0.5, **detection},
        "reader_on_ground_truth_rows": _rates(gt_row_pairs),
        "end_to_end": _rates(e2e_pairs),
        "through_inference_pipeline": pipeline,
        "seconds": round(time.perf_counter() - start, 1),
    }
    if save:
        model_path = save_glyph_model(net, DEFAULT_MODEL_PATH, {"split_digest": manifest.digest, "fit": fit})
        report["glyph_model"] = str(model_path)
        report["row_detector_model"] = str(save_row_detector(rownet, DEFAULT_DETECTOR_PATH,
                                                             {"split_digest": manifest.digest, "fit": det_fit}))
        out = SYNTHETIC_MODELS_ROOT / "reports" / "ocr_benchmark" / "ocr_benchmark.json"
        assert_synthetic_model_destination(out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
        report["report_path"] = str(out)
    return report


def _through_inference(rows: list[Any], reader: SyntheticGlyphReader, detector: SyntheticRowDetector) -> dict[str, Any]:
    """Run the real ``src.inference.analyze`` with the synthetic detector and reader plugged in."""
    from src.inference import analyze

    kept = abstained = exact = 0
    for r in rows:
        res = analyze(r.image_path, detector=detector, transcriber=reader, records=[]).to_dict()
        ocr = [o for o in res["layers"]["ai_observation"]["ocr"] if o["engine"] == READER_ENGINE]
        cand = [o for o in ocr if o["status"] == "candidate"]
        if cand:
            kept += 1
            ref = WORD_SEPARATOR.join(" ".join(w) for w in r.record["synthetic_glyph_sequence"])
            exact += cand[0]["text"] == ref
            assert cand[0]["is_reading"] is False and cand[0]["provenance"] == "ai_prediction"
        else:
            abstained += 1
    n = max(len(rows), 1)
    return {"images": len(rows), "candidates_kept_by_screen": kept, "abstained": abstained,
            "abstention_rate": round(abstained / n, 4), "exact_sequence_rate_of_kept": round(exact / kept, 4) if kept else None,
            "note": "src.ocr.screen_ocr keeps an engine output only at engine score >= 0.9; below that the pipeline "
                    "abstains ('No reliable transcription established.'). Candidates are never readings."}


def render_benchmark(rep: dict[str, Any]) -> str:
    o, e, p = rep["oracle_segmentation"], rep["end_to_end"], rep["through_inference_pipeline"]
    g, dl, dc = rep["reader_on_ground_truth_rows"], rep["region_detection"]["learned"], rep["region_detection"]["classical"]
    return "\n".join([
        "#" * 72, f"#  {OCR_BENCHMARK_NAME.upper()}", f"#  {MARKER}", "#  Synthetic glyph codes; not a transcription of any script.",
        "#" * 72,
        f"glyph crops: train {rep['data']['train_glyphs']}, val {rep['data']['val_glyphs']}, test {rep['data']['test_glyphs']}; "
        f"test rows {rep['data']['test_rows']}",
        f"classifier: best validation glyph accuracy {rep['classifier']['best_val_glyph_accuracy']} ({rep['classifier']['device']})",
        "",
        f"ORACLE SEGMENTATION  glyph accuracy {o['glyph_accuracy']}  CER {o['cer']}  WER {o['wer']}  exact {o['exact_sequence_rate']}",
        f"row detector: best validation pixel IoU {rep['row_detector']['best_val_pixel_iou']}",
        f"REGION DETECTION (learned)    P {dl['precision']}  R {dl['recall']}  F1 {dl['f1']}  mean IoU {dl['mean_iou_of_matches']}  "
        f"false alarms on row-free images {dl['false_alarm_rate_on_images_without_row']}",
        f"REGION DETECTION (classical)  P {dc['precision']}  R {dc['recall']}  F1 {dc['f1']}  mean IoU {dc['mean_iou_of_matches']}  "
        f"false alarms on row-free images {dc['false_alarm_rate_on_images_without_row']}",
        f"READER ON GT ROWS    CER {g['cer']}  WER {g['wer']}  exact {g['exact_sequence_rate']}  glyph count {g['glyph_count_accuracy']}",
        f"END TO END (learned) CER {e['cer']}  WER {e['wer']}  exact {e['exact_sequence_rate']}  glyph count {e['glyph_count_accuracy']}",
        f"THROUGH analyze()    {p['images']} images: {p['candidates_kept_by_screen']} kept as candidates, "
        f"{p['abstained']} abstained; exact among kept {p['exact_sequence_rate_of_kept']}",
        f"\nreport: {rep.get('report_path', '-')}",
    ])


__all__ = [
    "DEFAULT_DETECTOR_PATH",
    "DEFAULT_MODEL_PATH",
    "GLYPH_PX",
    "NOT_A_TRANSCRIPTION",
    "READER_ENGINE",
    "WORD_SEPARATOR",
    "GlyphNet",
    "RowNet",
    "SyntheticGlyphReader",
    "SyntheticRowDetector",
    "classify",
    "detect_rows",
    "detect_rows_learned",
    "glyph_crops",
    "load_glyph_model",
    "load_row_detector",
    "quad_crop",
    "read_row",
    "render_benchmark",
    "run_benchmark",
    "train_glyph_classifier",
    "train_row_detector",
]
