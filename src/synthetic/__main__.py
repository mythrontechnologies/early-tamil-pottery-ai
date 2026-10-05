"""Synthetic engineering dataset CLI.   SYNTHETIC — NOT ARCHAEOLOGICAL EVIDENCE

    python -m src.synthetic generate [--force] [--config PATH]   # data/synthetic/ (deterministic)
    python -m src.synthetic split                                 # artifact-level hold-out split
    python -m src.synthetic stats  [--json]
    python -m src.synthetic verify [--regenerate N] [--json]
    python -m src.synthetic robustness --checkpoint PATH [--json]
    python -m src.synthetic ocr-benchmark [--json]
    python -m src.synthetic calibrate [--checkpoint PATH]          # temperature scaling on the VAL split
    python -m src.synthetic train-vision                           # region detector + OCR models (bundle)
    python -m src.synthetic demo [--image-id ID] [--json]          # the complete synthetic pipeline, once

Training and evaluation use the project's existing commands with an explicit dataset switch:

    python -m src.training train --dataset synthetic
    python -m src.evaluation evaluate --dataset synthetic --checkpoint <best.pt>

Nothing here reads or writes the research dataset, the annotation store, the knowledge base or
the readiness gate. Exit codes: 0 success, 1 verification failed, 2 usage/configuration error.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from src.console import utf8_console

from . import MARKER, PURPOSE


def _cfg(args: argparse.Namespace):
    from .config import SyntheticDatasetConfig

    return SyntheticDatasetConfig.load(args.config)


def cmd_generate(args: argparse.Namespace) -> int:
    from .dataset import generate_dataset, make_synthetic_split

    cfg = _cfg(args)
    print(f"{MARKER}\nGenerating {cfg.artifacts_per_class * 4} synthetic artifacts (generator {cfg.generator_version}, "
          f"seed {cfg.seed}) ...", flush=True)

    def progress(done: int, total: int) -> None:
        if done % 50 == 0 or done == total:
            print(f"  {done}/{total} artifacts", flush=True)

    res = generate_dataset(cfg, args.root, force=args.force, progress=progress)
    print(f"Wrote {res.images} images of {res.artifacts} artifacts ({res.bytes_written / 2**20:.1f} MiB) to "
          f"{res.root} in {res.seconds:.0f} s")
    if not args.no_split:
        manifest, path = make_synthetic_split(cfg, args.root)
        print(f"Split {manifest.strategy} {manifest.digest[:16]} -> {path}")
    print(PURPOSE)
    return 0


def cmd_split(args: argparse.Namespace) -> int:
    from .dataset import make_synthetic_split

    manifest, path = make_synthetic_split(_cfg(args), args.root)
    for part in manifest.partitions:
        s = manifest.summary[part]
        print(f"  {part:<6} {s['artifacts']:>5} artifacts {s['images']:>5} images  {s['artifacts_by_class']}")
    print(f"{MARKER}\nsplit {manifest.strategy} digest {manifest.digest} -> {path}")
    return 0


def cmd_stats(args: argparse.Namespace) -> int:
    from .audit import dataset_stats, render_stats

    s = dataset_stats(args.root)
    print(json.dumps(s, indent=2, ensure_ascii=False) if args.json else render_stats(s))
    return 0


def cmd_verify(args: argparse.Namespace) -> int:
    from .audit import verify_dataset

    rep = verify_dataset(args.root, regenerate=args.regenerate, config=_cfg(args))
    print(json.dumps(rep.to_dict(), indent=2, ensure_ascii=False) if args.json else rep.render())
    return 0 if rep.ok else 1


def cmd_robustness(args: argparse.Namespace) -> int:
    from .robustness import render_robustness, run_robustness

    rep = run_robustness(args.checkpoint, partition=args.partition, root=args.root, device=args.device)
    print(json.dumps(rep, indent=2, ensure_ascii=False) if args.json else render_robustness(rep))
    return 0


def cmd_ocr(args: argparse.Namespace) -> int:
    from .ocr_benchmark import render_benchmark, run_benchmark

    rep = run_benchmark(root=args.root, epochs=args.epochs, device=args.device, seed=args.seed)
    print(json.dumps(rep, indent=2, ensure_ascii=False) if args.json else render_benchmark(rep))
    return 0


def cmd_calibrate(args: argparse.Namespace) -> int:
    from .calibration import calibrate_checkpoint
    from .inference import latest_synthetic_checkpoint

    ckpt = args.checkpoint or latest_synthetic_checkpoint()
    if ckpt is None:
        print("error: no synthetic checkpoint; run `python -m src.training train --dataset synthetic`", file=sys.stderr)
        return 2
    cal = calibrate_checkpoint(ckpt, root=args.root, device=args.device)
    print(f"{MARKER}\ntemperature {cal.temperature} fitted on the VALIDATION split of {ckpt}")
    for part in ("val", "test"):
        b, a = cal.metrics[part]["before"], cal.metrics[part]["after"]
        print(f"  {part:<4} ECE {b['ece']:.4f} -> {a['ece']:.4f}   Brier {b['brier']:.4f} -> {a['brier']:.4f}   "
              f"mean confidence {b['mean_confidence']:.3f} -> {a['mean_confidence']:.3f} (accuracy {a['accuracy']:.3f})")
    print(f"calibration: {cal.metrics.get('path')}")
    return 0


def cmd_train_vision(args: argparse.Namespace) -> int:
    from .vision import train_vision

    out = train_vision(root=args.root, epochs_detector=args.epochs_detector, epochs_glyphs=args.epochs_glyphs,
                       epochs_centers=args.epochs_centers, seed=args.seed, device=args.device)
    print(f"{MARKER}\nsynthetic vision bundle: {out}")
    return 0


def cmd_demo(args: argparse.Namespace) -> int:
    from .demo import render_demo, run_demo

    rep = run_demo(image_id=args.image_id, root=args.root, device=args.device, record=not args.no_record)
    print(json.dumps(rep, indent=2, ensure_ascii=False) if args.json else render_demo(rep))
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="python -m src.synthetic",
                                description=f"Synthetic engineering dataset ({MARKER}).")
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--config", type=Path, default=None, help="generator config (default configs/synthetic_dataset.yaml)")
    common.add_argument("--root", type=Path, default=None, help="dataset root (default data/synthetic)")
    sub = p.add_subparsers(dest="command", required=True)

    g = sub.add_parser("generate", parents=[common], help="generate the synthetic dataset (deterministic)")
    g.add_argument("--force", action="store_true", help="replace an existing synthetic dataset")
    g.add_argument("--no-split", action="store_true", help="do not write the split manifest")
    g.set_defaults(func=cmd_generate)
    s = sub.add_parser("split", parents=[common], help="artifact-level hold-out split")
    s.set_defaults(func=cmd_split)
    st = sub.add_parser("stats", parents=[common], help="dataset statistics")
    st.add_argument("--json", action="store_true")
    st.set_defaults(func=cmd_stats)
    v = sub.add_parser("verify", parents=[common], help="integrity, reproducibility and separation checks")
    v.add_argument("--regenerate", type=int, default=8, help="images to re-render and compare (0 = skip)")
    v.add_argument("--json", action="store_true")
    v.set_defaults(func=cmd_verify)
    r = sub.add_parser("robustness", parents=[common], help="perturbation suite on a synthetic checkpoint")
    r.add_argument("--checkpoint", type=Path, required=True)
    r.add_argument("--partition", choices=["test", "val"], default="test")
    r.add_argument("--device", default="auto")
    r.add_argument("--json", action="store_true")
    r.set_defaults(func=cmd_robustness)
    o = sub.add_parser("ocr-benchmark", parents=[common], help="synthetic glyph recognition benchmark")
    o.add_argument("--epochs", type=int, default=20)
    o.add_argument("--seed", type=int, default=20261003)
    o.add_argument("--device", default="auto")
    o.add_argument("--json", action="store_true")
    o.set_defaults(func=cmd_ocr)
    c = sub.add_parser("calibrate", parents=[common], help="temperature-scale a synthetic checkpoint on the VAL split")
    c.add_argument("--checkpoint", type=Path, default=None, help="default: the newest synthetic best.pt")
    c.add_argument("--device", default="auto")
    c.set_defaults(func=cmd_calibrate)
    tv = sub.add_parser("train-vision", parents=[common], help="train the region detector and OCR models (bundle)")
    tv.add_argument("--epochs-detector", type=int, default=24)
    tv.add_argument("--epochs-glyphs", type=int, default=20)
    tv.add_argument("--epochs-centers", type=int, default=40)
    tv.add_argument("--seed", type=int, default=20261003)
    tv.add_argument("--device", default="auto")
    tv.set_defaults(func=cmd_train_vision)
    dm = sub.add_parser("demo", parents=[common], help="run the complete synthetic pipeline on one held-out image")
    dm.add_argument("--image-id", default=None, help="a synthetic test-split image id (default: a fixed demo image)")
    dm.add_argument("--device", default="auto")
    dm.add_argument("--no-record", action="store_true", help="do not write a run record")
    dm.add_argument("--json", action="store_true")
    dm.set_defaults(func=cmd_demo)
    return p


def main(argv: list[str] | None = None) -> int:
    utf8_console()
    args = build_parser().parse_args(argv)
    from src.training.checkpoint import CheckpointError

    from . import SyntheticSeparationError
    from .calibration import CalibrationError
    from .config import SyntheticConfigError
    from .dataset import SyntheticDatasetError
    from .vision import VisionModelError

    try:
        return args.func(args)
    except (SyntheticConfigError, SyntheticDatasetError, SyntheticSeparationError, CheckpointError, CalibrationError,
            VisionModelError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
