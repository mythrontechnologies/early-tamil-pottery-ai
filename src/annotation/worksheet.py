"""Annotation queue, worksheet round trip, field-level disagreement report and export (Milestone 11).

Everything here exists so that a person with no developer at hand can annotate:

* ``annotation_queue``   every research artifact, its annotation state and the next HUMAN step
* ``build_worksheets``   blank CSV worksheets (project annotator / expert) for any set of artifacts
* ``import_worksheet``   a filled worksheet -> validated annotations (all-or-nothing, dry run first)
* ``disagreement_report`` field by field, who said what; nothing is resolved here
* ``export_annotations``  the current annotations, each row labelled with its provenance tier

A worksheet row is ONE photograph. Rows of one artifact by one annotator become ONE annotation;
the artifact-level answers must then agree across those rows. Nothing is inferred: a blank cell
stays ``unknown`` / ``not_available``, and a worksheet never sets ``expert_reviewed`` for a
project annotator (rule N4). Free-text regions cannot be turned into coordinates; only the
explicit form ``x,y,w,h label`` (fractions of the image) becomes a region, anything else is kept
as a note and the annotator marks the region in the tool.
"""

from __future__ import annotations

import csv
import json
import re
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .model import (
    EVIDENCE_TYPES,
    PROVENANCE_ROLE,
    blank_annotation,
    utc_now,
)
from .resolve import resolve_artifact
from .store import AnnotationStore
from .validate import Problem

ROLES = {"project": "project_annotation", "expert": "expert_annotation"}
WORKSHEET_BASE = ("artifact_id", "image_id", "local_path", "source_page", "license", "attribution")

#: Human next step per resolution status.
NEXT_STEP = {
    "unannotated": "project annotator AND expert annotate independently",
    "provisional": "an expert annotates (a project label never becomes ground truth)",
    "project_disagreement": "an expert annotates; the project disagreement stays on record",
    "disputed": "an expert adjudicates (annotation with an 'adjudication' block), or more evidence is needed",
    "expert_label": "promotion dry run, then human approval (python -m src.annotation promote)",
    "adjudicated": "promotion dry run, then human approval (python -m src.annotation promote)",
}


# --------------------------------------------------------------------------- #
# Queue
# --------------------------------------------------------------------------- #


@dataclass
class QueueRow:
    artifact_id: str
    image_ids: list[str]
    in_pilot: bool
    status: str
    tiers: dict[str, int]
    missing_tiers: list[str]
    review_flags: list[str]
    label: str | None
    promoted: bool
    next_step: str
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return self.__dict__.copy()


def annotation_queue(records: list[dict[str, Any]], current: list[dict[str, Any]],
                     pilot_artifacts: tuple[str, ...] = (), required_tiers: tuple[str, ...] = (
                         "project_annotation", "expert_annotation"),
                     flags: dict[str, list[Any]] | None = None) -> list[QueueRow]:
    """Every research artifact with its state. Pilot artifacts first, then by id. Reads only."""
    by_art: dict[str, list[str]] = defaultdict(list)
    promoted: dict[str, bool] = defaultdict(bool)
    for r in records:
        by_art[r["artifact_id"]].append(r["image_id"])
        promoted[r["artifact_id"]] |= r.get("label_source") == "expert_annotation"
    rows = []
    for art in sorted(by_art, key=lambda a: (a not in pilot_artifacts, a)):
        res = resolve_artifact(art, current)
        tiers: dict[str, int] = defaultdict(int)
        for a in current:
            if a["artifact_id"] == art and a["provenance_type"] != "ai_prediction":
                tiers[a["provenance_type"]] += 1
        missing = [t for t in required_tiers if not tiers.get(t)]
        step = "already promoted; reverse with promote --revert if needed" if promoted[art] else NEXT_STEP.get(
            res.status, "-")
        if res.status in ("provisional", "project_disagreement", "unannotated") and missing:
            step = f"missing: {', '.join(missing)}; {NEXT_STEP[res.status]}"
        rows.append(QueueRow(art, sorted(by_art[art]), art in pilot_artifacts, res.status, dict(tiers), missing,
                             [f"{f.label} ({'confirmed' if f.confirmed else 'unconfirmed'})"
                              for f in (flags or {}).get(art, [])],
                             res.label, promoted[art], step, list(res.notes)))
    return rows


# --------------------------------------------------------------------------- #
# Worksheets
# --------------------------------------------------------------------------- #


