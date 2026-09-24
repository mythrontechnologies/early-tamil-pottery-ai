"""The inference pipeline and API (src.inference, src.detection, src.ocr, src.classification).

All images, annotations and checkpoints are SYNTHETIC (tmp_path). Live raw images are only
READ, and a test asserts they are unchanged.
"""

from __future__ import annotations

import hashlib
import io
import json
import threading
import urllib.error
import urllib.request
from copy import deepcopy
from http.server import ThreadingHTTPServer

import pytest
from PIL import Image
from test_expert_pilot import NOREFS, annotation, expert

from src.classification import NO_MODEL, CheckpointClassifier, ClassificationResult
from src.detection import NO_DETECTOR, Region, RegionError, crop, parse_region
from src.inference import LAYERS, InferenceError, analyze, render
from src.inference.__main__ import main as cli
from src.inference.server import make_handler
from src.ocr import NO_TRANSCRIPTION, OCRResult, enhance, screen_ocr
from src.reasoning.engine import INSUFFICIENT


def _png(seed: int = 7, size: int = 64) -> bytes:
    img = Image.new("RGB", (size, size), (seed * 3 % 255, 120, 90))
    img.putpixel((seed % size, 3), (255, 255, 255))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _world_image(world, n: int = 0) -> bytes:
    return (world["raw"] / world["records"][n]["image_path"]).read_bytes()


def _run(world, data, **kw):
    return analyze(data, store=world["store"], records=world["records"], **kw)


class _FakeClassifier:
    name = "SYNTHETIC_fake"

    def classify(self, image):
        return ClassificationResult("predicted", "SYNTHETIC", label="tamil_brahmi",
                                    probabilities={"tamil_brahmi": 0.97, "graffiti": 0.01, "none": 0.01, "uncertain": 0.01},
                                    model={"name": "SYNTHETIC"})


class _FakeOCR:
    name = "SYNTHETIC_ocr"

    def __init__(self, text, score):
        self.text, self.score = text, score

    def transcribe(self, crop):
        return OCRResult("candidate", "raw", text=self.text, confidence=self.score, engine=self.name)


class TestUnregisteredImages:
    def test_unknown_image_gives_insufficient_evidence(self, world):
        r = _run(world, _png())
        d = r.to_dict()
        assert r.summary == INSUFFICIENT and d["image"]["registered"] is False
        assert d["age"]["display"] == INSUFFICIENT and d["confidence"]["archaeological"] == "unknown"
        assert d["transcription"]["statement"] == NO_TRANSCRIPTION
        assert d["classification"]["ai_observation"]["statement"] == NO_MODEL
        assert any("Unregistered image" in w for w in d["warnings"])
        assert set(LAYERS) <= set(d["layers"])
        assert d["layers"]["verified_evidence"]["references"] == []
        assert set(d) >= {"classification", "script", "transcription", "translation", "age", "period",
                          "confidence", "reasoning", "evidence", "warnings", "image_quality"}

    def test_naming_an_artifact_does_not_attach_its_annotations(self, world):
        art = world["arts"][0]
        world["store"].append(expert(art, script="tamil_brahmi"), **NOREFS)
        d = _run(world, _png(), artifact_id=art).to_dict()
        assert d["script"]["statement"] == "Script not determined."
        assert d["layers"]["expert_annotation"]["annotations"] == []
        assert any("NOT applied" in w for w in d["warnings"])


