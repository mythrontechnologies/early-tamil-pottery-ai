"""Milestone 10: the complete synthetic AI demonstration.

SYNTHETIC — NOT ARCHAEOLOGICAL EVIDENCE. Models here are the tiny CPU models of conftest.py
(``tiny_synthetic_model``, ``tiny_synthetic_pipeline``), trained in pytest's temporary directory.
Live-model UI tests skip when the real synthetic models are not present on the machine.
"""

from __future__ import annotations

import io
import json
import re
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

import numpy as np
import pytest
import torch
from conftest import ROOT
from PIL import Image

from src.synthetic import SYNTHETIC_LABELS, SyntheticSeparationError
from src.synthetic.calibration import (
    Calibration,
    CalibrationError,
    apply_temperature,
    calibration_for,
    confidence_words,
    fit_temperature,
)
from src.synthetic.interpretation import CATEGORIES, GLYPH_GROUPS, interpret
from src.synthetic.pipeline import STAGES, STATEMENT, WARNING_CODE, SyntheticPipelineError, ocr_crop
from src.synthetic.reasoning import CATEGORIES as CHRONO_CATEGORIES
from src.synthetic.reasoning import chronology
from src.synthetic.vision import DetectedRegion, VisionModelError, load_model, match_boxes, save_model

YEARS = re.compile(r"\b(\d{2,4}\s*(BCE|CE|BC|AD)|century|centuries)\b", re.IGNORECASE)


# --------------------------------------------------------------------------- #
# Calibration
# --------------------------------------------------------------------------- #


class TestCalibration:
    def test_temperature_recovers_overconfidence_and_keeps_the_decision(self):
        rng = np.random.default_rng(0)
        n, k = 4000, 4
        logits = rng.normal(0, 1, (n, k)) * 2.0
        y = np.array([rng.choice(k, p=np.exp(row) / np.exp(row).sum()) for row in logits])
        over = np.exp(3 * logits) / np.exp(3 * logits).sum(axis=1, keepdims=True)      # 3x too sharp
        t = fit_temperature(over, y)
        assert 2.5 < t < 3.5
        cal = apply_temperature(over, t)
        assert np.array_equal(cal.argmax(1), over.argmax(1)) and np.allclose(cal.sum(1), 1)

    def test_bound_to_the_model_fingerprint(self, tmp_path):
        cal = Calibration(1.7, "fp-a", "ds-1", "sd", "x.pt", "exp")
        cal.save(tmp_path)
        assert calibration_for({"model_fingerprint": "fp-a", "dataset_fingerprint": "ds-1"}, tmp_path).temperature == 1.7
        assert calibration_for({"model_fingerprint": "fp-b", "dataset_fingerprint": "ds-1"}, tmp_path) is None
        with pytest.raises(CalibrationError):
            calibration_for({"model_fingerprint": "fp-a", "dataset_fingerprint": "other"}, tmp_path)
        (tmp_path / "bad.json").write_text(json.dumps(cal.to_dict() | {"dataset_type": "research"}), encoding="utf-8")
        with pytest.raises(CalibrationError):
            Calibration.load(tmp_path / "bad.json")

    def test_save_location_and_wording(self):
        with pytest.raises(SyntheticSeparationError):
            Calibration(1.0, "f", "d", "s", "c", "e").save(ROOT / "models" / "experiments")
        assert confidence_words(0.95).startswith("high") and "unsure" in confidence_words(0.3)


# --------------------------------------------------------------------------- #
# Interpretation, chronology, reasoning
# --------------------------------------------------------------------------- #


