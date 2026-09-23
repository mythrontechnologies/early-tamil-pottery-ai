"""Deterministic archaeological reasoning (Milestone 7).

    from src.reasoning import analyze_artifact, render_text
    python -m src.reasoning analyze <artifact_id>      # from the project's annotations
    python -m src.reasoning analyze --all

See docs/ARCHAEOLOGICAL_REASONING.md. The engine consumes structured, provenance-tagged
evidence and returns a traceable result, including "insufficient evidence" when that is
the honest answer.

Exports are loaded lazily: ``src.reasoning.types`` is shared with ``src.dating`` and
``src.translation``, which the engine itself imports.
"""

from typing import Any

__all__ = ["DISCLAIMER", "AnalysisResult", "analyze_artifact", "render_text"]


def __getattr__(name: str) -> Any:
    if name in __all__:
        from . import engine

        return getattr(engine, name)
    raise AttributeError(name)