class TestRegisteredImages:
    def test_registered_photo_uses_human_evidence_only(self, world):
        art = world["arts"][0]
        world["store"].append(expert(art, script="graffiti", regions=[(0.1, 0.1, 0.3, 0.2)]), **NOREFS)
        d = _run(world, _world_image(world), classifier=_FakeClassifier()).to_dict()
        assert d["image"]["registered"] and d["image"]["artifact_id"] == art
        assert d["script"]["value"] == "graffiti" and d["script"]["provenance"] == "expert_annotation"
        # the AI said tamil_brahmi with 0.97: reported, never adopted
        assert d["classification"]["ai_observation"]["label"] == "tamil_brahmi"
        assert d["classification"]["ai_observation"]["is_evidence"] is False
        assert [x["source"] for x in d["regions"]] == ["human_annotation"]
        assert len(d["layers"]["expert_annotation"]["annotations"]) == 1

    def test_personal_name_gets_no_literal_translation_and_tamil_survives(self, world):
        art = world["arts"][1]
        world["store"].append(expert(art, reading="சாதன்", itype="personal_name"), **NOREFS)
        r = _run(world, _world_image(world, 1))
        d = json.loads(r.to_json())
        assert d["translation"]["state"] == "personal_name" and d["translation"]["translation"] == "not_applicable"
        assert "சாதன்" in d["transcription"]["statement"]

    def test_project_only_annotation_is_labelled_not_expert(self, world):
        art = world["arts"][2]
        world["store"].append(annotation(art, script="graffiti"), **NOREFS)
        d = _run(world, _world_image(world, 2)).to_dict()
        assert len(d["layers"]["project_annotation"]["annotations"]) == 1
        assert d["layers"]["expert_annotation"]["annotations"] == []
        assert any("not expert-reviewed" in w for w in d["warnings"])

    def test_conflicting_dates_are_not_averaged(self, world):
        art = world["arts"][3]
        world["store"].append(expert(art, who="SYN_e1", dating=(-300, -200, "palaeography")), **NOREFS)
        world["store"].append(expert(art, who="SYN_e2", dating=(100, 200, "palaeography")), **NOREFS)
        d = _run(world, _world_image(world, 3)).to_dict()
        assert d["confidence"]["archaeological"] in ("low", "very_low", "unknown")
        text = json.dumps(d["age"])
        assert "50 BCE" not in text and "50 CE" not in text

    def test_deterministic(self, world):
        a = _run(world, _world_image(world)).analysis_digest
        assert a == _run(world, _world_image(world)).analysis_digest


class TestOCRAndRegions:
    def test_weak_ocr_is_discarded(self, world):
        d = _run(world, _png(), transcriber=_FakeOCR("ka ta", 0.4)).to_dict()
        ocr = d["transcription"]["ocr"][0]
        assert ocr["status"] == "no_reliable_transcription" and ocr["text"] is None
        assert d["transcription"]["statement"] == NO_TRANSCRIPTION

    def test_strong_ocr_is_only_a_candidate_never_a_reading(self, world):
        d = _run(world, _png(), transcriber=_FakeOCR("ka ta", 0.95)).to_dict()
        ocr = d["transcription"]["ocr"][0]
        assert ocr["status"] == "candidate" and ocr["is_reading"] is False and ocr["provenance"] == "ai_prediction"
        assert d["transcription"]["statement"] == NO_TRANSCRIPTION          # no human reading
        assert d["reasoning"] and "ka ta" not in " ".join(d["reasoning"])

    def test_screen_ocr_empty_candidate(self):
        assert screen_ocr(OCRResult("candidate", "x", text="  ", confidence=0.99)).status == "no_reliable_transcription"

    def test_user_region_is_not_evidence(self, world):
        d = _run(world, _png(), regions=[parse_region("0.1,0.1,0.5,0.5")]).to_dict()
        assert d["regions"][0]["source"] == "user_supplied" and d["regions"][0]["is_evidence"] is False
        assert d["layers"]["ai_observation"]["region_detection"]["statement"] == NO_DETECTOR

    @pytest.mark.parametrize("bad", ["0.9,0.9,0.5,0.5", "-0.1,0,0.2,0.2", "0,0,0,0.2", "a,b,c,d", "0.1,0.2", "nan,0,0.1,0.1"])
    def test_invalid_regions_refused(self, bad):
        with pytest.raises(RegionError):
            parse_region(bad)

    def test_crop_and_enhance_do_not_modify_the_image(self):
        img = Image.open(io.BytesIO(_png())).convert("RGB")
        before = img.tobytes()
        c = crop(img, Region(0.25, 0.25, 0.5, 0.5, "user_supplied"))
        e1, e2 = enhance(c), enhance(c)
        assert img.tobytes() == before and c.size == (32, 32)
        assert e1.mode == "L" and e1.tobytes() == e2.tobytes()


