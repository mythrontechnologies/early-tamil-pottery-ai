"""Annotation CLI.

    python -m src.annotation validate   [--store PATH]
    python -m src.annotation summary    [--store PATH]
    python -m src.annotation quality    [--store PATH] [--json]
    python -m src.annotation rules
    python -m src.annotation pilot      [--json]                      # Milestone 8 pilot progress
    python -m src.annotation agreement  [--all] [--rater-a X] [--rater-b Y] [--json]
    python -m src.annotation promote    [--dry-run] [--pilot | --artifact A ...] [--json]
    python -m src.annotation promote    --execute --approve <plan_digest> --approver <id>
    python -m src.annotation promote    --revert <promotion_id> [--execute --approve <digest> --approver <id>]
    python -m src.annotation promote    --log

``promote`` is a DRY RUN unless ``--execute`` is given together with the digest printed by
the dry run and the approving human's id. Nothing else in this CLI writes anything.

Exit codes: 0 valid / ok, 1 validation failure / refused.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

from src.dataset.convert import read_jsonl
from src.dataset.schema import RESEARCH_RECORDS_PATH

from .model import ANNOTATIONS_PATH
from .quality import quality_report
from .resolve import resolve_all
from .store import AnnotationStore
from .validate import RULES


def _records() -> list[dict]:
    return read_jsonl(RESEARCH_RECORDS_PATH) if RESEARCH_RECORDS_PATH.exists() else []


def cmd_validate(args: argparse.Namespace) -> int:
    from src.knowledge.base import load
    from src.knowledge.verification import verified_ref_ids

    kb = load()
    store = AnnotationStore(args.store)
    result = store.validate(knowledge_ref_ids=set(kb.references), verified_ref_ids=verified_ref_ids())
    print(f"Annotations       : {result.count}")
    print(f"Knowledge base    : {'PASS' if kb.ok else 'FAIL'} ({len(kb.references)} references, "
          f"{len(kb.entries)} entries)")
    for p in kb.problems:
        print(f"  {p}")
    print(f"Annotation status : {result.status}")
    for p in result.problems:
        print(f"  {p}")
    return 0 if result.ok and kb.ok else 1


def cmd_summary(args: argparse.Namespace) -> int:
    store = AnnotationStore(args.store)
    records = _records()
    current = store.current()
    res = resolve_all({r["artifact_id"] for r in records}, current)
    counts = Counter(r.status for r in res)
    prov = Counter(a["provenance_type"] for a in current)
    print(f"Artifacts                 : {len(res)}")
    print(f"Annotations (all / current): {len(store.all())} / {len(current)}")
    print(f"Current by provenance     : {dict(prov) or '{}'}")
    print(f"Status                    : {dict(sorted(counts.items()))}")
    print(f"Expert labels             : {counts.get('expert_label', 0)}")
    print(f"Ground-truth eligible     : {sum(r.ground_truth_eligible for r in res)}")
    for r in res:
        if r.disagreements:
            print(f"  disagreement {r.artifact_id}: {json.dumps(r.disagreements, ensure_ascii=False)}")
    return 0


def cmd_quality(args: argparse.Namespace) -> int:
    rows = quality_report(_records(), AnnotationStore(args.store).current())
    if args.json:
        print(json.dumps([r.to_dict() for r in rows], indent=2, ensure_ascii=False))
        return 0
    print("TECHNICAL QUALITY (uncalibrated heuristics)  |  ARCHAEOLOGICAL USABILITY (annotators)")
    for r in rows:
        tech = ",".join(r.technical_flags) or "no flags"
        usab = "; ".join(f"{who}: usable={u['usable_for_annotation']}" for who, u in r.usability.items()) \
            or "not yet assessed"
        print(f"  {r.image_id:<14} {r.artifact_id:<36} {tech:<28} | {usab}")
    print("\nTechnical flags never reject an image; usability is judged by annotators only.")
    return 0


def cmd_rules(args: argparse.Namespace) -> int:
    for k, v in RULES.items():
        print(f"  {k:<4} {v}")
    return 0


def cmd_pilot(args: argparse.Namespace) -> int:
    from .pilot import pilot_status, render_pilot

    ps = pilot_status(AnnotationStore(args.store).current(), {r["artifact_id"] for r in _records()})
    print(json.dumps(ps.to_dict(), indent=2, ensure_ascii=False) if args.json else render_pilot(ps))
    return 0


def cmd_agreement(args: argparse.Namespace) -> int:
    from .agreement import compute_agreement, render_agreement
    from .pilot import load_pilot

    current = AnnotationStore(args.store).current()
    ids = sorted({r["artifact_id"] for r in _records()}) if args.all else list(load_pilot().artifacts)
    rep = compute_agreement(current, ids, args.rater_a, args.rater_b)
    print(json.dumps(rep.to_dict(), indent=2, ensure_ascii=False) if args.json else render_agreement(rep))
    return 0


def cmd_promote(args: argparse.Namespace) -> int:
    from .pilot import load_pilot
    from .promote import (
        PromotionError,
        execute_promotion,
        execute_revert,
        plan_promotion,
        plan_revert,
        read_log,
        render_plan,
    )

    if args.log:
        for e in read_log():
            what = e.get("reverts") or ", ".join(e.get("artifacts", []))
            print(f"{e['executed_utc']}  {e['action']:<8} {e['promotion_id']}  by {e['approver']}  {what}")
        return 0
    if args.revert:
        try:
            if not args.execute:
                rp = plan_revert(args.revert)
                print(json.dumps(rp.to_dict(), indent=2, ensure_ascii=False))
                print("DRY RUN: nothing written." + (f" To execute: --revert {args.revert} --execute "
                                                     f"--approve {rp.plan_digest} --approver <id>"
                                                     if rp.executable else " Revert is not possible."))
                return 0
            entry = execute_revert(args.revert, approver=args.approver, approve=args.approve)
        except PromotionError as exc:
            print(f"REFUSED: {exc}")
            return 1
        print(f"Reverted {args.revert}: restored {len(entry['restored_image_ids'])} record(s); "
              f"logged as {entry['promotion_id']}")
        return 0

    artifacts = list(load_pilot().artifacts) if args.pilot else (args.artifact or None)
    store = AnnotationStore(args.store)

    def plan():
        return plan_promotion(store=store, artifact_ids=artifacts)

    if not args.execute:
        p = plan()
        print(json.dumps(p.to_dict(), indent=2, ensure_ascii=False) if args.json else render_plan(p))
        return 0
    try:
        entry = execute_promotion(plan, approver=args.approver, approve=args.approve)
    except PromotionError as exc:
        print(f"REFUSED: {exc}")
        return 1
    print(f"Promoted {', '.join(entry['artifacts'])} as {entry['promotion_id']} "
          f"({len(entry['changes'])} record(s)). Reverse with: python -m src.annotation promote "
          f"--revert {entry['promotion_id']}")
    return 0


def main(argv: list[str] | None = None) -> int:
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):  # pragma: no cover
            pass
    p = argparse.ArgumentParser(prog="python -m src.annotation")
    sub = p.add_subparsers(dest="command", required=True)
    for name, fn in (("validate", cmd_validate), ("summary", cmd_summary),
                     ("quality", cmd_quality), ("rules", cmd_rules)):
        sp = sub.add_parser(name)
        sp.add_argument("--store", type=Path, default=ANNOTATIONS_PATH)
        sp.add_argument("--json", action="store_true")
        sp.set_defaults(func=fn)
    pl = sub.add_parser("pilot", help="progress of the Milestone 8 expert annotation pilot")
    ag = sub.add_parser("agreement", help="inter-annotator agreement (pilot artifacts by default)")
    ag.add_argument("--all", action="store_true", help="all research artifacts, not only the pilot")
    ag.add_argument("--rater-a", default="project_annotation")
    ag.add_argument("--rater-b", default="expert_annotation")
    pr = sub.add_parser("promote", help="expert labels -> records (DRY RUN unless --execute)")
    scope = pr.add_mutually_exclusive_group()
    scope.add_argument("--pilot", action="store_true", help="only the pilot artifacts")
    scope.add_argument("--artifact", action="append", help="an artifact id (repeatable)")
    pr.add_argument("--dry-run", action="store_true", help="the default; accepted for clarity")
    pr.add_argument("--execute", action="store_true", help="write, with --approve and --approver")
    pr.add_argument("--approve", help="the plan digest printed by the dry run")
    pr.add_argument("--approver", help="id of the human approving this write")
    pr.add_argument("--revert", metavar="PROMOTION_ID")
    pr.add_argument("--log", action="store_true", help="list the promotion audit log")
    for sp, fn in ((pl, cmd_pilot), (ag, cmd_agreement), (pr, cmd_promote)):
        sp.add_argument("--store", type=Path, default=ANNOTATIONS_PATH)
        sp.add_argument("--json", action="store_true")
        sp.set_defaults(func=fn)
    args = p.parse_args(argv)
    if getattr(args, "execute", False) and getattr(args, "dry_run", False):
        p.error("--dry-run and --execute are mutually exclusive")
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
