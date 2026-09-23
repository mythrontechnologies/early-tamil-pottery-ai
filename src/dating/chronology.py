"""Signed-year arithmetic and the project's chronological reference frame.

Years are signed integers: negative = BCE, positive = CE. **There is no year 0**: 1 BCE
(-1) is followed directly by 1 CE (1). Every function here enforces that.

The competing positions on the earliest Tamil-Brahmi, and the named periods, are read
from ``configs/project.yaml``. Nothing is hard-coded, and every position carries its
verification status, which the reasoning layer reports. See docs/CHRONOLOGICAL_SCOPE.md.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from src.dataset.schema import load_config

MIN_YEAR, MAX_YEAR = -3000, 2100


class YearError(ValueError):
    """A year or range violates the project's conventions."""


def check_year(year: int, name: str = "year") -> int:
    if isinstance(year, bool) or not isinstance(year, int):
        raise YearError(f"{name} must be an integer, got {year!r}")
    if year == 0:
        raise YearError(f"{name} is 0: there is no year 0 (use -1 for 1 BCE, 1 for 1 CE)")
    if not MIN_YEAR <= year <= MAX_YEAR:
        raise YearError(f"{name}={year} outside [{MIN_YEAR}, {MAX_YEAR}]")
    return year


def check_range(start: int | None, end: int | None) -> tuple[int | None, int | None]:
    """Validate an optional range. ``None`` means an open (unconstrained) bound."""
    if start is not None:
        check_year(start, "start_year")
    if end is not None:
        check_year(end, "end_year")
    if start is not None and end is not None and start > end:
        raise YearError(f"start_year {start} is later than end_year {end}")
    return start, end


def years_between(start: int, end: int) -> int:
    """Number of years from ``start`` to ``end`` (exclusive of the missing year 0)."""
    check_year(start, "start")
    check_year(end, "end")
    span = end - start
    if start < 0 < end:
        span -= 1
    return span


def format_year(year: int) -> str:
    check_year(year)
    return f"{-year} BCE" if year < 0 else f"{year} CE"


def century_of(year: int) -> str:
    """'2nd century BCE' for -150, '1st century CE' for 50. No year 0."""
    check_year(year)
    n = (abs(year) - 1) // 100 + 1
    suffix = "th" if 10 <= n % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix} century {'BCE' if year < 0 else 'CE'}"


def format_range(start: int | None, end: int | None) -> str:
    check_range(start, end)
    if start is None and end is None:
        return "unconstrained"
    if start is None:
        return f"no later than {format_year(end)}"      # type: ignore[arg-type]
    if end is None:
        return f"no earlier than {format_year(start)}"
    if start == end:
        return format_year(start)
    return f"{format_year(start)} – {format_year(end)}"


def describe_centuries(start: int, end: int) -> str:
    a, b = century_of(start), century_of(end)
    return a if a == b else f"{a} – {b}"


def intersect(a: tuple[int | None, int | None], b: tuple[int | None, int | None]
              ) -> tuple[int | None, int | None] | None:
    """Intersection of two (possibly open) ranges, or ``None`` when they do not overlap."""
    starts = [x for x in (a[0], b[0]) if x is not None]
    ends = [x for x in (a[1], b[1]) if x is not None]
    lo = max(starts) if starts else None
    hi = min(ends) if ends else None
    if lo is not None and hi is not None and lo > hi:
        return None
    return lo, hi


def hull(ranges: list[tuple[int | None, int | None]]) -> tuple[int | None, int | None]:
    """Smallest range containing all given ranges (an open bound stays open)."""
    starts = [r[0] for r in ranges]
    ends = [r[1] for r in ranges]
    lo = None if any(s is None for s in starts) else min(starts)  # type: ignore[type-var]
    hi = None if any(e is None for e in ends) else max(ends)  # type: ignore[type-var]
    return lo, hi


@dataclass(frozen=True)
class Position:
    """One scholarly position on the earliest Tamil-Brahmi, as recorded in project.yaml."""

    id: str
    label: str
    lower_year: int | None
    upper_year: int | None
    basis: tuple[str, ...]
    reference: str
    verification_status: str
    kind: str = "date_position"          # or "methodological_objection"


@dataclass(frozen=True)
class Period:
    id: str
    label: str
    lower_year: int
    upper_year: int
    verification_status: str
    source_ref: str
    note: str = ""


def script_positions(config: dict[str, Any] | None = None) -> list[Position]:
    chron = (config or load_config()).get("chronology", {})
    out = []
    for p in chron.get("tamil_brahmi_earliest_positions", []):
        lo, hi = p.get("lower_year"), p.get("upper_year")
        check_range(lo, hi)
        out.append(Position(p["id"], p["label"], lo, hi, tuple(p.get("basis", [])),
                            str(p.get("reference", "")), str(p.get("verification_status", "unverified")),
                            str(p.get("kind", "date_position"))))
    return out


def periods(config: dict[str, Any] | None = None) -> list[Period]:
    chron = (config or load_config()).get("chronology", {})
    out = []
    for p in chron.get("periods", []):
        check_range(p["lower_year"], p["upper_year"])
        out.append(Period(p["id"], p["label"], p["lower_year"], p["upper_year"],
                          str(p.get("verification_status", "unverified")),
                          str(p.get("source_ref", "")), str(p.get("note", ""))))
    return out


__all__ = [
    "MAX_YEAR", "MIN_YEAR", "Period", "Position", "YearError", "century_of", "check_range",
    "check_year", "describe_centuries", "format_range", "format_year", "hull", "intersect",
    "periods", "script_positions", "years_between",
]
