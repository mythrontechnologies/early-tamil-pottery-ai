"""The generic training loop.

The :class:`Trainer` knows nothing about archaeology or about where its data came
from. It fits a model on whatever loaders it is given. Whether it may be given
research data at all is decided earlier, by the readiness gate in
:func:`src.training.run.run_training`. Unit tests drive it with tiny synthetic tensors.

Features: AdamW/Adam/SGD, cosine/step/plateau schedulers, frozen-then-unfrozen
backbone with a separate backbone learning rate, fp16 autocast + GradScaler on CUDA,
gradient clipping, label smoothing, class-weighted loss, early stopping on a validation
metric, best/last checkpoints.
"""

from __future__ import annotations

import math
import time
from collections.abc import Sequence
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import torch
from torch import nn
from torch.utils.data import DataLoader

from src.evaluation.metrics import compute_metrics

from .checkpoint import build_checkpoint, load_checkpoint, save_checkpoint
from .config import TrainingConfig
from .model import backbone_parameters, head_parameters, set_backbone_trainable
from .runtime import DeviceInfo


class TrainingError(RuntimeError):
    """The training loop cannot proceed."""


class EarlyStopping:
    def __init__(self, mode: str, patience: int, min_delta: float) -> None:
        if mode not in ("max", "min"):
            raise ValueError("mode must be 'max' or 'min'")
        self.mode, self.patience, self.min_delta = mode, patience, min_delta
        self.best: float | None = None
        self.bad_epochs = 0

    def improved(self, value: float) -> bool:
        if value is None or (isinstance(value, float) and math.isnan(value)):
            self.bad_epochs += 1
            return False
        if self.best is None:
            better = True
        elif self.mode == "max":
            better = value > self.best + self.min_delta
        else:
            better = value < self.best - self.min_delta
        if better:
            self.best, self.bad_epochs = value, 0
        else:
            self.bad_epochs += 1
        return better

    @property
    def should_stop(self) -> bool:
        return self.bad_epochs >= self.patience


@dataclass
class EpochResult:
    epoch: int
    train_loss: float
    val_loss: float
    val_metrics: dict[str, Any]
    monitor: float | None
    learning_rates: list[float]
    backbone_trainable: bool
    is_best: bool
    seconds: float


@dataclass
class FitResult:
    epochs_run: int
    best_epoch: int | None
    best_monitor: float | None
    stopped_early: bool
    history: list[EpochResult] = field(default_factory=list)
    best_checkpoint: str | None = None
    last_checkpoint: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Predictions:
    y_true: list[int]
    y_pred: list[int]
    probabilities: np.ndarray
    indices: list[int]
    loss: float


