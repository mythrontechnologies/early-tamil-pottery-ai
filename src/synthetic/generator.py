"""Procedural generator of synthetic pottery-like images.   SYNTHETIC — NOT ARCHAEOLOGICAL EVIDENCE

No photograph is used anywhere: surfaces, sherd outlines, backgrounds and marks are all drawn
from random numbers (NumPy + OpenCV + Pillow). The images resemble a photographed sherd only
enough to exercise an image pipeline; they depict nothing that exists.

Determinism. Every random draw comes from ``numpy.random.default_rng([seed, artifact, stream])``:

* ``STREAM_OBJECT``  sherd outline, surface, curvature, wear       (never sees the class)
* ``STREAM_VIEWS``   how many photographs the artifact gets        (never sees the class)
* ``STREAM_DISTRACT`` scratches, cracks and pits on EVERY class     (never sees the class)
* ``STREAM_MARKS``   the class-specific marks                      (the only class-dependent stream)
* ``STREAM_LANGUAGE`` the sentence of a Tamil-Brahmi-like glyph row (generator 1.1.0; see below)

Generator 1.1.0: a Tamil-Brahmi-like glyph row is a SENTENCE of the invented synthetic language
(``src.synthetic.lexicon``; SYNTHETIC LANGUAGE — NOT TAMIL-BRAHMI). The row is laid out exactly as in 1.0.0 (same
draws, same geometry, same glyph count); its codes are kept when they already form a valid sentence, otherwise
they are replaced by a sentence of the same length drawn from ``STREAM_LANGUAGE``. So no other image changes, and
a row that was already grammatical (e.g. ``SG01 SG09 SG02``) is byte-identical. A row of fewer than 3 glyphs
(placement had to drop glyphs) cannot be a sentence and keeps its codes; its language target says so.
* ``VIEW_BASE + v``  camera, lighting, background, blur, noise, occlusion, JPEG quality of view v
                                                                    (never sees the class)

So photographic conditions are identically distributed across the four classes: no colour,
blur, exposure or framing can act as a label signature. Same seed + generator version +
configuration -> identical parameters and pixels; JPEG bytes are identical for the same
Pillow/libjpeg build.

Classes (generator facts, not archaeological categories):

* ``synthetic_tamil_brahmi_like`` - a left-to-right row of 3-8 synthetic glyphs (``SG00``-``SG15``)
  on a baseline, sometimes split into two "words" by a wider gap;
* ``synthetic_graffiti_like``     - 1-3 larger abstract motifs placed freely;
* ``synthetic_none``              - no deliberate mark (scratches, cracks and pits only, as on all classes);
* ``synthetic_uncertain``         - marks deliberately degraded below legibility: a row cut off by
  the break (``cut_row``), very faint and eroded marks (``faint``), isolated stroke fragments
  (``fragment``) or marks buried under dense scratching (``overscratched``).
"""

from __future__ import annotations

import hashlib
import io
import json
import math
from dataclasses import dataclass, field
from typing import Any

import cv2
import numpy as np
from PIL import Image

from . import SYNTHETIC_LABELS
from .glyphs import BY_CODE, GLYPH_CODES, MOTIFS, motif_strokes
from .lexicon import decode, sample_sentence

GENERATOR_VERSION = "1.1.0"       # 1.1.0: Tamil-Brahmi-like rows are synthetic-language sentences

STREAM_OBJECT, STREAM_MARKS, STREAM_DISTRACT, STREAM_VIEWS = 1, 2, 3, 4
STREAM_LANGUAGE = 5
VIEW_BASE = 100
_ASSIGNMENT_STREAM = 0xC1A55

#: Surface families (RGB 0-255). Neutral colour words; no ware name is implied.
SURFACES: dict[str, tuple[int, int, int]] = {
    "reddish": (168, 80, 50),
    "buff": (194, 156, 114),
    "grey": (130, 124, 118),
    "dark": (66, 56, 50),
    "two_tone": (168, 80, 50),          # blended towards "dark" across the sherd
}
SURFACE_NAMES = tuple(SURFACES)
BACKGROUNDS = ("studio_paper", "cloth", "soil", "wood", "grey_card")

INSCRIPTION_TYPE = {
    "synthetic_tamil_brahmi_like": "synthetic_glyph_row",
    "synthetic_graffiti_like": "synthetic_isolated_marks",
    "synthetic_none": "not_applicable",
    "synthetic_uncertain": "synthetic_degraded_marks",
}
INSCRIPTION_PRESENT = {
    "synthetic_tamil_brahmi_like": "yes",
    "synthetic_graffiti_like": "yes",
    "synthetic_none": "no",
    "synthetic_uncertain": "uncertain",
}


def rng_for(seed: int, artifact_index: int, stream: int) -> np.random.Generator:
    return np.random.default_rng([int(seed), int(artifact_index), int(stream)])


def artifact_id(index: int) -> str:
    return f"SYNTH-A{index + 1:04d}"


def image_id(index: int, view: int) -> str:
    return f"{artifact_id(index)}-V{view + 1}"


def class_assignment(seed: int, per_class: int) -> list[str]:
    """Class of every artifact index: a seeded permutation, so ids carry no class pattern."""
    labels = [lab for lab in SYNTHETIC_LABELS for _ in range(per_class)]
    order = np.random.default_rng([int(seed), _ASSIGNMENT_STREAM]).permutation(len(labels))
    return [labels[int(i)] for i in order]


def _r(x: float, nd: int = 4) -> float:
    return round(float(x), nd)


def _value_noise(rng: np.random.Generator, size: tuple[int, int], cells: int) -> np.ndarray:
    grid = rng.random((cells, cells)).astype(np.float32)
    return cv2.resize(grid, (size[1], size[0]), interpolation=cv2.INTER_CUBIC)


