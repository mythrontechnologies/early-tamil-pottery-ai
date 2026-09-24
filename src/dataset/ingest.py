"""Ingestion pipeline.

    input (.json / .jsonl / .csv)
            |
            v
      parse            -> a parse failure rejects the batch; nothing partial is kept
            |
            v
      schema validation (E1)
            |
            v
      cross-field validation (R1-R15, E2-E5)
            |
            v
      image existence check (R2)
            |
            v
      SHA-256 verification (E2)
            |
            v
      artifact grouping check (R3, R4, E5)
            |
            v
      dataset report
            |
            v
      ACCEPTED -> written to data/metadata/records.jsonl
      REJECTED -> nothing written, every reason reported

**The pipeline never repairs research metadata.** It does not fill in sentinels, coerce
types, normalise spellings, drop bad rows or guess at a missing value. A batch is taken
whole or refused whole, because a partially-ingested batch leaves the dataset in a state
nobody has reviewed.

Default mode is a dry run. Writing requires an explicit ``commit=True``.
"""

from __future__ import annotations

from dataclasses import dataclass
from dataclasses import field as dc_field
from pathlib import Path
from typing import Any

from .audit import AuditReport, audit
from .convert import ConversionError, load_records, read_jsonl, write_jsonl
from .schema import RESEARCH_DATA_ROOT, RESEARCH_RECORDS_PATH, load_schema
from .validation import ValidationResult, validate_records


@dataclass
class IngestionResult:
    source: str
    accepted: bool
    committed: bool
    reason: str
    records: list[dict[str, Any]] = dc_field(default_factory=list)
    validation: ValidationResult | None = None
    audit_report: AuditReport | None = None
    destination: str | None = None
    merged_existing: int = 0
    stage_log: list[str] = dc_field(default_factory=list)

    def render(self) -> str:
        lines = ["=" * 68, "INGESTION", "=" * 68, f"Source      : {self.source}"]
        lines += [f"  {line}" for line in self.stage_log]
        lines.append("")
        if self.validation is not None:
            lines.append(self.validation.summary())
            lines.append("")
            if self.validation.findings:
                lines.append(f"Findings ({len(self.validation.findings)}):")
                lines += [f"  {f}" for f in self.validation.findings]
                lines.append("")
        lines.append(f"Result      : {'ACCEPTED' if self.accepted else 'REJECTED'}")
        lines.append(f"Reason      : {self.reason}")
        lines.append(f"Committed   : {self.committed}")
        if self.destination:
            lines.append(f"Destination : {self.destination}")
        lines.append("=" * 68)
        return "\n".join(lines)


def ingest(
    source: Path | str,
    *,
    destination: Path | None = None,
    data_root: Path | None = None,
    verify_hashes: bool = True,
    export_mode: bool = False,
    strict: bool = False,
    commit: bool = False,
    merge: bool = True,
) -> IngestionResult:
    """Validate a batch and, on success and with ``commit``, write it to the dataset.

    Args:
        source: ``.json``, ``.jsonl`` or ``.csv`` input.
        destination: defaults to the canonical ``data/metadata/records.jsonl``.
        data_root: root for ``image_path``. Defaults to ``data/raw``; pass ``None``
            explicitly via ``skip_images`` semantics by pointing at a missing dir only
            if you accept that R2/E2 will be reported as skipped.
        verify_hashes: recompute SHA-256 for files that exist.
        merge: validate the incoming batch together with records already in the
            destination, so cross-record rules (R1, R3, R4) see the whole dataset.
    """
    source = Path(source)
    destination = Path(destination) if destination else RESEARCH_RECORDS_PATH
    data_root = Path(data_root) if data_root is not None else RESEARCH_DATA_ROOT

    result = IngestionResult(
        source=str(source), accepted=False, committed=False,
        reason="", destination=str(destination),
    )

    # -- stage 1: parse -------------------------------------------------------
    if not source.exists():
        result.reason = f"source does not exist: {source}"
        result.stage_log.append("parse            : FAILED (missing file)")
        return result
    try:
        incoming = load_records(source)
    except ConversionError as exc:
        result.reason = f"could not parse source: {exc}"
        result.stage_log.append(f"parse            : FAILED ({exc})")
        return result
    result.records = incoming
    result.stage_log.append(f"parse            : OK ({len(incoming)} record(s))")

    # -- stage 2: merge context ----------------------------------------------
    existing: list[dict[str, Any]] = []
    if merge and destination.exists():
        try:
            existing = read_jsonl(destination)
        except ConversionError as exc:
            result.reason = f"existing dataset is unreadable, refusing to append: {exc}"
            result.stage_log.append(f"merge            : FAILED ({exc})")
            return result
    result.merged_existing = len(existing)
    result.stage_log.append(
        f"merge            : {len(existing)} existing record(s) included in checks"
        if merge else "merge            : skipped (batch validated alone)"
    )

    combined = existing + incoming

    # -- stages 3-7: validation ----------------------------------------------
    effective_root = data_root if data_root.is_dir() else None
    validation = validate_records(
        combined,
        data_root=effective_root,
        verify_hashes=verify_hashes,
        export_mode=export_mode,
        strict=strict,
        schema=load_schema(),
    )
    result.validation = validation

    result.stage_log.append("schema (E1)      : included")
    result.stage_log.append("cross-field      : R1-R15, E2-E5 applied")
    result.stage_log.append(
        f"image existence  : {'checked against ' + str(data_root) if effective_root else 'SKIPPED - ' + str(data_root) + ' not present'}"
    )
    result.stage_log.append(
        f"sha-256          : {'verified' if validation.hashes_verified else 'skipped'}"
    )
    result.stage_log.append("artifact grouping: R3/R4/E5 applied")

    # -- stage 8: report ------------------------------------------------------
    result.audit_report = audit(combined, source=destination, validation=validation)

    # -- stage 9: accept or reject -------------------------------------------
    if not validation.ok:
        n_err, n_warn = len(validation.errors), len(validation.warnings)
        bits = [f"{n_err} error(s)"]
        if strict and n_warn:
            bits.append(f"{n_warn} warning(s) under --strict")
        result.reason = f"validation failed: {', '.join(bits)}. Nothing was written."
        return result

    result.accepted = True

    if not commit:
        result.reason = (
            f"validation passed for {len(incoming)} incoming record(s). "
            "Dry run - pass --commit to write."
        )
        return result

    written = write_jsonl(destination, combined)
    result.committed = True
    result.reason = (
        f"accepted {len(incoming)} record(s); {written} total record(s) written to "
        f"{destination}"
    )
    return result


__all__ = ["IngestionResult", "ingest"]
