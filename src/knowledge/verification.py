"""Reference verification (Milestone 8).

A reference is *verified* only for the claims a named human actually checked in the
physical or authorised publication. Finding the citation online, in a catalogue or in a
bibliography is not verification, and software never verifies anything: there is no AI
verifier role.

Registry: ``knowledge/verification/reference_verifications.jsonl`` (append-only; a later
check supersedes an earlier one by ``supersedes``). Schema:
``data/metadata/schema/reference_verification.schema.json``.

Rules:

``V1`` record conforms to the schema
``V2`` the reference id exists in the knowledge base
``V3`` ``verified_against_source`` names a human verifier and role, a date not in the future,
       the page/plate/catalogue locator, where the copy is held, and how it was accessed
``V4`` ``discrepancy_found`` names a verifier, date and access, and explains the discrepancy
``V5`` ``source_unavailable`` records that the source was not accessed, by whom, and why
``V6`` ``unverified`` carries no verification date
``V7`` a claim id resolves to a knowledge-base claim (or is ``not_applicable``)
``V8`` ids are unique; a record supersedes one earlier record of the same reference and claim
``K6`` a knowledge-base reference may not itself claim ``verified_against_source``
       unless the registry holds a current verified record for it

Effective status of a reference (``reference_status``): ``discrepancy_found`` if any
current record found one; otherwise ``verified_against_source`` if at least one claim was
verified (the verified claims are listed wherever the status is shown, because verifying one
claim does not verify every claim that cites the work); otherwise the knowledge-base status.
"""

from __future__ import annotations

import json
import uuid
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

from src.dataset.schema import ROOT, load_config

from .base import KnowledgeBase, default_kb

SCHEMA_PATH = ROOT / "data" / "metadata" / "schema" / "reference_verification.schema.json"
VERIFICATION_SCHEMA_VERSION = "1.0.0"
VERIFIED = "verified_against_source"
NA = "not_applicable"

RULES: dict[str, str] = {
    "V1": "record conforms to reference_verification.schema.json",
    "V2": "the reference id exists in the knowledge base",
    "V3": "a verified claim names a human verifier, role, date, locator, copy location and access",
    "V4": "a discrepancy names verifier, date and access, and explains the discrepancy",
    "V5": "source_unavailable records who tried, when, and why (source not accessed)",
    "V6": "an unverified record carries no verification date",
    "V7": "claim_id resolves to a knowledge-base claim or is 'not_applicable'",
    "V8": "ids unique; a revision supersedes one earlier record of the same reference and claim",
    "K6": "a knowledge-base reference claiming verified_against_source is backed by the registry",
}


def registry_path(config: dict[str, Any] | None = None) -> Path:
    rel = (config or load_config()).get("verification", {}).get(
        "registry", "knowledge/verification/reference_verifications.jsonl")
    return ROOT / rel


def key_references(config: dict[str, Any] | None = None) -> list[str]:
    return list((config or load_config()).get("verification", {}).get("key_references", []))


@lru_cache(maxsize=1)
def _validator() -> Draft202012Validator:
    return Draft202012Validator(json.loads(SCHEMA_PATH.read_text(encoding="utf-8")))


# --------------------------------------------------------------------------- #
# Claims: what the project relies on each reference for
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class Claim:
    claim_id: str
    ref_ids: tuple[str, ...]
    statement: str
    where: str                   # knowledge file / config path
    locator: str = "not_available"


def claims(kb: KnowledgeBase | None = None, config: dict[str, Any] | None = None) -> list[Claim]:
    """Every claim in the knowledge base and the chronology config that cites a reference."""
    kb = kb or default_kb()
    out: list[Claim] = []
    for eid, e in sorted(kb.entries.items()):
        kind = kb.kinds[eid]
        if "reference_ids" in e:
            text = "; ".join(f"{k}: {v}" for k, v in e.items()
                             if k.endswith("_as_printed") and v not in (None, ""))
            out.append(Claim(eid, tuple(e["reference_ids"]), text or eid, f"knowledge/{kind}",
                             str(e.get("locator", "not_available"))))
        for i, a in enumerate(e.get("assertions", [])):
            out.append(Claim(f"{eid}.assertions[{i}]", tuple(a.get("reference_ids", [])),
                             str(a.get("statement", "")), f"knowledge/{kind}",
                             str(a.get("locator", "not_available"))))
    chron = (config or load_config()).get("chronology", {})
    for p in chron.get("tamil_brahmi_earliest_positions", []):
        rng = f"{p.get('lower_year')} to {p.get('upper_year')} (signed years)"
        out.append(Claim(f"config:chronology.position_{p['id']}", (str(p.get("reference")),),
                         f"Earliest Tamil-Brahmi position {p['id']} ({p.get('label')}): "
                         + (rng if p.get("kind", "date_position") == "date_position"
                            else "methodological objection"),
                         "configs/project.yaml#chronology"))
    return out


