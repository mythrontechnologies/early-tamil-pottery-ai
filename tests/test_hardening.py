"""Engineering hardening (final engineering phase): safe checkpoint loading, model
fingerprints, training resume, acquisition host allow-list, UTF-8 console set-up.

Everything here is SYNTHETIC: tiny random models and noise tensors in tmp_path. No real data
is read or trained on.
"""

from __future__ import annotations

import io
import pickle
import sys

import pytest
import torch
from test_acquisition import candidate
from test_training_framework import _NoiseDataset, _trainer
from torch.utils.data import DataLoader

from src.acquisition.policy import APPROVED_HOSTS, evaluate
from src.console import utf8_console
from src.training.checkpoint import (
    CheckpointError,
    load_checkpoint,
    model_fingerprint,
    save_checkpoint,
)
from src.training.engine import TrainingError


def _loaders():
    return (DataLoader(_NoiseDataset(16, 4), batch_size=8),
            DataLoader(_NoiseDataset(8, 4, seed=1), batch_size=8))


class _Exploit:
    """Unpickling this would run code. weights_only loading must refuse it."""

    def __reduce__(self):
        return (print, ("PWNED: arbitrary code ran during checkpoint load",))


class TestSafeCheckpoints:
    def test_malicious_pickle_is_refused(self, tmp_path, capsys):
        bad = tmp_path / "evil.pt"
        torch.save({"payload": _Exploit()}, bad)
        with pytest.raises(CheckpointError, match="weights_only"):
            load_checkpoint(bad)
        assert "PWNED" not in capsys.readouterr().out

    def test_raw_pickle_file_is_refused(self, tmp_path):
        bad = tmp_path / "raw.pt"
        bad.write_bytes(pickle.dumps(_Exploit()))
        with pytest.raises(CheckpointError):
            load_checkpoint(bad)

    def test_trained_checkpoint_round_trips_with_fingerprint(self, tmp_path):
        t = _trainer(tmp_path)
        fit = t.fit(*_loaders())
        ckpt = load_checkpoint(fit.last_checkpoint)
        assert ckpt["model_fingerprint"] == model_fingerprint(t.model.state_dict())
        assert ckpt["trainer_state"]["early_stopping"]["bad_epochs"] >= 0

    def test_tampered_weights_are_detected(self, tmp_path):
        t = _trainer(tmp_path)
        fit = t.fit(*_loaders())
        ckpt = load_checkpoint(fit.last_checkpoint)
        key = next(k for k, v in ckpt["state_dict"].items() if v.is_floating_point())
        ckpt["state_dict"][key] = ckpt["state_dict"][key] + 1.0
        torch.save(ckpt, tmp_path / "tampered.pt")           # bypasses save_checkpoint's check
        with pytest.raises(CheckpointError, match="fingerprint"):
            load_checkpoint(tmp_path / "tampered.pt")

    def test_fingerprint_is_deterministic_and_content_sensitive(self):
        a = {"w": torch.ones(2, 2), "n": torch.tensor(3)}
        assert model_fingerprint(a) == model_fingerprint({"n": torch.tensor(3), "w": torch.ones(2, 2)})
        assert model_fingerprint(a) != model_fingerprint({"w": torch.ones(2, 2) * 2, "n": torch.tensor(3)})

    def test_non_plain_metadata_is_refused_at_save(self, tmp_path):
        t = _trainer(tmp_path)
        fit = t.fit(*_loaders())
        ckpt = load_checkpoint(fit.last_checkpoint)
        ckpt["metrics"] = {"bad": io.BytesIO()}
        from src.training.checkpoint import _plain

        with pytest.raises(CheckpointError, match="cannot be stored safely"):
            _plain(ckpt["metrics"], "metrics")
        save_checkpoint(load_checkpoint(fit.last_checkpoint), tmp_path / "again.pt")


class TestResume:
    def test_resume_continues_from_the_next_epoch(self, tmp_path):
        first = _trainer(tmp_path, optimization={"epochs": 1})
        fit1 = first.fit(*_loaders())
        assert fit1.epochs_run == 1
        second = _trainer(tmp_path / "b", optimization={"epochs": 3})
        assert second.resume(fit1.last_checkpoint) == 1
        assert second.stopper.best == first.stopper.best
        fit2 = second.fit(*_loaders())
        assert [h.epoch for h in fit2.history] == [1, 2] and fit2.epochs_run == 3

    def test_resume_refuses_another_dataset_version(self, tmp_path):
        fit = _trainer(tmp_path, optimization={"epochs": 1}).fit(*_loaders())
        other = _trainer(tmp_path / "b")
        other.provenance["dataset_fingerprint"] = "A_DIFFERENT_DATASET"
        with pytest.raises(TrainingError, match="different dataset"):
            other.resume(fit.last_checkpoint)

    def test_resume_refuses_another_class_list(self, tmp_path):
        fit = _trainer(tmp_path, optimization={"epochs": 1}).fit(*_loaders())
        other = _trainer(tmp_path / "b")
        other.class_names = ["a", "b", "c", "d"]
        with pytest.raises(CheckpointError, match="class list"):
            other.resume(fit.last_checkpoint)


class TestAcquisitionHosts:
    def test_commons_candidate_on_approved_hosts_passes_a2(self):
        assert not [r for r in evaluate(candidate("FIXTURE ok.png", b"x"), max_file_bytes=10**6).reasons
                    if r.startswith("A2")]

    def test_image_url_on_another_host_is_refused(self):
        c = candidate("FIXTURE evil.png", b"x", original_image_url="https://evil.example.org/x.png")
        reasons = evaluate(c, max_file_bytes=10**6).reasons
        assert any("not an approved host" in r for r in reasons)
        assert APPROVED_HOSTS["wikimedia_commons"]["original_image_url"] == ("upload.wikimedia.org",)

    def test_lookalike_host_is_refused(self):
        c = candidate("FIXTURE evil.png", b"x", original_image_url="https://upload.wikimedia.org.evil.example/x.png")
        assert any("not an approved host" in r for r in evaluate(c, max_file_bytes=10**6).reasons)


def test_utf8_console_is_safe_on_any_stream(monkeypatch):
    monkeypatch.setattr(sys, "stdout", io.StringIO())      # StringIO has no reconfigure()
    utf8_console()
    print("தமிழ் — Tamiḻi")
    assert "தமிழ்" in sys.stdout.getvalue()
