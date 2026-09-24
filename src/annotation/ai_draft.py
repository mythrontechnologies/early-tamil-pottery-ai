"""The AI-prepared pilot draft: an optional, read-only reference layer. Never evidence.

``outputs/pilot_handoff/ai_draft_annotations.jsonl`` (git-ignored) holds observations an AI
assistant made from the pilot photographs. It is loaded here only for display, with
``AI_DRAFT_WARNING``, and only if every record in it is an ``ai_prediction``. Nothing in this
module writes to the annotation store, the records or the worksheets. Rule N15 separately
refuses to store an AI-marked record under a human provenance tier, so the draft cannot be
re-labelled as a project or expert annotation by copying it.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from src.dataset.schema import ROOT

AI_DRAFT_PATH = ROOT / "outputs" / "pilot_handoff" / "ai_draft_annotations.jsonl"
AI_DRAFT_BANNER = "AI DRAFT — NOT HUMAN EVIDENCE"
AI_DRAFT_WARNING = ("AI-generated observation. Not archaeological evidence. Do not copy into expert "
                    "annotation without independent verification.")
#: Text that marks a record as AI-prepared, wherever it appears (see rule N15).
AI_MARKERS = ("AI-PREPARED DRAFT", AI_DRAFT_BANNER)
AI_ANNOTATOR_PREFIX = "ai_"


def is_ai_marked(a: dict[str, Any]) -> bool:
    """True when an annotation carries an AI-draft marker or an AI annotator id."""
    aid = str(a.get("annotator", {}).get("annotator_id", ""))
    text = " ".join(str(a.get(k, "")) for k in ("notes", "uncertainty_notes"))
    return aid.startswith(AI_ANNOTATOR_PREFIX) or any(m in text for m in AI_MARKERS)


def load_ai_draft(path: Path | None = None) -> dict[str, list[dict[str, Any]]]:
    """artifact_id -> AI draft records. Empty if the file is absent. Raises ValueError if any
    record is not an ``ai_prediction``: a mislabelled draft is refused, not displayed."""
    path = Path(path or AI_DRAFT_PATH)
    if not path.exists():
        return {}
    out: dict[str, list[dict[str, Any]]] = {}
    for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        a = json.loads(line)
        if a.get("provenance_type") != "ai_prediction":
            raise ValueError(f"{path.name} line {n}: provenance_type {a.get('provenance_type')!r}; "
                             "the AI draft must consist of ai_prediction records only")
        out.setdefault(a["artifact_id"], []).append(a)
    return out


__all__ = ["AI_ANNOTATOR_PREFIX", "AI_DRAFT_BANNER", "AI_DRAFT_PATH", "AI_DRAFT_WARNING", "AI_MARKERS",
           "is_ai_marked", "load_ai_draft"]
