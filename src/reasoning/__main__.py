"""Reasoning CLI.

    python -m src.reasoning analyze <artifact_id> [--json]
    python -m src.reasoning analyze --all [--json]
"""

from __future__ import annotations

import argparse
import json
import sys

from src.dataset.convert import read_jsonl
from src.dataset.schema import RESEARCH_RECORDS_PATH

from .engine import analyze_artifact, render_text
from .from_annotations import build_inputs


def main(argv: list[str] | None = None) -> int:
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):  # pragma: no cover
            pass
    p = argparse.ArgumentParser(prog="python -m src.reasoning")
    sub = p.add_subparsers(dest="command", required=True)
    a = sub.add_parser("analyze")
    a.add_argument("artifact_id", nargs="?")
    a.add_argument("--all", action="store_true")
    a.add_argument("--json", action="store_true")
    args = p.parse_args(argv)

    records = read_jsonl(RESEARCH_RECORDS_PATH) if RESEARCH_RECORDS_PATH.exists() else []
    ids = sorted({r["artifact_id"] for r in records}) if args.all else [args.artifact_id]
    if not ids or ids == [None]:
        print("error: give an artifact_id or --all", file=sys.stderr)
        return 2
    out = []
    for aid in ids:
        try:
            result = analyze_artifact(build_inputs(aid, records=records))
        except KeyError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
        out.append(result)
    if args.json:
        print(json.dumps([r.to_dict() for r in out], indent=2, ensure_ascii=False))
    else:
        print(("\n" + "=" * 72 + "\n").join(render_text(r) for r in out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