def worksheet_rows(records: list[dict[str, Any]], artifacts: list[str] | None = None) -> list[dict[str, str]]:
    keep = set(artifacts) if artifacts else None
    out = []
    for r in sorted(records, key=lambda r: (r["artifact_id"], r["image_id"])):
        if keep is not None and r["artifact_id"] not in keep:
            continue
        out.append({"artifact_id": r["artifact_id"], "image_id": r["image_id"],
                    "local_path": f"data/raw/{r['image_path']}",
                    "source_page": r.get("source_reference", "not_available"),
                    "license": r.get("license", "unknown"),
                    "attribution": r.get("rights_notes", "not_available")})
    return out


def build_worksheets(records: list[dict[str, Any]], out_dir: Path, artifacts: list[str] | None = None,
                     prefix: str = "worksheet") -> list[Path]:
    from .handoff import ANNOTATION_COLUMNS, EXPERT_COLUMNS, _write

    rows = worksheet_rows(records, artifacts)
    base = list(WORKSHEET_BASE)
    return [_write(Path(out_dir) / f"{prefix}_project_annotator.csv", base + list(ANNOTATION_COLUMNS), rows),
            _write(Path(out_dir) / f"{prefix}_expert.csv", base + list(EXPERT_COLUMNS) + list(ANNOTATION_COLUMNS),
                   rows)]


# --------------------------------------------------------------------------- #
# Import
# --------------------------------------------------------------------------- #


def _col(row: dict[str, str], name: str) -> str:
    for k, v in row.items():
        if k and k.split(" (")[0].strip() == name:
            return (v or "").strip()
    return ""


_REGION = re.compile(r"^\s*([0-9.]+)\s*,\s*([0-9.]+)\s*,\s*([0-9.]+)\s*,\s*([0-9.]+)\s+([a-z_]+)"
                     r"(?:\s+#(\d+))?(?:\s+'([^']*)')?\s*$")
_RANGE = re.compile(r"^\s*(-?\d{1,4})\s*(?:\.\.|to)\s*(-?\d{1,4})\s*$")
_CONF = {"high", "moderate", "low", "very_low"}


@dataclass
class WorksheetImport:
    annotations: list[dict[str, Any]]
    skipped_rows: int
    problems: list[str]

    @property
    def ok(self) -> bool:
        return not self.problems


def parse_regions(text: str, image_id: str) -> tuple[list[dict[str, Any]], str | None]:
    """``x,y,w,h label [#sign] ['reading']`` separated by ';'. Anything else -> returned as a note."""
    if not text:
        return [], None
    regions = []
    for part in [p for p in text.split(";") if p.strip()]:
        m = _REGION.match(part)
        if not m:
            return [], text
        x, y, w, h = (float(m.group(i)) for i in range(1, 5))
        reg: dict[str, Any] = {"image_id": image_id, "x": x, "y": y, "width": w, "height": h, "label": m.group(5)}
        if m.group(6):
            reg["sign_index"] = int(m.group(6))
        if m.group(7):
            reg["sign_reading"] = m.group(7)
        regions.append(reg)
    return regions, None


def parse_dating_evidence(text: str, association: str) -> list[dict[str, Any]]:
    """Rows separated by '|': ``type; observation; start..end or -; source``. Raises ValueError."""
    out = []
    assoc = {"object": "direct", "context only": "same_context_insecure", "context": "same_context_insecure",
             "neither": "not_established"}.get(association.lower(), association or "not_established")
    for i, part in enumerate([p for p in text.split("|") if p.strip()], 1):
        bits = [b.strip() for b in part.split(";")]
        if len(bits) != 4:
            raise ValueError(f"dating_evidence item {i}: expected 'type; observation; start..end or -; source', "
                             f"got {part.strip()!r}")
        etype, obs, rng, src = bits
        if etype not in EVIDENCE_TYPES:
            raise ValueError(f"dating_evidence item {i}: unknown evidence type {etype!r} ({', '.join(EVIDENCE_TYPES)})")
        ev: dict[str, Any] = {"evidence_id": f"E{i}", "evidence_type": etype, "observation": obs,
                              "confidence": "unknown", "source_reference": src or "annotator_observation"}
        if rng and rng != "-":
            m = _RANGE.match(rng)
            if not m:
                raise ValueError(f"dating_evidence item {i}: bounds {rng!r} are not 'start..end' signed years")
            ev["supports_start_year"], ev["supports_end_year"] = int(m.group(1)), int(m.group(2))
        if etype in ("stratigraphy", "absolute_dating"):
            ev["association"] = assoc
        out.append(ev)
    return out


