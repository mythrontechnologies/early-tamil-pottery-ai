"""RETIRED (2026-10-09). Placeholder interpretation categories over synthetic glyph codes ("synthetic grammar v1").

    No longer part of the synthetic pipeline: since generator 1.1.0 the synthetic glyphs form sentences of an invented
    language, and the INTERPRET stage reports a structured grammatical interpretation instead
    (``src.synthetic.lexicon.grammatical_interpretation``: agent, action, object). This module is kept, unchanged in
    behaviour, only so that synthetic runs and benchmark reports stored before that date remain readable and
    reproducible. Nothing current calls it.

Original description:

    SYNTHETIC INTERPRETATION — no language, no meaning, no person, no place.

The generator's glyphs (SG00-SG15) mean nothing. To exercise an interpretation stage end to end, this
module assigns each code to an invented glyph group and maps a glyph sequence to an invented
category with a placeholder text. The same rules applied to the generator's ground-truth sequence give
the expected category, so interpretation can be scored like everything else in the synthetic benchmark.

Categories end in ``_like`` and every placeholder says it is synthetic. Nothing here is, or may be
presented as, a reading of Tamil-Brahmi, a historical name or a translation.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

GRAMMAR_VERSION = "synthetic-grammar-1"
STATEMENT = "Synthetic interpretation — invented rule table over synthetic glyph codes; no language or meaning."

#: Invented glyph groups (engineering fiction).
GLYPH_GROUPS: dict[str, str] = {
    **{f"SG{i:02d}": "stem" for i in range(0, 8)},
    **{f"SG{i:02d}": "marker" for i in range(8, 12)},
    **{f"SG{i:02d}": "numeral_like" for i in range(12, 16)},
}

CATEGORIES: dict[str, str] = {
    "synthetic_personal_name_like": "synthetic placeholder interpretation: a name-like token sequence (no person)",
    "synthetic_name_and_title_like": "synthetic placeholder interpretation: a name-like sequence followed by a "
                                     "title-like word (no person, no title)",
    "synthetic_ownership_formula_like": "synthetic placeholder interpretation: a sequence ending in a marker glyph "
                                        "(no owner, no formula)",
    "synthetic_numeral_like": "synthetic placeholder interpretation: numeral-like glyphs only (no number)",
    "synthetic_symbolic_mark_like": "synthetic placeholder interpretation: isolated abstract marks, no glyph row "
                                    "(no symbol, no meaning)",
    "synthetic_no_reading": "no synthetic glyph transcription, so no synthetic interpretation",
}


@dataclass
class SyntheticInterpretation:
    category: str
    placeholder: str
    rule: str
    glyph_groups: dict[str, int]
    words: int
    grammar: str = GRAMMAR_VERSION
    statement: str = STATEMENT

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def interpret(words: list[list[str]], synthetic_class: str | None = None) -> SyntheticInterpretation:
    """Category of a synthetic glyph sequence (first matching rule wins)."""
    codes = [c for w in words for c in w if c in GLYPH_GROUPS]
    groups = {g: sum(GLYPH_GROUPS[c] == g for c in codes) for g in ("stem", "marker", "numeral_like")}

    def out(cat: str, rule: str) -> SyntheticInterpretation:
        return SyntheticInterpretation(cat, CATEGORIES[cat], rule, groups, len(words))

    if not codes:
        if synthetic_class == "synthetic_graffiti_like":
            return out("synthetic_symbolic_mark_like", "R0: no glyph row; the synthetic task class is graffiti-like")
        return out("synthetic_no_reading", "R0: no synthetic glyph transcription")
    if groups["numeral_like"] == len(codes):
        return out("synthetic_numeral_like", "R1: every glyph is in the numeral-like group")
    if len(words) >= 2 and words[1] and GLYPH_GROUPS.get(words[1][0]) == "marker":
        return out("synthetic_name_and_title_like", "R2: a second word that starts with a marker glyph")
    if GLYPH_GROUPS.get(codes[-1]) == "marker":
        return out("synthetic_ownership_formula_like", "R3: the sequence ends with a marker glyph")
    return out("synthetic_personal_name_like", "R4: default for a glyph row")


__all__ = ["CATEGORIES", "GLYPH_GROUPS", "GRAMMAR_VERSION", "STATEMENT", "SyntheticInterpretation", "interpret"]
