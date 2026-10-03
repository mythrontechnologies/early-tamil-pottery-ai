"""Milestone 9: the SYNTHETIC engineering dataset and the full pipeline on it.

SYNTHETIC — NOT ARCHAEOLOGICAL EVIDENCE. Every dataset and model here is generated in pytest's
temporary directory (``tiny_synthetic`` / ``tiny_synthetic_model`` in conftest.py) and trained on
the CPU without downloading weights. Numbers checked here prove the plumbing; none is a result.
The separation guarantees (synthetic data can never reach the research data, gates, stores or
history) are in ``test_synthetic_separation.py``.
"""

from __future__ import annotations

import hashlib
import io
import json
import shutil
import threading
import urllib.request
from http.server import ThreadingHTTPServer

import numpy as np
import pytest
from conftest import ROOT, tiny_synthetic_config
from PIL import Image

from src.dataset.convert import read_jsonl
from src.dataset.splits import partition_records
from src.synthetic import (
    ARCHITECTURE_SLOTS,
    EVALUATION_BANNER,
    LABEL_WARNING,
    MARKER,
    SYNTHETIC_LABELS,
    TRAINING_BANNER,
    UI_BANNER,
)
from src.synthetic.audit import dataset_stats, render_stats, verify_dataset
from src.synthetic.config import SyntheticConfigError, SyntheticDatasetConfig
from src.synthetic.dataset import (
    SyntheticDatasetError,
    find_manifest,
    generate_dataset,
    load_synthetic_dataset,
    synthetic_fingerprint,
    validate_synthetic_records,
)
from src.synthetic.generator import (
    GENERATOR_VERSION,
    build_artifact,
    class_assignment,
    generate_view,
    sample_view,
)
from src.synthetic.glyphs import GLYPH_CODES, GLYPHS

# --------------------------------------------------------------------------- #
# Configuration and generator
# --------------------------------------------------------------------------- #


class TestConfig:
    def test_shipped_config_is_valid(self):
        cfg = SyntheticDatasetConfig.load()
        assert cfg.dataset_type == "synthetic" and cfg.generator_version == GENERATOR_VERSION
        assert cfg.artifacts_per_class * 4 >= 500

    @pytest.mark.parametrize("change", [{"typo_key": 1}, {"dataset_type": "research"}, {"generator_version": "9.9.9"},
                                        {"artifacts_per_class": 0}])
    def test_strict(self, change):
        data = SyntheticDatasetConfig.load().to_dict() | change
        with pytest.raises(SyntheticConfigError):
            SyntheticDatasetConfig.from_dict(data)

    def test_digest_tracks_every_value(self):
        a = tiny_synthetic_config()
        assert a.digest == tiny_synthetic_config().digest
        assert a.digest != tiny_synthetic_config(seed=1).digest


class TestGenerator:
    def test_class_assignment_is_balanced_seeded_and_patternless(self):
        labels = class_assignment(7, 25)
        assert {lab: labels.count(lab) for lab in SYNTHETIC_LABELS} == dict.fromkeys(SYNTHETIC_LABELS, 25)
        assert labels != class_assignment(8, 25) and labels == class_assignment(7, 25)
        assert labels[:4] != list(SYNTHETIC_LABELS)          # ids do not cycle through the classes

    def test_views_are_deterministic(self):
        cfg = tiny_synthetic_config()
        a = generate_view(cfg, build_artifact(cfg, 3, "synthetic_graffiti_like"), 1)
        b = generate_view(cfg, build_artifact(cfg, 3, "synthetic_graffiti_like"), 1)
        assert a.sha256 == b.sha256 and a.view_params == b.view_params and a.regions == b.regions
        c = generate_view(tiny_synthetic_config(seed=99), build_artifact(tiny_synthetic_config(seed=99), 3,
                                                                         "synthetic_graffiti_like"), 1)
        assert c.sha256 != a.sha256

    def test_photographic_conditions_never_see_the_class(self):
        """No leakage by construction: outline, surface, distractors and every view parameter are
        identical whichever class the same artifact index is given. Only the marks differ."""
        cfg = tiny_synthetic_config()
        states = {lab: build_artifact(cfg, 11, lab) for lab in SYNTHETIC_LABELS}
        params = [{k: v for k, v in s.params.items() if k not in ("marks_depth", "uncertain_mode")} for s in states.values()]
        assert all(p == params[0] for p in params)
        assert all(np.array_equal(s.mask, states["synthetic_none"].mask) for s in states.values())
        assert all(np.array_equal(s.albedo, states["synthetic_none"].albedo) for s in states.values())
        views = [sample_view(cfg, s, 0) for s in states.values()]
        assert all(v == views[0] for v in views)

    def test_marks_per_class(self):
        cfg = tiny_synthetic_config()
        for i, lab in enumerate(class_assignment(cfg.seed, 8)):
            s = build_artifact(cfg, i, lab)
            kinds = {r["kind"] for r in s.marks["regions"]}
            if lab == "synthetic_none":
                assert not s.marks["regions"] and s.marks["glyph_sequence"] == []
            elif lab == "synthetic_tamil_brahmi_like":
                seq = [c for w in s.marks["glyph_sequence"] for c in w]
                assert kinds == {"glyph_row", "glyph"} and 2 <= len(seq) <= 8 and len(s.marks["glyph_sequence"]) <= 2
                assert set(seq) <= set(GLYPH_CODES)
            elif lab == "synthetic_graffiti_like":
                assert kinds == {"mark"}
            else:
                assert kinds == {"mark"} and s.marks["uncertain_mode"] in cfg.marks.uncertain_modes

    def test_glyph_alphabet_is_sixteen_compound_invented_shapes(self):
        assert len(GLYPHS) == 16 and len(set(GLYPH_CODES)) == 16
        for g in GLYPHS:     # no single-element sign: >= 2 elements, or one polyline of >= 4 vertices
            assert len(g.strokes) + len(g.dots) >= 2 or len(g.strokes[0]) >= 4, g.name