class TestImageSafety:
    def test_corrupted_bytes(self, world):
        with pytest.raises(InferenceError):
            _run(world, b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)

    def test_truncated_image(self, world):
        data = _png(size=256)
        with pytest.raises(InferenceError):
            _run(world, data[: len(data) // 2])

    def test_empty_and_oversized(self, world):
        with pytest.raises(InferenceError, match="empty"):
            _run(world, b"")
        with pytest.raises(InferenceError, match="limit"):
            _run(world, _png(), max_bytes=10)

    def test_decompression_bomb_ceiling(self, world):
        from src.dataset.schema import load_config

        cfg = deepcopy(load_config())
        cfg["preprocessing"]["max_pixels"] = 1000
        with pytest.raises(InferenceError):
            _run(world, _png(size=200), config=cfg)

    def test_directory_and_missing_path(self, world, tmp_path):
        with pytest.raises(InferenceError, match="not a regular file"):
            _run(world, tmp_path)
        with pytest.raises(InferenceError):
            _run(world, tmp_path / "nope.png")

    def test_unsupported_format(self, world):
        with pytest.raises(InferenceError):
            _run(world, b"GIF89a" + b"\x00" * 64)

    def test_live_raw_image_is_not_modified(self, live_research):
        if not live_research["records"]:
            pytest.skip("no research records")
        rec = live_research["records"][0]
        path = live_research["raw_root"] / rec["image_path"]
        if not path.exists():
            pytest.skip("image not present")
        before = (path.stat().st_mtime_ns, hashlib.sha256(path.read_bytes()).hexdigest())
        d = analyze(path).to_dict()
        assert d["image"]["registered"] and d["image"]["artifact_id"] == rec["artifact_id"]
        assert (path.stat().st_mtime_ns, hashlib.sha256(path.read_bytes()).hexdigest()) == before


class TestCheckpointClassifier:
    def test_synthetic_checkpoint_gives_ai_probabilities(self, tmp_path):
        from test_training_framework import _NoiseDataset, _trainer
        from torch.utils.data import DataLoader

        fit = _trainer(tmp_path, optimization={"epochs": 1}).fit(
            DataLoader(_NoiseDataset(8, 4), batch_size=8), DataLoader(_NoiseDataset(8, 4, seed=1), batch_size=8))
        clf = CheckpointClassifier(fit.last_checkpoint)
        res = clf.classify(Image.open(io.BytesIO(_png())).convert("RGB"))
        assert res.status == "predicted" and res.provenance == "ai_prediction" and res.is_evidence is False
        assert abs(sum(res.probabilities.values()) - 1.0) < 1e-4
        assert res.model["fingerprint"] and res.model["dataset_fingerprint"] == "SYNTHETIC"


class TestInterfaces:
    def test_cli_analyze_and_errors(self, tmp_path, capsys):
        f = tmp_path / "x.png"
        f.write_bytes(_png())
        assert cli(["analyze", str(f), "--json"]) == 0
        assert json.loads(capsys.readouterr().out)["summary"] == INSUFFICIENT
        assert cli(["analyze", str(f), "--region", "2,2,2,2"]) == 2
        (tmp_path / "bad.png").write_bytes(b"not an image")
        assert cli(["analyze", str(tmp_path / "bad.png")]) == 1
        assert "IMAGE QUALITY" in render(analyze(f))

    def test_http_api(self):
        httpd = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(max_bytes=200_000))
        t = threading.Thread(target=httpd.serve_forever, daemon=True)
        t.start()
        base = f"http://127.0.0.1:{httpd.server_address[1]}"
        try:
            with urllib.request.urlopen(base + "/health", timeout=30) as resp:
                assert json.loads(resp.read())["status"] == "ok"
            req = urllib.request.Request(base + "/analyze", data=_png(), method="POST",
                                         headers={"Content-Type": "image/png"})
            with urllib.request.urlopen(req, timeout=60) as resp:
                body = json.loads(resp.read().decode("utf-8"))
            assert body["summary"] == INSUFFICIENT and body["image"]["registered"] is False

            def status(data, ctype="image/png", path="/analyze"):
                r = urllib.request.Request(base + path, data=data, method="POST", headers={"Content-Type": ctype})
                try:
                    urllib.request.urlopen(r, timeout=30)
                except urllib.error.HTTPError as e:
                    return e.code
                return 200

            assert status(b"x" * 300_000) == 413
            assert status(b"not an image") == 422
            assert status(_png(), ctype="text/plain") == 415
            assert status(b"/etc/passwd", path="/analyze?path=/etc/passwd") == 422   # bytes, never a path
            assert status(_png(), path="/other") == 404
        finally:
            httpd.shutdown()
            httpd.server_close()