def _references(text: str, kb_refs: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    from src.knowledge.verification import effective_statuses

    eff = effective_statuses()
    out = []
    for part in [p.strip() for p in re.split(r"[;,]", text) if p.strip()]:
        rid, _, loc = part.partition(" ")
        if rid not in kb_refs:
            raise ValueError(f"reference {rid!r} is not in the knowledge base (python -m src.knowledge status --all)")
        status = eff[rid].effective_status
        ref = {"ref_id": rid, "citation": kb_refs[rid]["citation"],
               "verification_status": status if status in ("verified_against_source", "bibliographic_only")
               else "unverified"}
        if loc.strip():
            ref["locator"] = loc.strip()
        out.append(ref)
    return out


def _fill(a: dict[str, Any], row: dict[str, str], image_id: str, kb_refs: dict[str, dict[str, Any]]) -> list[str]:
    """Write one worksheet row's answers into annotation ``a``. Returns problems."""
    probs: list[str] = []
    o, ins, it, d = a["object"], a["inscription"], a["interpretation"], a["dating"]
    notes = []

    def put(section: dict[str, Any], key: str, value: str) -> None:
        if not value:
            return
        if section.get(key) not in (None, "unknown", "not_available", "not_applicable", [], value):
            probs.append(f"{a['artifact_id']}: '{key}' differs between rows of one artifact "
                         f"({section[key]!r} vs {value!r}); artifact-level answers must agree")
            return
        section[key] = value

    put(o, "object_status", _col(row, "object_status"))
    if _col(row, "object_notes"):
        o["object_notes"] = _col(row, "object_notes")
    put(ins, "inscription_present", _col(row, "inscription_present"))
    put(ins, "script_type", _col(row, "script_type"))
    put(ins, "script_confidence", _col(row, "script_confidence"))
    put(ins, "inscription_type", _col(row, "inscription_type"))
    put(ins, "reading_completeness", _col(row, "reading_completeness"))
    cv = _col(row, "characters_visible")
    if cv:
        if not cv.isdigit():
            probs.append(f"{a['artifact_id']}/{image_id}: characters_visible {cv!r} is not a count")
        else:
            ins["characters_visible"] = int(cv)
    reading = _col(row, "reading")
    if reading:
        put(ins, "reading", reading)
        if ins.get("reading_source") in (None, "not_available"):
            ins["reading_source"] = "this_annotator"
    put(ins, "reading_confidence", _col(row, "reading_confidence"))
    for alt in [x.strip() for x in _col(row, "alternative_readings").split(";") if x.strip()]:
        m = re.match(r"^(.*?)\s*\(([^)]+)\)\s*$", alt)
        entry = {"reading": m.group(1), "source": m.group(2)} if m else {"reading": alt, "source": "this_annotator"}
        if entry not in ins["alternative_readings"]:
            ins["alternative_readings"].append(entry)
    if _col(row, "published_reading"):
        notes.append(f"published reading cited by the annotator: {_col(row, 'published_reading')}")
    regions, region_note = parse_regions(_col(row, "regions"), image_id)
    ins["regions"].extend(regions)
    if region_note:
        notes.append(f"regions described on {image_id} (mark them in the tool): {region_note}")
    put(it, "interpretation_type", _col(row, "interpretation_type"))
    if _col(row, "translation"):
        put(it, "translation", _col(row, "translation"))
    put(it, "translation_source", _col(row, "translation_source"))
    put(it, "translation_confidence", _col(row, "translation_confidence"))
    if _col(row, "meaning"):
        it["meaning"] = _col(row, "meaning")
    if _col(row, "linguistic_observations"):
        notes.append(f"linguistic observations: {_col(row, 'linguistic_observations')}")
    try:
        evidence = parse_dating_evidence(_col(row, "dating_evidence"), _col(row, "dating_object_or_context"))
    except ValueError as exc:
        probs.append(f"{a['artifact_id']}/{image_id}: {exc}")
        evidence = []
    if evidence and not d["dating_evidence"]:
        d["dating_evidence"] = evidence
        d["dating_basis"] = sorted({e["evidence_type"] for e in evidence})
    rng = _col(row, "dating_range")
    if rng and rng.lower() != "insufficient evidence":
        m = _RANGE.match(rng)
        if not m:
            probs.append(f"{a['artifact_id']}/{image_id}: dating_range {rng!r} is not 'start..end' signed years "
                         "or 'Insufficient evidence'")
        else:
            d["estimated_start_year"], d["estimated_end_year"] = int(m.group(1)), int(m.group(2))
    conf = _col(row, "dating_confidence")
    if conf:
        d["dating_confidence"] = conf
        for e in d["dating_evidence"]:
            if conf in _CONF:
                e["confidence"] = conf
    if _col(row, "dating_unresolved_conflict"):
        d["unresolved_conflict"] = _col(row, "dating_unresolved_conflict")
    if _col(row, "references"):
        try:
            for ref in _references(_col(row, "references"), kb_refs):
                if ref["ref_id"] not in {r["ref_id"] for r in a["references"]}:
                    a["references"].append(ref)
        except ValueError as exc:
            probs.append(f"{a['artifact_id']}/{image_id}: {exc}")
    usable = _col(row, "usable_for_annotation")
    if usable:
        a["image_usability"].append({"image_id": image_id, "usable_for_annotation": usable})
    if _col(row, "uncertainty_notes"):
        a["uncertainty_notes"] = _col(row, "uncertainty_notes")
    if notes:
        a["notes"] = " | ".join(([a["notes"]] if a.get("notes") else []) + notes)
    return probs


def import_worksheet(path: Path, role: str, store: AnnotationStore, *, revise: bool = False,
                     kb_refs: dict[str, dict[str, Any]] | None = None) -> WorksheetImport:
    """Parse a filled worksheet and validate every resulting annotation against the whole store.

    Writes nothing (see ``commit_worksheet``). ``role`` is 'project' or 'expert'. Rows whose
    annotator_id and every judgement column are blank are skipped."""
    from .handoff import ANNOTATION_COLUMNS

    if role not in ROLES:
        raise ValueError(f"role must be one of {sorted(ROLES)}")
    if kb_refs is None:
        from src.knowledge.base import default_kb

        kb_refs = default_kb().references
    pt = ROLES[role]
    judgement = [c.split(" (")[0] for c in ANNOTATION_COLUMNS if not c.startswith("annotator_id")]
    groups: dict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)
    skipped = 0
    problems: list[str] = []
    with Path(path).open(encoding="utf-8-sig", newline="") as fh:
        for n, row in enumerate(csv.DictReader(fh), 2):
            annotator = _col(row, "annotator_id")
            if not annotator and not any(_col(row, c) for c in judgement):
                skipped += 1
                continue
            if not annotator:
                problems.append(f"row {n}: answers given but annotator_id is blank")
                continue
            if not _col(row, "artifact_id") or not _col(row, "image_id"):
                problems.append(f"row {n}: artifact_id and image_id are required")
                continue
            groups[(_col(row, "artifact_id"), annotator)].append(row)
    current = store.current()
    out = []
    for (art, annotator), rows in sorted(groups.items()):
        prev = [a for a in current if a["artifact_id"] == art and a["annotator"]["annotator_id"] == annotator]
        if prev and not revise:
            problems.append(f"{art}: {annotator} already has annotation {prev[0]['annotation_id']}; "
                            "re-run with --revise to record a revision (the old one is kept)")
            continue
        qual = _col(rows[0], "qualification_and_affiliation") or None
        a = blank_annotation(art, sorted({_col(r, "image_id") for r in rows}), annotator_id=annotator,
                             provenance_type=pt, qualification=qual,
                             supersedes=prev[0]["annotation_id"] if prev else None)
        if role == "expert":
            state = _col(rows[0], "review_state")
            if state:
                a["review_state"] = state
        elif _col(rows[0], "review_state"):
            problems.append(f"{art}: a project annotator's worksheet cannot set review_state")
        for r in rows:
            problems += _fill(a, r, _col(r, "image_id"), kb_refs)
        prev_notes = a.get("notes")
        a["notes"] = (f"{prev_notes} | " if prev_notes else "") + f"imported from worksheet {Path(path).name} on {utc_now()[:10]}"
        out.append(a)
    if out:
        res = store.validate(out)
        mine = {a["annotation_id"] for a in out} | {a["supersedes"] for a in out if a["supersedes"]}
        problems += [str(p) for p in res.problems if p.annotation_id in mine]
    return WorksheetImport(out, skipped, problems)