# --------------------------------------------------------------------------- #
# Dataset on disk
# --------------------------------------------------------------------------- #


class TestDataset:
    def test_records_are_valid_explicit_and_sentinelled(self, tiny_synthetic):
        recs = tiny_synthetic["records"]
        assert len({r["artifact_id"] for r in recs}) == 20 and 40 <= len(recs) <= 60
        assert validate_synthetic_records(recs, tiny_synthetic["root"]) == []
        for r in recs:
            assert r["dataset_type"] == "synthetic" and r["synthetic_marker"] == MARKER and r["label_warning"] == LABEL_WARNING
            assert r["artifact_id"].startswith("SYNTH-") and r["catalogue_number"].startswith("SYNTH-ONLY-")
            assert all(r[k] == "not_applicable" for k in ("site", "context", "period", "dating_basis", "transcription",
                                                          "translation"))
            assert r["label_source"] == "synthetic_ground_truth" and r["source"] == "synthetic_generator"
            # unknown vs uncertain are never confused: the generator always knows what it drew
            assert r["inscription_present"] == {"synthetic_none": "no", "synthetic_uncertain": "uncertain"}.get(
                r["script_type"], "yes")
            for reg in r["synthetic_regions"]:
                assert 0 <= reg["x"] <= 1 and 0 <= reg["y"] <= 1 and reg["x"] + reg["width"] <= 1 + 1e-6

    def test_provenance_matches_records_and_files(self, tiny_synthetic):
        root = tiny_synthetic["root"]
        prov = {p["image_id"]: p for p in read_jsonl(root / "manifests" / "provenance.jsonl")}
        assert set(prov) == {r["image_id"] for r in tiny_synthetic["records"]}
        for r in tiny_synthetic["records"]:
            p = prov[r["image_id"]]
            assert p["image_sha256"] == r["image_sha256"] == hashlib.sha256((root / r["image_path"]).read_bytes()).hexdigest()
            assert p["view_params_sha256"] == r["generation_params_sha256"] and p["generator_version"] == GENERATOR_VERSION
            assert p["random_streams"]["view"][:2] == [tiny_synthetic["cfg"].seed, r["artifact_index"]]
        run = json.loads((root / "manifests" / "generation_run.json").read_text(encoding="utf-8"))
        assert run["git"]["commit"] and run["generated_utc"] and run["dataset_type"] == "synthetic"

    def test_regeneration_is_byte_identical(self, tiny_synthetic, tmp_path):
        generate_dataset(tiny_synthetic["cfg"], tmp_path / "again")
        a, b = tiny_synthetic["root"], tmp_path / "again"
        assert (a / "metadata" / "records.jsonl").read_bytes() == (b / "metadata" / "records.jsonl").read_bytes()
        assert (a / "manifests" / "provenance.jsonl").read_bytes() == (b / "manifests" / "provenance.jsonl").read_bytes()
        for r in tiny_synthetic["records"][:6]:
            assert (a / r["image_path"]).read_bytes() == (b / r["image_path"]).read_bytes()

    def test_generate_refuses_to_overwrite_without_force(self, tiny_synthetic):
        with pytest.raises(SyntheticDatasetError, match="--force"):
            generate_dataset(tiny_synthetic["cfg"], tiny_synthetic["root"])

    def test_fingerprint_changes_with_every_component(self, tiny_synthetic):
        recs, cfg = tiny_synthetic["records"], tiny_synthetic["cfg"]

        def fp(records=recs, gen=GENERATOR_VERSION, cfgd=cfg.digest, split="s1"):
            return synthetic_fingerprint(records, generator_version=gen, config_digest=cfgd, split_digest=split)

        base = fp()
        assert fp(records=list(reversed(recs))) == base                      # order-independent
        changed_hash = [dict(recs[0], image_sha256="0" * 64), *recs[1:]]
        changed_meta = [dict(recs[0], synthetic_surface="grey" if recs[0]["synthetic_surface"] != "grey" else "buff"), *recs[1:]]
        variants = [fp(records=changed_hash), fp(records=changed_meta), fp(gen="1.0.1"), fp(cfgd="x"), fp(split="s2"),
                    fp(records=recs[1:])]
        assert len({base, *variants}) == len(variants) + 1

    def test_split_is_artifact_level_without_leakage(self, tiny_synthetic):
        ds = load_synthetic_dataset(tiny_synthetic["root"])
        m = find_manifest(ds, tiny_synthetic["root"])
        parts = partition_records(m, ds)
        arts = [{r.artifact_id for r in v} for v in parts.values()]
        hashes = [{r.image_sha256 for r in v} for v in parts.values()]
        ids = [{r.image_id for r in v} for v in parts.values()]
        for group in (arts, hashes, ids):
            assert all(not (a & b) for i, a in enumerate(group) for b in group[i + 1:])
        assert sum(map(len, arts)) == 20
        for part in ("train", "val", "test"):
            assert {r.script_type for r in parts[part]} == set(SYNTHETIC_LABELS)
        from src.synthetic.dataset import make_synthetic_split

        again, _ = make_synthetic_split(tiny_synthetic["cfg"], tiny_synthetic["root"])
        assert again.digest == m.digest                                       # deterministic

    def test_validation_detects_tampering(self, tiny_synthetic, tmp_path):
        recs = [dict(r) for r in tiny_synthetic["records"]]
        root = tmp_path / "copy"
        shutil.copytree(tiny_synthetic["root"], root)
        (root / recs[0]["image_path"]).write_bytes(b"tampered")
        recs.append(dict(recs[1]))
        recs[2] = dict(recs[2], script_type="synthetic_none" if recs[2]["script_type"] != "synthetic_none" else "synthetic_uncertain")
        rules = {f.rule for f in validate_synthetic_records(recs, root)}
        assert {"S2", "S3", "S4", "S6"} <= rules

    def test_stats_and_verify(self, tiny_synthetic):
        s = dataset_stats(tiny_synthetic["root"])
        assert s["artifacts"] == 20 and s["hash_collisions"] == 0 and s["duplicate_image_ids"] == 0
        assert s["split"]["strategy"] == "holdout" and s["storage"]["image_files"] == s["images"]
        assert MARKER in render_stats(s)
        rep = verify_dataset(tiny_synthetic["root"], regenerate=3, config=tiny_synthetic["cfg"])
        assert rep.ok, rep.render()
        assert {c.id for c in rep.checks} >= {f"V{i}" for i in range(1, 15)}

    def test_cli(self, tiny_synthetic, capsys):
        from src.synthetic.__main__ import main

        args = ["--root", str(tiny_synthetic["root"]), "--config", str(tiny_synthetic["config_path"])]
        assert main(["stats", *args, "--json"]) == 0
        assert json.loads(capsys.readouterr().out)["artifacts"] == 20
        assert main(["verify", *args, "--regenerate", "2"]) == 0
        assert "RESULT: PASS" in capsys.readouterr().out
        assert main(["generate", *args]) == 2                                 # exists; --force required