def _fbm(rng: np.random.Generator, size: tuple[int, int], octaves: tuple[tuple[int, float], ...]) -> np.ndarray:
    out = np.zeros(size, np.float32)
    total = 0.0
    for cells, weight in octaves:
        out += weight * _value_noise(rng, size, cells)
        total += weight
    return np.clip(out / total, 0.0, 1.0)


# --------------------------------------------------------------------------- #
# Artifact (object space)
# --------------------------------------------------------------------------- #


@dataclass
class ArtifactState:
    index: int
    artifact_id: str
    label: str
    S: int
    albedo: np.ndarray            # (S, S, 3) float32 0-1
    mask: np.ndarray              # (S, S) float32 0-1
    groove: np.ndarray            # (S, S) float32 0-1, all incised lines (marks + distractors)
    cracks: np.ndarray            # (S, S) float32 0-1
    curvature: np.ndarray         # (S, S) float32 shading multiplier
    centroid: tuple[float, float]
    diameter: float
    params: dict[str, Any]
    marks: dict[str, Any]         # inscription_type, uncertain_mode, glyph_sequence, regions (object px)
    n_views: int


def _sherd_outline(rng: np.random.Generator, S: int) -> tuple[np.ndarray, dict[str, Any]]:
    """An irregular fragment outline. Outlines too thin to hold any mark (largest inscribed circle
    under 18% of the canvas) are redrawn from the same stream, for every class alike."""
    attempts = 0
    while True:
        attempts += 1
        mask, info = _outline_once(rng, S)
        if attempts >= 25 or cv2.distanceTransform((mask > 0.5).astype(np.uint8), cv2.DIST_L2, 5).max() >= 0.18 * S:
            return mask, info | {"outline_attempts": attempts}


def _outline_once(rng: np.random.Generator, S: int) -> tuple[np.ndarray, dict[str, Any]]:
    n = int(rng.integers(6, 12))
    angles = np.sort(rng.uniform(0, 2 * math.pi, n))
    radii = rng.uniform(0.3, 0.46, n) * S
    sx, sy = rng.uniform(0.78, 1.0), rng.uniform(0.78, 1.0)
    rough = rng.uniform(0.004, 0.018) * S
    cx, cy = S / 2 + rng.uniform(-0.03, 0.03) * S, S / 2 + rng.uniform(-0.03, 0.03) * S
    corners = np.stack([cx + sx * radii * np.cos(angles), cy + sy * radii * np.sin(angles)], axis=1)
    pts = []
    for i in range(n):
        a, b = corners[i], corners[(i + 1) % n]
        seg = np.linalg.norm(b - a)
        k = max(2, int(seg / (0.03 * S)))
        normal = np.array([-(b - a)[1], (b - a)[0]]) / (seg + 1e-9)
        for t in np.linspace(0, 1, k, endpoint=False):
            jitter = rng.normal(0, rough) if t > 0 else 0.0
            pts.append(a + (b - a) * t + normal * jitter)
    poly = np.clip(np.array(pts), 1, S - 2).astype(np.int32)
    mask = np.zeros((S, S), np.uint8)
    cv2.fillPoly(mask, [poly], 255, lineType=cv2.LINE_AA)
    return mask.astype(np.float32) / 255.0, {"vertices": n, "elongation": [_r(sx), _r(sy)], "edge_roughness_px": _r(rough, 2)}


def _surface(rng: np.random.Generator, S: int, mask: np.ndarray) -> tuple[np.ndarray, np.ndarray, dict[str, Any]]:
    name = SURFACE_NAMES[int(rng.integers(len(SURFACE_NAMES)))]
    base = np.array(SURFACES[name], np.float32) + rng.normal(0, 9, 3).astype(np.float32)
    texture = float(rng.uniform(0.12, 0.32))
    noise = _fbm(rng, (S, S), ((4, 0.5), (14, 0.3), (48, 0.2)))
    shade = 1.0 + texture * (noise - 0.5) * 2
    albedo = np.clip(base / 255.0, 0, 1)[None, None, :] * shade[..., None]
    if name == "two_tone":
        ang = rng.uniform(0, 2 * math.pi)
        yy, xx = np.mgrid[0:S, 0:S].astype(np.float32) / S - 0.5
        t = 1 / (1 + np.exp(-(xx * math.cos(ang) + yy * math.sin(ang)) * rng.uniform(6, 14)))
        dark = np.array(SURFACES["dark"], np.float32) / 255.0
        albedo = albedo * (1 - t[..., None]) + dark[None, None, :] * shade[..., None] * t[..., None]
    # temper / grog speckles
    speck = np.zeros((S, S), np.float32)
    for _ in range(int(rng.integers(80, 320))):
        x, y = rng.integers(0, S, 2)
        cv2.circle(speck, (int(x), int(y)), int(rng.integers(1, 3)), float(rng.choice([-1.0, 1.0]) * rng.uniform(0.3, 1.0)), -1)
    albedo = albedo * (1 + 0.18 * speck[..., None])
    # slip wear: patches drifting towards a paler fabric colour
    wear = _fbm(rng, (S, S), ((6, 0.7), (20, 0.3)))
    wear_amount = float(rng.uniform(0.0, 0.5))
    fabric = np.array([0.72, 0.58, 0.44], np.float32)
    w = np.clip((wear - (1 - wear_amount)) * 3, 0, 1)[..., None] * 0.6
    albedo = albedo * (1 - w) + fabric[None, None, :] * w
    # broken edges show the paler fabric
    m8 = (mask * 255).astype(np.uint8)
    edge = (m8.astype(np.float32) - cv2.erode(m8, np.ones((5, 5), np.uint8)).astype(np.float32)) / 255.0
    albedo = albedo * (1 - 0.45 * edge[..., None]) + fabric[None, None, :] * 0.45 * edge[..., None]
    erosion = _fbm(rng, (S, S), ((5, 0.6), (17, 0.4)))
    return (np.clip(albedo, 0, 1).astype(np.float32), erosion,
            {"surface": name, "base_rgb": [int(v) for v in np.clip(base, 0, 255)], "texture_strength": _r(texture),
             "slip_wear": _r(wear_amount)})


