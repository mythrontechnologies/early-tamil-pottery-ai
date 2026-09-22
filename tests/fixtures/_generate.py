"""Regenerate the fixture files from ``valid/base_record.json``.

Each fixture is the base record with one deliberate defect, so that a test failure points
at exactly one rule. Run from the project root:

    python tests/fixtures/_generate.py

Committed output is deterministic. This script is documentation as much as a tool: the
``CASES`` table below is the authoritative statement of what each invalid fixture breaks.
"""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

HERE = Path(__file__).resolve().parent
BASE = json.loads((HERE / "valid" / "base_record.json").read_text(encoding="utf-8"))


def rec(**overrides) -> dict:
    """Base record with overrides applied; a value of ``...`` deletes the field."""
    out = deepcopy(BASE)
    for key, value in overrides.items():
        if value is ...:
            out.pop(key, None)
        else:
            out[key] = value
    return out


def ident(n: int, artifact: str | None = None, **overrides) -> dict:
    """A variant record with distinct ids, so only the intended rule fires."""
    aid = artifact or f"FIXTURE_ART_{n:03d}"
    return rec(
        artifact_id=aid,
        image_id=f"{aid}__exterior__{n}",
        image_path=f"fixture_site/{aid}__exterior__{n}.jpg",
        image_sha256=f"{n:064x}",
        **overrides,
    )


