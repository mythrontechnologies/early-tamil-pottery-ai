"""Dataset validation.

Two layers, deliberately kept distinct:

* **Schema layer** (``E1``) - the JSON Schema contract. Catches missing required fields,
  empty strings, year zero, unsupported enum values (including ``view``), unknown fields,
  and malformed types.
* **Cross-field layer** (``R1``-``R15``) - the rules specified in
  ``docs/SPLIT_METHODOLOGY.md`` §4, which JSON Schema cannot express.

Rule numbering is load-bearing:

* ``R*`` rules come from ``docs/SPLIT_METHODOLOGY.md`` §4 and encode either project
  methodology or archaeological reasoning agreed in Milestone 1.
* ``E*`` rules are **engineering checks added in Milestone 2**. They assert file-system
  and data-hygiene facts. They are *not* archaeological claims, and none of them asserts
  anything about pottery, scripts or chronology.

Nothing here repairs a record. Validation reports; it never edits.
"""

from __future__ import annotations

import hashlib
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from dataclasses import field as dc_field
from pathlib import Path
from typing import Any, Literal

from jsonschema import Draft202012Validator

from .schema import (
    SENTINELS,
    has_real_value,
    is_sentinel,
    load_schema,
    required_fields,
)

Severity = Literal["error", "warning"]

#: Fields whose absence is worth warning about (rule R15).
#: This is an engineering/curation judgement about research usefulness, not a
#: statement that any of these is archaeologically required.
RECOMMENDED_FIELDS: tuple[str, ...] = (
    "image_sha256",
    "view",
    "source_reference",
    "site",
    "context_reliability",
    "artifact_type",
    "pottery_type",
    "label_confidence",
    "inscription_technique",
    "reading_status",
    "dating_text",
    "dating_basis",
    "dating_reliability",
    "publication",
    "annotator",
    "annotation_date",
)

#: Fields that must read ``not_applicable`` when there is no script (rule R6).
_R6_FIELDS = ("transcription", "transliteration", "translation_en", "translation_ta")

RULE_TITLES: dict[str, str] = {
    "E1": "record conforms to the JSON Schema",
    "E2": "recorded image_sha256 matches the file on disk",
    "E3": "image_path is a safe relative POSIX path",
    "E4": "schema_version is compatible",
    "E5": "no duplicate photograph within one artifact",
    "R1": "image_id is unique across the dataset",
    "R2": "image_path resolves to an existing file",
    "R3": "all records of one artifact share one split",
    "R4": "one photograph is not claimed by two artifacts",
    "R5": "inscription_present=no implies script_type=none",
    "R6": "script_type=none implies reading fields are not_applicable",
    "R7": "script_type=other_script requires script_type_other_detail",
    "R8": "dating_lower_year <= dating_upper_year",
    "R9": "a numeric date requires a dating_source",
    "R10": "stratigraphic dating requires a stratified context",
    "R11": "unknown redistribution rights block export",
    "R12": "split=excluded requires a reason",
    "R13": "inscription_regions lie within the image",
    "R14": "test-split labels should be source-backed",
    "R15": "recommended fields are populated",
}


@dataclass(frozen=True)
class Finding:
    rule: str
    severity: Severity
    message: str
    image_id: str | None = None
    field: str | None = None
    record_index: int | None = None

    @property
    def sort_key(self) -> tuple:
        return (self.record_index if self.record_index is not None else 1 << 30,
                self.rule, self.field or "", self.message)

    def __str__(self) -> str:
        where = self.image_id or (f"record[{self.record_index}]"
                                  if self.record_index is not None else "<dataset>")
        fld = f" ({self.field})" if self.field else ""
        return f"[{self.severity.upper():7}] {self.rule} {where}{fld}: {self.message}"