def _curvature(rng: np.random.Generator, S: int) -> tuple[np.ndarray, dict[str, Any]]:
    ang = rng.uniform(0, math.pi)
    k = rng.uniform(0.0, 0.35)
    yy, xx = np.mgrid[0:S, 0:S].astype(np.float32) / (S / 2) - 1
    t = xx * math.cos(ang) + yy * math.sin(ang)
    return (1 - k * t * t).astype(np.float32), {"axis_degrees": _r(math.degrees(ang), 2), "strength": _r(k)}


def _transform(points: list[tuple[float, float]], center: np.ndarray, size: tuple[float, float],
               angle: float, bow: float = 0.0, bow_span: float = 1.0, bow_x0: float = 0.0) -> np.ndarray:
    p = (np.asarray(points, np.float64) - 0.5) * np.asarray(size)
    c, s = math.cos(angle), math.sin(angle)
    out = p @ np.array([[c, s], [-s, c]]) + center
    if bow:
        rel = (out[:, 0] - bow_x0) / max(bow_span, 1e-6)
        out[:, 1] += bow * rel * rel
    return out


def _draw_poly(canvas: np.ndarray, pts: np.ndarray, thickness: float, value: float) -> None:
    th = max(1, round(thickness))
    cv2.polylines(canvas, [np.round(pts * 4).astype(np.int32)], False, float(value), th, lineType=cv2.LINE_AA, shift=2)


def _inside(mask: np.ndarray, pts: np.ndarray, thr: float = 0.5) -> bool:
    S = mask.shape[0]
    if (pts < 2).any() or (pts > S - 3).any():
        return False
    return bool(all(mask[int(y), int(x)] > thr for x, y in pts))


_DIST_CACHE: list[tuple[np.ndarray, np.ndarray]] = []


def _distance(mask: np.ndarray) -> np.ndarray:
    """Distance-to-edge map of a sherd mask; cached for the mask currently being decorated."""
    if _DIST_CACHE and _DIST_CACHE[0][0] is mask:
        return _DIST_CACHE[0][1]
    dist = cv2.distanceTransform((mask > 0.5).astype(np.uint8), cv2.DIST_L2, 5)
    _DIST_CACHE[:] = [(mask, dist)]
    return dist


def _centers(rng: np.random.Generator, mask: np.ndarray, min_dist: float, n: int) -> np.ndarray:
    dist = _distance(mask)
    ys, xs = np.nonzero(dist > min_dist)
    if len(xs) == 0:
        ys, xs = np.nonzero(dist >= dist.max() * 0.8)
    pick = rng.integers(0, len(xs), n)
    return np.stack([xs[pick], ys[pick]], axis=1).astype(np.float64)


def _glyph_row(rng: np.random.Generator, S: int, cfg_marks: Any, n: int | None = None,
               h_scale: float = 1.0) -> dict[str, Any]:
    """Geometry of one left-to-right glyph row in a local frame centred on (0, 0)."""
    lo, hi = cfg_marks.glyphs_per_row
    n = int(n if n is not None else rng.integers(lo, hi + 1))
    h = rng.uniform(0.075, 0.125) * S * h_scale
    widths = h * rng.uniform(0.72, 1.0, n)
    gap = h * rng.uniform(0.25, 0.5)
    brk = int(rng.integers(2, n - 1)) if n >= 4 and rng.random() < cfg_marks.word_break_probability else None
    big_gap = gap * rng.uniform(2.6, 3.6)
    total = float(widths.sum() + gap * (n - 1) + ((big_gap - gap) if brk else 0))
    limit = 0.62 * S
    if total > limit:
        f = limit / total
        h, widths, gap, big_gap, total = h * f, widths * f, gap * f, big_gap * f, limit
    codes = [GLYPH_CODES[int(i)] for i in rng.integers(0, len(GLYPH_CODES), n)]
    xs, x = [], -total / 2
    for i in range(n):
        if i:
            x += big_gap if brk == i else gap
        xs.append(x + widths[i] / 2)
        x += widths[i]
    return {"n": n, "h": float(h), "widths": widths.tolist(), "xs": xs, "codes": codes, "break_at": brk,
            "total": float(total), "slope": rng.uniform(-8, 8), "bow": rng.uniform(-0.15, 0.15) * h,
            "thickness": float(np.clip(h * rng.uniform(0.08, 0.14), 2.0, 9.0)),
            "jitter": rng.normal(0, 1, (n, 4)).tolist()}


