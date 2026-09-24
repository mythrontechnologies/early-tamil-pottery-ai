"""Tamper evidence for the append-only stores (src.integrity; rules N16, V10) and the
knowledge-base structure (K7, K8, V9, describe()).

SYNTHETIC data in tmp_path only. The live knowledge base and stores are only READ.
"""

from __future__ import annotations

import json

import pytest
from test_expert_pilot import NOREFS, annotation, expert

from src.integrity import IntegrityError, append_line, ledger_path, seal, verify
from src.knowledge.base import describe, load
from src.knowledge.verification import (
    VerificationRegistry,
    new_verification,
    validate_verification,
)


class TestLedger:
    def test_empty_and_intact(self, tmp_path):
        f = tmp_path / "log.jsonl"
        assert verify(f).status == "EMPTY"
        append_line(f, '{"a": 1}')
        append_line(f, '{"a": "தமிழ்"}')
        rep = verify(f)
        assert rep.ok and rep.lines == 2 and rep.status == "INTACT"

    def test_edited_line_is_detected(self, tmp_path):
        f = tmp_path / "log.jsonl"
        append_line(f, '{"a": 1}')
        append_line(f, '{"a": 2}')
        f.write_text(f.read_text(encoding="utf-8").replace('{"a": 1}', '{"a": 9}'), encoding="utf-8")
        assert not verify(f).ok

    def test_deleted_line_is_detected(self, tmp_path):
        f = tmp_path / "log.jsonl"
        for i in range(3):
            append_line(f, json.dumps({"i": i}))
        lines = f.read_text(encoding="utf-8").splitlines()
        f.write_text("\n".join(lines[:2]) + "\n", encoding="utf-8")
        assert any("removed" in p for p in verify(f).problems)

    def test_hand_appended_line_is_detected_and_blocks_further_appends(self, tmp_path):
        f = tmp_path / "log.jsonl"
        append_line(f, '{"i": 0}')
        with f.open("a", encoding="utf-8") as fh:
            fh.write('{"i": "by hand"}\n')
        assert any("not in the ledger" in p for p in verify(f).problems)
        with pytest.raises(IntegrityError):
            append_line(f, '{"i": 2}')

    def test_ledgerless_file_needs_explicit_seal(self, tmp_path):
        f = tmp_path / "legacy.jsonl"
        f.write_text('{"x": 1}\n', encoding="utf-8")
        assert not verify(f).ok
        assert seal(f).ok and ledger_path(f).exists()
        with pytest.raises(IntegrityError):
            seal(f)

    def test_multiline_record_refused(self, tmp_path):
        with pytest.raises(ValueError):
            append_line(tmp_path / "x.jsonl", "a\nb")


class TestStoresUseTheLedger:
    def test_annotation_store_tampering_fails_n16_and_blocks_promotion(self, world):
        from test_expert_pilot import plan

        art = world["arts"][0]
        world["store"].append(annotation(art), **NOREFS)
        world["store"].append(expert(art), **NOREFS)
        assert plan(world).candidates                             # intact -> a candidate
        p = world["store"].path
        p.write_text(p.read_text(encoding="utf-8").replace('"tamil_brahmi"', '"graffiti"'), encoding="utf-8")
        assert any(x.rule == "N16" for x in world["store"].validate(**NOREFS).problems)
        pl = plan(world)
        assert not pl.candidates and any("N16" in e for e in pl.validation_errors)

    def test_verification_registry_tampering_fails_v10(self, tmp_path):
        reg = VerificationRegistry(tmp_path / "reg.jsonl")
        reg.append(new_verification(ref_id="R1", citation="c", claim="SYNTHETIC claim", status="unverified"))
        reg.path.write_text(reg.path.read_text(encoding="utf-8").replace("SYNTHETIC", "EDITED"), encoding="utf-8")
        assert any(p.rule == "V10" for p in reg.validate().problems)


class TestKnowledgeStructure:
    def test_live_kb_passes_and_cited_ids_resolve(self):
        kb = load()
        assert kb.ok, kb.problems
        assert {"R3", "R5"} <= set(kb.references)
        for rid in ("R3", "R5"):
            r = kb.references[rid]
            assert r["resolution"] == "unresolved" and r["verification_status"] == "unverified"
            assert r["citation"].startswith("UNRESOLVED")

    def test_k7_missing_cited_reference(self, tmp_path):
        (tmp_path / "references").mkdir()
        (tmp_path / "references" / "r.yaml").write_text(
            "kind: references\nentries:\n  - id: SX\n    citation: SYNTHETIC\n    verification_status: unverified\n",
            encoding="utf-8")
        cfg = {"chronology": {"tamil_brahmi_earliest_positions": [{"id": "Z", "reference": "NOPE"}]}}
        assert any(p.startswith("K7") for p in load(tmp_path, config=cfg).problems)

    def test_k8_placeholder_cannot_be_verified(self, tmp_path):
        (tmp_path / "references").mkdir()
        (tmp_path / "references" / "r.yaml").write_text(
            "kind: references\nentries:\n  - id: PX\n    citation: UNRESOLVED\n"
            "    verification_status: bibliographic_only\n    resolution: unresolved\n", encoding="utf-8")
        probs = load(tmp_path).problems
        assert any("must be 'unverified'" in p for p in probs)
        assert any("candidate_works" in p for p in probs)

    def test_v9_registry_refuses_verifying_a_placeholder(self):
        kb = load()
        v = new_verification(ref_id="R5", citation="x", claim="c", status="verified_against_source",
                             verifier="SYN", verifier_role="expert", verification_date="2026-01-01",
                             locator="p. 1", source_location="SYNTHETIC library", source_access="physical_copy")
        assert "V9" in {p.rule for p in validate_verification(v, kb, set())}

    def test_describe_gives_every_field_and_marks_nothing_verified(self):
        rows = describe()
        keys = {"id", "claim", "source", "provenance", "verification_status", "scope", "locator", "notes",
                "uncertainty", "recorded_in"}
        assert rows and all(keys <= set(r) for r in rows)
        assert not any(r["verification_status"] == "verified_against_source" for r in rows)
        pos_b = next(r for r in rows if r["id"] == "config:chronology.position_B")
        assert "never an object date" in pos_b["scope"] and "unresolved placeholder" in pos_b["uncertainty"]
        site = next(r for r in rows if r["id"].startswith("keezhadi."))
        assert "site-level" in site["scope"]
