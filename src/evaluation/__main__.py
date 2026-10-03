"""Command-line interface for evaluation.

    python -m src.evaluation evaluate --checkpoint PATH [--partition test|val]
    python -m src.evaluation evaluate --dataset synthetic --checkpoint PATH [--partition test|val]
    python -m src.evaluation reproducibility [--json]

Evaluation runs only on the canonical research dataset, and only when the readiness
gate passes. Otherwise it prints ``NO REAL DATA — EVALUATION BLOCKED`` and exits with
code 3. It never produces a score from fixtures or from an empty dataset.

``--dataset synthetic`` (Milestone 9) evaluates a SYNTHETIC checkpoint on the synthetic engineering
dataset instead, under the banner "SYNTHETIC DATA ONLY — NOT ARCHAEOLOGICAL PERFORMANCE". It does not
consult the research gate, refuses research checkpoints, and writes only under models/synthetic/.

Exit codes: 0 success, 2 usage error, 3 evaluation blocked.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from src.console import utf8_console

EXIT_OK, EXIT_USAGE, EXIT_BLOCKED = 0, 2, 3


def cmd_evaluate(args: argparse.Namespace) -> int:
    if args.dataset == "synthetic":
        return _evaluate_synthetic(args)
    from src.dataset.readiness import evaluate as readiness

    from .metrics import blocked_report

    report = readiness()
    if not report.training_ready:
        print(blocked_report(report.reason).render())
        return EXIT_BLOCKED

    if args.checkpoint is None:
        print("error: --checkpoint is required once evaluation is unblocked", file=sys.stderr)
        return EXIT_USAGE

    # Heavy imports only once the gate has passed.
    from src.dataset.classes import ClassSpec
    from src.dataset.loader import load_dataset
    from src.dataset.schema import ROOT
    from src.dataset.splits import SplitManifest, partition_records
    from src.training.augmentation import ImageGeometry, build_eval_transform
    from src.training.checkpoint import load_checkpoint
    from src.training.config import TrainingConfig
    from src.training.data import PotteryImageDataset, make_loader
    from src.training.engine import Trainer
    from src.training.model import build_model
    from src.training.runtime import select_device

    from .metrics import aggregate_by_artifact, evaluate_predictions

    spec = ClassSpec.from_config()
    cfg = TrainingConfig.load(args.config)
    ckpt = load_checkpoint(args.checkpoint, class_names=spec.trainable, expected_dataset_type="research")
    dataset = load_dataset()
    if ckpt["dataset_fingerprint"] != dataset.fingerprint:
        print("error: checkpoint was trained on a different dataset version", file=sys.stderr)
        return EXIT_USAGE
    manifest = SplitManifest.load(ROOT / report.split_manifest)  # type: ignore[operator]
    if manifest.strategy == "grouped_kfold":
        print("error: k-fold manifests are evaluated per fold during training", file=sys.stderr)
        return EXIT_USAGE
    records = partition_records(manifest, dataset)[args.partition]
    cfg.model.pretrained = False
    model = build_model(cfg.model)
    model.load_state_dict(ckpt["state_dict"])
    device = select_device(cfg.runtime.device, mixed_precision=cfg.runtime.mixed_precision)
    trainer = Trainer(model, cfg, spec.trainable, device)
    ds = PotteryImageDataset(records, spec, build_eval_transform(ImageGeometry.from_project()))
    preds = trainer.predict(make_loader(ds, train=False, batch_size=cfg.data.batch_size,
                                        seed=cfg.runtime.seed))
    aids = [records[i].artifact_id for i in preds.indices]
    _, a_true, a_prob = aggregate_by_artifact(aids, preds.y_true, preds.probabilities)
    result = evaluate_predictions(a_true, list(a_prob.argmax(axis=1)), spec.trainable,
                                  y_prob=a_prob, unit="artifact")
    print(json.dumps(result.to_dict(), indent=2) if args.json else result.render())
    return EXIT_OK


def _evaluate_synthetic(args: argparse.Namespace) -> int:
    from src.synthetic.dataset import SyntheticDatasetError
    from src.synthetic.evaluate import evaluate_checkpoint, render_evaluation
    from src.training.checkpoint import CheckpointError

    if args.checkpoint is None:
        print("error: --checkpoint is required (a SYNTHETIC checkpoint under models/synthetic/)", file=sys.stderr)
        return EXIT_USAGE
    try:
        rep = evaluate_checkpoint(args.checkpoint, args.partition)
    except (CheckpointError, SyntheticDatasetError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_USAGE
    print(json.dumps(rep, indent=2, ensure_ascii=False) if args.json else render_evaluation(rep))
    return EXIT_OK


def cmd_reproducibility(args: argparse.Namespace) -> int:
    from .reproducibility import render_report, reproducibility_report

    rep = reproducibility_report()
    print(json.dumps(rep, indent=2, ensure_ascii=False) if args.json else render_report(rep))
    return EXIT_OK


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="python -m src.evaluation",
                                description="Evaluation (gated on real data).")
    sub = p.add_subparsers(dest="command", required=True)
    e = sub.add_parser("evaluate", help="evaluate a checkpoint on a held-out partition")
    e.add_argument("--dataset", choices=["research", "synthetic"], default="research",
                   help="research (default; gated) or synthetic (engineering validation; never archaeological)")
    e.add_argument("--checkpoint", type=Path, required=False, default=None)
    e.add_argument("--config", type=Path, default=None)
    e.add_argument("--partition", choices=["test", "val"], default="test")
    e.add_argument("--json", action="store_true")
    e.set_defaults(func=cmd_evaluate)
    r = sub.add_parser("reproducibility", help="code, environment, data, config and store fingerprints")
    r.add_argument("--json", action="store_true")
    r.set_defaults(func=cmd_reproducibility)
    return p


def main(argv: list[str] | None = None) -> int:
    utf8_console()
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
