"""OCR evaluation hooks: character and word error rate against EXPERT readings.

Only pairs whose reference is an expert (or verified published) reading may be scored; the
caller is responsible for that, and ``evaluate_ocr`` refuses to run on no references at all
("Evaluation blocked"). Strings are NFC-normalised and whitespace-collapsed first, so Tamil
and IAST text compare by what is written, not by how it was encoded. Editorial marks
(brackets, question marks) are content and are kept.
"""

from __future__ import annotations

import unicodedata
from collections.abc import Sequence
from typing import Any

OCR_BLOCKED = ("Evaluation blocked — insufficient expert-labelled archaeological data: no expert reading "
               "exists to score OCR against.")


def _norm(text: str) -> str:
    return " ".join(unicodedata.normalize("NFC", text).split())


def _edit_distance(a: Sequence[Any], b: Sequence[Any]) -> int:
    prev = list(range(len(b) + 1))
    for i, x in enumerate(a, 1):
        cur = [i]
        for j, y in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (x != y)))
        prev = cur
    return prev[-1]


def edit_distance(a: Sequence[Any], b: Sequence[Any]) -> int:
    """Levenshtein distance between two sequences (characters, glyph codes, words...)."""
    return _edit_distance(a, b)


def character_error_rate(reference: str, hypothesis: str) -> float:
    """Edit distance over Unicode code points (after NFC) / reference length. >1 is possible."""
    ref, hyp = _norm(reference), _norm(hypothesis)
    if not ref:
        raise ValueError("a reference reading is required (empty reference)")
    return _edit_distance(ref, hyp) / len(ref)


def word_error_rate(reference: str, hypothesis: str) -> float:
    ref, hyp = _norm(reference).split(), _norm(hypothesis).split()
    if not ref:
        raise ValueError("a reference reading is required (empty reference)")
    return _edit_distance(ref, hyp) / len(ref)


def evaluate_ocr(pairs: Sequence[tuple[str, str | None]]) -> dict[str, Any]:
    """(expert_reference, ocr_hypothesis or None) pairs -> CER/WER summary. A missing hypothesis
    ("no reliable transcription") is counted as abstention, not as an error of zero."""
    pairs = [(r, h) for r, h in pairs if r and _norm(r)]
    if not pairs:
        return {"status": "BLOCKED", "message": OCR_BLOCKED}
    answered = [(r, h) for r, h in pairs if h and _norm(h)]
    cers = [character_error_rate(r, h) for r, h in answered]
    wers = [word_error_rate(r, h) for r, h in answered]
    return {"status": "COMPLETED", "n_references": len(pairs), "n_answered": len(answered),
            "abstention_rate": 1 - len(answered) / len(pairs),
            "mean_cer": sum(cers) / len(cers) if cers else None,
            "mean_wer": sum(wers) / len(wers) if wers else None,
            "exact_match_rate": (sum(_norm(r) == _norm(h) for r, h in answered) / len(answered)) if answered else None}


__all__ = ["OCR_BLOCKED", "character_error_rate", "edit_distance", "evaluate_ocr", "word_error_rate"]
