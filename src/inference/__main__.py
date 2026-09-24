"""Inference CLI.

    python -m src.inference analyze IMAGE [--artifact-id ID] [--region x,y,w,h ...]
                                          [--checkpoint PATH] [--json]
    python -m src.inference serve [--host 127.0.0.1] [--port 8765] [--max-mb 25]

``analyze`` reads one image and writes nothing. ``--checkpoint`` runs a trained classifier as an
AI observation (none exists while training is blocked). Exit codes: 0 analysed (whatever the
answer, including "Insufficient evidence"), 1 the image could not be analysed, 2 usage error.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from src.console import utf8_console


def cmd_analyze(args: argparse.Namespace) -> int:
    from src.detection import RegionError, parse_region

    from . import InferenceError, analyze, render

    try:
        regions = [parse_region(t) for t in args.region or []]
    except RegionError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    classifier = None
    if args.checkpoint:
        from src.classification import CheckpointClassifier
        from src.training.checkpoint import CheckpointError

        try:
            classifier = CheckpointClassifier(args.checkpoint)
        except (CheckpointError, OSError) as exc:
            print(f"error: checkpoint refused: {exc}", file=sys.stderr)
            return 2
    try:
        result = analyze(args.image, artifact_id=args.artifact_id, regions=regions, classifier=classifier)
    except InferenceError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(result.to_json() if args.json else render(result))
    return 0


def cmd_serve(args: argparse.Namespace) -> int:
    from .server import serve

    serve(args.host, args.port, int(args.max_mb * 2**20))
    return 0


def main(argv: list[str] | None = None) -> int:
    utf8_console()
    p = argparse.ArgumentParser(prog="python -m src.inference", description="Analyse a pottery photograph.")
    sub = p.add_subparsers(dest="command", required=True)
    a = sub.add_parser("analyze", help="analyse one image (writes nothing)")
    a.add_argument("image", type=Path)
    a.add_argument("--artifact-id", help="expected artifact (annotations apply only if the image is registered)")
    a.add_argument("--region", action="append", help="normalised x,y,w,h (user-supplied viewing aid; repeatable)")
    a.add_argument("--checkpoint", type=Path, help="a trained classifier checkpoint (AI observation only)")
    a.add_argument("--json", action="store_true")
    a.set_defaults(func=cmd_analyze)
    s = sub.add_parser("serve", help="HTTP API on localhost (GET /health, POST /analyze)")
    s.add_argument("--host", default="127.0.0.1")
    s.add_argument("--port", type=int, default=8765)
    s.add_argument("--max-mb", type=float, default=25.0)
    s.set_defaults(func=cmd_serve)
    args = p.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
