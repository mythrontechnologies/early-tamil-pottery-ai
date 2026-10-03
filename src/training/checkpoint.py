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
    model_fingerprint    SHA-256 over the weights (key, dtype, shape, bytes); re-checked on load
    trainer_state        optional: early-stopping best/bad_epochs and backbone state, for resume
    dataset_type         "research" or "synthetic" (Milestone 9; absent in older files = research)
    synthetic            synthetic checkpoints only: the SYNTHETIC ONLY marker, generator version,
                         synthetic fingerprint, seed, environment and the label/slot mapping

:func:`load_checkpoint` refuses a file whose structure or class list does not match, or whose
weights no longer match their fingerprint. Given ``expected_dataset_type`` it also refuses a
checkpoint of the other kind, so a synthetic model can never be loaded where a model of the
archaeological classes is expected. A synthetic checkpoint must carry the marker and synthetic
class names, and can only be saved outside the research model directories.

**Safe loading.** Checkpoints hold only tensors and plain Python values (the metadata is
converted on save), and are read with ``torch.load(..., weights_only=True)``: a checkpoint
cannot execute code when it is loaded. A file that needs arbitrary unpickling is refused.
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import torch
from torch import nn

from src.synthetic import (
    MARKER,
    SYNTHETIC_LABELS,
    SYNTHETIC_MODELS_ROOT,
    SyntheticSeparationError,
    assert_synthetic_model_destination,
)

CHECKPOINT_FORMAT = "1.0.0"
DATASET_TYPES = ("research", "synthetic")
REQUIRED_KEYS = (
    "format_version", "model_name", "num_classes", "class_names", "state_dict", "epoch",
    "metrics", "monitor", "config", "dataset_fingerprint", "split_digest", "git",
    "created_utc",
)


class CheckpointError(RuntimeError):
    """The checkpoint is malformed, incompatible, unsafe to load, or tampered with."""


def _plain(value: Any, where: str = "checkpoint") -> Any:
    """Metadata -> tensors and plain Python only (what ``weights_only`` loading accepts)."""
    if isinstance(value, np.generic):          # before the float check: np.float64 IS a float subclass
        return value.item()
    if value is None or isinstance(value, (bool, torch.Tensor)):
        return value
    # str/int/float SUBCLASSES (e.g. torch.__version__ is a TorchVersion) would pickle as their own
    # class, which weights_only loading refuses; store the plain built-in value instead.
    if isinstance(value, str):
        return str(value)
    if isinstance(value, int):
        return int(value)
    if isinstance(value, float):
        return float(value)
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, Path):
        return value.as_posix()
    if isinstance(value, Mapping):
        return {k if isinstance(k, (str, int)) else str(k): _plain(v, f"{where}.{k}") for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return type(value)(_plain(v, f"{where}[]") for v in value)
    raise CheckpointError(f"{where}: {type(value).__name__} cannot be stored safely in a checkpoint")


def model_fingerprint(state_dict: Mapping[str, torch.Tensor]) -> str:
    """Deterministic SHA-256 over the weights: key, dtype, shape and raw bytes, in key order."""
    h = hashlib.sha256()
    for key in sorted(state_dict):
        t = state_dict[key].detach().cpu().contiguous()
        h.update(key.encode("utf-8"))
        h.update(str(t.dtype).encode())
        h.update(str(tuple(t.shape)).encode())
        h.update(t.reshape(-1).view(torch.uint8).numpy().tobytes() if t.numel() else b"")
    return h.hexdigest()


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
    trainer_state: dict[str, Any] | None = None,
    dataset_type: str = "research",
    synthetic: dict[str, Any] | None = None,
) -> dict[str, Any]:
    state = {k: v.detach().cpu() for k, v in model.state_dict().items()}
    extra = {"synthetic": _plain(synthetic, "synthetic")} if synthetic is not None else {}
    return extra | {
        "format_version": CHECKPOINT_FORMAT,
        "model_name": model_name,
        "num_classes": len(class_names),
        "class_names": list(class_names),
        "state_dict": state,
        "model_fingerprint": model_fingerprint(state),
        "optimizer_state": _plain(optimizer.state_dict(), "optimizer_state") if optimizer is not None else None,
        "scheduler_state": _plain(scheduler.state_dict(), "scheduler_state") if scheduler is not None else None,
        "epoch": int(epoch),
        "metrics": _plain(metrics, "metrics"),
        "monitor": _plain(monitor, "monitor"),
        "config": _plain(config, "config"),
        "dataset_fingerprint": str(dataset_fingerprint),
        "split_digest": str(split_digest),
        "git": _plain(git, "git"),
        "created_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "trainer_state": _plain(trainer_state or {}, "trainer_state"),
        "dataset_type": str(dataset_type),
    }