class TestSyntheticInterpretation:
    @pytest.mark.parametrize("words,cls,expected", [
        ([], "synthetic_none", "synthetic_no_reading"),
        ([], "synthetic_graffiti_like", "synthetic_symbolic_mark_like"),
        ([["SG12", "SG15"]], None, "synthetic_numeral_like"),
        ([["SG01", "SG02"], ["SG09", "SG03"]], None, "synthetic_name_and_title_like"),
        ([["SG01", "SG10"]], None, "synthetic_ownership_formula_like"),
        ([["SG01", "SG02", "SG03"]], None, "synthetic_personal_name_like"),
    ])
    def test_rules(self, words, cls, expected):
        assert interpret(words, cls).category == expected

    def test_never_language_or_people(self):
        assert len(GLYPH_GROUPS) == 16
        for cat, text in CATEGORIES.items():
            assert cat.startswith("synthetic_") and ("synthetic" in text or "no synthetic" in text)
        for text in CATEGORIES.values():
            assert "no person" in text or "no number" in text or "no owner" in text or "no symbol" in text or "no synthetic" in text


class TestSyntheticChronology:
    def test_estimated_conflict_insufficient(self):
        est = chronology(words=[["SG04", "SG05"]], synthetic_class="synthetic_tamil_brahmi_like", class_confidence=0.9,
                         ocr_score=0.95, surface="reddish")
        assert est.state == "estimated" and est.categories == ["SYNTH_CAT_02", "SYNTH_CAT_03"]
        conflict = chronology(words=[["SG08", "SG09"]], synthetic_class="synthetic_tamil_brahmi_like", class_confidence=0.9,
                              ocr_score=0.9, surface="dark")
        assert conflict.state == "conflict" and conflict.categories == [] and len(conflict.conflict) == 3
        assert "not averaged" in conflict.display
        none = chronology(words=[], synthetic_class="synthetic_none", class_confidence=0.9, ocr_score=None, surface=None)
        assert none.state == "insufficient" and none.confidence == "none"

    def test_no_years_or_periods_ever(self):
        for words in ([], [["SG00"]], [["SG12", "SG13"]]):
            for surface in (None, "buff", "dark"):
                c = chronology(words=words, synthetic_class="synthetic_tamil_brahmi_like", class_confidence=0.5,
                               ocr_score=0.5, surface=surface).to_dict()
                assert not YEARS.search(json.dumps(c)) and set(c["categories"]) <= set(CHRONO_CATEGORIES)
                assert c["statement"] == "Synthetic demonstration — not archaeological dating."


# --------------------------------------------------------------------------- #
# Vision helpers and persistence
# --------------------------------------------------------------------------- #


class TestVisionHelpers:
    def test_box_matching_is_one_to_one(self):
        m = match_boxes([(0, 0, 0.5, 0.5), (0.02, 0, 0.5, 0.5)], [(0, 0, 0.5, 0.5)])
        assert len(m) == 1 and m[0][2] > 0.99

    def test_ocr_crop_unites_row_and_containing_region(self):
        row = DetectedRegion(0.4, 0.4, 0.2, 0.1, 0.9, "synthetic_glyph_row")
        region = DetectedRegion(0.2, 0.35, 0.6, 0.2, 0.9, "synthetic_inscription_region")
        elsewhere = DetectedRegion(0.0, 0.0, 0.1, 0.1, 0.9, "synthetic_inscription_region")
        assert ocr_crop(row, [region, elsewhere], 100, 100) == (20, 35, 80, 55)
        assert ocr_crop(row, [elsewhere], 100, 100) == (40, 40, 60, 50)

    def test_weights_are_fingerprinted_typed_and_located(self, tmp_path):
        from src.synthetic.ocr_benchmark import GlyphNet

        info = save_model(GlyphNet(), tmp_path / "g.pt", "glyph_classifier", {})
        assert load_model(tmp_path / "g.pt", "glyph_classifier", info)
        with pytest.raises(VisionModelError):
            load_model(tmp_path / "g.pt", "glyph_centers", info)                     # wrong kind
        blob = torch.load(tmp_path / "g.pt", weights_only=True)
        blob["state_dict"]["head.2.bias"] += 1
        torch.save(blob, tmp_path / "g.pt")
        with pytest.raises(VisionModelError):
            load_model(tmp_path / "g.pt", "glyph_classifier", info)                   # manifest hash
        with pytest.raises(VisionModelError):
            load_model(tmp_path / "g.pt", "glyph_classifier", None)                   # weights vs fingerprint
        with pytest.raises(SyntheticSeparationError):
            save_model(GlyphNet(), ROOT / "models" / "checkpoints" / "g.pt", "glyph_classifier", {})