# --------------------------------------------------------------------------- #
# Records
# --------------------------------------------------------------------------- #


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def new_verification(*, ref_id: str, citation: str, claim: str, status: str,
                     claim_id: str = NA, verifier: str = NA, verifier_role: str = NA,
                     verification_date: str = NA, locator: str = "not_available",
                     source_location: str = "not_available", source_access: str = "not_accessed",
                     notes: str | None = None, supersedes: str | None = None) -> dict[str, Any]:
    rec: dict[str, Any] = {
        "verification_schema_version": VERIFICATION_SCHEMA_VERSION,
        "verification_id": "ver_" + uuid.uuid4().hex[:16],
        "ref_id": ref_id, "citation": citation, "claim": claim, "claim_id": claim_id,
        "status": status, "verifier": verifier, "verifier_role": verifier_role,
        "verification_date": verification_date, "locator": locator,
        "source_location": source_location, "source_access": source_access,
        "created_utc": _utc_now(), "supersedes": supersedes,
    }
    if notes:
        rec["notes"] = notes
    return rec


def _claim_key(v: dict[str, Any]) -> tuple[str, str]:
    cid = v.get("claim_id", NA)
    return v.get("ref_id", ""), cid if cid != NA else " ".join(str(v.get("claim", "")).split()).casefold()


def _real(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip()) and value not in (
        NA, "not_available", "unknown")


@dataclass(frozen=True)
class VProblem:
    rule: str
    message: str
    verification_id: str | None = None

    def __str__(self) -> str:
        return f"{self.rule} {self.verification_id or '<record>'}: {self.message}"


def validate_verification(v: dict[str, Any], kb: KnowledgeBase, claim_ids: set[str],
                          today: date | None = None) -> list[VProblem]:
    vid = v.get("verification_id") if isinstance(v, dict) else None
    out: list[VProblem] = []

    def add(rule: str, msg: str) -> None:
        out.append(VProblem(rule, msg, vid))

    for err in sorted(_validator().iter_errors(v), key=lambda e: list(e.path)):
        add("V1", f"{'.'.join(map(str, err.path)) or '<root>'}: {err.message}")
    if out:
        return out
    if v["ref_id"] not in kb.references:
        add("V2", f"reference {v['ref_id']!r} is not in knowledge/references")
    status, today = v["status"], today or datetime.now(timezone.utc).date()
    checked = v["verification_date"] != NA
    if checked and date.fromisoformat(v["verification_date"]) > today:
        add("V3", f"verification_date {v['verification_date']} is in the future")
    if status == VERIFIED:
        if not _real(v["verifier"]) or v.get("verifier_role", NA) == NA:
            add("V3", "a verified claim needs the human verifier's id and role")
        if not checked:
            add("V3", "a verified claim needs a verification_date")
        if not _real(v["locator"]):
            add("V3", "a verified claim needs the page / plate / catalogue number where it was found")
        if not _real(v["source_location"]):
            add("V3", "a verified claim needs source_location (where the copy consulted is held)")
        if v["source_access"] == "not_accessed":
            add("V3", "a claim cannot be verified from a source that was not accessed")
    elif status == "discrepancy_found":
        if not _real(v["verifier"]) or not checked or v["source_access"] == "not_accessed":
            add("V4", "a discrepancy needs verifier, verification_date and the access used")
        if not _real(v.get("notes")):
            add("V4", "a discrepancy must explain what the source says instead (notes)")
    elif status == "source_unavailable":
        if v["source_access"] != "not_accessed":
            add("V5", "source_unavailable requires source_access='not_accessed'")
        if not _real(v["verifier"]) or not checked or not _real(v.get("notes")):
            add("V5", "source_unavailable records who tried (verifier), when, and why (notes)")
    elif status == "unverified" and checked:
        add("V6", "an unverified record carries no verification_date")
    if v["claim_id"] != NA and v["claim_id"] not in claim_ids:
        add("V7", f"claim_id {v['claim_id']!r} is not a known claim (python -m src.knowledge claims)")
    return out


@dataclass
class VerificationValidation:
    problems: list[VProblem] = field(default_factory=list)
    count: int = 0

    @property
    def ok(self) -> bool:
        return not self.problems


