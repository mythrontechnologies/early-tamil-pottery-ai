"""Streamlit UI smoke tests (streamlit.testing AppTest). The annotation store is redirected to
tmp_path; the analysis page writes nothing."""

from __future__ import annotations

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def apptest(tmp_path, monkeypatch):
    from streamlit.testing.v1 import AppTest

    monkeypatch.setenv("ETPAI_ANNOTATIONS_PATH", str(tmp_path / "annotations.jsonl"))
    return lambda name: AppTest.from_file(str(ROOT / "app" / name), default_timeout=300)


def test_analysis_page_waits_for_input(apptest):
    at = apptest("analyze.py").run()
    assert not at.exception and at.info


def test_analysis_page_on_a_registered_photograph(apptest, live_research):
    if not live_research["records"]:
        pytest.skip("no research records")
    at = apptest("analyze.py").run()
    at.sidebar.radio(key="mode").set_value("A registered research photograph").run()
    assert not at.exception
    assert any(m.value.startswith("### ") for m in at.markdown)
    # the AI layer is labelled as not evidence, and nothing AI-generated is styled as success
    assert any("AI OBSERVATION: not archaeological evidence" in w.value for w in at.warning)
    assert not at.success
    heads = [s.value for s in at.subheader]
    for h in ("Summary", "Image quality (technical)", "Reasoning", "Evidence layers (kept apart)",
              "Warnings and limitations"):
        assert h in heads


def test_region_input_is_validated(apptest, live_research):
    if not live_research["records"]:
        pytest.skip("no research records")
    at = apptest("analyze.py").run()
    at.sidebar.radio(key="mode").set_value("A registered research photograph").run()
    at.sidebar.text_area[0].set_value("0.9,0.9,0.5,0.5").run()
    assert not at.exception and any("Region not accepted" in e.value for e in at.error)


def test_main_navigation_starts(apptest):
    assert not apptest("main.py").run().exception