def _render_row(row: dict[str, Any], center: np.ndarray, groove: np.ndarray, depth: float) -> list[dict[str, Any]]:
    """Draw a laid-out row at ``center``; return per-glyph quads in object pixels."""
    slope = math.radians(row["slope"])
    c, s = math.cos(slope), math.sin(slope)
    out = []
    word = 0
    for i in range(row["n"]):
        if row["break_at"] is not None and i == row["break_at"]:
            word = 1
        jx, jy, jr, js = row["jitter"][i]
        scale = 1 + 0.06 * jx
        local = np.array([row["xs"][i] + 0.04 * row["h"] * jy, 0.04 * row["h"] * js])
        gc = center + np.array([local[0] * c - local[1] * s, local[0] * s + local[1] * c])
        gc[1] += row["bow"] * (row["xs"][i] / (row["total"] / 2 + 1e-6)) ** 2
        angle = slope + math.radians(5 * jr)
        size = (row["widths"][i] * scale, row["h"] * scale)
        glyph = BY_CODE[row["codes"][i]]
        th = row["thickness"] * (1 + 0.12 * js)
        for stroke in glyph.strokes:
            _draw_poly(groove, _transform(list(stroke), gc, size, angle), th, depth)
        for dot in glyph.dots:
            p = _transform([dot], gc, size, angle)[0]
            cv2.circle(groove, (round(p[0] * 4), round(p[1] * 4)), max(1, round(th * 0.9)) * 4, float(depth), -1,
                       lineType=cv2.LINE_AA, shift=2)
        quad = _transform([(0, 0), (1, 0), (1, 1), (0, 1)], gc, size, angle)
        out.append({"kind": "glyph", "token": glyph.code, "glyph_index": i, "word_index": word, "quad": quad.tolist()})
    return out


def _row_quads(row: dict[str, Any], center: np.ndarray) -> np.ndarray:
    """Quads of every glyph of ``row`` placed at ``center`` (no drawing), for placement checks."""
    scratch = np.zeros((4, 4), np.float32)
    return np.array([q["quad"] for q in _render_row(row, center, scratch, 0.0)]).reshape(-1, 2)


def _place_row(rng: np.random.Generator, mask: np.ndarray, row: dict[str, Any], tries: int = 60) -> np.ndarray | None:
    for center in _centers(rng, mask, row["h"] * 0.8, tries):
        if _inside(mask, _row_quads(row, center)):
            return center
    return None


def _motif(rng: np.random.Generator, S: int, mask: np.ndarray, placed: list[np.ndarray], groove: np.ndarray,
           depth: float, size_range: tuple[float, float] = (0.18, 0.36), tries: int = 50) -> dict[str, Any] | None:
    name = MOTIFS[int(rng.integers(len(MOTIFS)))]
    strokes = motif_strokes(name, rng)
    size = rng.uniform(*size_range) * S
    aspect = rng.uniform(0.75, 1.25)
    angle = math.radians(rng.uniform(-40, 40))
    th = float(np.clip(size * rng.uniform(0.025, 0.05), 2.5, 10.0))
    for center in _centers(rng, mask, size * 0.3, tries):
        pts = [_transform(list(st), center, (size * aspect, size), angle) for st in strokes]
        allp = np.concatenate(pts)
        lo, hi = allp.min(axis=0), allp.max(axis=0)
        box = np.array([lo, hi])
        overlap = any(not (box[1, 0] < b[0, 0] or box[0, 0] > b[1, 0] or box[1, 1] < b[0, 1] or box[0, 1] > b[1, 1])
                      for b in placed)
        if overlap or not _inside(mask, np.array([lo, hi, [lo[0], hi[1]], [hi[0], lo[1]], center])):
            continue
        for p in pts:
            _draw_poly(groove, p, th, depth)
        placed.append(box)
        return {"kind": "mark", "token": name, "quad": [lo.tolist(), [hi[0], lo[1]], hi.tolist(), [lo[0], hi[1]]]}
    return None


def _visible_box(marks: np.ndarray, mask: np.ndarray) -> list[list[float]] | None:
    ys, xs = np.nonzero((marks * mask) > 0.03)
    if len(xs) < 6:
        return None
    lo, hi = [float(xs.min()), float(ys.min())], [float(xs.max()), float(ys.max())]
    return [lo, [hi[0], lo[1]], hi, [lo[0], hi[1]]]