# --------------------------------------------------------------------------- #
# The complete pipeline (tiny CPU models)
# --------------------------------------------------------------------------- #


def _brahmi(tiny):
    return next(r for r in tiny["records"] if r["script_type"] == "synthetic_tamil_brahmi_like")


class TestPipeline:
    def test_bundle_manifest(self, tiny_synthetic_pipeline):
        m = json.loads((tiny_synthetic_pipeline["bundle_dir"] / "manifest.json").read_text(encoding="utf-8"))
        assert m["dataset_type"] == "synthetic" and m["segmentation"]["selected_on"] == "val"
        assert set(m["segmentation"]["comparison_val"]) == {"projection", "components", "learned_centers"}
        for k in ("region_detector", "glyph_classifier", "glyph_centers"):
            assert m["models"][k]["model_fingerprint"] and m["models"][k]["sha256"]
        for k in ("dataset_fingerprint", "split_digest", "synthetic_fingerprint", "generator_version", "git", "seed"):
            assert m[k]

    def test_complete_run(self, tiny_synthetic, tiny_synthetic_pipeline):
        rec = _brahmi(tiny_synthetic)
        seen = []
        a = tiny_synthetic_pipeline["pipeline"].run(tiny_synthetic["root"] / rec["image_path"], record=rec,
                                                    on_stage=seen.append)
        assert [s["key"] for s in seen] == [k for k, _ in STAGES] and all(s["seconds"] >= 0 for s in seen)
        assert a["dataset_type"] == "synthetic" and a["warning"] == WARNING_CODE and a["statement"] == STATEMENT
        c = a["classification"]
        assert c["label"] in SYNTHETIC_LABELS and abs(sum(c["probabilities"].values()) - 1) < 1e-3
        assert c["display_label"].startswith("Synthetic ") and "calibrat" in c["calibration_status"].lower()
        assert all(r["class"] == "synthetic_inscription_region" for r in a["inscription"]["regions"])
        assert len(a["evidence_chain"]) == 8 and all(n["synthetic"] for n in a["evidence_chain"])
        assert a["reasoning"][-1].startswith("This result has no archaeological significance")
        assert all(line.startswith("SYNTHETIC") for line in a["reasoning"][:-1])
        assert ("uncalibrated model probability" in a["reasoning"][0]) is not c["calibrated"]   # never claims calibration it lacks
        gt = a["ground_truth_check"]
        assert gt["true_label"] == rec["script_type"] and "true_transcription" in gt
        perf = a["performance"]
        assert perf["total_seconds"] > 0 and set(perf["stage_seconds"]) == {k for k, _ in STAGES}
        text = json.dumps(a, ensure_ascii=False)
        assert "Tamil-Brahmi transcription" not in text and not YEARS.search(text)
        if a["ocr"]["status"] == "read":
            assert a["ocr"]["label"] == "Synthetic glyph transcription"

    def test_refuses_models_from_different_synthetic_data(self, tiny_synthetic_model, tiny_synthetic_pipeline, tmp_path):
        import shutil

        from src.synthetic.pipeline import SyntheticPipeline

        other = tmp_path / "other_bundle"
        shutil.copytree(tiny_synthetic_pipeline["bundle_dir"], other)
        m = json.loads((other / "manifest.json").read_text(encoding="utf-8"))
        m["dataset_fingerprint"] = "0" * 64
        (other / "manifest.json").write_text(json.dumps(m), encoding="utf-8")
        with pytest.raises(SyntheticPipelineError, match="different synthetic"):
            SyntheticPipeline(tiny_synthetic_model["checkpoint"], other, device="cpu")

    def test_analyze_runs_the_pipeline_on_synthetic_images_only(self, tiny_synthetic, tiny_synthetic_pipeline, world):
        from src.inference import analyze

        pipe, index = tiny_synthetic_pipeline["pipeline"], tiny_synthetic_pipeline["index"]
        rec = _brahmi(tiny_synthetic)
        d = analyze(tiny_synthetic["root"] / rec["image_path"], records=[], synthetic_records=index,
                    synthetic_pipeline=pipe).to_dict()
        assert d["dataset_type"] == "synthetic" and d["synthetic_analysis"]["warning"] == WARNING_CODE
        assert d["dataset"]["warning_code"] == "synthetic_not_archaeological"
        assert all(r["source"] == "ai_prediction" and r["is_evidence"] is False for r in d["regions"])

        class Spy:
            classifier = pipe.classifier

            def run(self, *a, **k):
                raise AssertionError("the synthetic pipeline must not run on a research photograph")

        real = analyze(world["raw"] / world["records"][0]["image_path"], records=world["records"], store=world["store"],
                       synthetic_records=index, synthetic_pipeline=Spy()).to_dict()
        assert real["dataset_type"] == "research" and real["synthetic_analysis"] is None
        assert real["dataset"]["notice"] == "REAL RESEARCH PHOTO DETECTED"
        assert real["dataset"]["ml_inference"].startswith("Real archaeological inference is unavailable")
        assert real["layers"]["ai_observation"]["classification"]["status"] == "no_model"

    def test_demo_and_report(self, tiny_synthetic, tiny_synthetic_pipeline):
        from src.synthetic.demo import render_demo, run_demo

        a = run_demo(root=tiny_synthetic["root"], pipeline=tiny_synthetic_pipeline["pipeline"], record=False)
        text = render_demo(a)
        for line in ("SYNTHETIC DEMONSTRATION", "Classification:", "Model confidence:", "Inscription region:",
                     "Synthetic glyph transcription:", "Synthetic interpretation:", "Synthetic chronology:",
                     "This result has no archaeological significance and has not been validated on real material."):
            assert line in text
        assert a["demo"]["image_id"] == a["input"]["image_id"]

    def test_integrated_benchmark(self, tiny_synthetic, tiny_synthetic_model, tiny_synthetic_pipeline):
        from src.synthetic.benchmark import BANNER, render_benchmark, run_synthetic_benchmark

        r = run_synthetic_benchmark(root=tiny_synthetic["root"], device="cpu", robustness=False, save=False,
                                    log=lambda _m: None, pipeline=tiny_synthetic_pipeline["pipeline"],
                                    checkpoint=tiny_synthetic_model["checkpoint"])
        for key in ("A_classification", "B_detection", "C_ocr", "F_interpretation_and_chronology", "G_performance"):
            assert key in r
        assert {"precision", "recall", "f1", "mean_iou_of_matches"} <= set(r["B_detection"]["regions"])
        assert set(r["C_ocr"]["strategies"]) == {"projection", "components", "learned_centers"}
        text = render_benchmark(r)
        assert BANNER in text and "synthetic benchmark" in text and "synthetic glyph benchmark" in text
        assert "Tamil-Brahmi accuracy" not in text and "date prediction" not in text.lower()


