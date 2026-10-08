"""Command-line interface for evaluation.

    python -m src.evaluation evaluate --checkpoint PATH [--partition test|val] [--robustness]
    python -m src.evaluation detection --predictions PRED.jsonl [--json]   # vs expert-promoted regions
    python -m src.evaluation ocr --predictions PRED.jsonl [--json]         # vs expert-promoted readings
    python -m src.evaluation evaluate --dataset synthetic --checkpoint PATH [--partition test|val]
    python -m src.evaluation reproducibility [--json]
    python -m src.evaluation synthetic [--partition test|val] [--skip-robustness] [--json]

Evaluation runs only on the canonical research dataset, and only when the readiness
gate passes. Otherwise it prints ``NO REAL DATA — EVALUATION BLOCKED`` and exits with
code 3. It never produces a score from fixtures or from an empty dataset.

``--dataset synthetic`` (Milestone 9) evaluates a SYNTHETIC checkpoint on the synthetic engineering
dataset instead, under the banner "SYNTHETIC DATA ONLY — NOT ARCHAEOLOGICAL PERFORMANCE". It does not
consult the research gate, refuses research checkpoints, and writes only under models/synthetic/.

``detection`` and ``ocr`` (Milestone 11) score ANY detector / transcriber whose output is a JSONL
file (``{"image_id": ..., "regions": [[x, y, w, h], ...]}`` or ``{"image_id": ..., "reading": ...}``)
against the ground truth that experts promoted into the records. With no promoted regions or
readings they are BLOCKED (exit 3), never scored against nothing.

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
    from .tasks import error_analysis, robustness_report

    a_ids = sorted(set(aids))
    out = result.to_dict() | {"evidence_tier": "real_expert_labelled",
                              "error_analysis": error_analysis(a_ids, a_true, a_prob, spec.trainable)}
    if args.robustness:
        import torch

        from src.training.data import load_rgb

        tf = build_eval_transform(ImageGeometry.from_project())

        def predict(images):
            model.eval()
            with torch.no_grad():
                x = torch.stack([tf(im) for im in images]).to(device.device if hasattr(device, "device") else device)
                return torch.softmax(model(x), dim=1).cpu().numpy()

        imgs = [load_rgb(r.image_path) for r in records]
        out["robustness"] = robustness_report(predict, imgs, [spec.trainable.index(r.script_type) for r in records],
                                              ids=[r.image_id for r in records])
    if args.json:
        print(json.dumps(out, indent=2, default=str))
    else:
        print(result.render())
        ea = out["error_analysis"]
        print(f"Errors: {len(ea['errors'])} artifact(s); high-confidence errors: {ea['high_confidence_errors']}")
        for row in ea["accuracy_by_confidence"]:
            print(f"  confidence {row['confidence']}: n={row['n']} accuracy={row['accuracy']}")
        if "robustness" in out:
            for name, row in out["robustness"]["perturbations"].items():
                print(f"  robustness {name:<18} {row['family']:<12} accuracy={row['accuracy']} drop={row['drop_from_clean']}")
    return EXIT_OK


def _promoted_truth(kind: str) -> tuple[dict, list[str]]:
    """Expert-promoted ground truth from the research records: regions or readings per image."""
    from src.dataset.convert import read_jsonl
    from src.dataset.schema import RESEARCH_RECORDS_PATH

    recs = [r for r in (read_jsonl(RESEARCH_RECORDS_PATH) if RESEARCH_RECORDS_PATH.exists() else [])
            if r.get("label_source") == "expert_annotation"]
    if kind == "detection":
        truth = {r["image_id"]: [(g["x"], g["y"], g["w"], g["h"]) for g in r.get("inscription_regions", [])
                                 if g.get("region_label") in ("inscription", "graffiti", "possible_inscription")]
                 for r in recs if r.get("inscription_present") in ("yes", "no")}
        return truth, [r["image_id"] for r in recs]
    truth = {r["image_id"]: r["transcription"] for r in recs
             if r.get("transcription") not in (None, "not_available", "not_applicable")
             and r.get("reading_status") != "disputed"}
    return truth, [r["image_id"] for r in recs]


def _read_predictions(path: Path) -> list[dict]:
    rows = []
    for n, line in enumerate(Path(path).read_text(encoding="utf-8").splitlines(), 1):
        if line.strip():
            row = json.loads(line)
            if not isinstance(row, dict) or "image_id" not in row:
                raise ValueError(f"line {n}: each prediction needs an image_id")
            rows.append(row)
    return rows


def cmd_task(args: argparse.Namespace) -> int:
    from .metrics import BLOCKED_MESSAGE
    from .tasks import detection_report, ocr_report

    truth, promoted = _promoted_truth(args.command)
    if not truth:
        what = "regions" if args.command == "detection" else "readings"
        print(BLOCKED_MESSAGE)
        model = "region detector" if args.command == "detection" else "transcriber"
        print(f"No expert-promoted {what} exist ({len(promoted)} promoted record(s)). A {model} is scored only "
              "against expert ground truth.")
        return EXIT_BLOCKED
    try:
        preds = _read_predictions(args.predictions)
    except (OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_USAGE
    if args.command == "detection":
        pred = {p["image_id"]: [tuple(b) for b in p.get("regions", [])] for p in preds}
        rep = detection_report(truth, pred)
    else:
        hyp = {p["image_id"]: p.get("reading") for p in preds}
        rep = ocr_report([(ref, hyp.get(iid)) for iid, ref in sorted(truth.items())])
    print(json.dumps(rep, indent=2, default=str))
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


def cmd_synthetic(args: argparse.Namespace) -> int:
    """The integrated SYNTHETIC ENGINEERING BENCHMARK (classifier, detector, OCR, calibration, robustness)."""
    from src.synthetic.benchmark import render_benchmark, run_synthetic_benchmark
    from src.synthetic.dataset import SyntheticDatasetError
    from src.synthetic.pipeline import SyntheticPipelineError
    from src.training.checkpoint import CheckpointError

    def log(msg: str) -> None:
        print(msg, file=sys.stderr, flush=True)

    try:
        rep = run_synthetic_benchmark(partition=args.partition, robustness=not args.skip_robustness, log=log)
    except (CheckpointError, SyntheticDatasetError, SyntheticPipelineError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_USAGE
    print(json.dumps(rep, indent=2, ensure_ascii=False) if args.json else render_benchmark(rep))
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
    e.add_argument("--robustness", action="store_true",
                   help="also re-score under photographic perturbations (lighting, blur, noise, scale, crop, occlusion)")
    e.set_defaults(func=cmd_evaluate)
    for name, what in (("detection", "region detection vs expert-promoted regions"),
                       ("ocr", "transcription vs expert-promoted readings")):
        t = sub.add_parser(name, help=f"{what} (BLOCKED until experts promote ground truth)")
        t.add_argument("--predictions", type=Path, required=True, help="JSONL, one prediction per image")
        t.set_defaults(func=cmd_task)
    y = sub.add_parser("synthetic", help="integrated SYNTHETIC ENGINEERING BENCHMARK (never archaeological performance)")
    y.add_argument("--partition", choices=["test", "val"], default="test")
    y.add_argument("--skip-robustness", action="store_true")
    y.add_argument("--json", action="store_true")
    y.set_defaults(func=cmd_synthetic)
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
