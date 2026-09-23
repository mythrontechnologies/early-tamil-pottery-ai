"""Annotation CLI.

    python -m src.annotation validate   [--store PATH]
    python -m src.annotation summary    [--store PATH]
    python -m src.annotation quality    [--store PATH] [--json]
    python -m src.annotation rules

Exit codes: 0 valid / ok, 1 validation failure.
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

    kb = load()
    store = AnnotationStore(args.store)
    result = store.validate(knowledge_ref_ids=set(kb.references))
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
    args = p.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