# --------------------------------------------------------------------------- #
# API and CLI
# --------------------------------------------------------------------------- #


class TestApiAndCli:
    def test_synthetic_endpoint(self, tiny_synthetic, tiny_synthetic_pipeline, monkeypatch, live_research):
        import src.inference as inference
        from src.inference.server import make_handler

        monkeypatch.setattr(inference, "synthetic_index", lambda: tiny_synthetic_pipeline["index"])

        def serve(pipeline):
            httpd = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(50 * 2**20, None, pipeline))
            threading.Thread(target=httpd.serve_forever, daemon=True).start()
            return httpd, f"http://127.0.0.1:{httpd.server_address[1]}"

        def post(base, path, data):
            req = urllib.request.Request(base + path, data=data, method="POST", headers={"Content-Type": "image/jpeg"})
            try:
                with urllib.request.urlopen(req, timeout=120) as resp:
                    return resp.status, json.loads(resp.read().decode("utf-8"))
            except urllib.error.HTTPError as err:
                return err.code, json.loads(err.read().decode("utf-8"))

        rec = _brahmi(tiny_synthetic)
        blob = (tiny_synthetic["root"] / rec["image_path"]).read_bytes()
        httpd, base = serve(tiny_synthetic_pipeline["pipeline"])
        try:
            status, body = post(base, "/synthetic/analyze", blob)
            assert status == 200 and body["warning"] == "synthetic_not_archaeological"
            assert body["synthetic_analysis"]["dataset_type"] == "synthetic"
            status, body = post(base, "/analyze", blob)
            assert status == 200 and body["synthetic_analysis"]["warning"] == WARNING_CODE
            buf = io.BytesIO()
            Image.new("RGB", (90, 90), (1, 2, 3)).save(buf, format="JPEG")
            status, body = post(base, "/synthetic/analyze", buf.getvalue())
            assert status == 422 and body["dataset_type"] == "unregistered"
            real = [r for r in live_research["records"] if (live_research["raw_root"] / r["image_path"]).is_file()]
            if real:
                status, body = post(base, "/synthetic/analyze", (live_research["raw_root"] / real[0]["image_path"]).read_bytes())
                assert status == 422 and body["dataset"]["notice"] == "REAL RESEARCH PHOTO DETECTED"
        finally:
            httpd.shutdown()
            httpd.server_close()
        httpd, base = serve(None)
        try:
            assert post(base, "/synthetic/analyze", blob)[0] == 503
        finally:
            httpd.shutdown()
            httpd.server_close()

    def test_cli_synthetic(self, tiny_synthetic, tiny_synthetic_pipeline, monkeypatch, capsys, world):
        import src.inference as inference
        import src.inference.__main__ as cli

        monkeypatch.setattr(inference, "synthetic_index", lambda: tiny_synthetic_pipeline["index"])
        monkeypatch.setattr(cli, "_pipeline", lambda device="auto": tiny_synthetic_pipeline["pipeline"])
        rec = _brahmi(tiny_synthetic)
        assert cli.main(["synthetic", "--image", str(tiny_synthetic["root"] / rec["image_path"])]) == 0
        assert "SYNTHETIC DEMONSTRATION" in capsys.readouterr().out
        assert cli.main(["synthetic", "--image", str(tiny_synthetic["root"] / rec["image_path"]), "--json"]) == 0
        assert json.loads(capsys.readouterr().out)["warning"] == WARNING_CODE
        other = world["raw"] / world["records"][0]["image_path"]
        assert cli.main(["synthetic", "--image", str(other)]) == 3
        assert "synthetic engineering dataset" in capsys.readouterr().err


