"""Training-pipeline smoke tests on SYNTHETIC noise tensors (final engineering phase).

They prove the machinery (CUDA + mixed precision, deterministic mode, early stopping,
checkpoint -> classifier) works. They train on noise, so every number they produce is
meaningless by construction, and training on real research data stays behind the gate.
"""

from __future__ import annotations

import pytest
import torch
from test_training_framework import FOUR, _cfg, _NoiseDataset, _trainer
from torch.utils.data import DataLoader

from src.training.checkpoint import load_checkpoint, model_fingerprint
from src.training.engine import Trainer
from src.training.model import build_model
from src.training.runtime import seed_everything, select_device


def _loaders(n=16):
    return (DataLoader(_NoiseDataset(n, 4), batch_size=8),
            DataLoader(_NoiseDataset(8, 4, seed=1), batch_size=8))


@pytest.mark.skipif(not torch.cuda.is_available(), reason="no CUDA device")
def test_cuda_mixed_precision_smoke(tmp_path):
    cfg = _cfg(model={"pretrained": False}, optimization={"epochs": 1},
               runtime={"device": "cuda", "mixed_precision": True})
    t = Trainer(build_model(cfg.model), cfg, FOUR, select_device("cuda", mixed_precision=True),
                checkpoint_dir=tmp_path / "ckpt",
                provenance={"dataset_fingerprint": "SYNTHETIC", "split_digest": "SYNTHETIC",
                            "git": {"commit": "test", "dirty": None}})
    assert t.device.type == "cuda" and t.amp is True
    fit = t.fit(*_loaders())
    assert fit.epochs_run == 1
    ckpt = load_checkpoint(fit.last_checkpoint, map_location="cpu")
    assert ckpt["model_fingerprint"] == model_fingerprint({k: v.cpu() for k, v in t.model.state_dict().items()})


def test_deterministic_mode_reproduces_weights_on_cpu(tmp_path):
    prints = []
    for run in ("a", "b"):
        seed_everything(1234, deterministic=True)
        t = _trainer(tmp_path / run, optimization={"epochs": 1})
        t.fit(*_loaders())
        prints.append(model_fingerprint(t.model.state_dict()))
    assert prints[0] == prints[1]


def test_early_stopping_state_survives_in_the_checkpoint(tmp_path):
    t = _trainer(tmp_path, optimization={"epochs": 3},
                 early_stopping={"enabled": True, "patience": 1, "monitor": "loss", "mode": "min"})
    fit = t.fit(*_loaders())
    es = load_checkpoint(fit.last_checkpoint)["trainer_state"]["early_stopping"]
    assert es["bad_epochs"] == t.stopper.bad_epochs and es["best"] == t.stopper.best