def dataset_type_of(ckpt: dict[str, Any]) -> str:
    """``research`` or ``synthetic``. Checkpoints written before Milestone 9 have no field and were research."""
    return str(ckpt.get("dataset_type", "research"))


def check_checkpoint(ckpt: dict[str, Any], *, class_names: Sequence[str] | None = None,
                     expected_dataset_type: str | None = None) -> None:
    missing = [k for k in REQUIRED_KEYS if k not in ckpt]
    if missing:
        raise CheckpointError(f"checkpoint is missing keys: {missing}")
    kind = dataset_type_of(ckpt)
    if expected_dataset_type is not None and kind != expected_dataset_type:
        raise CheckpointError(
            f"this is a {kind.upper()} checkpoint but a {expected_dataset_type} model is required"
            + (" (SYNTHETIC ONLY: it was trained on generated images and is not a model of the archaeological "
               "classes)" if kind == "synthetic" else ""))
    if ckpt["format_version"].split(".")[0] != CHECKPOINT_FORMAT.split(".")[0]:
        raise CheckpointError(f"incompatible checkpoint format {ckpt['format_version']}")
    if ckpt["num_classes"] != len(ckpt["class_names"]):
        raise CheckpointError("num_classes does not match class_names")
    if class_names is not None and list(class_names) != list(ckpt["class_names"]):
        raise CheckpointError(
            f"class list mismatch: checkpoint {ckpt['class_names']} vs expected {list(class_names)}")
    fp = ckpt.get("model_fingerprint")
    if fp is not None and fp != model_fingerprint(ckpt["state_dict"]):
        raise CheckpointError("model weights do not match the checkpoint's model_fingerprint (modified file?)")
    if kind not in DATASET_TYPES:
        raise CheckpointError(f"unknown dataset_type {kind!r}; expected one of {DATASET_TYPES}")
    synthetic_names = [c for c in ckpt["class_names"] if c in SYNTHETIC_LABELS]
    if kind == "synthetic":
        if (ckpt.get("synthetic") or {}).get("marker") != MARKER:
            raise CheckpointError("a synthetic checkpoint must carry the SYNTHETIC ONLY marker")
        if len(synthetic_names) != len(ckpt["class_names"]):
            raise CheckpointError("a synthetic checkpoint must use the synthetic class names only")
    elif synthetic_names:
        raise CheckpointError(f"synthetic class names {synthetic_names} in a checkpoint not marked synthetic")


def save_checkpoint(ckpt: dict[str, Any], path: Path | str) -> Path:
    check_checkpoint(ckpt)
    path = Path(path)
    try:
        if dataset_type_of(ckpt) == "synthetic":
            assert_synthetic_model_destination(path)
        elif _inside(path, SYNTHETIC_MODELS_ROOT):
            raise SyntheticSeparationError(f"refusing to write a research checkpoint into {SYNTHETIC_MODELS_ROOT}")
    except SyntheticSeparationError as exc:
        raise CheckpointError(str(exc)) from exc
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    torch.save(ckpt, tmp)
    tmp.replace(path)
    return path


def _inside(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
    except ValueError:
        return False
    return True


def load_checkpoint(path: Path | str, *, class_names: Sequence[str] | None = None,
                    map_location: str = "cpu", expected_dataset_type: str | None = None) -> dict[str, Any]:
    try:
        ckpt = torch.load(Path(path), map_location=map_location, weights_only=True)
    except Exception as exc:
        raise CheckpointError(f"{path} could not be loaded safely (weights_only): {exc}") from exc
    if not isinstance(ckpt, dict):
        raise CheckpointError(f"{path} does not contain a checkpoint dict")
    check_checkpoint(ckpt, class_names=class_names, expected_dataset_type=expected_dataset_type)
    return ckpt


__all__ = [
    "CHECKPOINT_FORMAT",
    "DATASET_TYPES",
    "REQUIRED_KEYS",
    "CheckpointError",
    "build_checkpoint",
    "check_checkpoint",
    "dataset_type_of",
    "load_checkpoint",
    "model_fingerprint",
    "save_checkpoint",
]