# --------------------------------------------------------------------------- #
# UI (live synthetic models)
# --------------------------------------------------------------------------- #

LIVE_MODELS = (ROOT / "models" / "synthetic" / "vision").is_dir() and any(
    (ROOT / "models" / "synthetic" / "checkpoints").glob("*/best.pt"))


@pytest.fixture
def apptest(tmp_path, monkeypatch):
    from streamlit.testing.v1 import AppTest

    monkeypatch.setenv("ETPAI_ANNOTATIONS_PATH", str(tmp_path / "annotations.jsonl"))
    return lambda name: AppTest.from_file(str(ROOT / "app" / name), default_timeout=300)


def _html(at) -> str:
    return "\n".join(x.proto.body for x in at.get("html"))


class TestUi:
    def test_real_research_is_the_default_mode(self, apptest):
        at = apptest("analyze.py").run()
        assert not at.exception and at.segmented_control(key="data_mode").value == "Real Research"
        html = _html(at)
        assert "REAL RESEARCH MODE" in html and "etp-mode-banner" not in html
        assert all(r != "A synthetic demonstration image" for r in at.radio(key="mode").options)

    def test_research_photo_notice(self, apptest, live_research):
        if not live_research["records"]:
            pytest.skip("no research records")
        at = apptest("analyze.py").run()
        at.radio(key="mode").set_value("A registered research photograph").run()
        html = _html(at)
        assert "REAL RESEARCH PHOTO DETECTED" in html
        assert "Real archaeological inference is unavailable until expert-labelled training data is available." in html
        assert "b-synthetic" not in html and "etp-synthetic" not in html

    @pytest.mark.skipif(not LIVE_MODELS, reason="no trained synthetic models on this machine")
    def test_synthetic_demo_flow(self, apptest):
        at = apptest("analyze.py")
        at.query_params["data"] = "synthetic"
        at.run()
        assert not at.exception and at.segmented_control(key="data_mode").value == "Synthetic Demonstration"
        assert "etp-mode-banner" in _html(at)
        at.button(key="run_synthetic").click().run()
        assert not at.exception, [e.value for e in at.exception]
        html = _html(at)
        for needle in ("Synthetic model output — not archaeological evidence.", "Synthetic glyph transcription",
                       "Synthetic evidence chain", "Synthetic chronology", "Synthetic demonstration — not archaeological dating.",
                       "Ground-truth check", "Performance of this run", "Model confidence", "synthetic benchmark calibration",
                       "This result has no archaeological significance and has not been validated on real material."):
            assert needle in html, needle
        assert "b-verified" not in html and "Tamil-Brahmi transcription" not in html
        assert not at.success

    def test_replay_component_is_labelled_and_accessible(self):
        import sys

        sys.path.insert(0, str(ROOT / "app"))
        from ui.synthetic3d import replay_html

        a = {"classification": {"display_label": "Synthetic graffiti-like class", "confidence": 0.7},
             "ocr": {"status": "no_reading", "transcription": ""}, "inscription": {"regions": []},
             "stages": [{"number": i + 1, "title": t, "seconds": 0.001, "summary": f"</script><b>{k}</b>"}
                        for i, (k, t) in enumerate(STAGES)], "performance": {"total_seconds": 0.01}}
        page = replay_html(a)
        assert "Illustrative visualization · not a scan of the input image · SYNTHETIC" in page
        assert "prefers-reduced-motion" in page and 'aria-live="polite"' in page and "2D view" in page
        assert "</script><b>" not in page                     # data can never close the script element
        for label in ("Pause the replay", "Skip to the end", "Replay the recorded run", "Show the illustration in 2D"):
            assert label in page


