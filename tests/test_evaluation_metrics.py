"""Milestone 5 evaluation metrics and the evaluation block.

Inputs are small hand-written label vectors. They test arithmetic, not a model.
"""

from __future__ import annotations

import numpy as np
import pytest
from sklearn.metrics import (
    accuracy_score,
    balanced_accuracy_score,
    f1_score,
    precision_score,
    recall_score,
)
from sklearn.metrics import (
    confusion_matrix as sk_confusion,
)

from src.evaluation.__main__ import EXIT_BLOCKED
from src.evaluation.__main__ import main as evaluation_cli
from src.evaluation.metrics import (
    BLOCKED_MESSAGE,
    EmptyEvaluationError,
    aggregate_by_artifact,
    compute_metrics,
    evaluate_predictions,
    top_k_accuracy,
)

NAMES = ["tamil_brahmi", "graffiti", "none", "uncertain"]


class TestMetrics:
    def test_matches_sklearn_when_every_class_has_support(self):
        y_true = [0, 0, 1, 1, 2, 2, 3, 3, 0, 1]
        y_pred = [0, 1, 1, 1, 2, 0, 3, 2, 0, 1]
        m = compute_metrics(y_true, y_pred, NAMES)
        assert m.accuracy == pytest.approx(accuracy_score(y_true, y_pred))
        assert m.balanced_accuracy == pytest.approx(balanced_accuracy_score(y_true, y_pred))
        assert m.macro_f1 == pytest.approx(f1_score(y_true, y_pred, average="macro"))
        assert m.weighted_f1 == pytest.approx(f1_score(y_true, y_pred, average="weighted"))
        assert m.macro_precision == pytest.approx(precision_score(y_true, y_pred, average="macro"))
        assert m.macro_recall == pytest.approx(recall_score(y_true, y_pred, average="macro"))
        assert m.confusion_matrix == sk_confusion(y_true, y_pred, labels=[0, 1, 2, 3]).tolist()

    def test_per_class_values(self):
        m = compute_metrics([0, 0, 1, 1], [0, 1, 1, 1], ["a", "b"])
        assert m.per_class["a"].precision == 1.0 and m.per_class["a"].recall == 0.5
        assert m.per_class["b"].precision == pytest.approx(2 / 3)
        assert m.per_class["b"].support == 2 and m.per_class["b"].predicted == 3

    def test_class_without_support_is_undefined_not_zero(self):
        m = compute_metrics([0, 1, 0, 1], [0, 1, 0, 1], NAMES)
        assert m.per_class["none"].recall is None and m.per_class["none"].f1 is None
        assert m.classes_without_support == ["none", "uncertain"]
        assert m.balanced_accuracy == 1.0 and m.macro_f1 == 1.0

    def test_never_predicted_class_with_support_has_zero_precision(self):
        m = compute_metrics([0, 1, 1], [0, 0, 0], ["a", "b"])
        assert m.per_class["b"].precision == 0.0 and m.per_class["b"].recall == 0.0

    def test_top_k(self):
        probs = np.array([[0.6, 0.3, 0.1], [0.5, 0.4, 0.1], [0.2, 0.3, 0.5]])
        assert top_k_accuracy([1, 1, 0], probs, 1) == pytest.approx(0.0)
        assert top_k_accuracy([1, 1, 0], probs, 2) == pytest.approx(2 / 3)
        m = compute_metrics([1, 1, 0], [0, 0, 2], ["a", "b", "c"], y_prob=probs)
        assert m.top_k_accuracy == {2: pytest.approx(2 / 3)}

    def test_top_k_skipped_when_k_not_smaller_than_classes(self):
        m = compute_metrics([0, 1], [0, 1], ["a", "b"], y_prob=np.eye(2))
        assert m.top_k_accuracy == {}

    def test_out_of_range_label_is_an_error(self):
        with pytest.raises(ValueError, match="out of range"):
            compute_metrics([0, 5], [0, 1], ["a", "b"])

    def test_empty_raises(self):
        with pytest.raises(EmptyEvaluationError, match="EVALUATION BLOCKED"):
            compute_metrics([], [], NAMES)


class TestReports:
    def test_empty_evaluation_is_blocked_not_zero(self):
        report = evaluate_predictions([], [], NAMES)
        assert report.status == "BLOCKED" and report.metrics is None
        assert BLOCKED_MESSAGE in report.render()
        assert BLOCKED_MESSAGE == "NO REAL DATA — EVALUATION BLOCKED"

    def test_synthetic_provenance_is_stamped(self):
        report = evaluate_predictions([0, 1], [0, 1], ["a", "b"], provenance="synthetic_test")
        assert "NOT AN ARCHAEOLOGICAL RESULT" in report.render()

    def test_report_serialises(self):
        d = evaluate_predictions([0, 1, 1], [0, 1, 0], ["a", "b"]).to_dict()
        assert d["status"] == "COMPLETED" and d["metrics"]["per_class"]["a"]["support"] == 1

    def test_artifact_aggregation(self):
        ids = ["A", "A", "B", "C", "C"]
        y = [0, 0, 1, 1, 1]
        probs = np.array([[0.9, 0.1], [0.4, 0.6], [0.2, 0.8], [0.6, 0.4], [0.7, 0.3]])
        aids, labels, p = aggregate_by_artifact(ids, y, probs)
        assert aids == ["A", "B", "C"] and labels == [0, 1, 1]
        assert p[0].tolist() == pytest.approx([0.65, 0.35])

    def test_artifact_with_two_labels_is_an_error(self):
        with pytest.raises(ValueError, match="inconsistent"):
            aggregate_by_artifact(["A", "A"], [0, 1], np.eye(2))


class TestEvaluationBlocked:
    def test_evaluate_command_is_blocked_without_real_data(self, capsys):
        assert evaluation_cli(["evaluate"]) == EXIT_BLOCKED
        assert "NO REAL DATA — EVALUATION BLOCKED" in capsys.readouterr().out
