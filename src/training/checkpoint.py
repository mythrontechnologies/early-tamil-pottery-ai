"""Checkpoint format.

A checkpoint is a dict with a fixed set of keys. Everything needed to know *what* the
weights are, and *what data they were trained on*, travels with the weights:

    format_version       "1.0.0"
    model_name           e.g. "resnet18"
    num_classes          int
    class_names          list[str], index order
    state_dict           model weights
    optimizer_state      optional
    scheduler_state      optional
    epoch                int (0-based, last completed)
    metrics              validation metrics at this epoch
    monitor              {"name": ..., "value": ..., "mode": ...}
    config               full training config (dict)
    dataset_fingerprint  src.dataset.fingerprint.dataset_fingerprint
    split_digest         SplitManifest.digest
    git                  {"commit": ..., "dirty": ...}
    created_utc          ISO timestamp

:func:`load_checkpoint` refuses a file whose structure or class list does not match.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import torch
from torch import nn

CHECKPOINT_FORMAT = "1.0.0"
REQUIRED_KEYS = (
    "format_version", "model_name", "num_classes", "class_names", "state_dict", "epoch",
    "metrics", "monitor", "config", "dataset_fingerprint", "split_digest", "git",
    "created_utc",
)


class CheckpointError(RuntimeError):
    """The checkpoint is malformed or incompatible."""


def build_checkpoint(
    model: nn.Module,
    *,
    model_name: str,
    class_names: Sequence[str],
    epoch: int,
    metrics: dict[str, Any],
    monitor: dict[str, Any],
    config: dict[str, Any],
    dataset_fingerprint: str,
    split_digest: str,
    git: dict[str, Any],
    optimizer: torch.optim.Optimizer | None = None,
    scheduler: Any | None = None,
) -> dict[str, Any]:
    return {
        "format_version": CHECKPOINT_FORMAT,
        "model_name": model_name,
        "num_classes": len(class_names),
        "class_names": list(class_names),
        "state_dict": {k: v.detach().cpu() for k, v in model.state_dict().items()},
        "optimizer_state": optimizer.state_dict() if optimizer is not None else None,
        "scheduler_state": scheduler.state_dict() if scheduler is not None else None,
        "epoch": int(epoch),
        "metrics": metrics,
        "monitor": monitor,
        "config": config,
        "dataset_fingerprint": dataset_fingerprint,
        "split_digest": split_digest,
        "git": git,
        "created_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }


def check_checkpoint(ckpt: dict[str, Any], *, class_names: Sequence[str] | None = None) -> None:
    missing = [k for k in REQUIRED_KEYS if k not in ckpt]
    if missing:
        raise CheckpointError(f"checkpoint is missing keys: {missing}")
    if ckpt["format_version"].split(".")[0] != CHECKPOINT_FORMAT.split(".")[0]:
        raise CheckpointError(f"incompatible checkpoint format {ckpt['format_version']}")
    if ckpt["num_classes"] != len(ckpt["class_names"]):
        raise CheckpointError("num_classes does not match class_names")
    if class_names is not None and list(class_names) != list(ckpt["class_names"]):
        raise CheckpointError(
            f"class list mismatch: checkpoint {ckpt['class_names']} vs expected {list(class_names)}")


def save_checkpoint(ckpt: dict[str, Any], path: Path | str) -> Path:
    check_checkpoint(ckpt)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    torch.save(ckpt, tmp)
    tmp.replace(path)
    return path


def load_checkpoint(path: Path | str, *, class_names: Sequence[str] | None = None,
                    map_location: str = "cpu") -> dict[str, Any]:
    ckpt = torch.load(Path(path), map_location=map_location, weights_only=False)
    if not isinstance(ckpt, dict):
        raise CheckpointError(f"{path} does not contain a checkpoint dict")
    check_checkpoint(ckpt, class_names=class_names)
    return ckpt


__all__ = [
    "CHECKPOINT_FORMAT",
    "REQUIRED_KEYS",
    "CheckpointError",
    "build_checkpoint",
    "check_checkpoint",
    "load_checkpoint",
    "save_checkpoint",
]