# --------------------------------------------------------------------------- #
# Separation of the Milestone 10 artefacts
# --------------------------------------------------------------------------- #


class TestM10Separation:
    def test_a_synthetic_result_cannot_become_expert_evidence(self, tiny_synthetic, tiny_synthetic_pipeline, world):
        from test_expert_pilot import NOREFS, expert

        from src.annotation.store import AnnotationRejected

        rec = _brahmi(tiny_synthetic)
        a = tiny_synthetic_pipeline["pipeline"].run(tiny_synthetic["root"] / rec["image_path"], record=rec)
        ann = expert(rec["artifact_id"], reading=a["ocr"]["transcription"] or "SG00")
        ann["image_ids"] = [rec["image_id"]]
        with pytest.raises(AnnotationRejected) as err:
            world["store"].append(ann, **NOREFS)
        assert any(p.rule == "N17" for p in err.value.validation.problems)
        assert world["store"].all() == []

    def test_benchmark_reports_stay_in_models_synthetic(self):
        from src.synthetic import SYNTHETIC_MODELS_ROOT, assert_synthetic_model_destination
        from src.synthetic.benchmark import REPORT_DIR
        from src.synthetic.demo import RUNS_DIR

        for d in (REPORT_DIR, RUNS_DIR):
            assert d.resolve().is_relative_to(SYNTHETIC_MODELS_ROOT.resolve())
        with pytest.raises(SyntheticSeparationError):
            assert_synthetic_model_destination(ROOT / "models" / "experiments" / "benchmark.json")

    def test_vision_weights_are_not_checkpoints(self, tiny_synthetic_pipeline):
        from src.classification import CheckpointClassifier
        from src.training.checkpoint import CheckpointError, load_checkpoint

        f = tiny_synthetic_pipeline["bundle_dir"] / "region_detector.pt"
        with pytest.raises(CheckpointError):
            load_checkpoint(f)
        with pytest.raises(CheckpointError):
            CheckpointClassifier(f)
