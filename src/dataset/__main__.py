"""Command-line interface for the dataset layer.

    python -m src.dataset validate  <path> [options]
    python -m src.dataset ingest    <path> [options]
    python -m src.dataset audit     [--records PATH]
    python -m src.dataset readiness [--out PATH]
    python -m src.dataset convert   <in> <out>
    python -m src.dataset rules
    python -m src.dataset stats     [--json]
    python -m src.dataset split     [--strategy auto|holdout|grouped_kfold] [--seed N]
                                    [--adopt-existing] [--dry-run]

Exit codes: 0 success, 1 validation/ingestion failure or refused split, 2 usage or I/O error.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .audit import audit
from .convert import ConversionError, csv_to_jsonl, jsonl_to_csv, load_records
from .ingest import ingest
from .readiness import evaluate, write_report
from .schema import RESEARCH_DATA_ROOT, RESEARCH_RECORDS_PATH
from .validation import RULE_TITLES, validate_records
from .loader import LOADER_RULES, DatasetLoadError, load_dataset
from .splits import SplitError, SplitSettings, adopt_existing_split, make_split
from .statistics import compute_statistics

EXIT_OK, EXIT_FAIL, EXIT_USAGE = 0, 1, 2


def _force_utf8_output() -> None:
    """Print Tamil and other non-Latin text without crashing on a legacy console.

    Windows consoles commonly default to cp1252, which cannot encode Tamil. Since
    record content routinely contains it, a report that raises UnicodeEncodeError
    halfway through is worse than one with a few replacement characters.
    """
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):  # pragma: no cover - non-reconfigurable stream
            pass


def _add_validation_flags(p: argparse.ArgumentParser) -> None:
    p.add_argument("--data-root", type=Path, default=None,
                   help=f"root for image_path (default: {RESEARCH_DATA_ROOT}). "
                        "Omit and the directory must exist, or R2/E2 are reported as skipped.")
    p.add_argument("--no-images", action="store_true",
                   help="skip image existence and hash checks (reported as skipped, not passed)")
    p.add_argument("--verify-hashes", action="store_true",
                   help="recompute SHA-256 for image files that exist")
    p.add_argument("--export", action="store_true",
                   help="enable R11: only redistributable='yes' records may pass")
    p.add_argument("--strict", action="store_true", help="treat warnings as failures")


def cmd_validate(args: argparse.Namespace) -> int:
    try:
        records = load_records(args.path)
    except (ConversionError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_USAGE

    root = None if args.no_images else (args.data_root or RESEARCH_DATA_ROOT)
    if root is not None and not Path(root).is_dir():
        print(f"note: data root {root} does not exist; image checks will be skipped")
        root = None

    result = validate_records(
        records,
        data_root=root,
        verify_hashes=args.verify_hashes,
        export_mode=args.export,
        strict=args.strict,
    )

    if args.json:
        print(json.dumps(
            {
                "source": str(args.path),
                "status": result.status,
                "record_count": result.record_count,
                "errors": len(result.errors),
                "warnings": len(result.warnings),
                "images_checked": result.images_checked,
                "hashes_verified": result.hashes_verified,
                "by_rule": result.by_rule(),
                "findings": [
                    {
                        "rule": f.rule, "severity": f.severity, "message": f.message,
                        "image_id": f.image_id, "field": f.field,
                        "record_index": f.record_index,
                    }
                    for f in result.findings
                ],
            },
            indent=2, ensure_ascii=False,
        ))
    else:
        print(f"Source: {args.path}\n")
        print(result.summary())
        if result.findings:
            print(f"\nFindings ({len(result.findings)}):")
            for f in result.findings:
                print(f"  {f}")
        else:
            print("\nNo findings.")
    return EXIT_OK if result.ok else EXIT_FAIL


def cmd_ingest(args: argparse.Namespace) -> int:
    root = Path("/nonexistent-skip-images") if args.no_images else (
        args.data_root or RESEARCH_DATA_ROOT
    )
    result = ingest(
        args.path,
        destination=args.destination,
        data_root=root,
        verify_hashes=args.verify_hashes,
        export_mode=args.export,
        strict=args.strict,
        commit=args.commit,
        merge=not args.no_merge,
    )
    print(result.render())
    return EXIT_OK if result.accepted else EXIT_FAIL


def cmd_audit(args: argparse.Namespace) -> int:
    path = args.records or RESEARCH_RECORDS_PATH
    if not Path(path).exists():
        report = audit([], source=path)
        print(report.render() if not args.json else json.dumps(report.to_dict(), indent=2))
        return EXIT_OK

    try:
        records = load_records(path)
    except (ConversionError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_USAGE

    root = RESEARCH_DATA_ROOT if RESEARCH_DATA_ROOT.is_dir() else None
    validation = validate_records(records, data_root=root)
    report = audit(records, source=path, validation=validation)
    print(json.dumps(report.to_dict(), indent=2, ensure_ascii=False) if args.json
          else report.render())
    return EXIT_OK if validation.ok else EXIT_FAIL


def cmd_readiness(args: argparse.Namespace) -> int:
    report = evaluate(args.records, args.data_root)
    if args.out:
        written = write_report(args.out, report)
        print(f"written: {written}")
    print(report.to_json() if args.json else report.render())
    return EXIT_OK


def cmd_convert(args: argparse.Namespace) -> int:
    src, dst = Path(args.src), Path(args.dst)
    s, d = src.suffix.lower(), dst.suffix.lower()
    try:
        if s in {".jsonl", ".json"} and d == ".csv":
            n = jsonl_to_csv(src, dst)
            direction = "JSONL -> CSV"
        elif s == ".csv" and d == ".jsonl":
            n = csv_to_jsonl(src, dst)
            direction = "CSV -> JSONL"
        else:
            print(f"error: cannot convert {s or '?'} to {d or '?'}; "
                  "supported: .jsonl->.csv and .csv->.jsonl", file=sys.stderr)
            return EXIT_USAGE
    except (ConversionError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_USAGE
    print(f"{direction}: {n} record(s)\n  {src}\n  -> {dst}")
    return EXIT_OK


def cmd_rules(args: argparse.Namespace) -> int:
    print("Validation rules\n")
    print("  R* - specified in docs/SPLIT_METHODOLOGY.md §4 (project methodology)")
    print("  E* - engineering checks added in Milestone 2 (data hygiene, not domain claims)\n")
    for rule, title in sorted(
        RULE_TITLES.items(), key=lambda kv: (kv[0][0] != "R", int(kv[0][1:]))
    ):
        print(f"  {rule:<4} {title}")
    print()
    print("  L* - loader checks added in Milestone 5 (engineering, applied before training)")
    print()
    for rule, title in LOADER_RULES.items():
        print(f"  {rule:<4} {title}")
    return EXIT_OK


def cmd_stats(args: argparse.Namespace) -> int:
    try:
        stats = compute_statistics(args.records, args.data_root, manifest_path=args.manifest,
                                   verify_hashes=not args.no_verify)
    except (DatasetLoadError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_USAGE
    print(json.dumps(stats.to_dict(), indent=2, ensure_ascii=False) if args.json
          else stats.render())
    return EXIT_OK


def cmd_split(args: argparse.Namespace) -> int:
    """Validate, then split by artifact. Refuses rather than fabricate or mislead."""
    try:
        dataset = load_dataset(args.records, args.data_root)
    except DatasetLoadError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_USAGE

    print(f"Source            : {dataset.source}")
    print(f"Records           : {dataset.raw_record_count}")
    print(f"Accepted          : {len(dataset.records)}")
    print(f"Rejected          : {len(dataset.rejections)}")
    for rej in dataset.rejections[:20]:
        print(f"    {rej}")
    if len(dataset.rejections) > 20:
        print(f"    ... and {len(dataset.rejections) - 20} more")

    try:
        manifest = (adopt_existing_split(dataset, seed=args.seed) if args.adopt_existing
                    else make_split(dataset, strategy=args.strategy, seed=args.seed))
    except SplitError as exc:
        print()
        print("SPLIT REFUSED")
        for problem in exc.problems:
            print(f"  - {problem}")
        print()
        print("No split manifest was written.")
        return EXIT_FAIL

    print()
    print(f"Strategy          : {manifest.strategy}")
    print(f"Seed              : {manifest.seed}")
    print(f"Dataset fingerprint: {manifest.dataset_fingerprint}")
    print(f"Split digest      : {manifest.digest}")
    for part, entry in manifest.summary.items():
        print(f"  {part:<8} {entry['artifacts']:>5} artifacts {entry['images']:>6} images  "
              f"{entry['artifacts_by_class']}")
    for w in manifest.warnings:
        print(f"warning: {w}")
    if args.dry_run:
        print()
        print("(dry run - manifest not written)")
        return EXIT_OK
    out_dir = args.out_dir or SplitSettings.from_config().manifest_dir
    written = manifest.save(Path(out_dir) / manifest.default_filename())
    print()
    print(f"written: {written}")
    return EXIT_OK


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m src.dataset",
        description="Dataset ingestion, validation, conversion and audit.",
    )
    sub = p.add_subparsers(dest="command", required=True)

    v = sub.add_parser("validate", help="validate a file without writing anything")
    v.add_argument("path", type=Path)
    v.add_argument("--json", action="store_true")
    _add_validation_flags(v)
    v.set_defaults(func=cmd_validate)

    i = sub.add_parser("ingest", help="validate and, with --commit, append to the dataset")
    i.add_argument("path", type=Path)
    i.add_argument("--destination", type=Path, default=None)
    i.add_argument("--commit", action="store_true", help="write (default is a dry run)")
    i.add_argument("--no-merge", action="store_true",
                   help="validate the batch alone rather than with existing records")
    _add_validation_flags(i)
    i.set_defaults(func=cmd_ingest)

    a = sub.add_parser("audit", help="count what is in the dataset")
    a.add_argument("--records", type=Path, default=None)
    a.add_argument("--json", action="store_true")
    a.set_defaults(func=cmd_audit)

    r = sub.add_parser("readiness", help="report whether training may proceed")
    r.add_argument("--records", type=Path, default=None)
    r.add_argument("--data-root", type=Path, default=None)
    r.add_argument("--out", type=Path, default=None, help="also write the JSON report here")
    r.add_argument("--json", action="store_true")
    r.set_defaults(func=cmd_readiness)

    c = sub.add_parser("convert", help="CSV <-> JSONL")
    c.add_argument("src", type=Path)
    c.add_argument("dst", type=Path)
    c.set_defaults(func=cmd_convert)

    ru = sub.add_parser("rules", help="list the validation rules")
    ru.set_defaults(func=cmd_rules)

    st = sub.add_parser("stats", help="dataset statistics, splits and training readiness")
    st.add_argument("--records", type=Path, default=None)
    st.add_argument("--data-root", type=Path, default=None)
    st.add_argument("--manifest", type=Path, default=None)
    st.add_argument("--no-verify", action="store_true", help="skip SHA-256 recomputation")
    st.add_argument("--json", action="store_true")
    st.set_defaults(func=cmd_stats)

    sp = sub.add_parser("split", help="artifact-level, deterministic split manifest")
    sp.add_argument("--records", type=Path, default=None)
    sp.add_argument("--data-root", type=Path, default=None)
    sp.add_argument("--strategy", choices=["auto", "holdout", "grouped_kfold"], default="auto")
    sp.add_argument("--seed", type=int, default=None, help="default: split.seed in project.yaml")
    sp.add_argument("--adopt-existing", action="store_true",
                    help="build the manifest from split values already in the records")
    sp.add_argument("--out-dir", type=Path, default=None)
    sp.add_argument("--dry-run", action="store_true")
    sp.set_defaults(func=cmd_split)

    return p


def main(argv: list[str] | None = None) -> int:
    _force_utf8_output()
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