def _marks(rng: np.random.Generator, label: str, S: int, mask: np.ndarray, cfg: Any,
           erosion: np.ndarray, language: np.random.Generator | None = None) -> tuple[np.ndarray, dict[str, Any]]:
    """Class-specific marks. Returns (marks groove map, description). Only this stream sees the class."""
    m = cfg.marks
    groove = np.zeros((S, S), np.float32)
    info: dict[str, Any] = {"inscription_type": INSCRIPTION_TYPE[label], "uncertain_mode": "not_applicable",
                            "glyph_sequence": [], "regions": [], "depth": None}
    if label == "synthetic_none":
        return groove, info
    depth = float(rng.uniform(0.55, 1.0))
    info["depth"] = _r(depth)

    if label == "synthetic_tamil_brahmi_like":
        lo, hi = m.glyphs_per_row
        n0 = int(rng.integers(lo, hi + 1))
        for attempt in range(14):   # shrink the glyphs first; drop glyphs only if that is not enough
            n = max(2, n0 - max(0, attempt - 5))
            row = _glyph_row(rng, S, m, n=n, h_scale=0.9 ** min(attempt, 5))
            center = _place_row(rng, mask, row)
            if center is not None:
                break
        else:  # pragma: no cover - outlines are guaranteed an inscribed circle of 18% of the canvas
            raise RuntimeError("could not place a glyph row")
        if language is not None and row["n"] >= 3 and decode(row["codes"]).status != "translated":
            row["codes"] = sample_sentence(language, row["n"])
        glyphs = _render_row(row, center, groove, depth)
        words: list[list[str]] = [[], []]
        for g in glyphs:
            words[g["word_index"]].append(g["token"])
        info["glyph_sequence"] = [w for w in words if w]
        allq = np.array([g["quad"] for g in glyphs]).reshape(-1, 2)
        lo, hi = allq.min(axis=0), allq.max(axis=0)
        info["regions"] = [{"kind": "glyph_row", "token": "row", "quad": [lo.tolist(), [hi[0], lo[1]], hi.tolist(), [lo[0], hi[1]]]},
                           *glyphs]
        return groove, info

    if label == "synthetic_graffiti_like":
        lo, hi = m.graffiti_motifs
        placed: list[np.ndarray] = []
        for _ in range(int(rng.integers(lo, hi + 1))):
            r = _motif(rng, S, mask, placed, groove, depth)
            if r is not None:
                info["regions"].append(r)
        for lo_hi in ((0.12, 0.16), (0.09, 0.12), (0.06, 0.09), (0.04, 0.06)):   # narrow sherd: shrink until one fits
            if info["regions"]:
                break
            r = _motif(rng, S, mask, placed, groove, depth, lo_hi, 200)
            if r is not None:
                info["regions"].append(r)
        if not info["regions"]:  # pragma: no cover - a 4% motif fits inside any generated outline
            raise RuntimeError(f"could not place a mark on artifact index with mask area {int(mask.sum())}")
        return groove, info

    # synthetic_uncertain: deliberately below legibility
    mode = m.uncertain_modes[int(rng.integers(len(m.uncertain_modes)))]
    info["uncertain_mode"] = mode
    if mode == "cut_row":
        for _ in range(80):
            row = _glyph_row(rng, S, m, n=int(rng.integers(3, 7)))
            m8 = (mask > 0.5).astype(np.uint8)
            ys, xs = np.nonzero(m8 - cv2.erode(m8, np.ones((3, 3), np.uint8)))
            k = int(rng.integers(len(xs)))
            center = np.array([xs[k], ys[k]], np.float64) + rng.normal(0, row["h"] * 0.5, 2)
            quads = _row_quads(row, center).reshape(-1, 4, 2)
            inside = sum(_inside(mask, q.mean(axis=0, keepdims=True)) for q in quads)
            if 1 <= inside <= max(1, row["n"] - 2):
                _render_row(row, center, groove, depth)
                break
    elif mode == "faint":
        depth = float(rng.uniform(0.16, 0.3))
        info["depth"] = _r(depth)
        if rng.random() < 0.5:
            row = _glyph_row(rng, S, m)
            center = _place_row(rng, mask, row)
            if center is not None:
                _render_row(row, center, groove, depth)
        else:
            _motif(rng, S, mask, [], groove, depth)
        groove *= np.clip(erosion * 1.6 - 0.25, 0.15, 1.0)          # patchy erosion
    elif mode == "fragment":
        for _ in range(int(rng.integers(1, 4))):
            glyph = BY_CODE[GLYPH_CODES[int(rng.integers(len(GLYPH_CODES)))]]
            stroke = np.asarray(glyph.strokes[int(rng.integers(len(glyph.strokes)))])
            keep = max(2, int(len(stroke) * rng.uniform(0.4, 0.8)))
            part = stroke[:keep] if len(stroke) > 2 else stroke
            h = rng.uniform(0.07, 0.12) * S
            center = _centers(rng, mask, h, 1)[0]
            _draw_poly(groove, _transform([tuple(p) for p in part], center, (h, h), math.radians(rng.uniform(-90, 90))),
                       float(np.clip(h * rng.uniform(0.08, 0.14), 2, 8)), depth)
    else:  # overscratched
        if rng.random() < 0.5:
            row = _glyph_row(rng, S, m)
            center = _place_row(rng, mask, row)
            if center is not None:
                _render_row(row, center, groove, depth)
        else:
            _motif(rng, S, mask, [], groove, depth)
        box = _visible_box(groove, mask)
        cx, cy = (np.mean(box, axis=0) if box else (S / 2, S / 2))
        for _ in range(int(rng.integers(8, 17))):
            a = rng.uniform(0, math.pi)
            L = rng.uniform(0.15, 0.4) * S
            c0 = np.array([cx, cy]) + rng.normal(0, 0.06 * S, 2)
            d = np.array([math.cos(a), math.sin(a)]) * L / 2
            _draw_poly(groove, np.array([c0 - d, c0 + d]), rng.uniform(1.5, 4.0), rng.uniform(0.5, 0.85))
    if _visible_box(groove, mask) is None:          # the chosen degradation left nothing visible: one fragment
        h = rng.uniform(0.07, 0.1) * S
        center = _centers(rng, mask, h, 1)[0]
        fragment = BY_CODE[GLYPH_CODES[int(rng.integers(len(GLYPH_CODES)))]].strokes[0]
        _draw_poly(groove, _transform(list(fragment), center, (h, h), 0.0), 3.0, max(depth, 0.3))
    box = _visible_box(groove, mask)
    if box is not None:
        info["regions"] = [{"kind": "mark", "token": f"uncertain_{mode}", "quad": box}]
    return groove, info


