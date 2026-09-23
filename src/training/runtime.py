"""Device selection, seeding and provenance for reproducible runs."""

from __future__ import annotations

import os
import platform
import random
import subprocess
from dataclasses import asdict, dataclass
from typing import Any

import numpy as np
import torch

from src.dataset.schema import ROOT


class DeviceError(RuntimeError):
    """The requested device is not available."""


@dataclass(frozen=True)
class DeviceInfo:
    device: str                 # "cuda" or "cpu"
    requested: str
    cuda_available: bool
    gpu_name: str | None
    gpu_memory_gib: float | None
    amp_enabled: bool
    fallback_reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def select_device(requested: str = "auto", *, mixed_precision: bool = True,
                  cuda_available: bool | None = None) -> DeviceInfo:
    """Resolve ``auto``/``cuda``/``cpu`` to a device.

    ``auto`` falls back to CPU (recording why). An explicit ``cuda`` request on a
    machine without CUDA is an error, not a silent fallback. Mixed precision is enabled
    only on CUDA. ``cuda_available`` can be injected so the fallback path is testable on
    a GPU machine.
    """
    if requested not in ("auto", "cuda", "cpu"):
        raise DeviceError(f"unknown device {requested!r}; use auto, cuda or cpu")
    has_cuda = torch.cuda.is_available() if cuda_available is None else cuda_available
    name = mem = None
    if has_cuda and torch.cuda.is_available():
        props = torch.cuda.get_device_properties(0)
        name, mem = props.name, round(props.total_memory / 2**30, 2)

    if requested == "cpu":
        return DeviceInfo("cpu", requested, has_cuda, name, mem, False)
    if requested == "cuda" and not has_cuda:
        raise DeviceError("device=cuda requested but CUDA is not available")
    if has_cuda:
        return DeviceInfo("cuda", requested, True, name, mem, bool(mixed_precision))
    return DeviceInfo("cpu", requested, False, None, None, False,
                      fallback_reason="CUDA not available; using CPU")


def seed_everything(seed: int, *, deterministic: bool = True) -> dict[str, Any]:
    """Seed Python, NumPy and torch (CPU and CUDA); optionally request determinism.

    Full bitwise determinism on GPU is not guaranteed for every kernel. Deterministic
    algorithms are requested with ``warn_only=True`` so an op without a deterministic
    implementation warns instead of aborting; the returned dict records what was set.
    """
    random.seed(seed)
    np.random.seed(seed % 2**32)
    torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)
    state = {"seed": seed, "deterministic": deterministic}
    if deterministic:
        os.environ.setdefault("CUBLAS_WORKSPACE_CONFIG", ":4096:8")
        torch.backends.cudnn.deterministic = True
        torch.backends.cudnn.benchmark = False
        torch.use_deterministic_algorithms(True, warn_only=True)
        state["cublas_workspace_config"] = os.environ["CUBLAS_WORKSPACE_CONFIG"]
    return state


def git_commit() -> dict[str, Any]:
    """Current commit and whether the working tree has uncommitted changes."""
    def run(*args: str) -> str | None:
        try:
            out = subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True,
                                 timeout=10, check=True)
            return out.stdout.strip()
        except (OSError, subprocess.SubprocessError):
            return None

    commit = run("rev-parse", "HEAD")
    status = run("status", "--porcelain")
    return {"commit": commit or "unknown",
            "dirty": bool(status) if status is not None else None}


def environment() -> dict[str, Any]:
    import torchvision

    return {
        "python": platform.python_version(),
        "platform": platform.platform(),
        "torch": torch.__version__,
        "torchvision": torchvision.__version__,
        "cuda_runtime": torch.version.cuda,
        "cudnn": torch.backends.cudnn.version() if torch.backends.cudnn.is_available() else None,
    }


__all__ = ["DeviceError", "DeviceInfo", "environment", "git_commit", "seed_everything",
           "select_device"]
