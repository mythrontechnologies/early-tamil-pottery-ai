"""Training readiness gate.

Answers one question: **may a model be trained right now?**

The answer today is no, because there is no research data. The gate exists so that
answer is enforced by code rather than by remembering. Every training entry point from
Milestone 4 onward must call :func:`assert_training_ready` before it constructs a model:

    from src.dataset.readiness import assert_training_ready
    assert_training_ready()          # raises NotTrainingReadyError until data exists

The gate is deliberately conservative. It fails closed: any error reading the dataset
makes it report *not ready*.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field as dc_field
from pathlib import Path
from typing import Any

from .audit import audit
from .convert import read_jsonl
from .schema import (
    ROOT,
    RESEARCH_DATA_ROOT,
    RESEARCH_RECORDS_PATH,
    load_config,
)
from .validation import validate_records

IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".tif", ".tiff", ".webp", ".bmp"}


def _relative(path: Path | str) -> str:
    """Project-relative path where possible, so reports are machine-independent."""
    path = Path(path)
    try:
        return path.resolve().relative_to(ROOT).as_posix()
    except ValueError:
        return str(path)


class NotTrainingReadyError(RuntimeError):
    """Raised when training is attempted without a usable research dataset."""


@dataclass
class ReadinessReport:
    research_data_present: bool
    record_count: int
    unique_artifacts: int
    validation_status: str
    training_ready: bool
    reason: str
    image_files_present: int = 0
    artifacts_by_class: dict[str, int] = dc_field(default_factory=dict)
    min_artifacts_per_class_required: int = 0
    classes_below_threshold: list[str] = dc_field(default_factory=list)
    blockers: list[str] = dc_field(default_factory=list)
    records_path: str = RESEARCH_RECORDS_PATH.name
    data_root: str = RESEARCH_DATA_ROOT.name

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False)

    def render(self) -> str:
        lines = [
            "=" * 68,
            "TRAINING READINESS GATE",
            "=" * 68,
            f"Research data present : {self.research_data_present}",
            f"Records               : {self.record_count}",
            f"Unique artifacts      : {self.unique_artifacts}",
            f"Image files on disk   : {self.image_files_present}",
            f"Validation status     : {self.validation_status}",
            f"Training ready        : {self.training_ready}",
            f"Reason                : {self.reason}",
        ]
        if self.artifacts_by_class:
            lines.append("")
            lines.append(f"Artifacts per class (threshold {self.min_artifacts_per_class_required}):")
            for cls, n in sorted(self.artifacts_by_class.items()):
                flag = "  << below threshold" if cls in self.classes_below_threshold else ""
                lines.append(f"    {cls:<30} {n}{flag}")
        if self.blockers:
            lines.append("")
            lines.append("Blockers:")
            lines += [f"  - {b}" for b in self.blockers]
        lines.append("=" * 68)
        return "\n".join(lines)


def count_images(data_root: Path | None = None) -> int:
    root = Path(data_root) if data_root else RESEARCH_DATA_ROOT
    if not root.is_dir():
        return 0
    return sum(1 for p in root.rglob("*") if p.is_file() and p.suffix.lower() in IMAGE_SUFFIXES)


def evaluate(
    records_path: Path | None = None,
    data_root: Path | None = None,
    *,
    config: dict[str, Any] | None = None,
) -> ReadinessReport:
    """Assess whether the research dataset can support training."""
    records_path = Path(records_path) if records_path else RESEARCH_RECORDS_PATH
    data_root = Path(data_root) if data_root else RESEARCH_DATA_ROOT
    config = config or load_config()

    cfg_split = config.get("split", {})
    threshold = int(cfg_split.get("min_artifacts_per_class_for_holdout", 20))
    classes = list(config.get("classification", {}).get("classes", []))

    blockers: list[str] = []
    images = count_images(data_root)

    if not records_path.exists():
        return ReadinessReport(
            research_data_present=False,
            record_count=0,
            unique_artifacts=0,
            validation_status="PASS",
            training_ready=False,
            reason="No real archaeological images are currently available",
            image_files_present=images,
            min_artifacts_per_class_required=threshold,
            blockers=[
                f"{_relative(records_path)} does not exist - no records have been ingested",
                "See docs/DATA_INVENTORY.md for acquisition routes",
            ],
            records_path=_relative(records_path),
            data_root=_relative(data_root),
        )

    try:
        records = read_jsonl(records_path)
    except Exception as exc:  # noqa: BLE001 - fail closed on any read problem
        return ReadinessReport(
            research_data_present=False,
            record_count=0,
            unique_artifacts=0,
            validation_status="FAIL",
            training_ready=False,
            reason=f"Records file could not be read: {exc}",
            image_files_present=images,
            min_artifacts_per_class_required=threshold,
            blockers=[f"unreadable records file: {_relative(records_path)}"],
            records_path=_relative(records_path),
            data_root=_relative(data_root),
        )

    validation = validate_records(records, data_root=data_root if images else None)
    report_audit = audit(records, source=records_path, validation=validation)

    by_class = {c: report_audit.artifacts_by_script_type.get(c, 0) for c in classes}
    below = [c for c, n in by_class.items() if n < threshold]

    if not records:
        blockers.append("records file is empty")
    if images == 0:
        blockers.append(f"no image files under {_relative(data_root)}")
    if not validation.ok:
        blockers.append(f"{len(validation.errors)} validation error(s)")
    if below:
        blockers.append(
            f"classes below the {threshold}-artifact threshold: {', '.join(below)} "
            "(use grouped k-fold and report it, or acquire more artifacts)"
        )

    ready = not blockers
    if ready:
        reason = "Research dataset present, valid, and above the per-class artifact threshold"
    elif not records or images == 0:
        reason = "No real archaeological images are currently available"
    else:
        reason = "; ".join(blockers)

    return ReadinessReport(
        research_data_present=bool(records) and images > 0,
        record_count=len(records),
        unique_artifacts=report_audit.unique_artifacts,
        validation_status=validation.status,
        training_ready=ready,
        reason=reason,
        image_files_present=images,
        artifacts_by_class=by_class,
        min_artifacts_per_class_required=threshold,
        classes_below_threshold=below,
        blockers=blockers,
        records_path=_relative(records_path),
        data_root=_relative(data_root),
    )


def assert_training_ready(
    records_path: Path | None = None, data_root: Path | None = None
) -> ReadinessReport:
    """Raise :class:`NotTrainingReadyError` unless the dataset can support training.

    Call this at the top of every training entry point.
    """
    report = evaluate(records_path, data_root)
    if not report.training_ready:
        raise NotTrainingReadyError(
            "Training is blocked.\n"
            + report.render()
            + "\n\nThis gate exists to prevent a model being trained on fixtures, "
            "placeholders, or an empty dataset."
        )
    return report


def write_report(path: Path | str, report: ReadinessReport) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(report.to_json() + "\n", encoding="utf-8")
    return path


__all__ = [
    "NotTrainingReadyError",
    "ReadinessReport",
    "assert_training_ready",
    "evaluate",
    "count_images",
    "write_report",
]