# --------------------------------------------------------------------------- #
# Training, evaluation, robustness, OCR benchmark
# --------------------------------------------------------------------------- #


class TestTrainingAndEvaluation:
    def test_training_writes_a_marked_checkpoint_and_experiment(self, tiny_synthetic_model):
        from src.training.checkpoint import load_checkpoint, model_fingerprint

        ckpt = load_checkpoint(tiny_synthetic_model["checkpoint"], expected_dataset_type="synthetic")
        assert ckpt["class_names"] == list(SYNTHETIC_LABELS) and ckpt["dataset_type"] == "synthetic"
        meta = ckpt["synthetic"]
        assert meta["marker"] == MARKER and meta["banner"] == TRAINING_BANNER
        assert meta["generator_version"] == GENERATOR_VERSION and meta["architecture_slots"] == ARCHITECTURE_SLOTS
        assert meta["synthetic_fingerprint"] and meta["seed"] and meta["environment"]["torch"]
        assert ckpt["git"]["commit"] and ckpt["config"]["model"]["name"] == "resnet18"
        assert ckpt["model_fingerprint"] == model_fingerprint(ckpt["state_dict"])
        assert "train_loss" in ckpt["metrics"] and "balanced_accuracy" in ckpt["metrics"]
        exp = json.loads(tiny_synthetic_model["experiment"].read_text(encoding="utf-8"))
        assert exp["dataset_type"] == "synthetic" and TRAINING_BANNER in exp["notes"]
        assert exp["readiness"]["training_ready_for_archaeology"] is False
        assert exp["metrics"]["test_artifact_level"]["provenance"] == "synthetic"

    def test_evaluation_report(self, tiny_synthetic, tiny_synthetic_model):
        from src.synthetic.evaluate import evaluate_checkpoint, render_evaluation

        rep = evaluate_checkpoint(tiny_synthetic_model["checkpoint"], "test", root=tiny_synthetic["root"],
                                  config_path=tiny_synthetic_model["config_path"], device="cpu")
        assert rep["banner"] == EVALUATION_BANNER and rep["dataset_type"] == "synthetic"
        for level in ("image_level", "artifact_level"):
            m = rep[level]["metrics"]
            assert rep[level]["provenance"] == "synthetic"
            for key in ("accuracy", "balanced_accuracy", "macro_precision", "macro_recall", "macro_f1", "weighted_f1",
                        "per_class", "confusion_matrix", "top_k_accuracy"):
                assert key in m
            assert {"ece", "mce", "brier", "reliability"} <= set(m["calibration"])
        cd = rep["confidence_distribution"]["image"]
        assert sum(cd["correct"]) + sum(cd["incorrect"]) == rep["image_level"]["metrics"]["n_samples"]
        assert rep["artifact_level"]["metrics"]["n_samples"] == len({p["artifact_id"] for p in rep["predictions"]})
        text = render_evaluation(rep)
        assert EVALUATION_BANNER in text and "ARTIFACT LEVEL" in text
        assert str(tiny_synthetic["base"]) in rep["report_path"]

    def test_evaluation_cli_refuses_a_research_checkpoint(self, tmp_path, capsys):
        from test_training_framework import _NoiseDataset, _trainer
        from torch.utils.data import DataLoader

        from src.evaluation.__main__ import main

        fit = _trainer(tmp_path, optimization={"epochs": 1}).fit(
            DataLoader(_NoiseDataset(8, 4), batch_size=8), DataLoader(_NoiseDataset(8, 4, seed=1), batch_size=8))
        assert main(["evaluate", "--dataset", "synthetic", "--checkpoint", fit.last_checkpoint]) == 2
        assert "synthetic" in capsys.readouterr().err.lower()

    def test_robustness(self, tiny_synthetic, tiny_synthetic_model):
        from src.synthetic.robustness import PERTURBATIONS, render_robustness, run_robustness

        assert {f for f, _, _ in PERTURBATIONS.values()} >= {"blur", "exposure", "contrast", "noise", "compression",
                                                              "rotation", "scale", "occlusion", "background"}
        rep = run_robustness(tiny_synthetic_model["checkpoint"], root=tiny_synthetic["root"], device="cpu", save=False,
                             names=["clean", "blur_sigma2", "occlusion_16pct", "background_swap"],
                             config_path=tiny_synthetic_model["config_path"])
        assert set(rep["results"]) == {"clean", "blur_sigma2", "occlusion_16pct", "background_swap"}
        assert rep["results"]["clean"]["delta_image_balanced_accuracy"] == 0
        assert "Synthetic robustness is not archaeological robustness" in render_robustness(rep)

    def test_background_swap_keeps_the_object(self, tiny_synthetic):
        cfg = tiny_synthetic["cfg"]
        s = build_artifact(cfg, 0, "synthetic_none")
        a = generate_view(cfg, s, 0)
        bg = {"kind": "wood", "hue": 0.1, "saturation": 0.2, "value": 0.5, "seed": 5}
        b = generate_view(cfg, s, 0, overrides={"background": bg})
        assert a.sha256 != b.sha256 and a.regions == b.regions

    def test_ocr_benchmark(self, tiny_synthetic):
        from src.synthetic.ocr_benchmark import render_benchmark, run_benchmark

        rep = run_benchmark(root=tiny_synthetic["root"], epochs=2, device="cpu", pipeline_sample=2, save=False)
        assert rep["benchmark"] == "Synthetic glyph recognition benchmark" and "not a transcription" in rep["statement"]
        for name in ("learned", "classical"):
            d = rep["region_detection"][name]
            assert d["true_positives"] + d["false_negatives"] == rep["data"]["test_rows"]
            assert 0 <= d["false_alarm_rate_on_images_without_row"] <= 1
        assert rep["row_detector"]["train_images"] > rep["row_detector"]["val_images"] > 0
        for block in ("oracle_segmentation", "reader_on_ground_truth_rows", "end_to_end"):
            assert rep[block]["cer"] >= 0 and rep[block]["wer"] >= 0 and 0 <= rep[block]["exact_sequence_rate"] <= 1
        assert rep["through_inference_pipeline"]["images"] == min(2, rep["data"]["test_rows"])
        assert "Tamil-Brahmi" not in render_benchmark(rep)

    def test_reader_output_is_only_ever_a_candidate(self):
        from src.ocr import screen_ocr
        from src.synthetic.ocr_benchmark import GlyphNet, SyntheticGlyphReader

        res = screen_ocr(SyntheticGlyphReader(GlyphNet().eval()).transcribe(Image.new("RGB", (64, 32), (150, 90, 60))))
        assert res.is_reading is False and res.provenance == "ai_prediction"


