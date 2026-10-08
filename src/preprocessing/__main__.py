"""Command-line interface for preprocessing.

    python -m src.preprocessing inspect <image> [--json]
    python -m src.preprocessing run     <image|dir> --out DIR [options]
    python -m src.preprocessing checks

``inspect`` reads and reports; it writes nothing. ``run`` writes processed images and
their provenance sidecars, and refuses any output path under ``data/raw``.

Exit codes: 0 success, 1 one or more images failed, 2 usage or I/O error.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from src.console import utf8_console

from .loader import EXTENSION_FORMATS, ISSUE_TITLES
from .pipeline import (
    DEFAULT_OUTPUT_ROOT,
    PreprocessConfig,
    RawImmutabilityError,
    _strategy,
    preprocess_image,
    save_result,
)
from .quality import DISCLAIMER

EXIT_OK, EXIT_FAIL, EXIT_USAGE = 0, 1, 2


def _force_utf8_output() -> None:
    utf8_console()


def _config_from_args(args: argparse.Namespace) -> PreprocessConfig:
    cfg = PreprocessConfig.from_config()
    if getattr(args, "size", None):
        cfg.target_size = args.size
    if getattr(args, "strategy", None):
        cfg.resize_strategy = _strategy(args.strategy)
    return cfg


def _gather(target: Path) -> list[Path]:
    if target.is_file():
        return [target]
    if target.is_dir():
        suffixes = set(EXTENSION_FORMATS)
        return sorted(p for p in target.rglob("*") if p.is_file() and p.suffix.lower() in suffixes)
    return []


def cmd_inspect(args: argparse.Namespace) -> int:
    paths = _gather(args.path)
    if not paths:
        print(f"error: no images found at {args.path}", file=sys.stderr)
        return EXIT_USAGE

    cfg = _config_from_args(args)
    failed = 0
    payload = []

    for path in paths:
        result = preprocess_image(path, config=cfg)
        if not result.ok:
            failed += 1
        if args.json:
            payload.append(result.sidecar())
        else:
            print(result.render())
            print("-" * 68)

    if args.json:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        print(f"{len(paths)} image(s), {failed} failed")
        print(f"\nNote: {DISCLAIMER}")
    return EXIT_FAIL if failed else EXIT_OK


def cmd_run(args: argparse.Namespace) -> int:
    paths = _gather(args.path)
    if not paths:
        print(f"error: no images found at {args.path}", file=sys.stderr)
        return EXIT_USAGE

    out_root = args.out or DEFAULT_OUTPUT_ROOT
    base = args.path if args.path.is_dir() else args.path.parent
    cfg = _config_from_args(args)

    ok = failed = 0
    for path in paths:
        result = preprocess_image(path, config=cfg)
        if not result.ok:
            failed += 1
            print(f"FAIL {path}")
            for issue in result.errors:
                print(f"     {issue}")
            continue

        relative = path.relative_to(base) if path.is_relative_to(base) else Path(path.name)
        destination = Path(out_root) / relative.with_suffix(".png")
        try:
            save_result(result, destination, write_sidecar=not args.no_sidecar)
        except RawImmutabilityError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return EXIT_USAGE

        ok += 1
        flags = ",".join(result.quality.flags) if result.quality else ""
        print(f"OK   {path} -> {destination}" + (f"   [{flags}]" if flags else ""))

    print(f"\n{ok} written, {failed} failed  (output root: {out_root})")
    if ok:
        print(f"Note: {DISCLAIMER}")
    return EXIT_FAIL if failed else EXIT_OK


def cmd_checks(args: argparse.Namespace) -> int:
    print("Preprocessing checks\n")
    print("  P* - engineering checks on the file and image. Not archaeological claims.\n")
    for code, title in sorted(ISSUE_TITLES.items()):
        print(f"  {code:<4} {title}")
    print(f"\nQuality flags are warnings only.\n{DISCLAIMER}")
    return EXIT_OK


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m src.preprocessing",
        description="Deterministic image preprocessing. Never modifies source images.",
    )
    sub = p.add_subparsers(dest="command", required=True)

    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--size", type=int, default=None, help="override target size")
    common.add_argument("--strategy", choices=["pad", "crop"], default=None)

    i = sub.add_parser("inspect", parents=[common], help="report on images, write nothing")
    i.add_argument("path", type=Path)
    i.add_argument("--json", action="store_true")
    i.set_defaults(func=cmd_inspect)

    r = sub.add_parser("run", parents=[common], help="preprocess and write results")
    r.add_argument("path", type=Path)
    r.add_argument("--out", type=Path, default=None, help=f"default: {DEFAULT_OUTPUT_ROOT}")
    r.add_argument("--no-sidecar", action="store_true", help="skip the provenance JSON")
    r.set_defaults(func=cmd_run)

    c = sub.add_parser("checks", help="list the validation checks")
    c.set_defaults(func=cmd_checks)

    return p


def main(argv: list[str] | None = None) -> int:
    _force_utf8_output()
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