def commit_worksheet(imp: WorksheetImport, store: AnnotationStore) -> int:
    """Append every imported annotation, or nothing if any is invalid (all-or-nothing)."""
    if not imp.ok:
        from .store import AnnotationRejected
        from .validate import AnnotationValidation

        raise AnnotationRejected(AnnotationValidation([Problem("N1", p) for p in imp.problems], len(imp.annotations)))
    for a in imp.annotations:
        store.append(a)
    return len(imp.annotations)


# --------------------------------------------------------------------------- #
# Disagreements and export
# --------------------------------------------------------------------------- #

REPORT_FIELDS: dict[str, tuple[str, str]] = {
    "object_status": ("object", "object_status"),
    "inscription_present": ("inscription", "inscription_present"),
    "inscription_type": ("inscription", "inscription_type"),
    "script_type": ("inscription", "script_type"),
    "reading": ("inscription", "reading"),
    "reading_completeness": ("inscription", "reading_completeness"),
    "transliteration": ("inscription", "transliteration"),
    "interpretation_type": ("interpretation", "interpretation_type"),
    "translation": ("interpretation", "translation"),
}


def _value(a: dict[str, Any], key: str) -> Any:
    if key == "dating_range":
        d = a["dating"]
        return None if d["estimated_start_year"] is None and d["estimated_end_year"] is None else \
            f"{d['estimated_start_year']}..{d['estimated_end_year']}"
    if key == "dating_basis":
        return ",".join(sorted(b for b in a["dating"]["dating_basis"] if b not in ("not_available", "unknown")))
    if key == "region_count":
        return len(a["inscription"].get("regions", []))
    sec, k = REPORT_FIELDS[key]
    v = a[sec].get(k, "unknown")
    return " ".join(v.split()) if isinstance(v, str) else v


