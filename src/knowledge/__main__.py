"""Knowledge-base and reference-verification CLI (Milestone 8).

    python -m src.knowledge validate                 # K1-K6 and V1-V8
    python -m src.knowledge claims [--ref R1]        # what the project relies on each reference for
    python -m src.knowledge status [--all] [--json]  # effective verification status (key refs by default)
    python -m src.knowledge claim-report [--ref R1] [--json]   # per claim: publication, status, verifier
    python -m src.knowledge entries [--json]         # every claim: id, source, provenance, status, scope, uncertainty
    python -m src.knowledge verify --ref S03 --claim-id s03_keeladi_sathan --status verified_against_source \
        --verifier ID --role expert --date YYYY-MM-DD --locator "p. 12, Fig. 16" \
        --source-location "LIBRARY, shelfmark" --access physical_copy [--notes TEXT] [--commit]
    python -m src.knowledge import-checklist verification_checklist.csv [--commit]

``verify`` and ``import-checklist`` are DRY RUNS unless ``--commit`` is given: they print the
records and the rule check and write nothing. ``import-checklist`` is all-or-nothing. Only a
human who has checked the claim in the publication should commit.

Exit codes: 0 ok, 1 validation failure / rejected record.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from src.console import utf8_console

from .base import load
from .verification import (
    NA,
    RULES,
    VerificationRegistry,
    VerificationRejected,
    claims,
    commit_checklist,
    effective_statuses,
    import_checklist,
    key_references,
    new_verification,
)


def cmd_validate(args: argparse.Namespace) -> int:
    kb = load()
    reg = VerificationRegistry()
    res = reg.validate(kb=kb)
    print(f"Knowledge base : {'PASS' if kb.ok else 'FAIL'} ({len(kb.references)} references, "
          f"{len(kb.entries)} entries)")
    for p in kb.problems:
        print(f"  {p}")
    print(f"Verifications  : {res.count} record(s), {'PASS' if res.ok else 'FAIL'}")
    for p in res.problems:
        print(f"  {p}")
    return 0 if kb.ok and res.ok else 1


def cmd_claims(args: argparse.Namespace) -> int:
    for c in claims():
        if args.ref and args.ref not in c.ref_ids:
            continue
        print(f"{c.claim_id:<44} {','.join(c.ref_ids):<10} {c.where:<32} {c.statement[:110]}")
    return 0


def cmd_entries(args: argparse.Namespace) -> int:
    from .base import describe

    rows = describe()
    if args.json:
        print(json.dumps(rows, indent=2, ensure_ascii=False))
        return 0
    for r in rows:
        refs = ", ".join(f"{s['ref_id']} ({s['reference_status']})" for s in r["source"])
        print(f"\n{r['id']}  [{r['verification_status']}]")
        print(f"  claim       : {r['claim']}")
        print(f"  source      : {refs};  locator: {r['locator']}")
        print(f"  provenance  : {r['provenance']}")
        print(f"  scope       : {r['scope']}")
        print(f"  uncertainty : {r['uncertainty']}")
        if r["notes"]:
            print(f"  notes       : {r['notes']}")
    print(f"\n{len(rows)} claim(s); verified: {sum(r['verification_status'] == 'verified_against_source' for r in rows)}")
    return 0


def cmd_claim_report(args: argparse.Namespace) -> int:
    from .verification import claim_report

    rows = claim_report(args.ref or None)
    if args.json:
        print(json.dumps(rows, indent=2, ensure_ascii=False))
        return 0
    print("CLAIM VERIFICATION REPORT (read-only; 'unverified' until a named human checks the publication)")
    for r in rows:
        print(f"\n[{r['ref_id']}] {r['claim_id']}  ->  {r['verification_status'].upper()}")
        print(f"  claim        : {r['claim']}")
        print(f"  publication  : {r['expected_publication']}")
        print(f"  kb status    : {r['knowledge_base_status']};  locator recorded (unverified): {r['locator_recorded']}")
        print(f"  verifier     : {r['verifier']} ({r['verifier_role']}), {r['verification_date']};  "
              f"locator found: {r['locator_found']}")
        print(f"  notes        : {r['notes']}")
    counts: dict[str, int] = {}
    for r in rows:
        counts[r["verification_status"]] = counts.get(r["verification_status"], 0) + 1
    print(f"\n{len(rows)} claim row(s): {counts}")
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    statuses = effective_statuses()
    keys = key_references()
    shown = statuses if args.all else {k: statuses[k] for k in keys if k in statuses}
    if args.json:
        print(json.dumps({k: v.to_dict() for k, v in shown.items()}, indent=2, ensure_ascii=False))
        return 0
    print("REFERENCE VERIFICATION (a reference is verified only for claims a human checked in the "
          "publication)")
    for rid, s in shown.items():
        mark = "KEY " if rid in keys else "    "
        print(f"{mark}{rid:<5} effective: {s.effective_status:<24} knowledge base: {s.knowledge_base_status}")
        print(f"          {s.citation[:120]}")
        print(f"          claims relied on: {len(s.claims_relied_on)}; verified: {len(s.verified_claims)}; "
              f"other records: {len(s.other_records)}")
        for v in s.verified_claims:
            print(f"          VERIFIED {v['claim_id']} at {v['locator']} by {v['verifier']} "
                  f"on {v['verification_date']}")
        for v in s.other_records:
            print(f"          {v['status'].upper()} {v['claim_id']}: {v['claim'][:80]}")
    missing = [k for k in keys if k not in statuses]
    if missing:
        print(f"Key references missing from the knowledge base: {', '.join(missing)}")
    return 0


def cmd_verify(args: argparse.Namespace) -> int:
    kb = load()
    ref = kb.references.get(args.ref) or {}
    claim_text = args.claim
    if claim_text is None and args.claim_id != NA:
        claim_text = next((c.statement for c in claims(kb) if c.claim_id == args.claim_id), None)
    if not claim_text:
        print("Give --claim TEXT, or a --claim-id listed by `python -m src.knowledge claims`.")
        return 1
    rec = new_verification(
        ref_id=args.ref, citation=args.citation or ref.get("citation", "not_available"),
        claim=claim_text, claim_id=args.claim_id, status=args.status, verifier=args.verifier,
        verifier_role=args.role, verification_date=args.date, locator=args.locator,
        source_location=args.source_location, source_access=args.access, notes=args.notes,
        supersedes=args.supersedes)
    reg = VerificationRegistry()
    print(json.dumps(rec, indent=2, ensure_ascii=False))
    if not args.commit:
        res = reg.validate([rec], kb=kb)
        mine = [p for p in res.problems if p.verification_id == rec["verification_id"]]
        print("DRY RUN: nothing written. " + ("Record is valid; add --commit to append it."
                                              if not mine else "Record would be REJECTED:"))
        for p in mine:
            print(f"  {p}")
        return 1 if mine else 0
    try:
        reg.append(rec, kb=kb)
    except VerificationRejected as exc:
        print(str(exc))
        return 1
    print(f"Appended {rec['verification_id']} to {reg.path}")
    return 0


def cmd_import_checklist(args: argparse.Namespace) -> int:
    reg = VerificationRegistry()
    imp = import_checklist(args.path, reg)
    print(f"Rows with a status: {len(imp.records)}; blank rows skipped: {imp.skipped}")
    for v in imp.records:
        print(f"  {v['ref_id']:<5} {v['claim_id']:<40} {v['status']:<24} "
              f"{v['locator']} by {v['verifier']} on {v['verification_date']}"
              + (f" (supersedes {v['supersedes']})" if v["supersedes"] else ""))
    for p in imp.problems:
        print(f"  {p}")
    if not imp.ok:
        print("REJECTED: nothing written. Fix the rows above; the import is all-or-nothing.")
        return 1
    if not args.commit:
        print("DRY RUN: nothing written. Add --commit to append these records.")
        return 0
    n = commit_checklist(imp, reg)
    print(f"Appended {n} record(s) to {reg.path}")
    return 0


def cmd_rules(args: argparse.Namespace) -> int:
    for k, v in RULES.items():
        print(f"  {k:<4} {v}")
    return 0


def main(argv: list[str] | None = None) -> int:
    utf8_console()
    p = argparse.ArgumentParser(prog="python -m src.knowledge")
    sub = p.add_subparsers(dest="command", required=True)
    sub.add_parser("validate").set_defaults(func=cmd_validate)
    c = sub.add_parser("claims")
    c.add_argument("--ref")
    c.set_defaults(func=cmd_claims)
    s = sub.add_parser("status")
    s.add_argument("--all", action="store_true")
    s.add_argument("--json", action="store_true")
    s.set_defaults(func=cmd_status)
    en = sub.add_parser("entries", help="every knowledge-base claim in one normalised shape")
    en.add_argument("--json", action="store_true")
    en.set_defaults(func=cmd_entries)
    cr = sub.add_parser("claim-report", help="per-claim verification report (key refs + unresolved ids)")
    cr.add_argument("--ref", action="append", help="limit to a reference id (repeatable)")
    cr.add_argument("--json", action="store_true")
    cr.set_defaults(func=cmd_claim_report)
    sub.add_parser("rules").set_defaults(func=cmd_rules)
    ic = sub.add_parser("import-checklist", help="import a filled verification checklist (dry run unless --commit)")
    ic.add_argument("path", type=Path)
    ic.add_argument("--commit", action="store_true")
    ic.set_defaults(func=cmd_import_checklist)
    v = sub.add_parser("verify", help="record a human check of one claim (dry run unless --commit)")
    v.add_argument("--ref", required=True)
    v.add_argument("--claim-id", default=NA)
    v.add_argument("--claim")
    v.add_argument("--citation")
    v.add_argument("--status", required=True,
                   choices=["verified_against_source", "discrepancy_found", "source_unavailable",
                            "unverified"])
    v.add_argument("--verifier", default=NA)
    v.add_argument("--role", default=NA, choices=["project_member", "expert", NA])
    v.add_argument("--date", default=NA, help="YYYY-MM-DD")
    v.add_argument("--locator", default="not_available")
    v.add_argument("--source-location", default="not_available")
    v.add_argument("--access", default="not_accessed",
                   choices=["physical_copy", "authorised_digital_copy", "open_access_publication",
                            "not_accessed"])
    v.add_argument("--notes")
    v.add_argument("--supersedes")
    v.add_argument("--commit", action="store_true", help="append the record (default: dry run)")
    v.set_defaults(func=cmd_verify)
    args = p.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
