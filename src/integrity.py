"""Tamper evidence for the project's append-only JSONL files.

The annotation store, the reference-verification registry and the promotion log hold human
evidence and decisions. They are append-only by design; this module makes that *checkable*.

Every append writes the record line to ``<file>`` and one entry to ``<file>.ledger``::

    {"n": 3, "line_sha256": "...", "chain": sha256(previous chain + line_sha256), "utc": "..."}

``verify(path)`` recomputes the chain over the file and compares it with the ledger. It
detects an edited, deleted, reordered or inserted line, a line appended without the ledger
(e.g. by hand), and a truncated ledger. It cannot stop a determined person who rewrites both
files, but that leaves a different final chain hash, which is recorded in every promotion
audit entry and in git history.

A file that predates the ledger (or was deliberately adopted) is *sealed* explicitly with
``seal(path)`` by a human; nothing seals silently.
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

GENESIS = "0" * 64


class IntegrityError(RuntimeError):
    """An append-only file does not match its ledger."""


def ledger_path(path: Path) -> Path:
    return Path(path).with_name(Path(path).name + ".ledger")


def _lines(path: Path) -> list[bytes]:
    if not path.exists():
        return []
    # A trailing CR is normalised away: converting line endings (LF <-> CRLF) is not tampering.
    return [ln.rstrip(b"\r") for ln in path.read_bytes().split(b"\n") if ln.strip()]


def _entries(path: Path) -> list[dict[str, Any]]:
    lp = ledger_path(path)
    if not lp.exists():
        return []
    return [json.loads(x) for x in lp.read_text(encoding="utf-8").splitlines() if x.strip()]


def _link(prev: str, line: bytes) -> tuple[str, str]:
    h = hashlib.sha256(line).hexdigest()
    return h, hashlib.sha256((prev + h).encode("ascii")).hexdigest()


def _fsync_append(path: Path, data: bytes) -> None:
    with path.open("ab") as fh:
        fh.write(data)
        fh.flush()
        os.fsync(fh.fileno())


@dataclass
class IntegrityReport:
    path: str
    lines: int
    ledger_entries: int
    sealed: bool
    head: str
    problems: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.problems

    @property
    def status(self) -> str:
        if not self.lines and not self.ledger_entries:
            return "EMPTY"
        return "INTACT" if self.ok else "TAMPERED_OR_UNSEALED"


def verify(path: Path | str) -> IntegrityReport:
    path = Path(path)
    lines, entries = _lines(path), _entries(path)
    rep = IntegrityReport(path.as_posix(), len(lines), len(entries), bool(entries), GENESIS)
    if lines and not entries:
        rep.problems.append(f"{path.name} has {len(lines)} line(s) but no ledger: written outside the "
                            "append API, or never sealed (a human may adopt it with `seal`)")
        return rep
    chain = GENESIS
    for i, line in enumerate(lines):
        h, chain = _link(chain, line)
        if i >= len(entries):
            rep.problems.append(f"line {i + 1} is not in the ledger (appended outside the append API)")
            break
        e = entries[i]
        if e.get("n") != i + 1 or e.get("line_sha256") != h:
            rep.problems.append(f"line {i + 1} differs from the ledger (edited, deleted or reordered)")
            break
        if e.get("chain") != chain:
            rep.problems.append(f"ledger chain broken at entry {i + 1}")
            break
    if len(entries) > len(lines) and not rep.problems:
        rep.problems.append(f"ledger lists {len(entries)} line(s) but the file has {len(lines)} (lines removed)")
    rep.head = chain
    return rep


def append_line(path: Path | str, line: str) -> str:
    """Append one record line and its ledger entry. Refuses if the file is already inconsistent.
    Returns the new chain head."""
    path = Path(path)
    if "\n" in line:
        raise ValueError("a record must be a single line")
    rep = verify(path)
    if not rep.ok:
        raise IntegrityError(f"{path.name}: refusing to append to a file that fails its integrity check: "
                             + "; ".join(rep.problems))
    path.parent.mkdir(parents=True, exist_ok=True)
    data = line.encode("utf-8")
    h, chain = _link(rep.head, data)
    _fsync_append(path, data + b"\n")
    entry = {"n": rep.lines + 1, "line_sha256": h, "chain": chain,
             "utc": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    _fsync_append(ledger_path(path), (json.dumps(entry, sort_keys=True) + "\n").encode("utf-8"))
    return chain


def seal(path: Path | str) -> IntegrityReport:
    """Adopt an existing ledger-less file as it stands NOW (an explicit human action)."""
    path = Path(path)
    if ledger_path(path).exists():
        raise IntegrityError(f"{path.name} already has a ledger; nothing to seal")
    chain, rows = GENESIS, []
    for i, line in enumerate(_lines(path)):
        h, chain = _link(chain, line)
        rows.append(json.dumps({"n": i + 1, "line_sha256": h, "chain": chain, "sealed": True,
                                "utc": datetime.now(timezone.utc).isoformat(timespec="seconds")},
                               sort_keys=True))
    ledger_path(path).write_text("".join(r + "\n" for r in rows), encoding="utf-8")
    return verify(path)


__all__ = ["GENESIS", "IntegrityError", "IntegrityReport", "append_line", "ledger_path", "seal", "verify"]
