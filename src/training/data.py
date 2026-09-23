"""PyTorch datasets and loaders built from accepted records.

This module is plumbing. It turns a list of :class:`~src.dataset.loader.DatasetRecord`
into tensors and does **not** decide whether training may happen. That decision is made
once, in :func:`src.training.run.run_training`, by the readiness gate, before any
record reaches this module.

Each item is ``(image_tensor, class_index, record_index)``. The record index lets an
evaluator map every prediction back to its image and artifact, which is what makes
artifact-level evaluation possible.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any

import torch
from PIL import Image
from torch.utils.data import DataLoader, Dataset, WeightedRandomSampler

from src.dataset.classes import ClassSpec
from src.dataset.loader import DatasetRecord
from src.dataset.sampling import sample_weights
from src.preprocessing.transforms import apply_exif_orientation, to_rgb


class DataError(RuntimeError):
    """Records cannot be turned into a training dataset."""


def load_rgb(path: Any) -> Image.Image:
    """Open an image the same way Milestone 3 preprocessing does: EXIF, then RGB."""
    with Image.open(path) as im:
        im.load()
        return to_rgb(apply_exif_orientation(im))


class PotteryImageDataset(Dataset):
    """Images and trainable class indices for a fixed list of records.

    Refuses held-out or unknown labels at construction time: nothing is collapsed into
    a trainable class, and nothing is skipped silently during iteration.
    """

    def __init__(
        self,
        records: Sequence[DatasetRecord],
        spec: ClassSpec,
        transform: Callable[[Image.Image], torch.Tensor],
        *,
        loader: Callable[[Any], Image.Image] = load_rgb,
    ) -> None:
        self.records = list(records)
        self.spec = spec
        self.transform = transform
        self.loader = loader
        bad = [(r.image_id, r.script_type) for r in self.records
               if r.script_type not in spec.trainable]
        if bad:
            raise DataError(f"{len(bad)} record(s) have non-trainable labels, e.g. {bad[:3]}; "
                            "held-out labels are excluded before this point, never relabelled")
        self.targets = [spec.trainable.index(r.script_type) for r in self.records]

    def __len__(self) -> int:
        return len(self.records)

    def __getitem__(self, index: int) -> tuple[torch.Tensor, int, int]:
        rec = self.records[index]
        image = self.loader(rec.image_path)
        return self.transform(image), self.targets[index], index


def seed_worker(worker_id: int) -> None:
    """Seed numpy/random in each DataLoader worker from torch's per-worker seed."""
    import random

    import numpy as np

    seed = torch.initial_seed() % 2**32
    np.random.seed(seed)
    random.seed(seed)


def make_loader(
    dataset: PotteryImageDataset,
    *,
    batch_size: int,
    train: bool,
    seed: int,
    num_workers: int = 0,
    pin_memory: bool = False,
    imbalance_strategy: str = "none",
    count_unit: str = "artifact",
    equalise_artifacts: bool = True,
) -> DataLoader:
    """A deterministic-where-practical DataLoader.

    Weighted sampling applies to the training loader only, and only when
    ``imbalance_strategy == 'weighted_sampler'``. Evaluation loaders never shuffle.
    """
    generator = torch.Generator()
    generator.manual_seed(seed)
    sampler = None
    shuffle = train
    if train and imbalance_strategy == "weighted_sampler":
        weights = sample_weights(dataset.records, dataset.spec, unit=count_unit,  # type: ignore[arg-type]
                                 equalise_artifacts=equalise_artifacts)
        sampler = WeightedRandomSampler(weights, num_samples=len(weights), replacement=True,
                                        generator=generator)
        shuffle = False
    return DataLoader(
        dataset,
        batch_size=batch_size,
        shuffle=shuffle,
        sampler=sampler,
        num_workers=num_workers,
        pin_memory=pin_memory,
        worker_init_fn=seed_worker,
        generator=generator,
        drop_last=False,
        persistent_workers=False,
    )


__all__ = ["DataError", "PotteryImageDataset", "load_rgb", "make_loader", "seed_worker"]
