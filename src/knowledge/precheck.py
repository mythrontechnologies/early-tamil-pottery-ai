"""Software source pre-checks (Milestone 11): where a claim was found, NOT whether it is verified.

A software agent may read a copy of a cited publication that the project is allowed to consult
(the publisher's open-access PDF, an authorised government digital library) and record where
each claim appears. That record is useful: it turns the human verifier's job into "open this
copy at this page and confirm". It is not verification, and this module makes sure it can never
be mistaken for one:

* the registry (``knowledge/verification/source_prechecks.json``) has ``checked_by`` fixed to
  ``software_agent`` and ``effect`` fixed to ``none`` by its schema;
* nothing here is read by ``reference_status``, ``verified_ref_ids``, the reasoning engine or
  promotion: a pre-checked claim stays exactly as unverified as before;
* ``verification_from_precheck`` builds a registry record only for a NAMED HUMAN who states
  that they opened the source; the record is then validated by V1-V10 like any other.

Rules:

``PC1`` the registry conforms to ``source_precheck.schema.json``
``PC2`` every reference id exists in the knowledge base
``PC3`` a claim check names a claim (``python -m src.knowledge claims``) that cites that reference
``PC4`` every source id resolves, and a source belongs to the reference it is used for
``PC5`` a claim found in a source (found_*/partially_found) gives the locator and a short excerpt;
        found_with_differences explains the differences
``PC6`` a claim can be found only in the publication itself: catalogue records and tables of
        contents support bibliographic checks, never claim checks (except ``source_not_accessible``)
``PC7`` no claim is pre-checked as found against an unresolved placeholder (R3, R5); a candidate
        work may only be checked bibliographically (``candidate_work_exists``)
``PC8`` ids are unique and no check is dated in the future
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

from src.dataset.schema import ROOT

from .base import KnowledgeBase, default_kb

PRECHECK_PATH = ROOT / "knowledge" / "verification" / "source_prechecks.json"
SCHEMA_PATH = ROOT / "data" / "metadata" / "schema" / "source_precheck.schema.json"
FOUND = ("found_as_stated", "found_with_differences", "partially_found")
CLAIM_ACCESS = ("open_access_publication", "authorised_digital_copy")
LABEL = "SOFTWARE PRE-CHECK - NOT VERIFICATION"

RULES: dict[str, str] = {
    "PC1": "registry conforms to source_precheck.schema.json (checked_by software_agent, effect none)",
    "PC2": "every reference id exists in the knowledge base",
    "PC3": "a claim check names a known claim that cites that reference",
    "PC4": "source ids resolve; a source belongs to the reference it is used for",
    "PC5": "a found claim gives locator and excerpt; differences are explained",
    "PC6": "claims are found only in the publication itself, never in a catalogue or contents list",
    "PC7": "no claim is pre-checked as found against an unresolved placeholder (R3, R5)",
    "PC8": "ids unique; no check dated in the future",
}


@lru_cache(maxsize=1)
def _validator() -> Draft202012Validator:
    return Draft202012Validator(json.loads(SCHEMA_PATH.read_text(encoding="utf-8")))


@dataclass
class PrecheckSet:
    data: dict[str, Any]
    problems: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.problems

    @property
    def sources(self) -> dict[str, dict[str, Any]]:
        return {s["source_id"]: s for s in self.data.get("sources", [])}

    @property
    def claim_checks(self) -> list[dict[str, Any]]:
        return list(self.data.get("claim_checks", []))

    @property
    def bibliographic_checks(self) -> list[dict[str, Any]]:
        return list(self.data.get("bibliographic_checks", []))

    def for_claim(self, ref_id: str, claim_id: str) -> dict[str, Any] | None:
        return next((c for c in self.claim_checks
                     if c["ref_id"] == ref_id and c["claim_id"] == claim_id), None)

    def get(self, precheck_id: str) -> dict[str, Any] | None:
        return next((c for c in self.claim_checks if c["precheck_id"] == precheck_id), None)

    def for_reference(self, ref_id: str) -> dict[str, Any]:
        """Summary for one reference: bibliographic findings and claim findings by kind."""
        counts: dict[str, int] = {}
        for c in self.claim_checks:
            if c["ref_id"] == ref_id:
                counts[c["finding"]] = counts.get(c["finding"], 0) + 1
        return {"bibliographic": [b for b in self.bibliographic_checks if b["ref_id"] == ref_id],
                "claims": counts}


def load_prechecks(path: Path | None = None, *, kb: KnowledgeBase | None = None,
                   today: date | None = None) -> PrecheckSet:
    """Load and validate the registry. A missing file is an empty, valid registry."""
    path = path or PRECHECK_PATH
    if not path.exists():
        return PrecheckSet({"sources": [], "bibliographic_checks": [], "claim_checks": []})
    data = json.loads(path.read_text(encoding="utf-8"))
    ps = PrecheckSet(data)
    ps.problems = validate_prechecks(data, kb=kb, today=today)
    return ps


def validate_prechecks(data: dict[str, Any], *, kb: KnowledgeBase | None = None,
                       today: date | None = None) -> list[str]:
    from .verification import claims

    out = [f"PC1 {'.'.join(map(str, e.path)) or '<root>'}: {e.message}"
           for e in sorted(_validator().iter_errors(data), key=lambda e: list(e.path))]
    if out:
        return out
    kb = kb or default_kb()
    today = today or datetime.now(timezone.utc).date()
    known_claims = {c.claim_id: set(c.ref_ids) for c in claims(kb)}
    sources = {}
    for s in data["sources"]:
        if s["source_id"] in sources:
            out.append(f"PC8 duplicate source_id {s['source_id']}")
        sources[s["source_id"]] = s
        if s["ref_id"] not in kb.references:
            out.append(f"PC2 source {s['source_id']}: unknown reference {s['ref_id']!r}")
        if date.fromisoformat(s["accessed"]) > today:
            out.append(f"PC8 source {s['source_id']}: accessed date {s['accessed']} is in the future")
    ids: set[str] = set()
    for b in data["bibliographic_checks"]:
        cid = b["check_id"]
        if cid in ids:
            out.append(f"PC8 duplicate check id {cid}")
        ids.add(cid)
        ref = kb.references.get(b["ref_id"])
        if ref is None:
            out.append(f"PC2 {cid}: unknown reference {b['ref_id']!r}")
        elif ref.get("resolution") == "unresolved" and b["finding"] != "candidate_work_exists":
            out.append(f"PC7 {cid}: {b['ref_id']} is an unresolved placeholder; only a candidate work's "
                       "existence can be pre-checked ('candidate_work_exists')")
        for sid in b["source_ids"]:
            if sid not in sources:
                out.append(f"PC4 {cid}: unknown source {sid!r}")
            elif sources[sid]["ref_id"] != b["ref_id"]:
                out.append(f"PC4 {cid}: source {sid} belongs to {sources[sid]['ref_id']}, not {b['ref_id']}")
        if b["finding"] == "differs_from_knowledge_base" and "differences" not in b:
            out.append(f"PC5 {cid}: a difference must be described ('differences')")
        if date.fromisoformat(b["check_date"]) > today:
            out.append(f"PC8 {cid}: check_date {b['check_date']} is in the future")
    for c in data["claim_checks"]:
        pid, rid, finding = c["precheck_id"], c["ref_id"], c["finding"]
        if pid in ids:
            out.append(f"PC8 duplicate check id {pid}")
        ids.add(pid)
        ref = kb.references.get(rid)
        if ref is None:
            out.append(f"PC2 {pid}: unknown reference {rid!r}")
        elif ref.get("resolution") == "unresolved" and finding in FOUND:
            out.append(f"PC7 {pid}: no claim can be found in an unresolved placeholder ({rid}); identify "
                       "the exact work first")
        if c["claim_id"] not in known_claims:
            out.append(f"PC3 {pid}: unknown claim {c['claim_id']!r} (python -m src.knowledge claims)")
        elif rid not in known_claims[c["claim_id"]]:
            out.append(f"PC3 {pid}: claim {c['claim_id']!r} does not cite {rid}")
        src = sources.get(c["source_id"])
        if src is None:
            out.append(f"PC4 {pid}: unknown source {c['source_id']!r}")
        else:
            if src["ref_id"] != rid:
                out.append(f"PC4 {pid}: source {src['source_id']} belongs to {src['ref_id']}, not {rid}")
            if finding != "source_not_accessible" and src["access"] not in CLAIM_ACCESS:
                out.append(f"PC6 {pid}: a claim cannot be found in a {src['access']}; it needs the "
                           "publication itself")
        if finding in FOUND and not (c.get("locator_found") and c.get("excerpt")):
            out.append(f"PC5 {pid}: a found claim needs locator_found and excerpt")
        if finding == "found_with_differences" and not c.get("differences"):
            out.append(f"PC5 {pid}: found_with_differences must describe the differences")
        if date.fromisoformat(c["check_date"]) > today:
            out.append(f"PC8 {pid}: check_date {c['check_date']} is in the future")
    return out


def verification_from_precheck(precheck_id: str, *, verifier: str, verifier_role: str,
                               verification_date: str, status: str = "verified_against_source",
                               notes: str | None = None, prechecks: PrecheckSet | None = None,
                               kb: KnowledgeBase | None = None) -> dict[str, Any]:
    """A verification-registry record for a HUMAN who opened the pre-checked source.

    The pre-check supplies only where to look (locator, copy, access). The human supplies who
    they are, when they checked, and what they found. The record is validated by the registry
    (V1-V10) when appended; this function writes nothing."""
    from .verification import claims, new_verification

    kb = kb or default_kb()
    ps = prechecks or load_prechecks(kb=kb)
    pc = ps.get(precheck_id)
    if pc is None:
        raise KeyError(f"no pre-check {precheck_id!r} (python -m src.knowledge prechecks)")
    src = ps.sources[pc["source_id"]]
    if src["access"] not in CLAIM_ACCESS:
        raise ValueError(f"{precheck_id}: the pre-checked source is a {src['access']}; a claim can only be "
                         "verified in the publication itself")
    claim_text = next((c.statement for c in claims(kb) if c.claim_id == pc["claim_id"]), pc["claim_id"])
    auto = (f"Locator found with the help of software pre-check {precheck_id} "
            f"({pc['finding']}); the verifier opened the source and checked the passage.")
    return new_verification(
        ref_id=pc["ref_id"], citation=kb.references[pc["ref_id"]]["citation"], claim=claim_text,
        claim_id=pc["claim_id"], status=status, verifier=verifier, verifier_role=verifier_role,
        verification_date=verification_date, locator=pc.get("locator_found", "not_available"),
        source_location=src["url"], source_access=src["access"],
        notes=f"{notes} {auto}" if notes else auto)


__all__ = ["CLAIM_ACCESS", "FOUND", "LABEL", "PRECHECK_PATH", "RULES", "SCHEMA_PATH", "PrecheckSet",
           "load_prechecks", "validate_prechecks", "verification_from_precheck"]
