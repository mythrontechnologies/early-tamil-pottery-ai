"""Milestone 5 dataset layer: loader, classes, fingerprints, splits, sampling, statistics.

All data here is SYNTHETIC, generated into pytest's tmp_path by the ``synthetic_corpus``
fixture. Nothing touches data/.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.dataset.__main__ import main as dataset_cli
from src.dataset.classes import (
    ClassSpec,
    ClassSpecError,
    class_availability,
    eligibility,
)
from src.dataset.fingerprint import dataset_fingerprint, image_set_fingerprint
from src.dataset.loader import (
    DatasetLoadError,
    load_dataset,
)
from src.dataset.sampling import (
    ImbalanceError,
    check_strategy,
    class_counts,
    class_weights,
    imbalance_table,
    sample_weights,
)
from src.dataset.schema import RESEARCH_RECORDS_PATH, load_schema
from src.dataset.splits import (
    SplitError,
    SplitManifest,
    SplitSettings,
    adopt_existing_split,
    check_splittable,
    make_split,
    partition_records,
    verify_manifest,
    verify_partitions,
)
from src.dataset.statistics import compute_statistics

FOUR = ("tamil_brahmi", "graffiti", "none", "uncertain")


def _settings(**kw) -> SplitSettings:
    base = SplitSettings.from_config()
    return SplitSettings(**{**base.__dict__, **kw})


def _write(path: Path, records: list[dict]) -> None:
    path.write_text("".join(json.dumps(r) + "\n" for r in records), encoding="utf-8")


# --------------------------------------------------------------------------- #
# Loader
# --------------------------------------------------------------------------- #


class TestLoader:
    def test_valid_corpus_loads(self, tmp_path, synthetic_corpus):
        c = synthetic_corpus(tmp_path, {"tamil_brahmi": 2, "graffiti": 2}, images_per_artifact=2)
        ds = load_dataset(c["records_path"], c["data_root"])
        assert ds.ok and len(ds) == 8 and not ds.rejections
        assert ds.hashes_verified
        assert set(ds.by_artifact()) == {r["artifact_id"] for r in c["records"]}
        assert not ds.is_research_dataset          # tmp path is never the research dataset

    def test_artifact_identity_is_preserved(self, tmp_path, synthetic_corpus):
        c = synthetic_corpus(tmp_path, {"graffiti": 1}, images_per_artifact=3)
        ds = load_dataset(c["records_path"], c["data_root"])
        [(aid, recs)] = ds.by_artifact().items()
        assert len(recs) == 3 and all(r.artifact_id == aid for r in recs)

    def test_missing_file_is_an_empty_dataset(self, tmp_path):
        ds = load_dataset(tmp_path / "absent.jsonl", tmp_path / "raw")
        assert ds.is_empty and not ds.exists and len(ds) == 0

    def test_unparseable_file_raises(self, tmp_path):
        p = tmp_path / "r.jsonl"
        p.write_text("{nope\n", encoding="utf-8")
        with pytest.raises(DatasetLoadError):
            load_dataset(p, tmp_path)

    def test_missing_image_is_rejected(self, tmp_path, synthetic_corpus):
        c = synthetic_corpus(tmp_path, {"graffiti": 2})
        (c["data_root"] / c["records"][0]["image_path"]).unlink()
        ds = load_dataset(c["records_path"], c["data_root"])
        assert not ds.ok and len(ds.rejections) == 1
        assert any("R2" in r for r in ds.rejections[0].reasons)

    def test_bad_sha256_is_rejected(self, tmp_path, synthetic_corpus):
        c = synthetic_corpus(tmp_path, {"graffiti": 2})
        recs = c["records"]
        recs[1]["image_sha256"] = "f" * 64
        _write(c["records_path"], recs)
        ds = load_dataset(c["records_path"], c["data_root"])
        assert [r.image_id for r in ds.rejections] == [recs[1]["image_id"]]
        assert any("E2" in m for m in ds.rejections[0].reasons)

    def test_sentinel_hash_is_rejected_for_training(self, tmp_path, synthetic_corpus):
        c = synthetic_corpus(tmp_path, {"graffiti": 1}, overrides={"image_sha256": "unknown"})
        ds = load_dataset(c["records_path"], c["data_root"])
        assert any("L2" in m for m in ds.rejections[0].reasons)

    def test_invalid_record_is_rejected_not_repaired(self, tmp_path, synthetic_corpus):
        c = synthetic_corpus(tmp_path, {"graffiti": 2})
        recs = c["records"]
        recs[0]["view"] = "sideways"
        _write(c["records_path"], recs)
        ds = load_dataset(c["records_path"], c["data_root"])
        assert len(ds.rejections) == 1 and len(ds) == 1
        assert ds.records[0].record["image_id"] == recs[1]["image_id"]

    def test_duplicate_hash_across_artifacts_is_rejected(self, tmp_path, synthetic_corpus):
        c = synthetic_corpus(tmp_path, {"graffiti": 2})
        recs = c["records"]
        recs[1]["image_sha256"] = recs[0]["image_sha256"]
        _write(c["records_path"], recs)
        ds = load_dataset(c["records_path"], c["data_root"], verify_hashes=False)
        assert not ds.ok
        assert any("R4" in m for rej in ds.rejections for m in rej.reasons)

    def test_duplicate_image_id_is_rejected(self, tmp_path, synthetic_corpus):
        c = synthetic_corpus(tmp_path, {"graffiti": 2})
        recs = c["records"]
        recs[1]["image_id"] = recs[0]["image_id"]
        _write(c["records_path"], recs)
        ds = load_dataset(c["records_path"], c["data_root"], verify_hashes=False)
        assert any("R1" in m for rej in ds.rejections for m in rej.reasons)

    def test_path_escaping_the_root_is_rejected(self, tmp_path, synthetic_corpus):
        c = synthetic_corpus(tmp_path, {"graffiti": 1})
        recs = c["records"]
        recs[0]["image_path"] = "../records.jsonl"
        _write(c["records_path"], recs)
        ds = load_dataset(c["records_path"], c["data_root"])
        assert not ds.ok  # E3 (..) and/or L1

    def test_sentinels_are_preserved(self, tmp_path, synthetic_corpus):
        c = synthetic_corpus(tmp_path, {"none": 1})
        rec = load_dataset(c["records_path"], c["data_root"]).records[0]
        assert rec.get("transcription") == "not_applicable"
        assert rec.get("translation") == "not_applicable"        # brief alias
        assert rec.get("field_that_is_absent") == "unknown"      # absence -> sentinel, not None
        assert not rec.has("transcription")

    def test_brief_aliases_map_to_schema_fields(self, tmp_path, synthetic_corpus):
        c = synthetic_corpus(tmp_path, {"tamil_brahmi": 1})
        rec = load_dataset(c["records_path"], c["data_root"]).records[0]
        assert rec.get("dating_start") == rec.record["dating_lower_year"]
        assert rec.get("dating_end") == rec.record["dating_upper_year"]
        assert rec.get("inscription_type") == rec.record["inscription_technique"]
        view = rec.label_view()
        assert view["script_type"] == "tamil_brahmi" and "label_source" in view

    def test_period_is_reported_as_not_in_schema(self, tmp_path, synthetic_corpus):
        c = synthetic_corpus(tmp_path, {"graffiti": 1})
        rec = load_dataset(c["records_path"], c["data_root"]).records[0]
        with pytest.raises(KeyError, match="no 'period' field"):
            rec.get("period")

    def test_records_are_read_only(self, tmp_path, synthetic_corpus):
        c = synthetic_corpus(tmp_path, {"graffiti": 1})
        rec = load_dataset(c["records_path"], c["data_root"]).records[0]
        with pytest.raises(TypeError):
            rec.record["script_type"] = "none"  # type: ignore[index]


# --------------------------------------------------------------------------- #
# Schema 1.1.0 rights fields
# --------------------------------------------------------------------------- #


class TestRightsFields:
    def test_new_fields_exist_and_are_optional(self):
        schema = load_schema()
        for f in ("research_usable", "commercially_usable"):
            assert f in schema["properties"]
            assert f not in schema["required"]
        assert tuple(map(int, schema["schema_version"].split("."))) >= (1, 1, 0)  # added in 1.1.0

    def test_new_fields_use_yes_no_unknown(self, make_record):
        from src.dataset.validation import validate_records

        assert validate_records([make_record(research_usable="unknown")]).ok
        bad = validate_records([make_record(research_usable="maybe")])
        assert not bad.ok and bad.errors[0].rule == "E1"

    def test_version_1_0_0_records_remain_valid(self, make_record):
        from src.dataset.validation import validate_records

        rec = make_record(schema_version="1.0.0", research_usable=..., commercially_usable=...)
        assert validate_records([rec]).ok


# --------------------------------------------------------------------------- #
# Classes
# --------------------------------------------------------------------------- #


class TestClasses:
    def test_spec_matches_project_config(self):
        spec = ClassSpec.from_config()
        assert spec.trainable == FOUR
        assert set(spec.held_out) == {"other_script", "tamil_brahmi_and_graffiti", "unknown"}
        assert spec.num_classes == 4

    def test_held_out_labels_are_never_collapsed(self):
        spec = ClassSpec.from_config()
        assert spec.index_of("other_script") is None
        assert spec.index_of("tamil_brahmi_and_graffiti") is None
        assert spec.index_of("graffiti") == 1

    def test_every_schema_label_must_be_placed(self):
        with pytest.raises(ClassSpecError, match="neither trainable nor held out"):
            ClassSpec(FOUR, ("other_script",), FOUR + ("other_script", "tamil_brahmi_and_graffiti")).check()

    def test_eligibility_reasons(self, base_record):
        spec = ClassSpec.from_config()
        assert eligibility(base_record, spec) == (True, "eligible")
        assert eligibility({**base_record, "script_type": "other_script"}, spec)[1].startswith("held_out")
        assert eligibility({**base_record, "split": "excluded"}, spec)[0] is False

    def test_availability_is_explicit_for_every_label(self, tmp_path, synthetic_corpus):
        c = synthetic_corpus(tmp_path, {"tamil_brahmi": 2, "other_script": 1})
        rows = {a.label: a for a in class_availability(c["records"], ClassSpec.from_config())}
        assert set(rows) == set(FOUR) | {"other_script", "tamil_brahmi_and_graffiti", "unknown"}
        assert rows["tamil_brahmi"].available and not rows["none"].available
        assert rows["other_script"].status == "held_out" and rows["other_script"].artifacts == 1


# --------------------------------------------------------------------------- #
# Fingerprints
# --------------------------------------------------------------------------- #


class TestFingerprint:
    def test_order_independent(self, base_record, make_record):
        a, b = base_record, make_record(image_id="FIXTURE_ART_001__closeup__1")
        assert dataset_fingerprint([a, b]) == dataset_fingerprint([b, a])

    def test_any_metadata_change_changes_it(self, base_record, make_record):
        assert dataset_fingerprint([base_record]) != dataset_fingerprint(
            [make_record(notes="SYNTHETIC edited")])

    def test_image_fingerprint_ignores_metadata_edits(self, base_record, make_record):
        assert image_set_fingerprint([base_record]) == image_set_fingerprint(
            [make_record(notes="SYNTHETIC edited")])
        assert image_set_fingerprint([base_record]) != image_set_fingerprint(
            [make_record(image_sha256="a" * 64)])

    def test_empty_is_stable(self):
        assert dataset_fingerprint([]) == dataset_fingerprint([])


# --------------------------------------------------------------------------- #
# Splits
# --------------------------------------------------------------------------- #


def _balanced(tmp_path, synthetic_corpus, n=20, ipa=2, **kw):
    c = synthetic_corpus(tmp_path, dict.fromkeys(FOUR, n), images_per_artifact=ipa, **kw)
    return c, load_dataset(c["records_path"], c["data_root"])


class TestSplits:
    def test_empty_dataset_is_refused(self, tmp_path):
        ds = load_dataset(tmp_path / "absent.jsonl", tmp_path)
        with pytest.raises(SplitError, match="will not be fabricated"):
            make_split(ds)

    def test_holdout_is_artifact_disjoint(self, tmp_path, synthetic_corpus):
        _, ds = _balanced(tmp_path, synthetic_corpus)
        m = make_split(ds, strategy="holdout")
        tr, va, te = (m.artifacts_in(p) for p in ("train", "val", "test"))
        assert tr and va and te
        assert tr & va == set() and tr & te == set() and va & te == set()
        assert tr | va | te == set(ds.by_artifact())

    def test_all_photographs_of_an_artifact_share_a_partition(self, tmp_path, synthetic_corpus):
        _, ds = _balanced(tmp_path, synthetic_corpus, ipa=3)
        parts = partition_records(make_split(ds, strategy="holdout"), ds)
        seen: dict[str, str] = {}
        for name, recs in parts.items():
            for r in recs:
                assert seen.setdefault(r.artifact_id, name) == name

    def test_hashes_do_not_cross_partitions(self, tmp_path, synthetic_corpus):
        _, ds = _balanced(tmp_path, synthetic_corpus)
        parts = partition_records(make_split(ds, strategy="holdout"), ds)
        hashes = [{r.image_sha256 for r in recs} for recs in parts.values()]
        assert not (hashes[0] & hashes[1] or hashes[0] & hashes[2] or hashes[1] & hashes[2])

    def test_every_class_in_every_holdout_partition(self, tmp_path, synthetic_corpus):
        _, ds = _balanced(tmp_path, synthetic_corpus)
        m = make_split(ds, strategy="holdout")
        for part in ("train", "val", "test"):
            assert set(m.summary[part]["artifacts_by_class"]) == set(FOUR)

    def test_proportions_are_approximately_respected(self, tmp_path, synthetic_corpus):
        _, ds = _balanced(tmp_path, synthetic_corpus, n=40, ipa=1)
        m = make_split(ds, strategy="holdout")
        total = len(m.assignments)
        assert abs(len(m.artifacts_in("train")) / total - 0.70) < 0.05
        assert abs(len(m.artifacts_in("test")) / total - 0.15) < 0.05

    def test_secondary_site_balance(self, tmp_path, synthetic_corpus):
        _, ds = _balanced(tmp_path, synthetic_corpus, n=40, ipa=1)
        m = make_split(ds, strategy="holdout")
        for part in ("train", "val", "test"):
            sites = m.summary[part]["artifacts_by_site"]
            assert set(sites) == {"FIXTURE_SITE_A", "FIXTURE_SITE_B"}
            assert abs(sites["FIXTURE_SITE_A"] - sites["FIXTURE_SITE_B"]) <= 4

    def test_deterministic(self, tmp_path, synthetic_corpus):
        _, ds = _balanced(tmp_path, synthetic_corpus)
        assert make_split(ds, strategy="holdout").digest == make_split(ds, strategy="holdout").digest

    def test_seed_changes_assignment(self, tmp_path, synthetic_corpus):
        _, ds = _balanced(tmp_path, synthetic_corpus)
        assert (make_split(ds, strategy="holdout", seed=1).assignments
                != make_split(ds, strategy="holdout", seed=2).assignments)

    def test_record_order_does_not_matter(self, tmp_path, synthetic_corpus):
        c, ds = _balanced(tmp_path, synthetic_corpus)
        _write(c["records_path"], list(reversed(c["records"])))
        ds2 = load_dataset(c["records_path"], c["data_root"])
        assert make_split(ds, strategy="holdout").digest == make_split(ds2, strategy="holdout").digest

    def test_insufficient_artifacts_for_holdout(self, tmp_path, synthetic_corpus):
        c = synthetic_corpus(tmp_path, dict.fromkeys(FOUR, 6))
        ds = load_dataset(c["records_path"], c["data_root"])
        with pytest.raises(SplitError, match="holdout needs >= 20"):
            make_split(ds, strategy="holdout")

    def test_auto_falls_back_to_grouped_kfold(self, tmp_path, synthetic_corpus):
        c = synthetic_corpus(tmp_path, dict.fromkeys(FOUR, 6))
        ds = load_dataset(c["records_path"], c["data_root"])
        m = make_split(ds, strategy="auto")
        assert m.strategy == "grouped_kfold" and m.k == 5
        assert any("no untouched test set" in w for w in m.warnings)
        for fold in range(5):
            p = m.fold_partitions(fold)
            assert p["train"] & p["val"] == set() and p["val"]

    def test_too_few_for_anything_is_refused(self, tmp_path, synthetic_corpus):
        c = synthetic_corpus(tmp_path, dict.fromkeys(FOUR, 3))
        ds = load_dataset(c["records_path"], c["data_root"])
        with pytest.raises(SplitError, match="grouped k-fold"):
            make_split(ds, strategy="auto")

    def test_missing_class_is_refused(self, tmp_path, synthetic_corpus):
        c = synthetic_corpus(tmp_path, {"tamil_brahmi": 25, "graffiti": 25, "uncertain": 25})
        ds = load_dataset(c["records_path"], c["data_root"])
        with pytest.raises(SplitError, match="no artifacts at all for trainable class"):
            make_split(ds)

    def test_invalid_dataset_is_refused(self, tmp_path, synthetic_corpus):
        c, _ = _balanced(tmp_path, synthetic_corpus)
        (c["data_root"] / c["records"][0]["image_path"]).unlink()
        ds = load_dataset(c["records_path"], c["data_root"])
        with pytest.raises(SplitError, match="dataset is invalid"):
            make_split(ds)

    def test_preassigned_splits_are_not_resplit(self, tmp_path, synthetic_corpus):
        c, _ = _balanced(tmp_path, synthetic_corpus, overrides={"split": "train"})
        ds = load_dataset(c["records_path"], c["data_root"])
        with pytest.raises(SplitError, match="invalidate"):
            make_split(ds)

    def test_adopt_existing_split(self, tmp_path, synthetic_corpus):
        c = synthetic_corpus(tmp_path, dict.fromkeys(FOUR, 3), images_per_artifact=2)
        recs = c["records"]
        for r in recs:
            r["split"] = ["train", "val", "test"][int(r["artifact_id"][-1]) % 3]
        _write(c["records_path"], recs)
        m = adopt_existing_split(load_dataset(c["records_path"], c["data_root"]))
        assert m.strategy == "adopted" and m.artifacts_in("test")

    def test_inconsistent_label_within_artifact_is_refused(self, tmp_path, synthetic_corpus):
        c = synthetic_corpus(tmp_path, dict.fromkeys(FOUR, 20), images_per_artifact=2)
        recs = c["records"]
        recs[1].update({"script_type": "graffiti"})   # recs[0], recs[1] share an artifact
        _write(c["records_path"], recs)
        ds = load_dataset(c["records_path"], c["data_root"])
        _, problems = check_splittable(ds, ClassSpec.from_config(), SplitSettings.from_config())
        assert any("inconsistent script_type" in p for p in problems)

    def test_held_out_labels_are_excluded_not_relabelled(self, tmp_path, synthetic_corpus):
        c = synthetic_corpus(tmp_path, {**dict.fromkeys(FOUR, 20), "other_script": 2,
                                        "tamil_brahmi_and_graffiti": 1})
        m = make_split(load_dataset(c["records_path"], c["data_root"]), strategy="holdout")
        assert len(m.excluded) == 3
        assert all(v.startswith("held_out_label") for v in m.excluded.values())
        assert not set(m.excluded) & set(m.assignments)

    def test_manifest_roundtrip_and_tamper_detection(self, tmp_path, synthetic_corpus):
        _, ds = _balanced(tmp_path, synthetic_corpus)
        m = make_split(ds, strategy="holdout")
        path = m.save(tmp_path / "m.json")
        assert SplitManifest.load(path).digest == m.digest
        data = json.loads(path.read_text(encoding="utf-8"))
        aid = next(iter(data["assignments"]))
        data["assignments"][aid] = "test" if data["assignments"][aid] != "test" else "train"
        path.write_text(json.dumps(data), encoding="utf-8")
        with pytest.raises(SplitError, match="edited by hand"):
            SplitManifest.load(path)

    def test_manifest_for_a_changed_dataset_fails_verification(self, tmp_path, synthetic_corpus):
        c, ds = _balanced(tmp_path, synthetic_corpus)
        m = make_split(ds, strategy="holdout")
        recs = c["records"]
        recs[0]["notes"] = "SYNTHETIC edited after splitting"
        _write(c["records_path"], recs)
        errors = verify_manifest(m, load_dataset(c["records_path"], c["data_root"]))
        assert errors and "different dataset" in errors[0]

    def test_verify_partitions_catches_artifact_and_hash_leaks(self, tmp_path, synthetic_corpus):
        _, ds = _balanced(tmp_path, synthetic_corpus, n=2, ipa=2)
        recs = list(ds.records)
        errors = verify_partitions({"train": recs[:3], "test": recs[1:]})
        assert any("artifact" in e for e in errors)
        assert any("image hash" in e for e in errors)
        assert verify_partitions({"train": recs[:2], "test": recs[2:4]}) == []

    def test_manifest_never_uses_image_level_grouping(self, tmp_path, synthetic_corpus):
        _, ds = _balanced(tmp_path, synthetic_corpus)
        m = make_split(ds, strategy="holdout")
        m.group_key = "image_id"
        assert any("only artifact_id" in e for e in verify_manifest(m, ds))


# --------------------------------------------------------------------------- #
# Sampling / imbalance
# --------------------------------------------------------------------------- #


class TestSampling:
    def test_both_strategies_at_once_is_rejected(self):
        with pytest.raises(ImbalanceError, match="ONE"):
            check_strategy(["class_weighted_loss", "weighted_sampler"])
        assert check_strategy("weighted_sampler") == "weighted_sampler"

    def test_counts_by_artifact_and_by_image(self, tmp_path, synthetic_corpus):
        c = synthetic_corpus(tmp_path, {"tamil_brahmi": 2, "graffiti": 1}, images_per_artifact=3)
        spec = ClassSpec.from_config()
        assert class_counts(c["records"], spec, "artifact")["tamil_brahmi"] == 2
        assert class_counts(c["records"], spec, "image")["tamil_brahmi"] == 6

    def test_inverse_frequency_weights(self):
        w = class_weights({"a": 10, "b": 30}, ["a", "b"])
        assert w[0] == pytest.approx(3 * w[1]) and sum(w) / 2 == pytest.approx(1.0)

    def test_empty_class_cannot_be_weighted(self):
        with pytest.raises(ImbalanceError, match="no examples"):
            class_weights({"a": 10, "b": 0}, ["a", "b"])

    def test_sampler_weights_give_classes_equal_mass(self, tmp_path, synthetic_corpus):
        c = synthetic_corpus(tmp_path, {c: n for c, n in zip(FOUR, (1, 2, 3, 4))},
                             images_per_artifact=2)
        spec = ClassSpec.from_config()
        w = sample_weights(c["records"], spec)
        mass = {lbl: sum(wi for wi, r in zip(w, c["records"]) if r["script_type"] == lbl)
                for lbl in FOUR}
        assert all(v == pytest.approx(1.0) for v in mass.values())

    def test_imbalance_table_reports_counts_and_percentages(self, tmp_path, synthetic_corpus):
        c = synthetic_corpus(tmp_path, {"tamil_brahmi": 3, "graffiti": 1, "other_script": 2})
        rows = {r.label: r for r in imbalance_table(c["records"], ClassSpec.from_config())}
        assert rows["tamil_brahmi"].artifact_percentage == pytest.approx(75.0)
        assert rows["other_script"].status == "held_out"
        assert rows["other_script"].artifact_percentage == 0.0


# --------------------------------------------------------------------------- #
# Statistics and CLI
# --------------------------------------------------------------------------- #


class TestStatisticsAndCli:
    def test_live_dataset_statistics_match_records_and_are_blocked(self, live_research):
        s = compute_statistics()
        assert s.artifacts == len(live_research["artifacts"])
        assert s.images == len(live_research["records"])
        assert not s.training_ready
        text = s.render()
        for line in (f"Artifacts: {s.artifacts}", f"Images: {s.images}",
                     "Training readiness: BLOCKED"):
            assert line in text

    def test_statistics_on_a_synthetic_corpus(self, tmp_path, synthetic_corpus):
        c = synthetic_corpus(tmp_path, {"tamil_brahmi": 2, "graffiti": 1}, images_per_artifact=2)
        s = compute_statistics(c["records_path"], c["data_root"])
        assert (s.artifacts, s.images) == (3, 6)
        assert "SOURCE IS NOT THE RESEARCH DATASET" in s.render()
        assert not s.training_ready

    def test_stats_command(self, capsys, live_research):
        assert dataset_cli(["stats"]) == 0
        out = capsys.readouterr().out
        assert f"Artifacts: {len(live_research['artifacts'])}" in out
        assert "Training readiness: BLOCKED" in out

    def test_split_command_refuses_the_live_dataset(self, capsys, tmp_path):
        """Empty, or populated only with unlabelled acquired images: no split either way."""
        assert dataset_cli(["split", "--out-dir", str(tmp_path)]) == 1
        assert "SPLIT REFUSED" in capsys.readouterr().out
        assert not list(tmp_path.iterdir())

    def test_split_command_writes_a_manifest(self, capsys, tmp_path, synthetic_corpus):
        c = synthetic_corpus(tmp_path, dict.fromkeys(FOUR, 20))
        out = tmp_path / "manifests"
        code = dataset_cli(["split", "--records", str(c["records_path"]), "--data-root",
                            str(c["data_root"]), "--out-dir", str(out)])
        assert code == 0
        [written] = list(out.iterdir())
        assert SplitManifest.load(written).strategy == "holdout"

    def test_every_live_research_record_was_acquired_with_provenance(self, live_research):
        for rec in live_research["records"]:
            prov = live_research["provenance"].get(rec["image_id"])
            assert prov is not None, f"{rec['image_id']} has no acquisition provenance"
            assert prov["target"] == "research"
            assert prov["image_sha256"] == rec["image_sha256"]
            assert prov["research_usable"] == rec["research_usable"] == "yes"
        assert RESEARCH_RECORDS_PATH.exists() == bool(live_research["records"])
