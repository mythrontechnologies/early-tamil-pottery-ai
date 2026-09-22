"""Shared test fixtures.

All record data originates from ``tests/fixtures/`` and is synthetic. See
``tests/fixtures/README.md``. Nothing here touches ``data/``.
"""

from __future__ import annotations

import json
import sys
from copy import deepcopy
from pathlib import Path
from typing import Any, Callable

import pytest

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = Path(__file__).resolve().parent / "fixtures"

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


@pytest.fixture(scope="session")
def fixtures_dir() -> Path:
    return FIXTURES


@pytest.fixture(scope="session")
def _base_record_raw() -> dict[str, Any]:
    return json.loads((FIXTURES / "valid" / "base_record.json").read_text(encoding="utf-8"))


@pytest.fixture
def base_record(_base_record_raw: dict[str, Any]) -> dict[str, Any]:
    """A complete, valid record. Mutating it does not affect other tests."""
    return deepcopy(_base_record_raw)


@pytest.fixture
def make_record(_base_record_raw: dict[str, Any]) -> Callable[..., dict[str, Any]]:
    """Build a variant of the base record.

    Passing ``...`` as a value deletes that field, which is how tests exercise
    missing-field behaviour.
    """

    def _make(**overrides: Any) -> dict[str, Any]:
        record = deepcopy(_base_record_raw)
        for key, value in overrides.items():
            if value is ...:
                record.pop(key, None)
            else:
                record[key] = value
        return record

    return _make


@pytest.fixture
def load_fixture() -> Callable[[str], list[dict[str, Any]]]:
    """Load a fixture file under ``tests/fixtures/`` by relative path."""

    def _load(relative: str) -> list[dict[str, Any]]:
        path = FIXTURES / relative
        text = path.read_text(encoding="utf-8")
        if path.suffix == ".jsonl":
            return [json.loads(line) for line in text.splitlines() if line.strip()]
        data = json.loads(text)
        return data if isinstance(data, list) else [data]

    return _load
