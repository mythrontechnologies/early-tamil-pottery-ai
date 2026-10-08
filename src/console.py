"""Console set-up shared by every command-line interface.

Tamil, IAST diacritics and typographic dashes appear in readings, citations and reports.
The Windows console defaults to a legacy code page, so each CLI switches stdout and stderr
to UTF-8 (unencodable characters are replaced, never allowed to crash a report).
"""

from __future__ import annotations

import contextlib
import sys


def utf8_console() -> None:
    """Reconfigure stdout/stderr to UTF-8 where the stream supports it."""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)     # absent on non-text streams
        with contextlib.suppress(AttributeError, ValueError):   # not a reconfigurable stream
            if reconfigure is not None:
                reconfigure(encoding="utf-8", errors="replace")


__all__ = ["utf8_console"]