def _distractors(rng: np.random.Generator, S: int, mask: np.ndarray, cfg: Any) -> tuple[np.ndarray, np.ndarray, dict[str, Any]]:
    c = cfg.conditions
    groove = np.zeros((S, S), np.float32)
    cracks = np.zeros((S, S), np.float32)
    n_s, n_c, n_p = (int(rng.integers(0, c.scratches_max + 1)), int(rng.integers(0, c.cracks_max + 1)),
                     int(rng.integers(0, c.pits_max + 1)))
    for _ in range(n_s):
        p0 = _centers(rng, mask, 4, 1)[0]
        a = rng.uniform(0, 2 * math.pi)
        L = rng.uniform(0.12, 0.6) * S
        bend = rng.normal(0, 0.08)
        t = np.linspace(0, 1, 12)[:, None]
        d = np.array([math.cos(a), math.sin(a)])
        nrm = np.array([-d[1], d[0]])
        pts = p0 + t * L * d + (t * (1 - t)) * bend * L * nrm
        _draw_poly(groove, pts, rng.uniform(1.0, 2.2), rng.uniform(0.15, 0.42))
    for _ in range(n_c):
        p = _centers(rng, mask, 4, 1)[0]
        a = rng.uniform(0, 2 * math.pi)
        pts = [p.copy()]
        for _ in range(int(rng.integers(5, 14))):
            a += rng.normal(0, 0.5)
            p = p + np.array([math.cos(a), math.sin(a)]) * rng.uniform(6, 18)
            pts.append(p.copy())
        _draw_poly(cracks, np.array(pts), rng.uniform(1.0, 2.0), rng.uniform(0.5, 1.0))
    for _ in range(n_p):
        p = _centers(rng, mask, 3, 1)[0]
        cv2.circle(groove, (int(p[0]), int(p[1])), int(rng.integers(1, 4)), float(rng.uniform(0.25, 0.6)), -1,
                   lineType=cv2.LINE_AA)
    return groove, cracks * mask, {"scratches": n_s, "cracks": n_c, "pits": n_p}


def build_artifact(cfg: Any, index: int, label: str) -> ArtifactState:
    """Everything about one synthetic object that is shared by all of its photographs."""
    S = cfg.object_px
    ro = rng_for(cfg.seed, index, STREAM_OBJECT)
    mask, outline = _sherd_outline(ro, S)
    albedo, erosion, surface = _surface(ro, S, mask)
    curvature, curv = _curvature(ro, S)
    groove_strength = float(ro.uniform(0.45, 0.75))
    marks_groove, marks = _marks(rng_for(cfg.seed, index, STREAM_MARKS), label, S, mask, cfg, erosion,
                                 rng_for(cfg.seed, index, STREAM_LANGUAGE))
    dist_groove, cracks, distract = _distractors(rng_for(cfg.seed, index, STREAM_DISTRACT), S, mask, cfg)
    groove = np.clip(np.maximum(marks_groove, dist_groove) * mask, 0, 1)
    groove = cv2.GaussianBlur(groove, (0, 0), 0.8)
    rv = rng_for(cfg.seed, index, STREAM_VIEWS)
    n_views = cfg.views.min
    while n_views < cfg.views.max and rv.random() < cfg.views.p_extra:
        n_views += 1
    ys, xs = np.nonzero(mask > 0.5)
    cxy = (float(xs.mean()), float(ys.mean()))
    diameter = 2 * float(np.sqrt(((xs - cxy[0]) ** 2 + (ys - cxy[1]) ** 2).max()))
    params = {"outline": outline, "surface": surface, "curvature": curv, "groove_darkness": _r(groove_strength),
              "distractors": distract, "marks_depth": marks["depth"], "uncertain_mode": marks["uncertain_mode"],
              "n_views": n_views}
    return ArtifactState(index, artifact_id(index), label, S, albedo, mask, groove, cracks, curvature, cxy, diameter,
                         params, marks, n_views)


# --------------------------------------------------------------------------- #
# Views (camera space)
# --------------------------------------------------------------------------- #


def sample_view(cfg: Any, state: ArtifactState, view: int) -> dict[str, Any]:
    """Photographic conditions of one view. Never depends on the class."""
    c = cfg.conditions
    rng = rng_for(cfg.seed, state.index, VIEW_BASE + view)
    W, H = (int(v) for v in rng.integers(cfg.canvas.min_px, cfg.canvas.max_px + 1, 2))
    bg_kind = BACKGROUNDS[int(rng.integers(len(BACKGROUNDS)))]
    vp = {
        "width": W, "height": H,
        "background": {"kind": bg_kind, "hue": _r(rng.uniform(0, 1)), "saturation": _r(rng.uniform(0.0, 0.35)),
                       "value": _r(rng.uniform(0.25, 0.92)), "seed": int(rng.integers(0, 2**31 - 1))},
        "object_fill": _r(rng.uniform(*c.object_fill)),
        "rotation_degrees": _r(rng.uniform(-c.rotation_degrees_max, c.rotation_degrees_max), 3),
        "offset": [_r(v) for v in rng.uniform(-1, 1, 2)],
        "perspective": _r(rng.uniform(0, c.perspective_max)),
        "perspective_jitter": [[_r(a), _r(b)] for a, b in rng.uniform(-1, 1, (4, 2))],
        "light_azimuth_degrees": _r(rng.uniform(0, 360), 2),
        "relief": _r(rng.uniform(0.6, 1.4)),
        "light_gradient": _r(rng.uniform(0, 0.35)),
        "light_gradient_degrees": _r(rng.uniform(0, 360), 2),
        "shadow": {"blur": _r(rng.uniform(4, 14), 2), "distance": _r(rng.uniform(3, 12), 2), "darkness": _r(rng.uniform(0.2, 0.5))},
        "exposure": _r(rng.uniform(*c.exposure)),
        "contrast": _r(rng.uniform(*c.contrast)),
        "white_balance": [_r(1 + v) for v in rng.uniform(-c.white_balance_jitter, c.white_balance_jitter, 3)],
        "vignette": _r(rng.uniform(0, 0.35)),
    }
    blurred = rng.random() < c.blur_probability
    vp["blur"] = ({"kind": "motion" if rng.random() < 0.2 else "gaussian", "sigma": _r(rng.uniform(0.3, c.blur_sigma_max)),
                   "angle_degrees": _r(rng.uniform(0, 180), 2)} if blurred else {"kind": "none", "sigma": 0.0, "angle_degrees": 0.0})
    vp["noise_sigma"] = _r(rng.uniform(0, c.noise_sigma_max), 3)
    vp["noise_seed"] = int(rng.integers(0, 2**31 - 1))
    occluded = rng.random() < c.occlusion_probability
    vp["occlusion"] = ({"kind": "card" if rng.random() < 0.5 else "blob",
                        "fraction": _r(rng.uniform(0.02, c.occlusion_max_fraction)),
                        "center": [_r(v) for v in rng.uniform(0.1, 0.9, 2)], "angle_degrees": _r(rng.uniform(0, 180), 2),
                        "aspect": _r(rng.uniform(0.3, 1.0)), "gray": _r(rng.uniform(0.15, 0.95))} if occluded else None)
    vp["jpeg_quality"] = int(rng.integers(cfg.jpeg_quality.min, cfg.jpeg_quality.max + 1))
    return vp


