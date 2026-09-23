"""Command-line interface for training.

    python -m src.training train  [--config PATH] [--manifest PATH]
    python -m src.training device [--config PATH]
    python -m src.training config [--config PATH]

``train`` evaluates the readiness gate on the canonical research dataset first. With
no authorised data it prints why and exits cleanly with code 3. It never trains on
fixtures, and it has no option that relaxes the gate.

Exit codes: 0 success, 2 configuration or usage error, 3 training blocked by the gate.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

EXIT_OK, EXIT_USAGE, EXIT_BLOCKED = 0, 2, 3


def _force_utf8_output() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):  # pragma: no cover
            pass


def cmd_train(args: argparse.Namespace) -> int:
    from .config import TrainingConfigError
    from .run import run_training

    try:
        outcome = run_training(args.config, args.manifest)
    except TrainingConfigError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_USAGE
    print(outcome.message)
    if outcome.status == "blocked":
        if args.verbose and outcome.readiness is not None:
            print()
            print(outcome.readiness.render())
        else:
            print("\n(run `python -m src.dataset readiness` for the full gate report)")
        return EXIT_BLOCKED
    for path in outcome.experiments:
        print(f"experiment: {path}")
    return EXIT_OK


def cmd_device(args: argparse.Namespace) -> int:
    from .config import TrainingConfig
    from .runtime import environment, select_device

    cfg = TrainingConfig.load(args.config)
    info = select_device(cfg.runtime.device, mixed_precision=cfg.runtime.mixed_precision)
    print(json.dumps({**info.to_dict(), "environment": environment()}, indent=2))
    return EXIT_OK


def cmd_config(args: argparse.Namespace) -> int:
    from .config import TrainingConfig, TrainingConfigError

    try:
        cfg = TrainingConfig.load(args.config)
        cfg.check_against_project()
    except TrainingConfigError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_USAGE
    print(json.dumps(cfg.to_dict(), indent=2))
    return EXIT_OK


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="python -m src.training",
                                description="Training framework (gated on real data).")
    sub = p.add_subparsers(dest="command", required=True)

    t = sub.add_parser("train", help="train on the canonical research dataset (gated)")
    t.add_argument("--config", type=Path, default=None)
    t.add_argument("--manifest", type=Path, default=None, help="split manifest to use")
    t.add_argument("--verbose", action="store_true", help="print the full gate report")
    t.set_defaults(func=cmd_train)

    d = sub.add_parser("device", help="report the selected device and GPU")
    d.add_argument("--config", type=Path, default=None)
    d.set_defaults(func=cmd_device)

    c = sub.add_parser("config", help="print the validated training configuration")
    c.add_argument("--config", type=Path, default=None)
    c.set_defaults(func=cmd_config)
    return p


def main(argv: list[str] | None = None) -> int:
    _force_utf8_output()
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
