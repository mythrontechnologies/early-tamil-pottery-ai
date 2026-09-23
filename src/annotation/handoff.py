"""Expert handoff pack for the Milestone 8 pilot (worksheets generated from project data).

    python -m src.annotation handoff [--out outputs/pilot_handoff]

Writes, to a git-ignored directory:

* ``pilot_worksheet_project_annotator.csv`` and ``pilot_worksheet_expert.csv``: one row per
  pilot photograph. Only identity and source columns are filled (artifact id, image id, local
  path, Commons page, licence, attribution). Every judgement column is BLANK. The
  worksheets are a paper aid; the annotation tool (``streamlit run app/annotate.py``) is where
  annotations are recorded and validated.
* ``verification_checklist.csv``: one row per claim the project relies on a key reference
  (R1, S01, S03) for. The claim text and the locator the project transcribed are filled; the
  verification columns (status, locator found, verifier, date, copy location, access) are
  BLANK. A filled checklist is imported with ``python -m src.knowledge import-checklist``
  (a dry run unless ``--commit``), which applies rules V1-V8 to every row.

Deliberately NOT in any worksheet: the uploader's caption (it dates the Keeladi deposit, not
these sherds), any script, reading, translation or date, and any AI output.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from src.dataset.schema import ROOT

from .pilot import Pilot, load_pilot

DEFAULT_OUT = ROOT / "outputs" / "pilot_handoff"

ANNOTATION_COLUMNS = (
    "annotator_id", "inscription_present (yes/no/uncertain)",
    "script_type (tamil_brahmi/graffiti/tamil_brahmi_and_graffiti/none/uncertain/other_script)",
    "script_confidence", "regions (describe; mark them in the tool)", "characters_visible",
    "reading (only if supported)", "alternative_readings", "reading_confidence",
    "inscription_type", "interpretation_type", "translation (only with a source)", "meaning",
    "linguistic_observations (with source)", "dating_evidence (type; observation; bounds; source)",
    "references (ids + page/plate)", "usable_for_annotation (yes/no/uncertain)",
    "uncertainty_notes",
)
EXPERT_COLUMNS = ("qualification_and_affiliation", "review_state (expert_reviewed/disputed)")
VERIFICATION_COLUMNS = (
    "status (verified_against_source/discrepancy_found/source_unavailable)",
    "locator_found (page/plate/figure/catalogue no.)", "verifier_id", "verifier_role (project_member/expert)",
    "verification_date (YYYY-MM-DD)", "source_location (library + shelfmark, or URL)",
    "source_access (physical_copy/authorised_digital_copy/open_access_publication/not_accessed)",
    "citation_as_checked (only if it differs)", "notes (required for a discrepancy or unavailability)",
)


@dataclass
class HandoffPack:
    out_dir: Path
    files: list[Path]
    photos: int
    claims: int


def _pilot_rows(records: list[dict[str, Any]], pilot: Pilot) -> list[dict[str, str]]:
    rows = []
    for r in sorted((r for r in records if r["artifact_id"] in pilot.artifacts),
                    key=lambda r: (pilot.artifacts.index(r["artifact_id"]), r["image_id"])):
        rows.append({"artifact_id": r["artifact_id"], "image_id": r["image_id"],
                     "local_path": f"data/raw/{r['image_path']}",
                     "source_page": r.get("source_reference", "not_available"),
                     "license": r.get("license", "unknown"),
                     "attribution": r.get("rights_notes", "not_available")})
    return rows


def _write(path: Path, header: list[str], rows: list[dict[str, str]]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as fh:     # BOM: opens cleanly in Excel
        w = csv.DictWriter(fh, fieldnames=header)
        w.writeheader()
        for row in rows:
            w.writerow({k: row.get(k, "") for k in header})
    return path


def claim_rows(ref_ids: list[str] | None = None) -> list[dict[str, str]]:
    from src.knowledge.base import default_kb
    from src.knowledge.verification import claims, key_references

    kb = default_kb()
    refs = ref_ids or key_references()
    rows = []
    for c in claims(kb):
        for rid in c.ref_ids:
            if rid not in refs:
                continue
            ref = kb.references.get(rid, {})
            rows.append({"ref_id": rid, "claim_id": c.claim_id,
                         "citation": ref.get("citation", "not in knowledge base"),
                         "knowledge_base_status": ref.get("verification_status", "unknown"),
                         "claim": c.statement,
                         "locator_as_transcribed (UNVERIFIED)": c.locator, "recorded_in": c.where})
    return sorted(rows, key=lambda r: (refs.index(r["ref_id"]), r["claim_id"]))


def build_handoff(records: list[dict[str, Any]], out_dir: Path | None = None,
                  pilot: Pilot | None = None) -> HandoffPack:
    out = Path(out_dir or DEFAULT_OUT)
    pilot = pilot or load_pilot()
    photos = _pilot_rows(records, pilot)
    base = ["artifact_id", "image_id", "local_path", "source_page", "license", "attribution"]
    files = [
        _write(out / "pilot_worksheet_project_annotator.csv", base + list(ANNOTATION_COLUMNS), photos),
        _write(out / "pilot_worksheet_expert.csv", base + list(EXPERT_COLUMNS) + list(ANNOTATION_COLUMNS),
               photos),
    ]
    claims = claim_rows()
    files.append(_write(out / "verification_checklist.csv",
                        ["ref_id", "claim_id", "citation", "knowledge_base_status", "claim",
                         "locator_as_transcribed (UNVERIFIED)", "recorded_in", *VERIFICATION_COLUMNS],
                        claims))
    return HandoffPack(out, files, len(photos), len(claims))


__all__ = ["ANNOTATION_COLUMNS", "DEFAULT_OUT", "EXPERT_COLUMNS", "VERIFICATION_COLUMNS",
           "HandoffPack", "build_handoff", "claim_rows"]
