"""Command-line interface for acquisition.

    python -m src.acquisition plan   <plan.yaml>            # dry run (default): licence gate + sizes
    python -m src.acquisition plan   <plan.yaml> --commit   # download, verify, place, ingest
    python -m src.acquisition rules                          # list policy checks A1-A9
    python -m src.acquisition registry                       # summarise acquired files

Nothing is downloaded without ``--commit``. Exit codes: 0 success, 1 at least one file
failed after download, 2 usage error.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

from src.console import utf8_console


def _utf8() -> None:
    utf8_console()


def cmd_plan(args: argparse.Namespace) -> int:
    from .commons import CommonsClient
    from .pipeline import PlanError, load_plan, run

    try:
        plan = load_plan(args.plan)
    except (PlanError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    report = run(plan, CommonsClient(min_interval=args.interval), dry_run=not args.commit)
    print(json.dumps(report.to_dict(), indent=2, ensure_ascii=False) if args.json else report.render())
    if report.dry_run:
        print("\nDRY RUN: nothing was downloaded. Re-run with --commit to acquire the 'planned' files.")
    return 1 if report.count("failed") else 0


def cmd_rules(args: argparse.Namespace) -> int:
    from .licenses import ALLOWED
    from .policy import BLOCKED_DOMAINS, RULES

    for k, v in RULES.items():
        print(f"  {k}  {v}")
    print("\nAllowed licences:", ", ".join(ALLOWED))
    print("Blocked sources :", ", ".join(BLOCKED_DOMAINS))
    return 0


def cmd_registry(args: argparse.Namespace) -> int:
    from .provenance import read_registry

    reg = read_registry()
    print(f"files: {len(reg)}")
    for key in ("target", "dataset_id", "license", "geographic_scope", "project_label"):
        print(f"{key}: {dict(Counter(r[key] for r in reg))}")
    return 0


def main(argv: list[str] | None = None) -> int:
    _utf8()
    p = argparse.ArgumentParser(prog="python -m src.acquisition")
    sub = p.add_subparsers(dest="command", required=True)
    pl = sub.add_parser("plan", help="evaluate (and with --commit, execute) an acquisition plan")
    pl.add_argument("plan", type=Path)
    pl.add_argument("--commit", action="store_true", help="download and ingest (default: dry run)")
    pl.add_argument("--interval", type=float, default=1.0, help="seconds between requests")
    pl.add_argument("--json", action="store_true")
    pl.set_defaults(func=cmd_plan)
    sub.add_parser("rules").set_defaults(func=cmd_rules)
    sub.add_parser("registry").set_defaults(func=cmd_registry)
    args = p.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