def validate_registry(records: list[dict[str, Any]], kb: KnowledgeBase | None = None,
                      config: dict[str, Any] | None = None,
                      today: date | None = None) -> VerificationValidation:
    kb = kb or default_kb()
    ids = {c.claim_id for c in claims(kb, config)}
    res = VerificationValidation(count=len(records))
    by_id: dict[str, dict[str, Any]] = {}
    for v in records:
        res.problems += validate_verification(v, kb, ids, today)
        vid = v.get("verification_id") if isinstance(v, dict) else None
        if isinstance(vid, str):
            if vid in by_id:
                res.problems.append(VProblem("V8", "duplicate verification_id", vid))
            by_id[vid] = v
    seen: dict[str, list[str]] = defaultdict(list)
    for v in records:
        if not isinstance(v, dict) or not v.get("supersedes"):
            continue
        prev = by_id.get(v["supersedes"])
        if prev is None:
            res.problems.append(VProblem("V8", f"supersedes unknown record {v['supersedes']!r}",
                                         v.get("verification_id")))
        elif _claim_key(prev) != _claim_key(v):
            res.problems.append(VProblem("V8", "supersedes a record of a different reference or claim",
                                         v.get("verification_id")))
        seen[v["supersedes"]].append(v.get("verification_id"))
    for old, new in seen.items():
        if len(new) > 1:
            res.problems.append(VProblem("V8", f"record {old} is superseded more than once: {new}", old))
    backed = {v["ref_id"] for v in current_records(records) if v.get("status") == VERIFIED}
    for rid, ref in sorted(kb.references.items()):
        if ref.get("verification_status") == VERIFIED and rid not in backed:
            res.problems.append(VProblem("K6", f"knowledge-base reference {rid} claims "
                                         "verified_against_source without a verification record"))
    return res


def current_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    superseded = {v.get("supersedes") for v in records if isinstance(v, dict) and v.get("supersedes")}
    return [v for v in records if isinstance(v, dict) and v.get("verification_id") not in superseded]


# --------------------------------------------------------------------------- #
# Registry
# --------------------------------------------------------------------------- #


class VerificationRejected(ValueError):
    def __init__(self, problems: list[VProblem]) -> None:
        self.problems = problems
        super().__init__("verification rejected:\n  - " + "\n  - ".join(map(str, problems)))


