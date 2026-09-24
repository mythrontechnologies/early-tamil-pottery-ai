"""Knowledge base loader and validator (``knowledge/*/*.yaml``).

Rules:

``K1`` every file declares ``kind`` and a list of ``entries`` with unique ids
``K2`` every reference has a citation and a known verification status
``K3`` every assertion names at least one reference id, and every id resolves
``K4`` every assertion and entry carries a verification status
``K5`` nothing claims ``verified_against_source`` without a ``verified_by`` and ``verified_on``

Retrieval rule: only material at ``integrity.min_verification_for_evidence``
(``verified_against_source``) may be presented as *evidence*. Everything else may be shown
as *unverified context*, labelled as such.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from src.dataset.schema import ROOT, load_config

KNOWLEDGE_ROOT = ROOT / "knowledge"
STATUSES = ("verified_against_source", "transcribed_unverified", "bibliographic_only", "unverified")


class KnowledgeError(ValueError):
    pass


@dataclass
class KnowledgeBase:
    references: dict[str, dict[str, Any]] = field(default_factory=dict)
    entries: dict[str, dict[str, Any]] = field(default_factory=dict)      # id -> entry (non-reference)
    kinds: dict[str, str] = field(default_factory=dict)                   # id -> kind
    problems: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.problems

    def reference(self, ref_id: str) -> dict[str, Any] | None:
        return self.references.get(ref_id)

    def is_evidence_grade(self, ref_id: str) -> bool:
        ref = self.references.get(ref_id)
        required = load_config().get("integrity", {}).get("min_verification_for_evidence",
                                                          "verified_against_source")
        return bool(ref) and ref.get("verification_status") == required

    def of_kind(self, kind: str) -> list[dict[str, Any]]:
        return [e for i, e in self.entries.items() if self.kinds[i] == kind]


def load(root: Path | None = None) -> KnowledgeBase:
    root = root or KNOWLEDGE_ROOT
    kb = KnowledgeBase()
    files = sorted(root.glob("*/*.yaml"))
    docs: list[tuple[Path, dict[str, Any]]] = []
    for path in files:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        rel = path.relative_to(root).as_posix()
        if not isinstance(data.get("kind"), str) or not isinstance(data.get("entries"), list):
            kb.problems.append(f"K1 {rel}: needs 'kind' and a list of 'entries'")
            continue
        docs.append((path, data))

    for _path, data in docs:                      # references first, so K3 can resolve
        if data["kind"] != "references":
            continue
        for e in data["entries"]:
            rid = e.get("id")
            if rid in kb.references:
                kb.problems.append(f"K1 duplicate reference id {rid!r}")
            if not e.get("citation"):
                kb.problems.append(f"K2 reference {rid!r} has no citation")
            if e.get("verification_status") not in STATUSES:
                kb.problems.append(f"K2 reference {rid!r} has status {e.get('verification_status')!r}")
            _check_verified(kb, rid, e)
            kb.references[rid] = e

    for path, data in docs:
        if data["kind"] == "references":
            continue
        for e in data["entries"]:
            eid = e.get("id")
            if not eid or eid in kb.entries or eid in kb.references:
                kb.problems.append(f"K1 missing or duplicate entry id {eid!r} in {path.name}")
                continue
            kb.entries[eid], kb.kinds[eid] = e, data["kind"]
            assertions = e.get("assertions", [])
            if "reference_ids" in e:
                assertions = [*assertions, e]        # an entry that is itself one sourced claim
            for i, a in enumerate(assertions):
                refs = a.get("reference_ids") or []
                if not refs:
                    kb.problems.append(f"K3 {eid} assertion {i}: no reference_ids")
                for r in refs:
                    if r not in kb.references:
                        kb.problems.append(f"K3 {eid} assertion {i}: unknown reference {r!r}")
                if a.get("verification_status") not in STATUSES:
                    kb.problems.append(f"K4 {eid} assertion {i}: missing/invalid verification_status")
                _check_verified(kb, f"{eid}[{i}]", a)
    return kb


def _check_verified(kb: KnowledgeBase, where: Any, item: dict[str, Any]) -> None:
    if item.get("verification_status") == "verified_against_source" and not (
            item.get("verified_by") and item.get("verified_on")):
        kb.problems.append(f"K5 {where}: 'verified_against_source' requires verified_by and verified_on")


@lru_cache(maxsize=1)
def default_kb() -> KnowledgeBase:
    return load()


def reference_ids() -> set[str]:
    return set(default_kb().references)


__all__ = [
    "KNOWLEDGE_ROOT",
    "STATUSES",
    "KnowledgeBase",
    "KnowledgeError",
    "default_kb",
    "load",
    "reference_ids",
]
