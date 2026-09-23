"""Dataset statistics: what is actually in the dataset, counted honestly.

``python -m src.dataset stats`` renders this. Counts are of *artifacts* first and
*images* second, because the artifact is the unit of evidence and of splitting.

Some quantities the Milestone 5 brief lists are not recorded by the schema. They are
reported as such rather than approximated:

* **Periods** - the schema has no period field. The report shows ``dating_reliability``
  and whether numeric bounds exist instead, and says so.
* **Inscription types** - reported from ``inscription_technique``, the closest schema
  field (how the mark was made), and labelled with that field name.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass
from dataclasses import field as dc_field
from pathlib import Path
from typing import Any

from .classes import ClassSpec
from .convert import read_jsonl
from .loader import DatasetLoadError, load_dataset
from .readiness import evaluate
from .sampling import imbalance_table, render_imbalance_table
from .schema import RESEARCH_DATA_ROOT, RESEARCH_RECORDS_PATH
from .splits import SplitManifest, SplitSettings, latest_manifest, verify_manifest


@dataclass
class DatasetStatistics:
    source: str
    is_research_dataset: bool
    artifacts: int = 0
    images: int = 0
    script_classes: list[dict[str, Any]] = dc_field(default_factory=list)
    sites: dict[str, int] = dc_field(default_factory=dict)
    dating_reliability: dict[str, int] = dc_field(default_factory=dict)
    records_with_numeric_dating: int = 0
    inscription_types: dict[str, int] = dc_field(default_factory=dict)
    inscription_present: dict[str, int] = dc_field(default_factory=dict)
    label_sources: dict[str, int] = dc_field(default_factory=dict)
    research_usable: dict[str, int] = dc_field(default_factory=dict)
    split_manifest: str | None = None
    split_strategy: str | None = None
    partitions: dict[str, dict[str, int]] = dc_field(default_factory=dict)
    duplicate_hashes_within_artifact: int = 0
    duplicate_hashes_across_artifacts: int = 0
    artifacts_across_partitions: int = 0
    missing_images: int = 0
    invalid_records: int = 0
    dataset_fingerprint: str = ""
    image_set_fingerprint: str = ""
    training_ready: bool = False
    readiness_reason: str = ""
    notes: list[str] = dc_field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def render(self) -> str:
        spec = ClassSpec.from_config()
        L: list[str] = ["=" * 68, "DATASET STATISTICS", "=" * 68]
        if not self.is_research_dataset:
            L += ["!! SOURCE IS NOT THE RESEARCH DATASET - counts below are not a corpus !!", ""]
        L += [f"Source      : {self.source}", "",
              f"Artifacts: {self.artifacts}", f"Images: {self.images}", "", "Script classes:"]
        by_label = {row["class"]: row for row in self.script_classes}
        for label in list(spec.trainable) + list(spec.held_out):
            row = by_label.get(label, {"artifacts": 0, "images": 0})
            tag = "" if label in spec.trainable else "   (held out of initial classifier)"
            L.append(f"    {label}: {row['artifacts']} artifact(s), {row['images']} image(s){tag}")

        def block(title: str, counts: dict[str, int], empty: str = "(none)") -> None:
            L.append("")
            L.append(title)
            if not counts:
                L.append(f"    {empty}")
            for k, n in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])):
                L.append(f"    {k}: {n}")

        block("Sites:", self.sites)
        block("Periods:", self.dating_reliability,
              "(no records) - note: the schema has no 'period' field; see dating_reliability")
        if self.images:
            L.append(f"    records with numeric dating bounds: {self.records_with_numeric_dating}")
            L.append("    (schema has no 'period' field; counts above are dating_reliability)")
        block("Inscription types (inscription_technique):", self.inscription_types)
        block("Label sources:", self.label_sources)
        block("Research use permitted (research_usable):", self.research_usable)

        L.append("")
        if self.partitions:
            L.append(f"Splits ({self.split_strategy}, {self.split_manifest}):")
            for name, c in self.partitions.items():
                L.append(f"    {name}: {c['artifacts']} artifact(s), {c['images']} image(s)")
        else:
            L += ["Train: none", "Validation: none", "Test: none",
                  "    (no verified split manifest for this dataset)"]

        L += ["",
              (f"Duplicate hashes: {self.duplicate_hashes_across_artifacts} across artifacts, "
               f"{self.duplicate_hashes_within_artifact} within an artifact"),
              f"Duplicate artifacts: {self.artifacts_across_partitions} across partitions",
              f"Missing images: {self.missing_images}",
              f"Invalid records: {self.invalid_records}",
              "",
              f"Dataset fingerprint: {self.dataset_fingerprint[:16]}...",
              "",
              f"Training readiness: {'READY' if self.training_ready else 'BLOCKED'}",
              f"    {self.readiness_reason}"]
        for n in self.notes:
            L.append(f"note: {n}")
        L.append("=" * 68)
        return "\n".join(L)


def _count(records: list[dict[str, Any]], field: str) -> dict[str, int]:
    """Value counts. Sentinels are counted as values, never dropped."""
    return dict(Counter(str(r.get(field, "unknown")) for r in records))


def compute_statistics(
    records_path: Path | None = None,
    data_root: Path | None = None,
    *,
    manifest_path: Path | None = None,
    verify_hashes: bool = True,
) -> DatasetStatistics:
    records_path = Path(records_path) if records_path else RESEARCH_RECORDS_PATH
    data_root = Path(data_root) if data_root else RESEARCH_DATA_ROOT
    spec = ClassSpec.from_config()

    readiness = evaluate(records_path, data_root, manifest_path=manifest_path,
                         verify_hashes=verify_hashes)
    try:
        dataset = load_dataset(records_path, data_root, verify_hashes=verify_hashes)
    except DatasetLoadError as exc:
        return DatasetStatistics(source=str(records_path), is_research_dataset=False,
                                 readiness_reason=readiness.reason,
                                 notes=[f"records unreadable: {exc}"])
    raw = read_jsonl(records_path) if records_path.exists() else []
    recs = [r for r in raw if isinstance(r, dict)]

    stats = DatasetStatistics(
        source=dataset.source,
        is_research_dataset=dataset.is_research_dataset,
        artifacts=len({r.get("artifact_id") for r in recs}),
        images=len(recs),
        script_classes=[row.to_dict() for row in imbalance_table(recs, spec)],
        sites=_count(recs, "site"),
        dating_reliability=_count(recs, "dating_reliability"),
        records_with_numeric_dating=sum(
            1 for r in recs if isinstance(r.get("dating_lower_year"), int)
            or isinstance(r.get("dating_upper_year"), int)),
        inscription_types=_count(recs, "inscription_technique"),
        inscription_present=_count(recs, "inscription_present"),
        label_sources=_count(recs, "label_source"),
        research_usable=_count(recs, "research_usable"),
        invalid_records=len(dataset.rejections),
        dataset_fingerprint=dataset.fingerprint,
        image_set_fingerprint=dataset.image_fingerprint,
        training_ready=readiness.training_ready,
        readiness_reason=readiness.reason,
    )
    if not dataset.exists:
        stats.notes.append(f"{dataset.source} does not exist: no records have been ingested")

    if dataset.validation is not None:
        errs = dataset.validation.findings
        stats.missing_images = sum(1 for f in errs if f.rule == "R2")
        stats.duplicate_hashes_across_artifacts = sum(1 for f in errs if f.rule == "R4")
        stats.duplicate_hashes_within_artifact = sum(1 for f in errs if f.rule == "E5")
        if not data_root.is_dir():
            stats.missing_images = len(recs)

    manifest_file = Path(manifest_path) if manifest_path else latest_manifest(
        SplitSettings.from_config().manifest_dir, dataset.fingerprint)
    if manifest_file and manifest_file.exists() and not dataset.is_empty:
        manifest = SplitManifest.load(manifest_file)
        errors = verify_manifest(manifest, dataset)
        stats.split_manifest = str(manifest_file.name)
        stats.split_strategy = manifest.strategy
        stats.artifacts_across_partitions = sum(1 for e in errors if e.startswith("artifact "))
        stats.partitions = {
            p: {"artifacts": len(manifest.artifacts_in(p)), "images": len(manifest.images_in(p))}
            for p in manifest.partitions
        }
        if errors:
            stats.notes.append(f"split manifest failed verification: {errors[0]}")
    return stats


def render_class_report(records: list[dict[str, Any]], spec: ClassSpec | None = None) -> str:
    """The pre-training class table: class, artifacts, images, percentage."""
    spec = spec or ClassSpec.from_config()
    return render_imbalance_table(imbalance_table(records, spec))


__all__ = ["DatasetStatistics", "compute_statistics", "render_class_report"]