def _background(bg: dict[str, Any], W: int, H: int) -> np.ndarray:
    rng = np.random.default_rng(bg["seed"])
    hsv = np.asarray([[[int(bg["hue"] * 179), int(bg["saturation"] * 255), int(bg["value"] * 255)]]], np.uint8)
    base = cv2.cvtColor(hsv, cv2.COLOR_HSV2RGB)[0, 0].astype(np.float32) / 255.0
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    kind = bg["kind"]
    if kind == "studio_paper":
        f = 1 + 0.18 * (yy / H - 0.5) + 0.03 * (_value_noise(rng, (H, W), 6) - 0.5)
    elif kind == "cloth":
        f = 1 + 0.05 * np.sin(xx * 1.7) * np.sin(yy * 1.7) + 0.12 * (_fbm(rng, (H, W), ((8, 0.6), (60, 0.4))) - 0.5)
    elif kind == "soil":
        f = 1 + 0.45 * (_fbm(rng, (H, W), ((10, 0.4), (40, 0.35), (120, 0.25))) - 0.5)
    elif kind == "wood":
        a = rng.uniform(0, math.pi)
        warp = 12 * _value_noise(rng, (H, W), 5)
        f = 1 + 0.12 * np.sin((xx * math.cos(a) + yy * math.sin(a) + warp) * 0.25) \
            + 0.08 * (_value_noise(rng, (H, W), 30) - 0.5)
    else:  # grey_card
        base = np.full(3, float(np.mean(base)), np.float32)
        f = 1 + 0.08 * (xx / W - 0.5) + 0.02 * (_value_noise(rng, (H, W), 4) - 0.5)
    return np.clip(base[None, None, :] * f[..., None], 0, 1).astype(np.float32)


def _homography(state: ArtifactState, vp: dict[str, Any]) -> np.ndarray:
    W, H = vp["width"], vp["height"]
    m = min(W, H)
    s = vp["object_fill"] * m / state.diameter
    a = math.radians(vp["rotation_degrees"])
    margin = m * (1 - vp["object_fill"]) / 2 * 0.9
    tx, ty = W / 2 + vp["offset"][0] * margin, H / 2 + vp["offset"][1] * margin
    cx, cy = state.centroid
    A = np.array([[s * math.cos(a), -s * math.sin(a), 0], [s * math.sin(a), s * math.cos(a), 0], [0, 0, 1]])
    A[0, 2] = tx - (A[0, 0] * cx + A[0, 1] * cy)
    A[1, 2] = ty - (A[1, 0] * cx + A[1, 1] * cy)
    S = state.S
    src = np.asarray([[0, 0], [S, 0], [S, S], [0, S]], np.float32)
    dst = cv2.perspectiveTransform(src[None], A)[0]
    dst = dst + np.asarray(vp["perspective_jitter"], np.float32) * vp["perspective"] * state.diameter * s
    return cv2.getPerspectiveTransform(src, dst.astype(np.float32))


def project(points: np.ndarray, Hm: np.ndarray) -> np.ndarray:
    return cv2.perspectiveTransform(np.asarray(points, np.float32).reshape(1, -1, 2), Hm)[0]


