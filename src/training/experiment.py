"""Lightweight experiment records: one JSON file per training run.

No tracking server. A run writes ``<experiments_dir>/<experiment_id>/experiment.json``
holding everything needed to say what was trained, on what, and how it did:

    experiment_id, timestamp, status, git_commit, git_dirty,
    dataset_version {fingerprint, image_set_fingerprint, source, records},
    config, model {name, parameters}, seed, device, environment,
    split {strategy, digest, manifest},
    training_split / validation_split / test_split {artifacts, images, artifact_ids},
    metrics, checkpoint {best, last}, readiness (gate snapshot), notes

A blocked run is **not** recorded as an experiment: nothing was trained.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

EXPERIMENT_FORMAT = "1.0.0"


def make_experiment_id(dataset_fingerprint: str, seed: int, when: datetime | None = None) -> str:
    when = when or datetime.now(timezone.utc)
    return f"{when.strftime('%Y%m%dT%H%M%SZ')}_{dataset_fingerprint[:8]}_s{seed}"


def split_summary(records: Iterable[Any]) -> dict[str, Any]:
    recs = list(records)
    artifacts = sorted({r.artifact_id for r in recs})
    return {"artifacts": len(artifacts), "images": len(recs), "artifact_ids": artifacts}


@dataclass
class ExperimentRecord:
    experiment_id: str
    timestamp: str
    status: str
    git_commit: str
    git_dirty: bool | None
    dataset_version: dict[str, Any]
    config: dict[str, Any]
    model: dict[str, Any]
    seed: int
    device: dict[str, Any]
    environment: dict[str, Any]
    split: dict[str, Any]
    training_split: dict[str, Any]
    validation_split: dict[str, Any]
    test_split: dict[str, Any] | None
    metrics: dict[str, Any] = field(default_factory=dict)
    checkpoint: dict[str, Any] = field(default_factory=dict)
    readiness: dict[str, Any] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)
    format_version: str = EXPERIMENT_FORMAT

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def save(self, experiments_dir: Path | str) -> Path:
        out = Path(experiments_dir) / self.experiment_id / "experiment.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(self.to_dict(), indent=2, ensure_ascii=False, default=str)
                       + "\n", encoding="utf-8")
        return out

    @classmethod
    def load(cls, path: Path | str) -> ExperimentRecord:
        return cls(**json.loads(Path(path).read_text(encoding="utf-8")))


__all__ = ["EXPERIMENT_FORMAT", "ExperimentRecord", "make_experiment_id", "split_summary"]
