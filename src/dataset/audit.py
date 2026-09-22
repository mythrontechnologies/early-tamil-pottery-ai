"""Dataset audit.

Counts what is actually in a record set. The audit is careful about one thing above
all: **test fixtures are not research data.** Any source other than the canonical
``data/metadata/records.jsonl`` is reported as a non-research source, with a banner, so
that a fixture count can never be mistaken for a corpus count.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass, field as dc_field
from pathlib import Path
from typing import Any

from .schema import RESEARCH_RECORDS_PATH, has_real_value
from .validation import ValidationResult

#: Fields whose population is worth counting in the audit.
_PRESENCE_FIELDS = {
    "records_with_transcription": "transcription",
    "records_with_transliteration": "transliteration",
    "records_with_translation": "translation_en",
    "records_with_dating_source": "dating_source",
    "records_with_publication": "publication",
    "records_with_sha256": "image_sha256",
    "records_with_regions": "inscription_regions",
}


@dataclass
class AuditReport:
    source: str
    is_research_dataset: bool
    total_records: int = 0
    unique_artifacts: int = 0
    unique_image_hashes: int = 0
    records_missing_hash: int = 0
    by_script_type: dict[str, int] = dc_field(default_factory=dict)
    by_inscription_present: dict[str, int] = dc_field(default_factory=dict)
    by_site: dict[str, int] = dc_field(default_factory=dict)
    by_label_source: dict[str, int] = dc_field(default_factory=dict)
    by_verification_status: dict[str, int] = dc_field(default_factory=dict)
    by_split: dict[str, int] = dc_field(default_factory=dict)
    artifacts_by_script_type: dict[str, int] = dc_field(default_factory=dict)
    records_with_transcription: int = 0
    records_with_transliteration: int = 0
    records_with_translation: int = 0
    records_with_dating: int = 0
    records_with_dating_basis: int = 0
    records_with_dating_source: int = 0
    records_with_publication: int = 0
    records_with_sha256: int = 0
    records_with_regions: int = 0
    photos_per_artifact_max: int = 0
    validation_errors: int = 0
    validation_warnings: int = 0
    validation_status: str = "NOT_RUN"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def render(self) -> str:
        lines: list[str] = []
        w = 34

        def row(label: str, value: Any) -> str:
            return f"{label:<{w}}: {value}"

        def block(label: str, counts: dict[str, int]) -> None:
            lines.append(f"{label}")
            if not counts:
                lines.append("    (none)")
                return
            for key, n in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])):
                lines.append(f"    {key:<30} {n}")

        lines.append("=" * 68)
        lines.append("DATASET AUDIT")
        lines.append("=" * 68)
        lines.append(row("Source", self.source))

        if not self.is_research_dataset:
            lines += [
                "",
                "!" * 68,
                "!!  SOURCE IS NOT THE RESEARCH DATASET.",
                "!!  These counts describe test fixtures or an ad-hoc file.",
                f"!!  The research dataset is {RESEARCH_RECORDS_PATH}",
                "!" * 68,
            ]
        lines.append("")

        if self.is_research_dataset and self.total_records == 0:
            lines += ["REAL DATASET: 0 records", ""]

        lines.append(row("Total records", self.total_records))
        lines.append(row("Unique artifacts", self.unique_artifacts))
        lines.append(row("Unique image hashes", self.unique_image_hashes))
        lines.append(row("Records missing a hash", self.records_missing_hash))
        lines.append(row("Max photographs per artifact", self.photos_per_artifact_max))
        lines.append("")

        block("Records by script_type", self.by_script_type)
        block("Artifacts by script_type", self.artifacts_by_script_type)
        block("Records by inscription_present", self.by_inscription_present)
        block("Records by site", self.by_site)
        block("Records by label_source", self.by_label_source)
        block("Records by verification_status", self.by_verification_status)
        block("Records by split", self.by_split)
        lines.append("")

        lines.append(row("Records with transcription", self.records_with_transcription))
        lines.append(row("Records with transliteration", self.records_with_transliteration))
        lines.append(row("Records with translation", self.records_with_translation))
        lines.append(row("Records with dating (bounds)", self.records_with_dating))
        lines.append(row("Records with dating_basis", self.records_with_dating_basis))
        lines.append(row("Records with dating_source", self.records_with_dating_source))
        lines.append(row("Records with publication", self.records_with_publication))
        lines.append(row("Records with SHA-256", self.records_with_sha256))
        lines.append(row("Records with regions", self.records_with_regions))
        lines.append("")

        lines.append(row("Validation status", self.validation_status))
        lines.append(row("Validation failures (errors)", self.validation_errors))
        lines.append(row("Validation warnings", self.validation_warnings))
        lines.append("=" * 68)
        return "\n".join(lines)


def is_research_source(path: Path | str) -> bool:
    """True only for the one canonical research dataset file."""
    try:
        return Path(path).resolve() == RESEARCH_RECORDS_PATH.resolve()
    except OSError:  # pragma: no cover - unreachable on supported platforms
        return False


def audit(
    records: list[dict[str, Any]],
    *,
    source: str | Path = "<memory>",
    validation: ValidationResult | None = None,
) -> AuditReport:
    report = AuditReport(
        source=str(source),
        is_research_dataset=is_research_source(source) if isinstance(source, (str, Path)) else False,
        total_records=len(records),
    )

    artifacts: dict[str, set[str]] = {}
    hashes: set[str] = set()
    per_artifact = Counter()

    def tally(field: str) -> dict[str, int]:
        c = Counter(
            str(r.get(field, "<absent>")) for r in records if isinstance(r, dict)
        )
        return dict(c)

    for rec in records:
        if not isinstance(rec, dict):
            continue

        aid = rec.get("artifact_id")
        if isinstance(aid, str):
            per_artifact[aid] += 1
            artifacts.setdefault(aid, set())
            st = rec.get("script_type")
            if isinstance(st, str):
                artifacts[aid].add(st)

        if has_real_value(rec, "image_sha256"):
            hashes.add(rec["image_sha256"])
        else:
            report.records_missing_hash += 1

        for attr, field in _PRESENCE_FIELDS.items():
            if has_real_value(rec, field):
                setattr(report, attr, getattr(report, attr) + 1)

        if isinstance(rec.get("dating_lower_year"), int) or isinstance(
            rec.get("dating_upper_year"), int
        ):
            report.records_with_dating += 1

        basis = rec.get("dating_basis")
        if isinstance(basis, list) and basis and basis != ["unknown"]:
            report.records_with_dating_basis += 1

    report.unique_artifacts = len(artifacts)
    report.unique_image_hashes = len(hashes)
    report.photos_per_artifact_max = max(per_artifact.values(), default=0)

    report.by_script_type = tally("script_type")
    report.by_inscription_present = tally("inscription_present")
    report.by_site = tally("site")
    report.by_label_source = tally("label_source")
    report.by_verification_status = tally("verification_status")
    report.by_split = tally("split")

    # An artifact counts once per class. Mixed-class artifacts count under each,
    # which is visible rather than hidden.
    artifact_classes = Counter()
    for classes in artifacts.values():
        for cls in classes or {"<absent>"}:
            artifact_classes[cls] += 1
    report.artifacts_by_script_type = dict(artifact_classes)

    if validation is not None:
        report.validation_errors = len(validation.errors)
        report.validation_warnings = len(validation.warnings)
        report.validation_status = validation.status

    return report


__all__ = ["AuditReport", "audit", "is_research_source"]