def render_view(state: ArtifactState, vp: dict[str, Any]) -> tuple[np.ndarray, dict[str, Any]]:
    """Render one view. Returns (uint8 RGB array before JPEG, geometry with regions in pixels)."""
    S, W, H = state.S, vp["width"], vp["height"]
    gb = state.groove
    gx = cv2.Sobel(gb, cv2.CV_32F, 1, 0, ksize=3)
    gy = cv2.Sobel(gb, cv2.CV_32F, 0, 1, ksize=3)
    az = math.radians(vp["light_azimuth_degrees"])
    relief = (gx * math.cos(az) + gy * math.sin(az)) * 0.2 * vp["relief"]
    shade = (1 - state.params["groove_darkness"] * gb + relief) * state.curvature
    ga = math.radians(vp["light_gradient_degrees"])
    yy, xx = np.mgrid[0:S, 0:S].astype(np.float32) / S - 0.5
    shade *= 1 + vp["light_gradient"] * (xx * math.cos(ga) + yy * math.sin(ga))
    obj = state.albedo * shade[..., None] * (1 - 0.65 * state.cracks[..., None])
    obj = np.clip(obj, 0, 1).astype(np.float32)

    Hm = _homography(state, vp)
    scale = vp["object_fill"] * min(W, H) / state.diameter
    pre = float(np.clip(0.5 * (1 / max(scale, 1e-3) - 1), 0, 1.6))
    if pre > 0.05:
        obj = cv2.GaussianBlur(obj, (0, 0), pre)
    warped = cv2.warpPerspective(obj, Hm, (W, H), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT)
    alpha = cv2.warpPerspective(state.mask, Hm, (W, H), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT)

    bg = _background(vp["background"], W, H)
    sh = vp["shadow"]
    shadow = cv2.GaussianBlur(alpha, (0, 0), sh["blur"])
    dx, dy = -math.cos(az) * sh["distance"], -math.sin(az) * sh["distance"]
    shadow = cv2.warpAffine(shadow, np.asarray([[1, 0, dx], [0, 1, dy]], np.float32), (W, H))
    bg = bg * (1 - sh["darkness"] * shadow[..., None])
    img = bg * (1 - alpha[..., None]) + warped * alpha[..., None]

    occ_mask = np.zeros((H, W), np.float32)
    occ = vp["occlusion"]
    if occ:
        area = occ["fraction"] * W * H
        rw = math.sqrt(area / occ["aspect"])
        rh = area / rw
        center = (occ["center"][0] * W, occ["center"][1] * H)
        if occ["kind"] == "card":
            box = cv2.boxPoints((center, (rw, rh), occ["angle_degrees"]))
            cv2.fillPoly(occ_mask, [np.round(box * 4).astype(np.int32)], 1.0, lineType=cv2.LINE_AA, shift=2)
        else:
            cv2.ellipse(occ_mask, (round(center[0] * 4), round(center[1] * 4)), (round(rw / 2 * 4), round(rh / 2 * 4)),
                        occ["angle_degrees"], 0, 360, 1.0, -1, lineType=cv2.LINE_AA, shift=2)
        tone = np.full(3, occ["gray"], np.float32)
        img = img * (1 - occ_mask[..., None]) + tone[None, None, :] * occ_mask[..., None]

    mean = img.mean()
    img = (img - mean) * vp["contrast"] + mean
    img = img * vp["exposure"] * np.asarray(vp["white_balance"], np.float32)[None, None, :]
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    r2 = ((xx / W - 0.5) ** 2 + (yy / H - 0.5) ** 2) * 2
    img = img * (1 - vp["vignette"] * r2)[..., None]
    blur = vp["blur"]
    if blur["kind"] == "gaussian":
        img = cv2.GaussianBlur(img, (0, 0), blur["sigma"])
    elif blur["kind"] == "motion":
        k = max(3, round(blur["sigma"] * 4) | 1)
        kernel = np.zeros((k, k), np.float32)
        kernel[k // 2, :] = 1
        rot = cv2.getRotationMatrix2D((k / 2 - 0.5, k / 2 - 0.5), blur["angle_degrees"], 1.0)
        kernel = cv2.warpAffine(kernel, rot, (k, k))
        img = cv2.filter2D(img, -1, (kernel / max(kernel.sum(), 1e-6)).astype(np.float32))
    if vp["noise_sigma"] > 0:
        img = img + np.random.default_rng(vp["noise_seed"]).normal(0, vp["noise_sigma"] / 255, img.shape).astype(np.float32)
    out = np.clip(np.round(img * 255), 0, 255).astype(np.uint8)

    regions = []
    for reg in state.marks["regions"]:
        quad = project(np.asarray(reg["quad"]), Hm)
        lo = np.clip(quad.min(axis=0), 0, [W, H])
        hi = np.clip(quad.max(axis=0), 0, [W, H])
        if hi[0] - lo[0] < 1 or hi[1] - lo[1] < 1:
            continue
        x0, y0, x1, y1 = (int(v) for v in (lo[0], lo[1], math.ceil(hi[0]), math.ceil(hi[1])))
        visible = 1.0 - float(occ_mask[y0:y1, x0:x1].mean()) if occ else 1.0
        regions.append({k: v for k, v in reg.items() if k != "quad"}
                       | {"x": _r(lo[0] / W, 5), "y": _r(lo[1] / H, 5), "width": _r((hi[0] - lo[0]) / W, 5),
                          "height": _r((hi[1] - lo[1]) / H, 5),
                          "quad": [[_r(px / W, 5), _r(py / H, 5)] for px, py in quad.tolist()],
                          "visible_fraction": _r(visible, 3)})
    return out, {"regions": regions, "homography": [[_r(v, 6) for v in row] for row in Hm.tolist()]}


def encode_jpeg(rgb: np.ndarray, quality: int) -> bytes:
    buf = io.BytesIO()
    Image.fromarray(rgb, "RGB").save(buf, format="JPEG", quality=int(quality), optimize=False, subsampling=2)
    return buf.getvalue()


@dataclass
class GeneratedView:
    artifact_index: int
    view: int
    image_id: str
    jpeg: bytes
    sha256: str
    width: int
    height: int
    view_params: dict[str, Any]
    regions: list[dict[str, Any]] = field(default_factory=list)

    @property
    def params_digest(self) -> str:
        return hashlib.sha256(json.dumps(self.view_params, sort_keys=True).encode()).hexdigest()


def generate_view(cfg: Any, state: ArtifactState, view: int, overrides: dict[str, Any] | None = None) -> GeneratedView:
    vp = sample_view(cfg, state, view)
    if overrides:
        vp = {**vp, **overrides}
    rgb, geo = render_view(state, vp)
    data = encode_jpeg(rgb, vp["jpeg_quality"])
    return GeneratedView(state.index, view, image_id(state.index, view), data, hashlib.sha256(data).hexdigest(),
                         vp["width"], vp["height"], vp, geo["regions"])


__all__ = [
    "BACKGROUNDS",
    "GENERATOR_VERSION",
    "INSCRIPTION_PRESENT",
    "INSCRIPTION_TYPE",
    "SURFACES",
    "ArtifactState",
    "GeneratedView",
    "artifact_id",
    "build_artifact",
    "class_assignment",
    "encode_jpeg",
    "generate_view",
    "image_id",
    "project",
    "render_view",
    "rng_for",
    "sample_view",
]
