"""Acquisition pipeline: web source -> licence gate -> download -> checks -> data/.

    plan (curated YAML)
      -> describe      metadata + licence read from the source API (never typed by hand)
      -> policy        A1-A9; any failure rejects the file, with reasons
      -> [dry run stops here and reports sizes]
      -> download      into a staging directory under data/interim/, size-capped
      -> verify        source checksum (Commons SHA-1) must match the bytes
      -> image checks  Milestone 3 loader: format, decode, dimensions, corruption (P1-P7)
      -> SHA-256       computed from the bytes
      -> duplicates    against records.jsonl, the provenance registry and the batch
      -> provenance    record built and validated against its schema
      -> place         path-safe move into data/raw/<subdir> or data/external/<subdir>;
                       never overwrites a different file
      -> records       research targets only: image_record built, validated and ingested
                       through src.dataset.ingest (rolled back if ingestion refuses)
      -> registry      provenance registry and dataset manifest updated

Research images get **no project label**: ``script_type`` and ``inscription_present``
are ``unknown`` (schema 1.2.0). The source's own title and description are kept verbatim
as ``source_label``. Anything the curator observed in an image is stored as a
``curation_note`` explicitly marked as an AI-assisted observation, never as a label.
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
from dataclasses import asdict, dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

import yaml

from src.dataset.convert import read_jsonl, write_jsonl
from src.dataset.ingest import ingest
from src.dataset.schema import (
    RESEARCH_DATA_ROOT,
    RESEARCH_RECORDS_PATH,
    ROOT,
    load_schema,
)
from src.dataset.validation import validate_records
from src.preprocessing.loader import load_image

from .commons import Fetcher
from .policy import Candidate, Decision, evaluate
from .provenance import (
    ACQUISITION_DIR,
    build_manifest,
    provenance_errors,
    read_registry,
    write_registry,
)

EXTERNAL_ROOT = ROOT / "data" / "external"
STAGING_ROOT = ROOT / "data" / "interim" / "acquisition_staging"
MIME_EXT = {"image/jpeg": ".jpg", "image/png": ".png", "image/tiff": ".tif", "image/webp": ".webp"}
NO_LABEL_BASIS = ("no project label assigned: requires expert epigraphic/archaeological "
                  "annotation; not derived from the source caption or from AI observation")


class PlanError(ValueError):
    """The acquisition plan is malformed."""


# --------------------------------------------------------------------------- #
# Plan
# --------------------------------------------------------------------------- #


@dataclass
class ItemPlan:
    title: str
    artifact_group: str
    grouping_basis: str
    object_type: str
    curation_note: str
    find_site: str = "not_stated_by_source"
    geographic_scope: str | None = None
    archaeological_period: str | None = None
    script_scope: str | None = None
    record: dict[str, Any] = field(default_factory=dict)


@dataclass
class DatasetPlan:
    dataset_id: str
    dataset_name: str
    target: str                 # research | external
    subdir: str
    source: str
    source_name: str
    source_url: str
    geographic_scope: str
    archaeological_period: str
    script_scope: str
    items: list[ItemPlan]
    excluded: dict[str, str] = field(default_factory=dict)
    notes: str = ""


@dataclass
class Plan:
    curator: str
    datasets: list[DatasetPlan]
    max_file_mb: float = 40.0
    max_total_mb: float = 500.0


_SAFE_SUBDIR = re.compile(r"^[a-z0-9_]+(/[a-z0-9_]+)*$")


def load_plan(path: Path | str) -> Plan:
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    try:
        datasets = []
        for d in data["datasets"]:
            items = [ItemPlan(**i) for i in d.pop("items")]
            ds = DatasetPlan(items=items, **d)
            if ds.target not in ("research", "external"):
                raise PlanError(f"{ds.dataset_id}: target must be research or external")
            if not _SAFE_SUBDIR.match(ds.subdir):
                raise PlanError(f"{ds.dataset_id}: unsafe subdir {ds.subdir!r}")
            titles = [i.title for i in items]
            if len(titles) != len(set(titles)):
                raise PlanError(f"{ds.dataset_id}: duplicate titles in plan")
            datasets.append(ds)
        return Plan(curator=data["curator"], datasets=datasets,
                    max_file_mb=float(data.get("max_file_mb", 40)),
                    max_total_mb=float(data.get("max_total_mb", 500)))
    except (KeyError, TypeError) as exc:
        raise PlanError(f"malformed plan {path}: {exc}") from exc


# --------------------------------------------------------------------------- #
# Results
# --------------------------------------------------------------------------- #


@dataclass
class ItemResult:
    dataset_id: str
    title: str
    status: str                  # planned | acquired | already_present | rejected | failed
    reasons: list[str] = field(default_factory=list)
    license: str = ""
    size_bytes: int = 0
    image_id: str = ""
    local_path: str = ""
    sha256: str = ""


@dataclass
class AcquisitionReport:
    dry_run: bool
    items: list[ItemResult] = field(default_factory=list)
    ingestion: dict[str, str] = field(default_factory=dict)
    manifests: list[str] = field(default_factory=list)

    def count(self, status: str) -> int:
        return sum(1 for i in self.items if i.status == status)

    @property
    def planned_bytes(self) -> int:
        return sum(i.size_bytes for i in self.items if i.status in ("planned", "acquired"))

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def render(self) -> str:
        L = ["=" * 72, f"ACQUISITION {'DRY RUN' if self.dry_run else 'RUN'}", "=" * 72]
        for i in self.items:
            size = f"{i.size_bytes / 2**20:6.1f} MB" if i.size_bytes else "      -  "
            L.append(f"[{i.status:<15}] {size} {i.license:<13} {i.title[5:70]}")
            L += [f"      - {r}" for r in i.reasons]
        L.append("")
        for s in ("planned", "acquired", "already_present", "rejected", "failed"):
            L.append(f"{s:<16}: {self.count(s)}")
        L.append(f"{'bytes':<16}: {self.planned_bytes / 2**20:.1f} MB")
        for k, v in self.ingestion.items():
            L.append(f"ingestion {k}: {v}")
        L += [f"manifest: {m}" for m in self.manifests]
        L.append("=" * 72)
        return "\n".join(L)


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


def _slug(title: str, limit: int = 60) -> str:
    stem = Path(title.split(":", 1)[-1]).stem
    s = re.sub(r"[^A-Za-z0-9]+", "_", stem).strip("_")
    return (s[:limit].rstrip("_") or "file")


def image_id_for(c: Candidate) -> str:
    prefix = {"wikimedia_commons": "wmc"}.get(c.source, "src")
    return f"{prefix}_{c.record_id}"


def safe_destination(root: Path, subdir: str, filename: str) -> Path:
    """Resolve root/subdir/filename and refuse anything escaping ``root``."""
    if "/" in filename or "\\" in filename or filename.startswith("."):
        raise PlanError(f"unsafe filename {filename!r}")
    dest = (root / subdir / filename).resolve()
    dest.relative_to(root.resolve())       # raises ValueError if it escapes
    return dest


def _rel(path: Path) -> str:
    return path.resolve().relative_to(ROOT.resolve()).as_posix()


def _existing_hashes(records_path: Path, registry: list[dict[str, Any]]) -> dict[str, str]:
    seen = {p["image_sha256"]: p["image_id"] for p in registry}
    if records_path.exists():
        for r in read_jsonl(records_path):
            h = r.get("image_sha256")
            if isinstance(h, str) and len(h) == 64:
                seen.setdefault(h, r.get("image_id", "?"))
    return seen


def build_provenance(ds: DatasetPlan, item: ItemPlan, c: Candidate, decision: Decision, *,
                     image_id: str, sha256: str, checksum_ok: bool, local: str,
                     curator: str, today: str) -> dict[str, Any]:
    lic = decision.license
    holder = c.artist.strip()
    attribution = (f"\"{c.title.split(':', 1)[-1]}\" by {holder}, {lic.license_id} "
                   f"({lic.license_url}), via Wikimedia Commons: {c.source_url}")
    source_label = f"{c.title} | {c.description}" if c.description else c.title
    return {
        "provenance_version": "1.0.0",
        "image_id": image_id,
        "target": ds.target,
        "dataset_id": ds.dataset_id,
        "dataset_name": ds.dataset_name,
        "source_name": ds.source_name,
        "source_url": c.source_url,
        "dataset_record_id": f"commons_pageid:{c.record_id}",
        "original_image_url": c.original_image_url,
        "download_date": today,
        "license": lic.license_id,
        "license_url": c.extra.get("license_url") or lic.license_url,
        "license_verbatim": lic.verbatim,
        "license_verified_from": "wikimedia_commons_api:imageinfo.extmetadata.LicenseShortName",
        "copyright_holder": holder,
        "attribution_text": attribution,
        "attribution_required": lic.attribution_required,
        "share_alike_required": lic.share_alike_required,
        "redistribution_allowed": lic.redistribution_allowed,
        "research_usable": lic.research_usable,
        "commercially_usable": lic.commercially_usable,
        "source_label": source_label,
        "source_categories": c.categories,
        "project_label": "unknown",
        "project_label_basis": NO_LABEL_BASIS,
        "geographic_scope": item.geographic_scope or ds.geographic_scope,
        "find_site": item.find_site,
        "archaeological_period": item.archaeological_period or ds.archaeological_period,
        "object_type": item.object_type,
        "script_scope": item.script_scope or ds.script_scope,
        "image_sha256": sha256,
        "source_checksum": c.checksum,
        "source_checksum_verified": checksum_ok,
        "file_size_bytes": c.size_bytes,
        "mime_type": c.mime,
        "width_px": c.width,
        "height_px": c.height,
        "local_path": local,
        "artifact_group_id": item.artifact_group,
        "grouping_basis": item.grouping_basis,
        "curation_note": item.curation_note,
        "curator": curator,
    }


def build_research_record(prov: dict[str, Any], item: ItemPlan) -> dict[str, Any]:
    """An image_record for data/metadata/records.jsonl. No label is asserted."""
    r = item.record
    if not prov["local_path"].startswith("data/raw/"):
        raise PlanError(f"{prov['image_id']}: research records must live under data/raw/")
    rec = {
        "schema_version": load_schema().get("schema_version", "1.2.0"),
        "image_id": prov["image_id"],
        "artifact_id": prov["artifact_group_id"],
        "image_path": prov["local_path"].removeprefix("data/raw/"),
        "image_sha256": prov["image_sha256"],
        "view": "unknown",
        "image_width_px": prov["width_px"],
        "image_height_px": prov["height_px"],
        "scale_bar_present": "unknown",
        "source": "online_repository",
        "source_reference": prov["source_url"],
        "collection": r.get("collection", "not_available"),
        "catalogue_reference": "not_available",
        "license": prov["license"],
        "redistributable": prov["redistribution_allowed"],
        "research_usable": prov["research_usable"],
        "commercially_usable": prov["commercially_usable"],
        "rights_notes": f"Attribution required: {prov['attribution_text']}"
                        + (" Share-alike applies to adaptations." if prov["share_alike_required"] else ""),
        "site": r.get("site", "not_available"),
        "site_district": r.get("site_district", "not_available"),
        "site_state": r.get("site_state", "not_available"),
        "excavation_reference": "not_available",
        "stratigraphic_context": "not_available",
        "context_reliability": r.get("context_reliability", "unknown"),
        "artifact_type": "unknown",
        "pottery_type": r.get("pottery_type", "unknown"),
        "sherd_part": "unknown",
        "fabric_notes": "not_available",
        "surface_treatment": "unknown",
        "inscription_present": "unknown",
        "script_type": "unknown",
        "script_type_other_detail": "not_applicable",
        "label_source": "unknown",
        "label_confidence": "unknown",
        "inscription_technique": "unknown",
        "inscription_placement": "unknown",
        "inscription_regions": [],
        "character_count_visible": None,
        "transcription": "not_available",
        "transcription_encoding": "not_available",
        "transliteration": "not_available",
        "transliteration_scheme": "not_available",
        "translation_en": "not_available",
        "translation_ta": "not_available",
        "reading_status": "unknown",
        "alternative_readings": [],
        "reading_source": "not_available",
        "dating_text": "not_available",
        "dating_lower_year": None,
        "dating_upper_year": None,
        "dating_basis": ["not_available"],
        "dating_reliability": "unknown",
        "dating_source": "not_available",
        "publication": "not_applicable",
        "publication_doi_or_url": "not_applicable",
        "split": "unassigned",
        "split_exclusion_reason": "not_applicable",
        "verification_status": "unverified",
        "annotator": "not_applicable",
        "annotation_date": "not_applicable",
        "notes": ("Acquired Milestone 6 from a public, openly licensed source. NO project label: "
                  "script_type/inscription_present are 'unknown' pending expert annotation. "
                  f"Source label (verbatim): {prov['source_label'][:300]}. "
                  f"Artifact grouping: {prov['grouping_basis']}. "
                  "Full provenance: data/metadata/acquisition/provenance.jsonl."),
    }
    return rec


# --------------------------------------------------------------------------- #
# Run
# --------------------------------------------------------------------------- #


def run(
    plan: Plan,
    fetcher: Fetcher,
    *,
    dry_run: bool = True,
    raw_root: Path = RESEARCH_DATA_ROOT,
    external_root: Path = EXTERNAL_ROOT,
    staging_root: Path = STAGING_ROOT,
    records_path: Path = RESEARCH_RECORDS_PATH,
    acquisition_dir: Path = ACQUISITION_DIR,
    today: str | None = None,
) -> AcquisitionReport:
    today = today or date.today().isoformat()
    report = AcquisitionReport(dry_run=dry_run)
    max_file = int(plan.max_file_mb * 2**20)
    registry_path = acquisition_dir / "provenance.jsonl"
    registry = read_registry(registry_path)
    known = _existing_hashes(records_path, registry)
    reg_by_id = {p["image_id"]: p for p in registry}

    # -- describe + policy, for every dataset, before anything is downloaded --------
    described: list[tuple[DatasetPlan, ItemPlan, Candidate | None, Decision | None]] = []
    for ds in plan.datasets:
        meta = fetcher.describe([i.title for i in ds.items])
        for item in ds.items:
            c = meta.get(item.title)
            if c is None:
                report.items.append(ItemResult(ds.dataset_id, item.title, "rejected",
                                               ["A6: file not found at the source"]))
                described.append((ds, item, None, None))
                continue
            d = evaluate(c, max_file_bytes=max_file, excluded=ds.excluded)
            res = ItemResult(ds.dataset_id, item.title, "planned" if d.accepted else "rejected",
                             [] if d.accepted else d.reasons, d.license.license_id, c.size_bytes,
                             image_id_for(c))
            if d.accepted and res.image_id in reg_by_id:
                res.status, res.local_path = "already_present", reg_by_id[res.image_id]["local_path"]
            report.items.append(res)
            described.append((ds, item, c, d))

    if report.planned_bytes > plan.max_total_mb * 2**20:
        for r in report.items:
            if r.status == "planned":
                r.status, r.reasons = "rejected", [
                    (f"batch total {report.planned_bytes / 2**20:.0f} MB exceeds max_total_mb "
                     f"{plan.max_total_mb}; review before a large download")]
        return report
    if dry_run:
        return report

    # -- download, verify, place ------------------------------------------------------
    results = {(r.dataset_id, r.title): r for r in report.items}
    new_prov: dict[str, list[tuple[dict[str, Any], ItemPlan]]] = {}
    placed: dict[str, Path] = {}
    for ds, item, c, d in described:
        res = results[(ds.dataset_id, item.title)]
        if res.status != "planned" or c is None or d is None:
            continue
        try:
            data = fetcher.download(c.original_image_url, max_file)
            algo, _, expected = c.checksum.partition(":")
            actual = hashlib.new(algo, data).hexdigest()
            if actual != expected:
                raise ValueError(f"checksum mismatch: source {c.checksum}, got {algo}:{actual}")
            sha256 = hashlib.sha256(data).hexdigest()
            if sha256 in known:
                raise ValueError(f"duplicate image: identical bytes already recorded as {known[sha256]}")
            ext = MIME_EXT[c.mime]
            filename = f"{res.image_id}_{_slug(c.title)}{ext}"
            staging = safe_destination(staging_root, ds.subdir, filename)
            staging.parent.mkdir(parents=True, exist_ok=True)
            staging.write_bytes(data)
            loaded = load_image(staging)
            if not loaded.ok:
                staging.unlink(missing_ok=True)
                raise ValueError("image checks failed: " + "; ".join(
                    f"{i.code} {i.message}" for i in loaded.issues if i.severity == "error"))
            root = raw_root if ds.target == "research" else external_root
            dest = safe_destination(root, ds.subdir, filename)
            if dest.exists():
                raise ValueError(f"destination exists, refusing to overwrite: {dest}")
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(staging), dest)
            logical = f"data/{'raw' if ds.target == 'research' else 'external'}/{ds.subdir}/{filename}"
            prov = build_provenance(ds, item, c, d, image_id=res.image_id, sha256=sha256,
                                    checksum_ok=True, local=logical, curator=plan.curator,
                                    today=today)
            errors = provenance_errors(prov)
            if errors:
                dest.unlink(missing_ok=True)
                raise ValueError("provenance invalid: " + "; ".join(errors[:3]))
            placed[res.image_id] = dest
            known[sha256] = res.image_id
            res.status, res.sha256, res.local_path = "acquired", sha256, prov["local_path"]
            new_prov.setdefault(ds.dataset_id, []).append((prov, item))
        except Exception as exc:  # noqa: BLE001 - every failure is reported per file
            res.status, res.reasons = "failed", [str(exc)]

    # -- research records via the existing ingestion pipeline -------------------------
    for ds in plan.datasets:
        batch = new_prov.get(ds.dataset_id, [])
        if ds.target == "research" and batch:
            records = [build_research_record(p, it) for p, it in batch]
            check = validate_records(records, data_root=raw_root, verify_hashes=True)
            batch_path = acquisition_dir / "batches" / f"{ds.dataset_id}_{today}.jsonl"
            batch_path.parent.mkdir(parents=True, exist_ok=True)
            write_jsonl(batch_path, records)
            result = ingest(batch_path, destination=records_path, data_root=raw_root,
                            verify_hashes=True, commit=check.ok)
            report.ingestion[ds.dataset_id] = f"{'ACCEPTED' if result.accepted else 'REJECTED'}: {result.reason}"
            if not (check.ok and result.accepted and result.committed):
                for p, _ in batch:                       # roll back: no file without a record
                    placed[p["image_id"]].unlink(missing_ok=True)
                if not check.ok:
                    report.ingestion[ds.dataset_id] += " | pre-check: " + "; ".join(
                        str(f) for f in check.errors[:3])
                for r in report.items:
                    if r.dataset_id == ds.dataset_id and r.status == "acquired":
                        r.status, r.reasons = "failed", ["ingestion refused; file removed"]
                new_prov[ds.dataset_id] = []

    # -- clear staging: nothing downloaded may linger outside data/raw or data/external --
    if staging_root.exists():
        for leftover in staging_root.rglob("*"):
            if leftover.is_file():
                leftover.unlink()
        shutil.rmtree(staging_root, ignore_errors=True)

    # -- registry + manifests ----------------------------------------------------------
    for batch in new_prov.values():
        for p, _ in batch:
            reg_by_id[p["image_id"]] = p
    if any(new_prov.values()):
        write_registry(list(reg_by_id.values()), registry_path)
    for ds in plan.datasets:
        provs = [p for p in reg_by_id.values() if p["dataset_id"] == ds.dataset_id]
        if not provs:
            continue
        root = "data/raw" if ds.target == "research" else "data/external"
        manifest = build_manifest({**asdict(ds), "local_directory": f"{root}/{ds.subdir}"}, provs)
        out = acquisition_dir / "manifests" / f"{ds.dataset_id}.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        report.manifests.append(_rel(out) if out.resolve().is_relative_to(ROOT.resolve()) else str(out))
    return report


__all__ = ["AcquisitionReport", "DatasetPlan", "ItemPlan", "ItemResult", "Plan", "PlanError",
           "build_provenance", "build_research_record", "image_id_for", "load_plan", "run",
           "safe_destination"]