class Trainer:
    def __init__(
        self,
        model: nn.Module,
        config: TrainingConfig,
        class_names: Sequence[str],
        device: DeviceInfo,
        *,
        class_weights: Sequence[float] | None = None,
        checkpoint_dir: Path | str | None = None,
        provenance: dict[str, Any] | None = None,
    ) -> None:
        self.cfg = config
        self.class_names = list(class_names)
        self.device_info = device
        self.device = torch.device(device.device)
        self.model = model.to(self.device)
        self.amp = bool(device.amp_enabled and self.device.type == "cuda")
        weight = (torch.tensor(list(class_weights), dtype=torch.float32, device=self.device)
                  if class_weights is not None else None)
        if weight is not None and weight.numel() != len(self.class_names):
            raise TrainingError("class_weights length does not match the number of classes")
        self.criterion = nn.CrossEntropyLoss(weight=weight,
                                             label_smoothing=config.optimization.label_smoothing)
        self.optimizer = self._build_optimizer()
        self.scheduler = self._build_scheduler()
        self.scaler = torch.amp.GradScaler("cuda", enabled=self.amp)
        self.checkpoint_dir = Path(checkpoint_dir) if checkpoint_dir else None
        self.provenance = provenance or {}
        self.backbone_trainable = not config.model.freeze_backbone
        es = config.early_stopping
        self.stopper = EarlyStopping(es.mode, es.patience, es.min_delta)
        self.start_epoch = 0

    # -- resume -------------------------------------------------------------

    def resume(self, checkpoint_path: Path | str) -> int:
        """Continue from a checkpoint written by this trainer: weights, optimizer, scheduler,
        early-stopping state and epoch. Refuses a checkpoint for other classes, another model,
        or another dataset version. Returns the epoch training will continue from."""
        ckpt = load_checkpoint(checkpoint_path, class_names=self.class_names)
        if ckpt["model_name"] != self.cfg.model.name:
            raise TrainingError(f"checkpoint is a {ckpt['model_name']!r}, config wants {self.cfg.model.name!r}")
        want = self.provenance.get("dataset_fingerprint")
        if want is not None and ckpt["dataset_fingerprint"] != want:
            raise TrainingError("checkpoint was trained on a different dataset version; not resuming")
        ts = ckpt.get("trainer_state") or {}
        if ts.get("backbone_trainable") and not self.backbone_trainable:
            set_backbone_trainable(self.model, True)
            self.backbone_trainable = True
        self.model.load_state_dict(ckpt["state_dict"])
        if ckpt.get("optimizer_state") is not None:
            self.optimizer.load_state_dict(ckpt["optimizer_state"])
        if self.scheduler is not None and ckpt.get("scheduler_state") is not None:
            self.scheduler.load_state_dict(ckpt["scheduler_state"])
        es = ts.get("early_stopping") or {}
        self.stopper.best = es.get("best")
        self.stopper.bad_epochs = int(es.get("bad_epochs", 0))
        self.start_epoch = int(ckpt["epoch"]) + 1
        return self.start_epoch

    # -- construction -------------------------------------------------------

    def _build_optimizer(self) -> torch.optim.Optimizer:
        o = self.cfg.optimization
        groups = [
            {"params": head_parameters(self.model), "lr": o.learning_rate, "name": "head"},
            {"params": backbone_parameters(self.model), "lr": o.backbone_learning_rate,
             "name": "backbone"},
        ]
        if o.optimizer == "adamw":
            return torch.optim.AdamW(groups, weight_decay=o.weight_decay)
        if o.optimizer == "adam":
            return torch.optim.Adam(groups, weight_decay=o.weight_decay)
        return torch.optim.SGD(groups, momentum=o.momentum, weight_decay=o.weight_decay)

    def _build_scheduler(self) -> Any:
        o = self.cfg.optimization
        if o.scheduler == "cosine":
            return torch.optim.lr_scheduler.CosineAnnealingLR(self.optimizer, T_max=o.epochs)
        if o.scheduler == "step":
            return torch.optim.lr_scheduler.StepLR(self.optimizer, step_size=o.step_size,
                                                   gamma=o.gamma)
        if o.scheduler == "plateau":
            return torch.optim.lr_scheduler.ReduceLROnPlateau(
                self.optimizer, mode=self.cfg.early_stopping.mode, factor=o.gamma,
                patience=o.plateau_patience)
        return None

    # -- loops --------------------------------------------------------------

    def _autocast(self) -> Any:
        return torch.autocast(device_type=self.device.type, dtype=torch.float16,
                              enabled=self.amp)

    def train_one_epoch(self, loader: DataLoader) -> float:
        self.model.train()
        total, count = 0.0, 0
        clip = self.cfg.optimization.gradient_clip_norm
        for images, targets, _ in loader:
            images = images.to(self.device, non_blocking=True)
            targets = torch.as_tensor(targets, device=self.device)
            self.optimizer.zero_grad(set_to_none=True)
            with self._autocast():
                loss = self.criterion(self.model(images), targets)
            if not torch.isfinite(loss):
                raise TrainingError(f"non-finite training loss: {loss.item()}")
            self.scaler.scale(loss).backward()
            if clip:
                self.scaler.unscale_(self.optimizer)
                nn.utils.clip_grad_norm_([p for p in self.model.parameters() if p.requires_grad],
                                         clip)
            self.scaler.step(self.optimizer)
            self.scaler.update()
            total += float(loss.item()) * images.size(0)
            count += images.size(0)
        if count == 0:
            raise TrainingError("training loader produced no samples")
        return total / count

    @torch.no_grad()
    def predict(self, loader: DataLoader) -> Predictions:
        self.model.eval()
        y_true: list[int] = []
        indices: list[int] = []
        probs: list[np.ndarray] = []
        total, count = 0.0, 0
        for images, targets, idx in loader:
            images = images.to(self.device, non_blocking=True)
            targets_t = torch.as_tensor(targets, device=self.device)
            with self._autocast():
                logits = self.model(images)
                loss = self.criterion(logits, targets_t)
            total += float(loss.item()) * images.size(0)
            count += images.size(0)
            probs.append(torch.softmax(logits.float(), dim=1).cpu().numpy())
            y_true.extend(int(t) for t in targets_t.cpu())
            indices.extend(int(i) for i in torch.as_tensor(idx))
        if count == 0:
            raise TrainingError("evaluation loader produced no samples")
        p = np.concatenate(probs, axis=0)
        return Predictions(y_true, [int(v) for v in p.argmax(axis=1)], p, indices, total / count)

    def _monitor_value(self, val_loss: float, metrics: dict[str, Any]) -> float | None:
        name = self.cfg.early_stopping.monitor
        return val_loss if name == "loss" else metrics.get(name)

    def fit(self, train_loader: DataLoader, val_loader: DataLoader) -> FitResult:
        es_cfg = self.cfg.early_stopping
        stopper = self.stopper
        result = FitResult(epochs_run=self.start_epoch, best_epoch=None, best_monitor=stopper.best,
                           stopped_early=False)
        unfreeze_at = self.cfg.model.unfreeze_backbone_at_epoch

        for epoch in range(self.start_epoch, self.cfg.optimization.epochs):
            start = time.perf_counter()
            if (not self.backbone_trainable and unfreeze_at is not None
                    and epoch >= unfreeze_at):
                set_backbone_trainable(self.model, True)
                self.backbone_trainable = True

            train_loss = self.train_one_epoch(train_loader)
            preds = self.predict(val_loader)
            metrics = compute_metrics(preds.y_true, preds.y_pred, self.class_names,
                                      y_prob=preds.probabilities).to_dict()
            monitor = self._monitor_value(preds.loss, metrics)

            if self.scheduler is not None:
                if isinstance(self.scheduler, torch.optim.lr_scheduler.ReduceLROnPlateau):
                    self.scheduler.step(monitor if monitor is not None else preds.loss)
                else:
                    self.scheduler.step()

            # Best-model selection always follows the monitor; only *stopping* is optional.
            is_best = stopper.improved(monitor)
            if is_best:
                result.best_epoch, result.best_monitor = epoch, monitor
                result.best_checkpoint = self._save(epoch, metrics, monitor, "best")
            if self.cfg.checkpoint.save_last:
                result.last_checkpoint = self._save(epoch, metrics, monitor, "last")

            result.history.append(EpochResult(
                epoch=epoch, train_loss=train_loss, val_loss=preds.loss, val_metrics=metrics,
                monitor=monitor, learning_rates=[g["lr"] for g in self.optimizer.param_groups],
                backbone_trainable=self.backbone_trainable, is_best=is_best,
                seconds=time.perf_counter() - start))
            result.epochs_run = epoch + 1
            if es_cfg.enabled and stopper.should_stop:
                result.stopped_early = True
                break
        return result

    def _save(self, epoch: int, metrics: dict[str, Any], monitor: float | None,
              which: str) -> str | None:
        if self.checkpoint_dir is None:
            return None
        if which == "best" and not self.cfg.checkpoint.save_best:
            return None
        ckpt = build_checkpoint(
            self.model, model_name=self.cfg.model.name, class_names=self.class_names,
            epoch=epoch, metrics=metrics,
            monitor={"name": self.cfg.early_stopping.monitor, "value": monitor,
                     "mode": self.cfg.early_stopping.mode},
            config=self.cfg.to_dict(),
            dataset_fingerprint=str(self.provenance.get("dataset_fingerprint", "unknown")),
            split_digest=str(self.provenance.get("split_digest", "unknown")),
            git=dict(self.provenance.get("git", {"commit": "unknown", "dirty": None})),
            optimizer=self.optimizer, scheduler=self.scheduler,
            trainer_state={"early_stopping": {"best": self.stopper.best,
                                              "bad_epochs": self.stopper.bad_epochs},
                           "backbone_trainable": self.backbone_trainable})
        return str(save_checkpoint(ckpt, self.checkpoint_dir / f"{which}.pt"))


__all__ = ["EarlyStopping", "EpochResult", "FitResult", "Predictions", "Trainer",
           "TrainingError"]