def disagreement_report(artifact_ids: list[str], current: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Per artifact: each compared field, every human annotator's value, and agree / disagree.

    Answers 'not assessed' (unknown / not_available) are shown but never counted as disagreement.
    Nothing is resolved here."""
    keys = [*REPORT_FIELDS, "dating_range", "dating_basis", "region_count"]
    out = []
    for art in artifact_ids:
        humans = sorted((a for a in current if a["artifact_id"] == art and a["provenance_type"] != "ai_prediction"),
                        key=lambda a: (a["annotator"]["annotator_id"], a["annotation_id"]))
        if not humans:
            continue
        res = resolve_artifact(art, current)
        fields = {}
        for k in keys:
            vals = {f"{a['annotator']['annotator_id']} [{a['provenance_type']}]": _value(a, k) for a in humans}
            assessed = {str(v) for v in vals.values() if v not in (None, "unknown", "not_available", "", 0)}
            fields[k] = {"values": vals,
                         "state": "single annotator" if len(humans) < 2 else
                         ("disagree" if len(assessed) > 1 else "agree" if assessed else "not assessed")}
        expert_reviewed = any(a["provenance_type"] == "expert_annotation" and a["review_state"] == "expert_reviewed"
                              for a in humans)
        out.append({"artifact_id": art, "status": res.status, "label": res.label,
                    "expert_reviewed": expert_reviewed, "provisional": res.status == "provisional",
                    "adjudication_id": res.adjudication_id, "notes": res.notes,
                    "disagreeing_fields": sorted(k for k, f in fields.items() if f["state"] == "disagree"),
                    "fields": fields})
    return out


def export_annotations(current: list[dict[str, Any]], out_dir: Path) -> list[Path]:
    """Current annotations as JSONL (complete) and CSV (one row each, tier stated first)."""
    from .handoff import safe_cell

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    jl = out_dir / "annotations_current.jsonl"
    jl.write_text("".join(json.dumps(a, ensure_ascii=False, sort_keys=True) + "\n" for a in current),
                  encoding="utf-8")
    cols = ["provenance_tier", "is_ai_output", "annotation_id", "artifact_id", "annotator_id", "role",
            "review_state", "adjudication", *REPORT_FIELDS, "dating_range", "dating_basis", "region_count",
            "created_utc", "supersedes"]
    cs = out_dir / "annotations_current.csv"
    with cs.open("w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        for a in sorted(current, key=lambda a: (a["artifact_id"], a["annotation_id"])):
            row = {"provenance_tier": a["provenance_type"], "is_ai_output": a["provenance_type"] == "ai_prediction",
                   "annotation_id": a["annotation_id"], "artifact_id": a["artifact_id"],
                   "annotator_id": a["annotator"]["annotator_id"], "role": a["annotator"]["role"],
                   "review_state": a["review_state"],
                   "adjudication": ",".join(a["adjudication"]["resolves"]) if a.get("adjudication") else "",
                   "created_utc": a["created_utc"], "supersedes": a.get("supersedes") or ""}
            for k in [*REPORT_FIELDS, "dating_range", "dating_basis", "region_count"]:
                row[k] = _value(a, k)
            w.writerow({k: safe_cell(v) for k, v in row.items()})
    return [jl, cs]


__all__ = [
    "NEXT_STEP",
    "PROVENANCE_ROLE",
    "ROLES",
    "QueueRow",
    "WorksheetImport",
    "annotation_queue",
    "build_worksheets",
    "commit_worksheet",
    "disagreement_report",
    "export_annotations",
    "import_worksheet",
    "parse_dating_evidence",
    "parse_regions",
    "worksheet_rows",
]
