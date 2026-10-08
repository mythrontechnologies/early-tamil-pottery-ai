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
    python -m src.annotation handoff    [--out DIR] [--all]           # blank worksheets (+ every artifact with --all)
    python -m src.annotation integrity  [--seal PATH]                 # append-only ledgers intact?
    python -m src.annotation queue      [--json]                      # every artifact: state + next HUMAN step
    python -m src.annotation disagreements [--all] [--json]           # field by field, who said what
    python -m src.annotation export     [--out DIR]                   # current annotations, tier-labelled
    python -m src.annotation import-worksheet FILE.csv --role project|expert [--revise] [--commit]

``promote`` is a DRY RUN unless ``--execute`` is given together with the digest printed by
the dry run and the approving human's id. ``import-worksheet`` is a DRY RUN unless ``--commit``
and is all-or-nothing. ``export`` and ``handoff`` write only under ``outputs/`` (git-ignored).
Nothing else in this CLI writes anything.

Exit codes: 0 valid / ok, 1 validation failure / refused.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

from src.console import utf8_console
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
    for problem in result.problems:
        print(f"  {problem}")
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


def cmd_integrity(args: argparse.Namespace) -> int:
    """Check the append-only ledgers of the annotation store, verification registry and
    promotion log. ``--seal PATH`` adopts one ledger-less file as it stands (human action)."""
    from src.integrity import seal, verify
    from src.knowledge.verification import registry_path

    from .promote import _settings as promotion_settings

    if args.seal:
        rep = seal(args.seal)
        print(f"sealed {rep.path}: {rep.lines} line(s), head {rep.head[:16]}")
        return 0 if rep.ok else 1
    ok = True
    for name, path in (("annotations", args.store), ("verification registry", registry_path()),
                       ("promotion log", promotion_settings(None)[0])):
        rep = verify(path)
        ok &= rep.ok
        print(f"{name:<22} {rep.status:<22} lines {rep.lines:<4} head {rep.head[:16]}  {path}")
        for p in rep.problems:
            print(f"    {p}")
    return 0 if ok else 1


def cmd_handoff(args: argparse.Namespace) -> int:
    from .handoff import DEFAULT_OUT, build_handoff
    from .worksheet import build_worksheets

    pack = build_handoff(_records(), args.out or DEFAULT_OUT)
    print(f"Handoff pack in {pack.out_dir}: {pack.photos} pilot photograph(s), {pack.claims} claim(s) to verify")
    for f in pack.files:
        print(f"  {f.name}")
    if args.all:
        for f in build_worksheets(_records(), pack.out_dir, prefix="worksheet_all"):
            print(f"  {f.name}  (every research photograph)")
    print("Judgement and verification columns are blank by design. Brief: docs/PILOT_HANDOFF.md")
    return 0


def cmd_queue(args: argparse.Namespace) -> int:
    from .pilot import load_pilot, load_review_flags
    from .worksheet import annotation_queue

    pilot = load_pilot()
    rows = annotation_queue(_records(), AnnotationStore(args.store).current(), pilot.artifacts,
                            pilot.required_tiers, load_review_flags())
    if args.json:
        print(json.dumps([r.to_dict() for r in rows], indent=2, ensure_ascii=False))
        return 0
    print("ANNOTATION QUEUE (every research artifact; nothing here is a label)")
    for r in rows:
        tiers = ", ".join(f"{k}={v}" for k, v in sorted(r.tiers.items())) or "none"
        print(f"  {'P ' if r.in_pilot else '  '}{r.artifact_id:<36} {len(r.image_ids)} photo(s)  "
              f"status: {r.status:<20} annotations: {tiers}")
        print(f"      next: {r.next_step}")
        for f in r.review_flags:
            print(f"      FLAG {f}")
        for n in r.notes:
            print(f"      note: {n}")
    states = Counter(r.status for r in rows)
    print(f"\n{len(rows)} artifact(s): {dict(sorted(states.items()))}.  P = pilot artifact.")
    print("Annotate: streamlit run app/main.py (Annotation), or fill a worksheet "
          "(python -m src.annotation handoff --all) and import it.")
    return 0


