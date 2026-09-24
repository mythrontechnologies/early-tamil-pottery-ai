"""Evaluation infrastructure added in the final engineering phase: calibration, confidence
analysis, OCR error rates, the blocked path and the reproducibility report.

All predictions are SYNTHETIC numbers; no metric here is an archaeological result.
"""

from __future__ import annotations

import unicodedata

import numpy as np
import pytest

from src.evaluation.calibration import calibration_report
from src.evaluation.metrics import BLOCKED_REASON, blocked_report, compute_metrics, evaluate_predictions
from src.evaluation.ocr import OCR_BLOCKED, character_error_rate, evaluate_ocr, word_error_rate
from src.evaluation.reproducibility import render_report, reproducibility_report

FOUR = ["tamil_brahmi", "graffiti", "none", "uncertain"]


class TestCalibration:
    def test_perfectly_calibrated_bins_have_zero_ece(self):
        # confidence 1.0 and always right
        probs = np.eye(4)[[0, 1, 2, 3]]
        rep = calibration_report([0, 1, 2, 3], probs)
        assert rep["ece"] == 0.0 and rep["mce"] == 0.0 and rep["brier"] == 0.0

    def test_confidently_wrong_is_maximally_miscalibrated(self):
        probs = np.eye(4)[[1, 2, 3, 0]]
        rep = calibration_report([0, 1, 2, 3], probs)
        assert rep["ece"] == 1.0 and rep["brier"] == pytest.approx(2.0)
        assert rep["confidence_analysis"]["overconfident"] is True
        assert rep["confidence_analysis"]["mean_confidence_correct"] is None

    def test_empty_bins_are_reported_as_empty_not_zero(self):
        rep = calibration_report([0], np.array([[0.55, 0.15, 0.15, 0.15]]), n_bins=10)
        empty = [b for b in rep["reliability"] if b["n"] == 0]
        assert len(empty) == 9 and all(b["accuracy"] is None for b in empty)

    def test_no_samples_and_bad_shapes(self):
        assert calibration_report([], np.zeros((0, 4))) is None
        with pytest.raises(ValueError):
            calibration_report([0, 1], np.zeros((3, 4)))

    def test_compute_metrics_carries_calibration_only_with_probabilities(self):
        probs = np.array([[0.7, 0.1, 0.1, 0.1], [0.2, 0.6, 0.1, 0.1], [0.1, 0.1, 0.4, 0.4]])
        m = compute_metrics([0, 1, 3], [0, 1, 2], FOUR, y_prob=probs)
        assert m.calibration and 0 <= m.calibration["ece"] <= 1
        assert compute_metrics([0, 1], [0, 1], FOUR).calibration is None
        text = evaluate_predictions([0, 1, 3], [0, 1, 2], FOUR, y_prob=probs, provenance="synthetic_test").render()
        assert "ECE" in text and "NOT AN ARCHAEOLOGICAL RESULT" in text


class TestBlocked:
    def test_blocked_report_states_the_reason(self):
        text = blocked_report().render()
        assert BLOCKED_REASON == "Evaluation blocked — insufficient expert-labelled archaeological data."
        assert BLOCKED_REASON in text
        assert evaluate_predictions([], [], FOUR).status == "BLOCKED"


class TestOCRMetrics:
    def test_cer_and_wer(self):
        assert character_error_rate("sathan", "sathan") == 0.0
        assert character_error_rate("sathan", "satan") == pytest.approx(1 / 6)
        assert word_error_rate("a b c", "a x c") == pytest.approx(1 / 3)

    def test_tamil_is_compared_after_nfc(self):
        composed = "கொ"                                   # U+0B95 U+0BCA
        decomposed = unicodedata.normalize("NFD", composed)
        assert composed != decomposed
        assert character_error_rate(composed, decomposed) == 0.0

    def test_empty_reference_refused_and_abstention_counted(self):
        with pytest.raises(ValueError):
            character_error_rate("", "x")
        rep = evaluate_ocr([("sathan", None), ("visaki", "visaki")])
        assert rep["abstention_rate"] == 0.5 and rep["mean_cer"] == 0.0 and rep["exact_match_rate"] == 1.0

    def test_no_expert_references_blocks(self):
        assert evaluate_ocr([]) == {"status": "BLOCKED", "message": OCR_BLOCKED}


class TestReproducibility:
    def test_report_captures_every_axis(self):
        r = reproducibility_report()
        assert {"code", "environment", "data", "configuration", "human_evidence_stores", "readiness"} <= set(r)
        assert r["environment"]["torch"] and "numpy" in r["environment"]["packages"]
        assert len(r["configuration"]["project_yaml_sha256"]) in (64, len("absent"))
        assert set(r["human_evidence_stores"]) == {"annotations", "verification_registry", "promotion_log"}
        assert "REPRODUCIBILITY REPORT" in render_report(r)