# (filename, rule(s) exercised, records)
CASES: list[tuple[str, str, list[dict]]] = [
    # -- E1: schema layer -----------------------------------------------------
    ("invalid/empty_string.jsonl", "E1",
     [ident(11, site="")]),
    ("invalid/missing_required.jsonl", "E1",
     [rec(artifact_id=..., license=..., verification_status=...)]),
    ("invalid/year_zero.jsonl", "E1",
     [ident(13, dating_lower_year=0, dating_upper_year=100)]),
    ("invalid/bad_view.jsonl", "E1",
     [ident(14, view="side_angle_photo")]),
    ("invalid/bad_label_source.jsonl", "E1",
     [ident(15, label_source="a_friend_told_me")]),
    ("invalid/unknown_field.jsonl", "E1",
     [ident(16) | {"artifcat_id": "typo"}]),

    # -- R5/R6: inscription and script consistency ---------------------------
    ("invalid/script_inscription_clash.jsonl", "R5",
     [ident(21, inscription_present="no", script_type="tamil_brahmi")]),
    ("invalid/none_script_with_reading.jsonl", "R6",
     [ident(22, inscription_present="no", script_type="none",
            transcription="FIXTURE_SHOULD_BE_NOT_APPLICABLE")]),

    # -- R7 -------------------------------------------------------------------
    ("invalid/other_script_no_detail.jsonl", "R7",
     [ident(23, script_type="other_script", script_type_other_detail="unknown")]),

    # -- R8/R9: dating --------------------------------------------------------
    ("invalid/reversed_dates.jsonl", "R8",
     [ident(31, dating_lower_year=300, dating_upper_year=-200)]),
    ("invalid/dating_no_source.jsonl", "R9",
     [ident(32, dating_source="not_available")]),
    ("invalid/dating_no_basis.jsonl", "E1",
     [ident(33, dating_basis=[])]),

    # -- R10 ------------------------------------------------------------------
    ("invalid/stratigraphy_unstratified.jsonl", "R10",
     [ident(34, context_reliability="surface_collection")]),

    # -- R11 (export mode only) ----------------------------------------------
    ("invalid/unknown_rights.jsonl", "R11",
     [ident(35, redistributable="unknown")]),

    # -- R12 ------------------------------------------------------------------
    ("invalid/excluded_no_reason.jsonl", "R12",
     [ident(36, split="excluded", split_exclusion_reason="not_applicable")]),

    # -- R13 ------------------------------------------------------------------
    ("invalid/region_outside_image.jsonl", "R13",
     [ident(37, inscription_regions=[
         {"x": 1100, "y": 850, "w": 400, "h": 200, "region_label": "inscription"}])]),

    # -- R14 (warning) --------------------------------------------------------
    ("invalid/unverified_test_label.jsonl", "R14",
     [ident(38, split="test", label_source="project_annotation_unverified")]),

    # -- R1/R3/R4: dataset-level ---------------------------------------------
    ("invalid/duplicate_image_id.jsonl", "R1",
     # Distinct hashes, so only R1 fires and not R4 as well.
     [ident(41), ident(42, artifact="FIXTURE_ART_042") |
      {"image_id": "FIXTURE_ART_041__exterior__41"}]),
    ("invalid/split_conflict.jsonl", "R3",
     [ident(43, artifact="FIXTURE_ART_043", split="train"),
      ident(44, artifact="FIXTURE_ART_043", split="test",
            label_source="expert_annotation")]),
    ("invalid/duplicate_hash.jsonl", "R4",
     [ident(45, artifact="FIXTURE_ART_045"),
      ident(46, artifact="FIXTURE_ART_046") | {"image_sha256": f"{45:064x}"}]),

    # -- valid ----------------------------------------------------------------
    ("valid/minimal_record.jsonl", "-",
     [{
         "image_id": "FIXTURE_MIN_001__exterior__1",
         "artifact_id": "FIXTURE_MIN_001",
         "image_path": "fixture_site/FIXTURE_MIN_001__exterior__1.jpg",
         "source": "unknown",
         "license": "unknown",
         "redistributable": "no",
         "inscription_present": "uncertain",
         "script_type": "uncertain",
         "label_source": "project_annotation_unverified",
         "verification_status": "unverified",
     }]),
    ("valid/multi_photo_artifact.jsonl", "-",
     [rec(image_id=f"FIXTURE_ART_100__{v}__1",
          image_path=f"fixture_site/FIXTURE_ART_100__{v}__1.jpg",
          artifact_id="FIXTURE_ART_100",
          view=v,
          image_sha256=f"{100 + i:064x}",
          split="train")
      for i, v in enumerate(("exterior", "interior", "closeup"))]),
    ("valid/unknown_heavy_record.jsonl", "-",
     [ident(50,
            site="unknown",
            stratigraphic_context="not_available",
            context_reliability="unprovenanced",
            inscription_present="no",
            script_type="none",
            inscription_technique="not_applicable",
            inscription_placement="not_applicable",
            inscription_regions=[],
            character_count_visible=None,
            transcription="not_applicable",
            transcription_encoding="not_applicable",
            transliteration="not_applicable",
            transliteration_scheme="not_applicable",
            translation_en="not_applicable",
            translation_ta="not_applicable",
            reading_status="not_applicable",
            alternative_readings=[],
            reading_source="not_applicable",
            dating_text="unknown",
            dating_lower_year=None,
            dating_upper_year=None,
            dating_basis=["unknown"],
            dating_reliability="unknown",
            dating_source="not_available",
            image_width_px=None,
            image_height_px=None,
            scale_bar_present="unknown")]),

    # -- conversion -----------------------------------------------------------
    ("conversion/roundtrip.jsonl", "-",
     [rec(image_id="FIXTURE_CONV_001__exterior__1",
          artifact_id="FIXTURE_CONV_001",
          image_path="fixture_site/FIXTURE_CONV_001__exterior__1.jpg",
          image_sha256=f"{201:064x}",
          # Unicode survival check. 'சோதனை' is the ordinary Tamil word for 'test'.
          translation_ta="சோதனை (FIXTURE — the Tamil word for 'test', not a translation)",
          notes="SYNTHETIC FIXTURE. Unicode, a semicolon; a \"quote\", and a comma, on purpose.",
          alternative_readings=[
              "FIXTURE_A; with a semicolon",
              "FIXTURE_B, with a comma",
              "FIXTURE_C \"with quotes\"",
          ]),
      ident(202, character_count_visible=None, dating_lower_year=None,
            dating_upper_year=None, alternative_readings=[], inscription_regions=[],
            dating_source="not_available"),
      {  # sparse: absent keys must round-trip as absent, not as empty strings
          "image_id": "FIXTURE_CONV_003__exterior__1",
          "artifact_id": "FIXTURE_CONV_003",
          "image_path": "fixture_site/FIXTURE_CONV_003__exterior__1.jpg",
          "source": "unknown",
          "license": "unknown",
          "redistributable": "no",
          "inscription_present": "uncertain",
          "script_type": "uncertain",
          "label_source": "project_annotation_unverified",
          "verification_status": "unverified",
      }]),
]


def main() -> int:
    written = 0
    for name, rules, records in CASES:
        path = HERE / name
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8", newline="\n") as fh:
            for record in records:
                fh.write(json.dumps(record, ensure_ascii=False) + "\n")
        print(f"{name:<48} {rules:<8} {len(records)} record(s)")
        written += 1
    print(f"\n{written} fixture file(s) written.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