@dataclass
class VerificationRegistry:
    path: Path = field(default_factory=registry_path)

    def all(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        return [json.loads(line) for line in self.path.read_text(encoding="utf-8").splitlines()
                if line.strip()]

    def current(self) -> list[dict[str, Any]]:
        return current_records(self.all())

    def validate(self, extra: list[dict[str, Any]] | None = None, *, kb: KnowledgeBase | None = None,
                 today: date | None = None) -> VerificationValidation:
        return validate_registry(self.all() + list(extra or []), kb, today=today)

    def append(self, record: dict[str, Any], *, kb: KnowledgeBase | None = None,
               today: date | None = None) -> dict[str, Any]:
        """Validate against the whole registry, then append. Raises VerificationRejected."""
        res = self.validate([record], kb=kb, today=today)
        mine = [p for p in res.problems
                if p.verification_id in (record.get("verification_id"), record.get("supersedes"))]
        if mine:
            raise VerificationRejected(mine)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8", newline="\n") as fh:
            fh.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
        return record


# --------------------------------------------------------------------------- #
# Effective status
# --------------------------------------------------------------------------- #


@dataclass
class ReferenceStatus:
    ref_id: str
    citation: str
    knowledge_base_status: str
    effective_status: str
    verified_claims: list[dict[str, str]] = field(default_factory=list)
    other_records: list[dict[str, str]] = field(default_factory=list)
    claims_relied_on: list[str] = field(default_factory=list)

    @property
    def verified(self) -> bool:
        return self.effective_status == VERIFIED

    def to_dict(self) -> dict[str, Any]:
        return asdict(self) | {"verified": self.verified}


def reference_status(ref_id: str, *, kb: KnowledgeBase | None = None,
                     current: list[dict[str, Any]] | None = None,
                     config: dict[str, Any] | None = None) -> ReferenceStatus:
    kb = kb or default_kb()
    current = VerificationRegistry().current() if current is None else current
    ref = kb.references.get(ref_id) or {}
    mine = [v for v in current if v.get("ref_id") == ref_id]
    kb_status = str(ref.get("verification_status", "unverified"))
    st = ReferenceStatus(ref_id, str(ref.get("citation", "not in knowledge base")), kb_status,
                         kb_status if kb_status != VERIFIED else "unverified")
    for v in mine:
        row = {"verification_id": v["verification_id"], "claim": v["claim"],
               "claim_id": v["claim_id"], "status": v["status"], "locator": v["locator"],
               "verifier": v["verifier"], "verification_date": v["verification_date"]}
        (st.verified_claims if v["status"] == VERIFIED else st.other_records).append(row)
    if any(v["status"] == "discrepancy_found" for v in mine):
        st.effective_status = "discrepancy_found"
    elif st.verified_claims:
        st.effective_status = VERIFIED
    st.claims_relied_on = [c.claim_id for c in claims(kb, config) if ref_id in c.ref_ids]
    return st


def effective_statuses(*, kb: KnowledgeBase | None = None,
                       current: list[dict[str, Any]] | None = None) -> dict[str, ReferenceStatus]:
    kb = kb or default_kb()
    current = VerificationRegistry().current() if current is None else current
    return {rid: reference_status(rid, kb=kb, current=current) for rid in sorted(kb.references)}


def verified_ref_ids(current: list[dict[str, Any]] | None = None) -> set[str]:
    """References with at least one current verified claim and no current discrepancy."""
    return {rid for rid, s in effective_statuses(current=current).items() if s.verified}


def _column(row: dict[str, str], prefix: str) -> str:
    """Value of the checklist column whose header starts with ``prefix`` ('' if blank)."""
    for k, v in row.items():
        if k and k.split(" (")[0].strip() == prefix:
            return (v or "").strip()
    return ""


@dataclass
class ChecklistImport:
    records: list[dict[str, Any]]
    skipped: int
    problems: list[VProblem]

    @property
    def ok(self) -> bool:
        return not self.problems


def import_checklist(path: Path, registry: VerificationRegistry, *, kb: KnowledgeBase | None = None,
                     today: date | None = None) -> ChecklistImport:
    """Turn a filled verification_checklist.csv into registry records and validate them all.

    Rows with a blank status are skipped (not checked yet). A row for a claim that already has a
    current record supersedes it. Nothing is written here; see ``commit_checklist``."""
    import csv

    kb = kb or default_kb()
    current = {_claim_key(v): v["verification_id"] for v in registry.current()}
    out, skipped = [], 0
    with Path(path).open(encoding="utf-8-sig", newline="") as fh:
        for row in csv.DictReader(fh):
            status = _column(row, "status")
            if not status:
                skipped += 1
                continue
            rec = new_verification(
                ref_id=_column(row, "ref_id"),
                citation=_column(row, "citation_as_checked") or _column(row, "citation") or "not_available",
                claim=_column(row, "claim") or "not_available", claim_id=_column(row, "claim_id") or NA,
                status=status, verifier=_column(row, "verifier_id") or NA,
                verifier_role=_column(row, "verifier_role") or NA,
                verification_date=_column(row, "verification_date") or NA,
                locator=_column(row, "locator_found") or "not_available",
                source_location=_column(row, "source_location") or "not_available",
                source_access=_column(row, "source_access") or "not_accessed",
                notes=_column(row, "notes") or None)
            rec["supersedes"] = current.get(_claim_key(rec))
            out.append(rec)
    res = registry.validate(out, kb=kb, today=today)
    mine = {v["verification_id"] for v in out} | {v["supersedes"] for v in out if v["supersedes"]}
    return ChecklistImport(out, skipped, [p for p in res.problems if p.verification_id in mine
                                          or p.verification_id is None])


def commit_checklist(imp: ChecklistImport, registry: VerificationRegistry, *,
                     kb: KnowledgeBase | None = None, today: date | None = None) -> int:
    """Append every imported record, or nothing if any is invalid (all-or-nothing)."""
    if not imp.ok:
        raise VerificationRejected(imp.problems)
    for rec in imp.records:
        registry.append(rec, kb=kb, today=today)
    return len(imp.records)


__all__ = [
    "NA",
    "RULES",
    "SCHEMA_PATH",
    "VERIFIED",
    "ChecklistImport",
    "Claim",
    "ReferenceStatus",
    "VProblem",
    "VerificationRegistry",
    "VerificationRejected",
    "VerificationValidation",
    "claims",
    "commit_checklist",
    "current_records",
    "effective_statuses",
    "import_checklist",
    "key_references",
    "new_verification",
    "reference_status",
    "registry_path",
    "validate_registry",
    "validate_verification",
    "verified_ref_ids",
]