@dataclass
class ValidationResult:
    findings: list[Finding] = dc_field(default_factory=list)
    record_count: int = 0
    images_checked: bool = False
    hashes_verified: bool = False
    export_mode: bool = False
    strict: bool = False

    @property
    def errors(self) -> list[Finding]:
        return [f for f in self.findings if f.severity == "error"]

    @property
    def warnings(self) -> list[Finding]:
        return [f for f in self.findings if f.severity == "warning"]

    @property
    def ok(self) -> bool:
        """Valid when there are no errors - and, in strict mode, no warnings either."""
        return not self.errors and not (self.strict and self.warnings)

    @property
    def status(self) -> str:
        return "PASS" if self.ok else "FAIL"

    def by_rule(self) -> dict[str, int]:
        counts: dict[str, int] = defaultdict(int)
        for f in self.findings:
            counts[f.rule] += 1
        return dict(sorted(counts.items()))

    def summary(self) -> str:
        lines = [
            f"Records checked   : {self.record_count}",
            f"Errors            : {len(self.errors)}",
            f"Warnings          : {len(self.warnings)}",
            f"Image existence   : {'checked' if self.images_checked else 'SKIPPED (no data root)'}",
            f"Hash verification : {'checked' if self.hashes_verified else 'skipped'}",
            f"Mode              : {'export' if self.export_mode else 'normal'}"
            f"{' + strict' if self.strict else ''}",
            f"Status            : {self.status}",
        ]
        return "\n".join(lines)