# --------------------------------------------------------------------------- #
# Inference, API, UI
# --------------------------------------------------------------------------- #


class _Raises:
    name = "must_not_run"

    def classify(self, image):
        raise AssertionError("this classifier must not be applied to this image")


def _index(tiny):
    return {r["image_sha256"]: r for r in tiny["records"]}


class TestInference:
    def test_synthetic_image_is_identified_and_marked(self, tiny_synthetic, tiny_synthetic_model):
        from src.inference import analyze, render
        from src.synthetic.inference import SyntheticCheckpointClassifier

        rec = tiny_synthetic["records"][0]
        res = analyze(tiny_synthetic["root"] / rec["image_path"], records=[], synthetic_records=_index(tiny_synthetic),
                      classifier=_Raises(), synthetic_classifier=SyntheticCheckpointClassifier(tiny_synthetic_model["checkpoint"]))
        d = res.to_dict()
        assert d["dataset_type"] == "synthetic" and d["dataset"]["indicator"] == "SYNTHETIC DEMONSTRATION"
        assert d["summary"].startswith(UI_BANNER) and any(MARKER in w for w in d["warnings"])
        assert d["dataset"]["ground_truth"]["label"] == rec["script_type"]
        cls = d["layers"]["ai_observation"]["classification"]
        assert cls["status"] == "predicted" and set(cls["probabilities"]) == set(SYNTHETIC_LABELS)
        assert cls["is_evidence"] is False and "SYNTHETIC" in cls["statement"]
        assert not d["layers"]["expert_annotation"]["annotations"] and not d["image"]["registered"]
        assert "SYNTHETIC DEMONSTRATION" in render(res)

    def test_without_a_synthetic_model_nothing_is_predicted(self, tiny_synthetic):
        from src.inference import analyze

        rec = tiny_synthetic["records"][0]
        d = analyze(tiny_synthetic["root"] / rec["image_path"], records=[], synthetic_records=_index(tiny_synthetic),
                    classifier=_Raises()).to_dict()
        assert d["dataset_type"] == "synthetic" and d["layers"]["ai_observation"]["classification"]["status"] == "no_model"

    def test_research_and_unregistered_images_never_reach_the_synthetic_model(self, tiny_synthetic, world):
        from src.inference import analyze

        buf = io.BytesIO()
        Image.new("RGB", (80, 80), (10, 120, 200)).save(buf, format="PNG")
        un = analyze(buf.getvalue(), records=[], synthetic_records=_index(tiny_synthetic), synthetic_classifier=_Raises())
        assert un.dataset_type == "unregistered" and un.dataset["indicator"] == "UNREGISTERED IMAGE"
        reg = analyze(world["raw"] / world["records"][0]["image_path"], records=world["records"], store=world["store"],
                      synthetic_records=_index(tiny_synthetic), synthetic_classifier=_Raises())
        assert reg.dataset_type == "research" and reg.dataset["indicator"] == "REAL RESEARCH DATA"

    def test_http_api_synthetic_and_real(self, tiny_synthetic, tiny_synthetic_model, monkeypatch, live_research):
        import src.inference as inference
        from src.inference.server import make_handler
        from src.synthetic.inference import SyntheticCheckpointClassifier

        monkeypatch.setattr(inference, "synthetic_index", lambda: _index(tiny_synthetic))
        clf = SyntheticCheckpointClassifier(tiny_synthetic_model["checkpoint"])
        httpd = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(50 * 2**20, clf))
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        base = f"http://127.0.0.1:{httpd.server_address[1]}"

        def post(data: bytes, ctype: str) -> dict:
            req = urllib.request.Request(base + "/analyze", data=data, method="POST", headers={"Content-Type": ctype})
            with urllib.request.urlopen(req, timeout=120) as resp:
                return json.loads(resp.read().decode("utf-8"))

        try:
            with urllib.request.urlopen(base + "/health", timeout=60) as resp:
                assert json.loads(resp.read())["synthetic_model_loaded"] is True
            rec = tiny_synthetic["records"][0]
            body = post((tiny_synthetic["root"] / rec["image_path"]).read_bytes(), "image/jpeg")
            assert body["dataset_type"] == "synthetic" and body["summary"].startswith(UI_BANNER)
            assert body["layers"]["ai_observation"]["classification"]["status"] == "predicted"
            real = [r for r in live_research["records"] if (live_research["raw_root"] / r["image_path"]).is_file()]
            if real:                                         # a real, openly licensed research photograph
                body = post((live_research["raw_root"] / real[0]["image_path"]).read_bytes(), "image/jpeg")
                assert body["dataset_type"] == "research" and body["image"]["registered"] is True
                assert body["image"]["license"] == real[0]["license"]
                assert body["layers"]["ai_observation"]["classification"]["status"] == "no_model"
        finally:
            httpd.shutdown()
            httpd.server_close()


