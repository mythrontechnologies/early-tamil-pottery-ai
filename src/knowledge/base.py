"""Knowledge base loader and validator (``knowledge/*/*.yaml``).

Rules:

``K1`` every file declares ``kind`` and a list of ``entries`` with unique ids
``K2`` every reference has a citation and a known verification status
``K3`` every assertion names at least one reference id, and every id resolves
``K4`` every assertion and entry carries a verification status
``K5`` nothing claims ``verified_against_source`` without a ``verified_by`` and ``verified_on``
``K7`` every reference id the chronology positions in ``configs/project.yaml`` cite resolves
``K8`` a reference marked ``resolution: unresolved`` (an author-level placeholder such as R3,
       R5) is ``unverified`` and lists its ``candidate_works``; nothing is verified against it

``describe()`` gives every claim in one normalised shape: identifier, claim, source,
provenance, verification status, scope, locator, notes and uncertainty. Scope, provenance and
uncertainty are DERIVED from the entry's kind and status unless the entry states them;
nothing archaeological is added.

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


def load(root: Path | None = None, config: dict[str, Any] | None = None) -> KnowledgeBase:
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
            if e.get("resolution") == "unresolved":
                if e.get("verification_status") != "unverified":
                    kb.problems.append(f"K8 unresolved placeholder {rid!r} must be 'unverified'")
                if not isinstance(e.get("candidate_works"), list):
                    kb.problems.append(f"K8 unresolved placeholder {rid!r} must list candidate_works")
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
                for r in refs:
                    if (kb.references.get(r, {}).get("resolution") == "unresolved"
                            and a.get("verification_status") == "verified_against_source"):
                        kb.problems.append(f"K8 {eid} assertion {i}: verified against unresolved placeholder {r!r}")
    if config is not None or root == KNOWLEDGE_ROOT:      # K7 concerns the project's own KB + config
        _check_config_citations(kb, config)
    return kb


def _check_config_citations(kb: KnowledgeBase, config: dict[str, Any] | None) -> None:
    chron = (config if config is not None else load_config()).get("chronology", {})
    for p in chron.get("tamil_brahmi_earliest_positions", []):
        ref = p.get("reference")
        if ref and ref not in kb.references:
            kb.problems.append(f"K7 chronology position {p.get('id')} cites {ref!r}, which is not in "
                               "knowledge/references (add it, as a placeholder if unresolved)")


#: Derived descriptions. An entry may state its own scope / uncertainty / notes.
SCOPE_BY_KIND = {
    "sites": "site-level statement (not a statement about any individual object)",
    "inscriptions": ("object-level published reading, transcribed as printed; NOT linked to any "
                     "project image and NOT a label"),
    "scripts": "script-level statement",
    "chronology": "position on the earliest Tamil-Brahmi (when the script began); never an object date",
}
PROVENANCE_BY_STATUS = {
    "verified_against_source": "checked by a named human against the publication (verification registry)",
    "transcribed_unverified": "transcribed by the project from a publication it read; not checked by an expert",
    "bibliographic_only": "the work's existence is confirmed; its content was not read by the project",
    "unverified": "a lead or placeholder; nothing about it is confirmed",
}
UNCERTAINTY_BY_STATUS = {
    "verified_against_source": "Verified only for the specific claim checked; other claims citing the same work are not.",
    "transcribed_unverified": "Transcription and locator are unverified; the source's own claim may be contested.",
    "bibliographic_only": "Content not read: whether the work supports this claim is unknown.",
    "unverified": "Unverified; may not support the claim at all.",
}


def describe(kb: KnowledgeBase | None = None, config: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """Every sourced claim (knowledge files + chronology config) in one normalised shape."""
    kb = kb or default_kb()
    rows: list[dict[str, Any]] = []

    def row(ident: str, claim: str, refs: list[str], status: str, kind: str, item: dict[str, Any],
            where: str) -> None:
        unresolved = [r for r in refs if kb.references.get(r, {}).get("resolution") == "unresolved"]
        uncertainty = item.get("uncertainty") or UNCERTAINTY_BY_STATUS.get(status, "Unknown status.")
        if unresolved:
            uncertainty += (f" Cites unresolved placeholder(s) {', '.join(unresolved)}: the source work "
                            "itself is not identified.")
        rows.append({
            "id": ident, "claim": claim,
            "source": [{"ref_id": r,
                        "citation": kb.references.get(r, {}).get("citation", "NOT IN KNOWLEDGE BASE"),
                        "reference_status": kb.references.get(r, {}).get("verification_status", "unknown")}
                       for r in refs],
            "provenance": item.get("provenance") or PROVENANCE_BY_STATUS.get(status, "unknown"),
            "verification_status": status,
            "scope": item.get("scope") or SCOPE_BY_KIND.get(kind, f"{kind} statement"),
            "locator": str(item.get("locator", "not_available")),
            "notes": item.get("notes") or item.get("project_notes") or "",
            "uncertainty": uncertainty,
            "recorded_in": where,
        })

    for eid, e in sorted(kb.entries.items()):
        kind = kb.kinds[eid]
        if "reference_ids" in e:
            claim = "; ".join(f"{k}: {v}" for k, v in e.items()
                              if k.endswith("_as_printed") and v not in (None, ""))
            row(eid, claim or eid, list(e["reference_ids"]), e.get("verification_status", "unknown"),
                kind, e, f"knowledge/{kind}")
        for i, a in enumerate(e.get("assertions", [])):
            row(f"{eid}.assertions[{i}]", str(a.get("statement", "")), list(a.get("reference_ids", [])),
                a.get("verification_status", "unknown"), kind, a, f"knowledge/{kind}")
    chron = (config if config is not None else load_config()).get("chronology", {})
    for p in chron.get("tamil_brahmi_earliest_positions", []):
        rng = (f": {p.get('lower_year')} to {p.get('upper_year')} (signed years)" if "lower_year" in p
               else ": methodological objection")
        row(f"config:chronology.position_{p['id']}", f"Position {p['id']} ({p.get('label')}){rng}",
            [str(p.get("reference"))], str(p.get("verification_status", "unverified")), "chronology", p,
            "configs/project.yaml#chronology")
    return rows


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
    "SCOPE_BY_KIND",
    "STATUSES",
    "KnowledgeBase",
    "KnowledgeError",
    "default_kb",
    "describe",
    "load",
    "reference_ids",
]