def sha256_file(path: Path, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        while block := fh.read(chunk):
            h.update(block)
    return h.hexdigest()


class DatasetValidator:
    """Validates a set of records. Reports; never modifies.

    Args:
        data_root: directory ``image_path`` values are relative to. When ``None``,
            rules R2/E2 are skipped and the result records that they were skipped -
            a skipped check is never reported as a pass.
        verify_hashes: recompute SHA-256 for files that exist (E2).
        export_mode: enable R11, which blocks export of unknown-rights material.
        strict: warnings count as failure.
    """

    def __init__(
        self,
        schema: dict[str, Any] | None = None,
        *,
        data_root: Path | None = None,
        verify_hashes: bool = False,
        export_mode: bool = False,
        strict: bool = False,
    ) -> None:
        self.schema = schema or load_schema()
        self._json_validator = Draft202012Validator(self.schema)
        self.data_root = Path(data_root) if data_root else None
        self.verify_hashes = verify_hashes
        self.export_mode = export_mode
        self.strict = strict

    # -- entry point ----------------------------------------------------------

    def validate(self, records: Iterable[dict[str, Any]]) -> ValidationResult:
        records = list(records)
        result = ValidationResult(
            record_count=len(records),
            images_checked=self.data_root is not None,
            hashes_verified=bool(self.verify_hashes and self.data_root),
            export_mode=self.export_mode,
            strict=self.strict,
        )
        findings: list[Finding] = []

        for idx, record in enumerate(records):
            if not isinstance(record, dict):
                findings.append(Finding("E1", "error",
                                        f"record is {type(record).__name__}, expected object",
                                        record_index=idx))
                continue
            findings.extend(self._record_findings(record, idx))

        findings.extend(self._dataset_findings(records))

        result.findings = sorted(findings, key=lambda f: f.sort_key)
        return result

    # -- per-record -----------------------------------------------------------

    def _record_findings(self, rec: dict[str, Any], idx: int) -> list[Finding]:
        iid = rec.get("image_id") if isinstance(rec.get("image_id"), str) else None
        out: list[Finding] = []

        def add(rule: str, sev: Severity, msg: str, fld: str | None = None) -> None:
            out.append(Finding(rule, sev, msg, image_id=iid, field=fld, record_index=idx))

        # E1 - schema conformance. Catches missing required fields, empty strings,
        # year zero, bad enum values (view, script_type, ...), and unknown fields.
        for err in sorted(self._json_validator.iter_errors(rec), key=lambda e: list(e.path)):
            path = ".".join(str(p) for p in err.path) or None
            add("E1", "error", err.message, path)

        # E4 - schema version compatibility (major version must match).
        declared = rec.get("schema_version")
        expected = self.schema.get("schema_version", "1.0.0")
        if isinstance(declared, str) and declared.split(".")[0] != expected.split(".")[0]:
            add("E4", "error",
                f"schema_version {declared} is incompatible with schema {expected}",
                "schema_version")

        # E3 - image_path hygiene.
        path_value = rec.get("image_path")
        if isinstance(path_value, str) and path_value:
            if "\\" in path_value:
                add("E3", "error", "use forward slashes, not backslashes", "image_path")
            if path_value.startswith("/") or (len(path_value) > 1 and path_value[1] == ":"):
                add("E3", "error", "must be relative to data/raw/, not absolute", "image_path")
            if ".." in Path(path_value.replace("\\", "/")).parts:
                add("E3", "error", "must not traverse outside data/raw/ ('..')", "image_path")

        # R2 / E2 - file existence and hash agreement.
        if self.data_root is not None and isinstance(path_value, str) and path_value:
            full = self.data_root / path_value
            if not full.is_file():
                add("R2", "error", f"image file not found: {full}", "image_path")
            elif self.verify_hashes and has_real_value(rec, "image_sha256"):
                actual = sha256_file(full)
                if actual != rec["image_sha256"]:
                    add("E2", "error",
                        f"recorded hash {rec['image_sha256'][:12]}... does not match "
                        f"file hash {actual[:12]}...", "image_sha256")

        # R5 - no inscription means no script.
        if rec.get("inscription_present") == "no" and rec.get("script_type") != "none":
            add("R5", "error",
                f"inscription_present='no' but script_type='{rec.get('script_type')}'",
                "script_type")

        # R6 - no script means the reading fields do not apply.
        if rec.get("script_type") == "none":
            for fld in _R6_FIELDS:
                if fld in rec and rec[fld] != "not_applicable":
                    add("R6", "error",
                        f"script_type='none' requires {fld}='not_applicable', "
                        f"got {rec[fld]!r}", fld)

        # R7 - 'other_script' must say which script.
        if rec.get("script_type") == "other_script" and not has_real_value(rec, "script_type_other_detail"):
            add("R7", "error",
                "script_type='other_script' requires script_type_other_detail "
                "to name the script", "script_type_other_detail")

        # R8 - date bounds ordered.
        lo, hi = rec.get("dating_lower_year"), rec.get("dating_upper_year")
        if isinstance(lo, int) and isinstance(hi, int) and lo > hi:
            add("R8", "error",
                f"dating_lower_year ({lo}) is later than dating_upper_year ({hi})",
                "dating_lower_year")

        # R9 - a numeric date needs a citation.
        if (isinstance(lo, int) or isinstance(hi, int)) and not has_real_value(rec, "dating_source"):
            add("R9", "error",
                "a numeric dating bound is given but dating_source is absent or a sentinel",
                "dating_source")

        # R10 - stratigraphic dating requires a stratified context.
        basis = rec.get("dating_basis")
        if isinstance(basis, list) and "stratigraphy" in basis:
            ctx = rec.get("context_reliability")
            if ctx != "excavated_stratified":
                add("R10", "error",
                    f"dating_basis includes 'stratigraphy' but context_reliability is "
                    f"{ctx!r}; a surface or unprovenanced find carries no stratigraphic date",
                    "context_reliability")

        # R11 - unknown rights block export.
        if self.export_mode and rec.get("redistributable") != "yes":
            add("R11", "error",
                f"redistributable={rec.get('redistributable')!r}; only 'yes' may be exported "
                "(unknown rights are treated as 'no')", "redistributable")

        # R12 - exclusion needs a reason.
        if rec.get("split") == "excluded" and not has_real_value(rec, "split_exclusion_reason"):
            add("R12", "error",
                "split='excluded' requires split_exclusion_reason", "split_exclusion_reason")

        # R13 - regions inside the image.
        regions = rec.get("inscription_regions")
        w, h = rec.get("image_width_px"), rec.get("image_height_px")
        if isinstance(regions, list) and isinstance(w, int) and isinstance(h, int):
            for i, reg in enumerate(regions):
                if not isinstance(reg, dict):
                    continue
                rx, ry = reg.get("x"), reg.get("y")
                rw, rh = reg.get("w"), reg.get("h")
                if not all(isinstance(v, int) for v in (rx, ry, rw, rh)):
                    continue
                if rx + rw > w or ry + rh > h:
                    add("R13", "error",
                        f"region {i} extends to ({rx + rw}, {ry + rh}), outside the "
                        f"{w}x{h} image", f"inscription_regions.{i}")

        # R14 - unverified labels in the test split (warning).
        if rec.get("split") == "test" and rec.get("label_source") == "project_annotation_unverified":
            add("R14", "warning",
                "test-split record carries an unverified project annotation; test labels "
                "should be source-backed or the metric measures annotator agreement",
                "label_source")

        # R15 - recommended fields absent rather than sentinel-filled (warning).
        for fld in RECOMMENDED_FIELDS:
            if fld not in rec:
                add("R15", "warning",
                    f"recommended field '{fld}' is absent; use an explicit sentinel "
                    f"({'/'.join(sorted(SENTINELS))}) rather than omitting it", fld)

        return out

    # -- dataset-wide ---------------------------------------------------------

    def _dataset_findings(self, records: list[dict[str, Any]]) -> list[Finding]:
        out: list[Finding] = []

        seen_ids: dict[str, int] = {}
        splits: dict[str, dict[str, int]] = defaultdict(dict)
        hash_owner: dict[str, tuple[str, str, int]] = {}  # hash -> (artifact, image_id, idx)

        for idx, rec in enumerate(records):
            if not isinstance(rec, dict):
                continue
            iid = rec.get("image_id")
            aid = rec.get("artifact_id")

            # R1 - image_id unique.
            if isinstance(iid, str):
                if iid in seen_ids:
                    out.append(Finding("R1", "error",
                                       f"duplicate image_id, first seen at record "
                                       f"[{seen_ids[iid]}]", iid, "image_id", idx))
                else:
                    seen_ids[iid] = idx

            # R3 - one artifact, one split.
            if isinstance(aid, str) and isinstance(rec.get("split"), str):
                splits[aid][rec["split"]] = idx

            # R4 / E5 - photograph identity.
            h = rec.get("image_sha256")
            if isinstance(h, str) and h not in SENTINELS and isinstance(aid, str):
                prev = hash_owner.get(h)
                if prev is None:
                    hash_owner[h] = (aid, iid if isinstance(iid, str) else "", idx)
                elif prev[0] != aid:
                    out.append(Finding("R4", "error",
                                       f"identical photograph (sha256 {h[:12]}...) is also "
                                       f"recorded under artifact_id '{prev[0]}' as "
                                       f"'{prev[1]}'; the same image cannot belong to two "
                                       f"artifacts without leaking across splits",
                                       iid if isinstance(iid, str) else None,
                                       "image_sha256", idx))
                else:
                    out.append(Finding("E5", "warning",
                                       f"duplicate photograph (sha256 {h[:12]}...) within "
                                       f"artifact '{aid}', already recorded as '{prev[1]}'",
                                       iid if isinstance(iid, str) else None,
                                       "image_sha256", idx))

        for aid, found in sorted(splits.items()):
            if len(found) > 1:
                where = ", ".join(f"{s} (record [{i}])" for s, i in sorted(found.items()))
                out.append(Finding("R3", "error",
                                   f"artifact '{aid}' is spread across multiple splits: "
                                   f"{where}. All photographs of one physical object must "
                                   f"share a split.",
                                   None, "split", min(found.values())))

        return out


def validate_records(
    records: Iterable[dict[str, Any]],
    *,
    data_root: Path | None = None,
    verify_hashes: bool = False,
    export_mode: bool = False,
    strict: bool = False,
    schema: dict[str, Any] | None = None,
) -> ValidationResult:
    """Convenience wrapper around :class:`DatasetValidator`."""
    return DatasetValidator(
        schema,
        data_root=data_root,
        verify_hashes=verify_hashes,
        export_mode=export_mode,
        strict=strict,
    ).validate(records)


def missing_required(record: dict[str, Any]) -> list[str]:
    """Required fields absent from a record. Exposed for clearer error messages."""
    return [f for f in required_fields() if f not in record]


__all__ = [
    "RECOMMENDED_FIELDS",
    "RULE_TITLES",
    "DatasetValidator",
    "Finding",
    "ValidationResult",
    "is_sentinel",
    "missing_required",
    "sha256_file",
    "validate_records",
]
