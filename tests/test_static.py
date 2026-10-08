"""Static checks as tests (Milestone 11): the codebase stays lint-clean (ruff, incl. the selected security
rules) and type-clean (mypy over src/, app/ and scripts/, configured in pyproject.toml). Skipped when the
tool is not installed (pip install -r requirements-dev.txt)."""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _run(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, "-m", *args], cwd=ROOT, capture_output=True, text=True,
                          encoding="utf-8", errors="replace", timeout=900)


@pytest.mark.skipif(importlib.util.find_spec("ruff") is None, reason="ruff not installed")
def test_ruff_is_clean():
    r = _run("ruff", "check", "src", "app", "scripts", "tests")
    assert r.returncode == 0, r.stdout[-4000:]


@pytest.mark.skipif(importlib.util.find_spec("mypy") is None, reason="mypy not installed")
def test_mypy_is_clean():
    r = _run("mypy")
    assert r.returncode == 0 and "Success" in r.stdout, r.stdout[-4000:]
