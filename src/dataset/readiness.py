"""Training readiness gate.

Answers one question: **may a model be trained right now?**

The answer today is no, because there is no authorised research data. The gate exists
so that answer is enforced by code rather than by remembering. Every training entry
point must call :func:`assert_training_ready` before it constructs a model:

    from src.dataset.readiness import assert_training_ready
    assert_training_ready()          # raises NotTrainingReadyError until data exists

The gate fails closed: any error reading the dataset, and any gate that could not be
evaluated, makes it report *not ready*.

Gates (Milestone 5). Each is tagged with the *basis* of the requirement, so an
engineering requirement is never mistaken for an archaeological claim:

====  ===========================================  ====================
G1    records come from the canonical dataset      engineering
G2    records exist                                engineering
G3    image files exist                            engineering
G4    metadata validation passes (E*, R*)          engineering
G5    every record loads, hash verified (L*, E2)   engineering
G6    no photograph under two artifacts (R4)       engineering
G7    every label has a known source               project_methodology
G8    research use of every image is permitted     rights
G9    every trainable class is present             project_methodology
G10   minimum artifacts per class                  engineering (statistical)
G11   verified artifact-level split manifest       engineering
====  ===========================================  ====================

None of these gates encodes an archaeological judgement. The class list (G9) is a
project methodology decision from ``configs/project.yaml``; the per-class threshold
(G10) is a statistical requirement for a meaningful held-out estimate, not a claim
about how many sherds exist or are needed to understand the material.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from dataclasses import field as dc_field
from pathlib import Path
from typing import Any

from .audit import is_research_source
from .classes import ClassSpec, class_availability, eligibility
from .convert import read_jsonl
from .loader import DatasetLoadError, LoadedDataset, load_dataset
from .schema import (
    RESEARCH_DATA_ROOT,
    RESEARCH_RECORDS_PATH,
    ROOT,
    load_config,
)
from .splits import (
    SplitError,
    SplitManifest,
    SplitSettings,
    latest_manifest,
    verify_manifest,
)

IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".tif", ".tiff", ".webp", ".bmp"}

NO_DATA_REASON = "No real archaeological images are currently available"

#: id -> (title, category, basis)
GATES: dict[str, tuple[str, str, str]] = {
    "G1": ("records come from the canonical research dataset", "integrity", "engineering"),
    "G2": ("records exist", "data_presence", "engineering"),
    "G3": ("image files exist", "data_presence", "engineering"),
    "G4": ("metadata validation passes", "validation", "engineering"),
    "G5": ("every record loads and its hash is verified", "validation", "engineering"),
    "G6": ("no photograph is recorded under two artifacts", "leakage", "engineering"),
    "G7": ("every training label has a known source", "labels", "project_methodology"),
    "G8": ("research use of every training image is permitted", "rights", "rights"),
    "G9": ("every trainable class is present", "classes", "project_methodology"),
    "G10": ("minimum artifacts per class", "statistics", "engineering"),
    "G11": ("verified artifact-level split manifest", "leakage", "engineering"),
}


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
class Gate:
    id: str
    title: str
    category: str
    basis: str
    passed: bool | None          # None = could not be evaluated (counts as failed)
    detail: str = ""

    @classmethod
    def make(cls, gate_id: str, passed: bool | None, detail: str = "") -> Gate:
        title, category, basis = GATES[gate_id]
        return cls(gate_id, title, category, basis, passed, detail)

    @property
    def status(self) -> str:
        return {True: "PASS", False: "FAIL", None: "NOT EVALUATED"}[self.passed]


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
    source_is_canonical: bool = False
    rejected_records: int = 0
    held_out_artifacts: dict[str, int] = dc_field(default_factory=dict)
    dataset_fingerprint: str = ""
    split_manifest: str | None = None
    split_strategy: str | None = None
    gates: list[dict[str, Any]] = dc_field(default_factory=list)

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
            for cls, n in self.artifacts_by_class.items():
                flag = "  << below threshold" if cls in self.classes_below_threshold else ""
                lines.append(f"    {cls:<30} {n}{flag}")
        if self.gates:
            lines.append("")
            lines.append("Gates:")
            for g in self.gates:
                lines.append(f"  {g['id']:<4} {Gate(**g).status:<14} {g['title']}  [{g['basis']}]")
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


def _unevaluated(ids: list[str], why: str) -> list[Gate]:
    return [Gate.make(g, None, why) for g in ids]


def evaluate(
    records_path: Path | None = None,
    data_root: Path | None = None,
    *,
    config: dict[str, Any] | None = None,
    manifest_path: Path | None = None,
    verify_hashes: bool = True,
    permit_noncanonical_source: bool = False,
) -> ReadinessReport:
    """Assess whether the research dataset can support training.

    ``permit_noncanonical_source`` exists so the gate's own logic can be tested on
    synthetic fixtures in a temporary directory. It is **not** reachable from the CLI or
    from :func:`assert_training_ready`, which always evaluate the canonical dataset.
    """
    records_path = Path(records_path) if records_path else RESEARCH_RECORDS_PATH
    data_root = Path(data_root) if data_root else RESEARCH_DATA_ROOT
    config = config or load_config()
    spec = ClassSpec.from_config(config)
    settings = SplitSettings.from_config(config)
    threshold = settings.min_artifacts_per_class_for_holdout

    canonical = is_research_source(records_path)
    images = count_images(data_root)
    gates: list[Gate] = [Gate.make(
        "G1", canonical or permit_noncanonical_source,
        "canonical" if canonical else
        (f"{_relative(records_path)} is not data/metadata/records.jsonl"
         + (" (permitted for testing only)" if permit_noncanonical_source else "")),
    )]
    base = dict(
        records_path=_relative(records_path),
        data_root=_relative(data_root),
        source_is_canonical=canonical,
        image_files_present=images,
    )

    def finish(report_kwargs: dict[str, Any], gates: list[Gate]) -> ReadinessReport:
        failed = [g for g in gates if g.passed is not True]
        blockers = [f"{g.id} {g.title}: {g.detail}" if g.detail else f"{g.id} {g.title}"
                    for g in failed]
        ready = not failed
        records_n = report_kwargs.get("record_count", 0)
        if ready:
            reason = "Research dataset present, valid, permitted, split, and above threshold"
        elif records_n == 0 or images == 0:
            reason = NO_DATA_REASON
        else:
            reason = "; ".join(blockers)
        return ReadinessReport(
            **base, **report_kwargs, training_ready=ready, reason=reason, blockers=blockers,
            gates=[asdict(g) for g in gates],
        )

    rest = ["G3", "G4", "G5", "G6", "G7", "G8", "G9", "G10", "G11"]

    if not records_path.exists():
        gates.append(Gate.make("G2", False, f"{_relative(records_path)} does not exist; "
                               "no records have been ingested (see docs/DATA_SOURCE_AUDIT.md)"))
        gates.append(Gate.make("G3", images > 0, f"{images} image file(s) under {_relative(data_root)}"))
        gates += _unevaluated(rest[1:], "no records")
        return finish(dict(research_data_present=False, record_count=0, unique_artifacts=0,
                           validation_status="PASS",
                           min_artifacts_per_class_required=threshold), gates)

    try:
        raw = read_jsonl(records_path)
        dataset: LoadedDataset = load_dataset(records_path, data_root, verify_hashes=verify_hashes)
    except (DatasetLoadError, OSError, ValueError) as exc:
        gates.append(Gate.make("G2", False, f"records file could not be read: {exc}"))
        gates += _unevaluated(rest, "records unreadable")
        return finish(dict(research_data_present=False, record_count=0, unique_artifacts=0,
                           validation_status="FAIL",
                           min_artifacts_per_class_required=threshold), gates)

    validation = dataset.validation
    avail = {a.label: a for a in class_availability(raw, spec)}
    by_class = {c: avail[c].artifacts for c in spec.trainable}
    held = {c: avail[c].artifacts for c in spec.held_out}
    eligible = [r for r in raw if isinstance(r, dict) and eligibility(r, spec)[0]]

    gates.append(Gate.make("G2", bool(raw), f"{len(raw)} record(s)"))
    gates.append(Gate.make("G3", images > 0, f"{images} image file(s) under {_relative(data_root)}"))
    gates.append(Gate.make(
        "G4", validation.ok if validation else False,
        f"{len(validation.errors)} error(s), {len(validation.warnings)} warning(s)"
        if validation else "validation did not run"))
    gates.append(Gate.make(
        "G5", not dataset.rejections,
        f"{len(dataset.rejections)} record(s) rejected by the loader"
        + ("" if dataset.hashes_verified else "; hashes NOT verified")))
    r4 = [f for f in (validation.errors if validation else []) if f.rule == "R4"]
    gates.append(Gate.make("G6", not r4, f"{len(r4)} photograph(s) claimed by two artifacts"))

    unsourced = sum(1 for r in eligible if r.get("label_source", "unknown") == "unknown")
    gates.append(Gate.make("G7", bool(eligible) and unsourced == 0,
                           f"{unsourced} training record(s) with label_source='unknown'"
                           if eligible else "no training-eligible records"))
    not_permitted = sum(1 for r in eligible if r.get("research_usable", "unknown") != "yes")
    gates.append(Gate.make(
        "G8", bool(eligible) and not_permitted == 0,
        f"{not_permitted} training record(s) without research_usable='yes' "
        "(absent or 'unknown' counts as not permitted)" if eligible
        else "no training-eligible records"))

    missing = [c for c in spec.trainable if by_class[c] == 0]
    gates.append(Gate.make("G9", not missing,
                           f"missing: {', '.join(missing)}" if missing else "all present"))

    manifest: SplitManifest | None = None
    manifest_file = Path(manifest_path) if manifest_path else latest_manifest(
        settings.manifest_dir, dataset.fingerprint)
    manifest_problem = ""
    if manifest_file is None or not Path(manifest_file).exists():
        manifest_problem = "no split manifest for this dataset; run `python -m src.dataset split`"
    else:
        try:
            manifest = SplitManifest.load(manifest_file)
            errors = verify_manifest(manifest, dataset)
            if errors:
                manifest_problem = "; ".join(errors[:5])
        except (SplitError, OSError, ValueError, TypeError) as exc:
            manifest_problem = f"manifest unreadable: {exc}"

    required = threshold
    if manifest is not None and manifest.strategy == "grouped_kfold":
        required = int(manifest.k or settings.k_folds)
    below = [c for c in spec.trainable if by_class[c] < required]
    gates.append(Gate.make(
        "G10", not below,
        f"classes below the {required}-artifact threshold: {', '.join(below)} (use grouped "
        "k-fold and report it, or acquire more artifacts)" if below
        else f"all classes have >= {required} artifacts"))
    gates.append(Gate.make("G11", not manifest_problem,
                           manifest_problem or f"{_relative(manifest_file)} verified"))

    return finish(dict(
        research_data_present=canonical and bool(raw) and images > 0,
        record_count=len(raw),
        unique_artifacts=len({r.get("artifact_id") for r in raw if isinstance(r, dict)}),
        validation_status=validation.status if validation else "FAIL",
        artifacts_by_class=by_class,
        classes_below_threshold=below,
        rejected_records=len(dataset.rejections),
        held_out_artifacts=held,
        dataset_fingerprint=dataset.fingerprint,
        split_manifest=_relative(manifest_file) if manifest_file else None,
        split_strategy=manifest.strategy if manifest else None,
        min_artifacts_per_class_required=required,
    ), gates)


def assert_training_ready(
    records_path: Path | None = None,
    data_root: Path | None = None,
    manifest_path: Path | None = None,
) -> ReadinessReport:
    """Raise :class:`NotTrainingReadyError` unless the dataset can support training.

    Call this at the top of every training entry point. There is deliberately no
    parameter that relaxes any gate.
    """
    report = evaluate(records_path, data_root, manifest_path=manifest_path)
    if not report.training_ready:
        raise NotTrainingReadyError(
            "Training is blocked.\n"
            + report.render()
            + "\n\nThis gate exists to prevent a model being trained on fixtures, "
            "placeholders, unauthorised images, or an empty dataset."
        )
    return report


def write_report(path: Path | str, report: ReadinessReport) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(report.to_json() + "\n", encoding="utf-8")
    return path


__all__ = [
    "GATES",
    "NO_DATA_REASON",
    "Gate",
    "NotTrainingReadyError",
    "ReadinessReport",
    "assert_training_ready",
    "count_images",
    "evaluate",
    "write_report",
]
