"""Synthetic glyph primitives and abstract mark motifs.   SYNTHETIC — NOT ARCHAEOLOGICAL EVIDENCE

The glyph alphabet below is a set of sixteen **compound geometric shapes invented for this
generator** (combs, brackets, stepped lines, rings with spurs...). It was not derived from a
Tamil-Brahmi sign list, a published inscription, a photograph or any other script table, and
it deliberately avoids single-element signs (a lone cross, ring, angle or vertical stroke) that
coincide with real letters. The codes ``SG00``-``SG15`` ("synthetic glyph") are labels for the
OCR benchmark; they have no sound, no reading and no meaning.

The motif generators draw larger, non-linear abstract marks (bursts, hatching, spirals,
zigzags...) for the ``synthetic_graffiti_like`` category. Recognisable real pottery-graffiti
motifs (ladders, tridents, fish, bow-and-arrow, svastika, trees) are intentionally absent.

Everything is expressed in a unit box (x right, y down). Callers scale, rotate and place it.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

Point = tuple[float, float]


def _arc(cx: float, cy: float, r: float, a0: float, a1: float, n: int = 14) -> list[Point]:
    return [(cx + r * math.cos(math.radians(a)), cy + r * math.sin(math.radians(a)))
            for a in np.linspace(a0, a1, n)]


@dataclass(frozen=True)
class Glyph:
    code: str
    name: str
    strokes: tuple[tuple[Point, ...], ...]
    dots: tuple[Point, ...] = field(default_factory=tuple)


def _g(code: str, name: str, strokes: list[list[Point]], dots: list[Point] | None = None) -> Glyph:
    return Glyph(code, name, tuple(tuple(s) for s in strokes), tuple(dots or ()))


#: The synthetic glyph alphabet (invented compound shapes; see the module docstring).
GLYPHS: tuple[Glyph, ...] = (
    _g("SG00", "comb", [[(0.12, 0.22), (0.88, 0.22)], [(0.2, 0.22), (0.2, 0.62)], [(0.5, 0.22), (0.5, 0.62)],
                        [(0.8, 0.22), (0.8, 0.62)]]),
    _g("SG01", "hooked bar with tick", [[(0.5, 0.1), (0.5, 0.72), (0.68, 0.9), (0.86, 0.74)], [(0.5, 0.3), (0.26, 0.16)]]),
    _g("SG02", "open box with tail", [[(0.82, 0.2), (0.2, 0.2), (0.2, 0.68), (0.82, 0.68)], [(0.82, 0.68), (0.9, 0.9)]]),
    _g("SG03", "double chevron", [[(0.14, 0.18), (0.5, 0.44), (0.86, 0.18)], [(0.14, 0.56), (0.5, 0.82), (0.86, 0.56)]]),
    _g("SG04", "ring with spur", [_arc(0.42, 0.5, 0.26, 0, 360, 20), [(0.68, 0.5), (0.92, 0.18)]]),
    _g("SG05", "zigzag", [[(0.08, 0.3), (0.3, 0.72), (0.5, 0.3), (0.7, 0.72), (0.92, 0.3)]]),
    _g("SG06", "step", [[(0.14, 0.84), (0.14, 0.5), (0.5, 0.5), (0.5, 0.16), (0.86, 0.16)]]),
    _g("SG07", "triangle with dot", [[(0.5, 0.12), (0.88, 0.8), (0.12, 0.8), (0.5, 0.12)]], dots=[(0.5, 0.58)]),
    _g("SG08", "S-curve with bar", [_arc(0.5, 0.32, 0.2, 0, -270, 14) + _arc(0.5, 0.72, 0.2, 270, 0, 14)[1:],
                                    [(0.18, 0.52), (0.82, 0.52)]]),
    _g("SG09", "bracket pair", [[(0.38, 0.14), (0.18, 0.14), (0.18, 0.86), (0.38, 0.86)],
                                [(0.62, 0.14), (0.82, 0.14), (0.82, 0.86), (0.62, 0.86)]]),
    _g("SG10", "peak over ring", [[(0.16, 0.62), (0.5, 0.12), (0.84, 0.62)], _arc(0.5, 0.78, 0.13, 0, 360, 16)]),
    _g("SG11", "two bars and diagonal", [[(0.14, 0.34), (0.86, 0.34)], [(0.14, 0.66), (0.86, 0.66)],
                                         [(0.26, 0.88), (0.74, 0.12)]]),
    _g("SG12", "open spiral hook", [_arc(0.5, 0.5, 0.32, -90, 180, 18), _arc(0.5, 0.5, 0.14, 180, 400, 12)]),
    _g("SG13", "beam", [[(0.14, 0.18), (0.86, 0.18)], [(0.5, 0.18), (0.5, 0.82)], [(0.28, 0.82), (0.72, 0.82)]]),
    _g("SG14", "wave over bar", [[(0.1 + 0.8 * t, 0.32 - 0.14 * math.sin(t * 2 * math.pi)) for t in np.linspace(0, 1, 16)],
                                 [(0.16, 0.76), (0.84, 0.76)]]),
    _g("SG15", "corner with dots", [[(0.2, 0.14), (0.2, 0.82), (0.82, 0.82)]], dots=[(0.55, 0.32), (0.74, 0.54)]),
)
GLYPH_CODES: tuple[str, ...] = tuple(g.code for g in GLYPHS)
BY_CODE: dict[str, Glyph] = {g.code: g for g in GLYPHS}
assert len(set(GLYPH_CODES)) == len(GLYPHS) == 16

MOTIFS: tuple[str, ...] = ("burst", "hatch", "nested_chevrons", "spiral", "zigzag_band", "concentric_arcs", "scribble")


def motif_strokes(name: str, rng: np.random.Generator) -> list[list[Point]]:
    """One abstract motif as polylines in the unit box. Every call varies with ``rng``."""
    if name == "burst":
        n = int(rng.integers(5, 10))
        offs = rng.uniform(0, 2 * math.pi)
        out = []
        for k in range(n):
            a = offs + 2 * math.pi * k / n + rng.normal(0, 0.12)
            r0, r1 = rng.uniform(0.0, 0.12), rng.uniform(0.32, 0.5)
            out.append([(0.5 + r0 * math.cos(a), 0.5 + r0 * math.sin(a)), (0.5 + r1 * math.cos(a), 0.5 + r1 * math.sin(a))])
        return out
    if name == "hatch":
        a, b = int(rng.integers(3, 6)), int(rng.integers(3, 6))
        out = [[(0.1, 0.1 + 0.8 * i / (a - 1)), (0.9, 0.1 + 0.8 * i / (a - 1) + rng.normal(0, 0.03))] for i in range(a)]
        out += [[(0.1 + 0.8 * j / (b - 1), 0.1), (0.1 + 0.8 * j / (b - 1) + rng.normal(0, 0.05), 0.9)] for j in range(b)]
        return out
    if name == "nested_chevrons":
        n = int(rng.integers(2, 5))
        return [[(0.1 + 0.08 * k, 0.15 + 0.16 * k), (0.5, 0.55 + 0.11 * k * 0.6), (0.9 - 0.08 * k, 0.15 + 0.16 * k)]
                for k in range(n)]
    if name == "spiral":
        turns = rng.uniform(1.5, 3.0)
        t = np.linspace(0, turns * 2 * math.pi, 60)
        r = 0.04 + 0.42 * t / t[-1]
        sign = 1 if rng.random() < 0.5 else -1
        return [[(0.5 + float(ri * math.cos(sign * ti)), 0.5 + float(ri * math.sin(sign * ti))) for ri, ti in zip(r, t)]]
    if name == "zigzag_band":
        peaks = int(rng.integers(4, 9))
        xs = np.linspace(0.05, 0.95, 2 * peaks + 1)
        line = [(float(x), 0.35 if i % 2 == 0 else 0.65) for i, x in enumerate(xs)]
        out = [line]
        if rng.random() < 0.5:
            out.append([(x, y + 0.18) for x, y in line])
        return out
    if name == "concentric_arcs":
        n = int(rng.integers(2, 5))
        a0 = rng.uniform(150, 210)
        return [_arc(0.5, 0.85, 0.15 + 0.11 * k, a0, a0 + rng.uniform(110, 170), 18) for k in range(n)]
    if name == "scribble":
        pts = rng.uniform(0.1, 0.9, size=(int(rng.integers(6, 12)), 2))
        fine = []
        for i in range(len(pts) - 1):
            for t in np.linspace(0, 1, 6, endpoint=False):
                fine.append((float(pts[i, 0] * (1 - t) + pts[i + 1, 0] * t), float(pts[i, 1] * (1 - t) + pts[i + 1, 1] * t)))
        fine.append((float(pts[-1, 0]), float(pts[-1, 1])))
        return [fine]
    raise ValueError(f"unknown motif {name!r}")


__all__ = ["BY_CODE", "GLYPHS", "GLYPH_CODES", "MOTIFS", "Glyph", "motif_strokes"]
