"""Translation / meaning: report only what a human source established.

The module never composes a translation. It selects among a small set of outcomes:

* no reading                -> "No reading established; nothing can be translated."
* personal name             -> translation not applicable; meaning explains it is a name
* sign / not translatable   -> no translation
* translation given with a source -> reported with its provenance and confidence
* otherwise                 -> "No translation established."
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from src.reasoning.types import InscriptionInput

NO_READING = "No reading established; nothing can be translated."
NO_TRANSLATION = "No translation established."
PERSONAL_NAME = "Proper name; no literal translation established."


@dataclass
class InterpretationResult:
    state: str               # no_reading | personal_name | not_translatable | translated | no_translation
    translation: str
    meaning: str
    confidence: str
    provenance: str
    source: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def interpret(ins: InscriptionInput) -> InterpretationResult:
    if not ins.reading.known:
        return InterpretationResult("no_reading", "not_applicable", NO_READING, "not_applicable",
                                    "none", "not_applicable")
    itype = ins.interpretation_type
    meaning = ins.meaning if ins.meaning not in ("unknown", "not_available", "not_applicable", "") else ""
    if itype.value == "personal_name":
        return InterpretationResult("personal_name", "not_applicable", meaning or PERSONAL_NAME,
                                    itype.confidence, itype.provenance, itype.source_reference)
    if itype.value in ("symbol", "not_translatable"):
        return InterpretationResult("not_translatable", "not_applicable",
                                    meaning or f"Interpreted as {itype.value.replace('_', ' ')}; no translation.",
                                    itype.confidence, itype.provenance, itype.source_reference)
    tr = ins.translation
    if tr.known and tr.provenance != "ai_prediction" and tr.source_reference not in ("not_available", "unknown"):
        return InterpretationResult("translated", str(tr.value), meaning or "not_available",
                                    tr.confidence, tr.provenance, tr.source_reference)
    return InterpretationResult("no_translation", "not_available", NO_TRANSLATION, "unknown",
                                "none", "not_applicable")


__all__ = ["NO_READING", "NO_TRANSLATION", "PERSONAL_NAME", "InterpretationResult", "interpret"]