def cmd_disagreements(args: argparse.Namespace) -> int:
    from .pilot import load_pilot
    from .worksheet import disagreement_report

    ids = sorted({r["artifact_id"] for r in _records()}) if args.all else list(load_pilot().artifacts)
    rep = disagreement_report(ids, AnnotationStore(args.store).current())
    if args.json:
        print(json.dumps(rep, indent=2, ensure_ascii=False))
        return 0
    if not rep:
        print("No human annotation yet: nothing to compare.")
        return 0
    for r in rep:
        print(f"\n{r['artifact_id']}  status: {r['status']}  label: {r['label'] or '-'}  "
              f"expert reviewed: {'yes' if r['expert_reviewed'] else 'NO'}"
              + ("  [PROVISIONAL]" if r["provisional"] else ""))
        for n in r["notes"]:
            print(f"  note: {n}")
        for k, f in r["fields"].items():
            if f["state"] in ("disagree", "agree"):
                vals = "; ".join(f"{who}: {v}" for who, v in f["values"].items())
                print(f"  {f['state'].upper():<9} {k:<22} {vals}")
    print("\nDisagreements are kept, never averaged. An expert resolves them by adjudication "
          "(docs/ANNOTATION_GUIDE.md).")
    return 0


def cmd_export(args: argparse.Namespace) -> int:
    from src.dataset.schema import ROOT

    from .worksheet import export_annotations

    out = args.out or ROOT / "outputs" / "annotation_export"
    for f in export_annotations(AnnotationStore(args.store).current(), out):
        print(f"wrote {f}")
    print("Every row states its provenance tier; AI predictions are marked is_ai_output=True.")
    return 0


def cmd_import_worksheet(args: argparse.Namespace) -> int:
    from .store import AnnotationRejected
    from .worksheet import commit_worksheet, import_worksheet

    store = AnnotationStore(args.store)
    imp = import_worksheet(args.path, args.role, store, revise=args.revise)
    print(f"Annotations parsed: {len(imp.annotations)}; blank rows skipped: {imp.skipped_rows}")
    for a in imp.annotations:
        ins = a["inscription"]
        print(f"  {a['artifact_id']:<36} {a['annotator']['annotator_id']:<20} {a['provenance_type']:<18} "
              f"present={ins['inscription_present']} script={ins['script_type']} "
              f"photos={len(a['image_ids'])}" + (f" (revises {a['supersedes']})" if a["supersedes"] else ""))
    for p in imp.problems:
        print(f"  {p}")
    if not imp.ok:
        print("REJECTED: nothing written. Fix the rows above; the import is all-or-nothing.")
        return 1
    if not args.commit:
        print("DRY RUN: nothing written. Add --commit to append these annotations.")
        return 0
    try:
        n = commit_worksheet(imp, store)
    except AnnotationRejected as exc:
        print(str(exc))
        return 1
    print(f"Appended {n} annotation(s) to {store.path}")
    return 0


def main(argv: list[str] | None = None) -> int:
    utf8_console()
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
    ho = sub.add_parser("handoff", help="write blank pilot worksheets + verification checklist")
    ho.add_argument("--out", type=Path, help="output directory (default outputs/pilot_handoff, git-ignored)")
    ho.add_argument("--all", action="store_true", help="also worksheets for every research photograph")
    qu = sub.add_parser("queue", help="every research artifact: annotation state and next human step")
    di = sub.add_parser("disagreements", help="field-level disagreement report (pilot by default)")
    di.add_argument("--all", action="store_true", help="all research artifacts")
    ex = sub.add_parser("export", help="export current annotations (JSONL + CSV, tier-labelled)")
    ex.add_argument("--out", type=Path, help="output directory (default outputs/annotation_export)")
    iw = sub.add_parser("import-worksheet", help="import a filled worksheet (dry run unless --commit)")
    iw.add_argument("path", type=Path)
    iw.add_argument("--role", required=True, choices=["project", "expert"])
    iw.add_argument("--revise", action="store_true", help="record revisions of existing annotations")
    iw.add_argument("--commit", action="store_true")
    it = sub.add_parser("integrity", help="verify the append-only ledgers (tamper evidence)")
    it.add_argument("--seal", type=Path, help="adopt a ledger-less file as it stands (human action)")
    for sp, fn in ((pl, cmd_pilot), (ag, cmd_agreement), (pr, cmd_promote), (ho, cmd_handoff),
                   (it, cmd_integrity), (qu, cmd_queue), (di, cmd_disagreements), (ex, cmd_export),
                   (iw, cmd_import_worksheet)):
        sp.add_argument("--store", type=Path, default=ANNOTATIONS_PATH)
        sp.add_argument("--json", action="store_true")
        sp.set_defaults(func=fn)
    args = p.parse_args(argv)
    if getattr(args, "execute", False) and getattr(args, "dry_run", False):
        p.error("--dry-run and --execute are mutually exclusive")
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
