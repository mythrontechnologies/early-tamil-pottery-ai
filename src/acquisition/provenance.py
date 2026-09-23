"""Provenance records, the provenance registry and dataset manifests."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

from src.dataset.schema import ROOT

PROVENANCE_SCHEMA_PATH = ROOT / "data" / "metadata" / "schema" / "acquisition_provenance.schema.json"
ACQUISITION_DIR = ROOT / "data" / "metadata" / "acquisition"
PROVENANCE_REGISTRY = ACQUISITION_DIR / "provenance.jsonl"


@lru_cache(maxsize=1)
def _validator() -> Draft202012Validator:
    return Draft202012Validator(json.loads(PROVENANCE_SCHEMA_PATH.read_text(encoding="utf-8")))


def provenance_errors(record: dict[str, Any]) -> list[str]:
    """Schema errors for one provenance record (empty list = valid)."""
    return [f"{'.'.join(map(str, e.path)) or '<record>'}: {e.message}"
            for e in sorted(_validator().iter_errors(record), key=lambda e: list(e.path))]


def read_registry(path: Path | None = None) -> list[dict[str, Any]]:
    path = path or PROVENANCE_REGISTRY
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def write_registry(records: list[dict[str, Any]], path: Path | None = None) -> Path:
    """Rewrite the registry, one record per image_id, sorted for stable diffs."""
    path = path or PROVENANCE_REGISTRY
    path.parent.mkdir(parents=True, exist_ok=True)
    by_id = {r["image_id"]: r for r in records}
    body = "".join(json.dumps(by_id[k], ensure_ascii=False, sort_keys=True) + "\n"
                   for k in sorted(by_id))
    tmp = path.with_suffix(".tmp")
    tmp.write_text(body, encoding="utf-8")
    tmp.replace(path)
    return path


def build_manifest(dataset: dict[str, Any], provenance: list[dict[str, Any]]) -> dict[str, Any]:
    """Dataset manifest. Every field is derived from provenance records; nothing is asserted
    that the records (and therefore the source) do not establish."""
    def distinct(key: str) -> list[Any]:
        return sorted({p[key] for p in provenance}, key=str)

    licences = distinct("license")
    return {
        "manifest_version": "1.0.0",
        "dataset_id": dataset["dataset_id"],
        "dataset_name": dataset["dataset_name"],
        "target": dataset["target"],
        "source_name": dataset["source_name"],
        "source_url": dataset["source_url"],
        "local_directory": dataset["local_directory"],
        "license": licences,
        "license_url": sorted({p["license_url"] for p in provenance}),
        "rights_holder": distinct("copyright_holder"),
        "download_date": distinct("download_date"),
        "number_of_files": len(provenance),
        "number_of_artifacts": len({p["artifact_group_id"] for p in provenance}),
        "number_of_unique_images": len({p["image_sha256"] for p in provenance}),
        "geographic_scope": distinct("geographic_scope"),
        "period_scope": distinct("archaeological_period"),
        "object_scope": distinct("object_type"),
        "script_scope": distinct("script_scope"),
        "project_labels": distinct("project_label"),
        "research_usable": distinct("research_usable"),
        "redistribution_allowed": distinct("redistribution_allowed"),
        "commercially_usable": distinct("commercially_usable"),
        "attribution_requirements": sorted({p["attribution_text"] for p in provenance
                                            if p["attribution_required"]}),
        "share_alike_required": any(p["share_alike_required"] for p in provenance),
        "notes": dataset.get("notes", ""),
    }


__all__ = ["ACQUISITION_DIR", "PROVENANCE_REGISTRY", "PROVENANCE_SCHEMA_PATH",
           "build_manifest", "provenance_errors", "read_registry", "write_registry"]