LIVE_SYNTHETIC = (ROOT / "data" / "synthetic" / "metadata" / "records.jsonl").exists()


class TestUI:
    @pytest.fixture
    def apptest(self, tmp_path, monkeypatch):
        from streamlit.testing.v1 import AppTest

        monkeypatch.setenv("ETPAI_ANNOTATIONS_PATH", str(tmp_path / "annotations.jsonl"))
        return lambda name: AppTest.from_file(str(ROOT / "app" / name), default_timeout=300)

    @staticmethod
    def _html(at) -> str:
        return "\n".join(x.proto.body for x in at.get("html"))

    @pytest.mark.skipif(not LIVE_SYNTHETIC, reason="no generated synthetic dataset under data/synthetic")
    def test_analysis_page_synthetic_mode(self, apptest):
        at = apptest("analyze.py").run()
        at.radio(key="mode").set_value("A synthetic demonstration image").run()
        assert not at.exception, [e.value for e in at.exception]
        html = self._html(at)
        assert 'class="etp-synthetic"' in html and UI_BANNER in html and "b-synthetic" in html
        assert MARKER in html and "task label, not evidence" in html
        assert "b-real" not in html and "b-verified" not in html.split('class="etp-synthetic"')[1].split("</section>")[0]
        assert not at.success

    def test_analysis_page_research_mode_shows_real_indicator(self, apptest, live_research):
        if not live_research["records"]:
            pytest.skip("no research records")
        at = apptest("analyze.py").run()
        at.radio(key="mode").set_value("A registered research photograph").run()
        html = self._html(at)
        assert not at.exception and "b-real" in html and 'class="etp-synthetic"' not in html

    def test_dataset_page_states_it_shows_research_data_only(self, apptest):
        html = self._html(apptest("views/dataset.py").run())
        assert "b-real" in html and "never counted here" in html
