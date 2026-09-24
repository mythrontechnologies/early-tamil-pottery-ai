"""Streamlit UI tests (streamlit.testing AppTest). The annotation store is redirected to
tmp_path; every page except the annotation tool is read-only.

Besides "it renders", these pin the UI's integrity rules: AI output is always labelled and
never styled as success, unresolved sources are never shown as verified, the training state
is shown honestly, and the illustrative 3D sherd is always labelled as illustrative.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "app"
if str(APP) not in sys.path:
    sys.path.insert(0, str(APP))

VIEWS = ["views/overview.py", "views/dataset.py", "views/evidence.py", "views/workflow.py", "views/about.py",
         "analyze.py", "annotate.py", "main.py"]


@pytest.fixture
def apptest(tmp_path, monkeypatch):
    from streamlit.testing.v1 import AppTest

    monkeypatch.setenv("ETPAI_ANNOTATIONS_PATH", str(tmp_path / "annotations.jsonl"))
    return lambda name: AppTest.from_file(str(APP / name), default_timeout=300)


def _html(at) -> str:
    return "\n".join(x.proto.body for x in at.get("html"))


@pytest.mark.parametrize("page", VIEWS)
def test_every_page_renders(apptest, page):
    at = apptest(page).run()
    assert not at.exception, [e.value for e in at.exception]
    assert not at.success                                   # nothing is ever styled as "success"


def test_analysis_page_waits_for_input(apptest):
    at = apptest("analyze.py").run()
    assert not at.exception and "No photograph selected" in _html(at)


def test_analysis_page_on_a_registered_photograph(apptest, live_research):
    if not live_research["records"]:
        pytest.skip("no research records")
    at = apptest("analyze.py").run()
    at.radio(key="mode").set_value("A registered research photograph").run()
    assert not at.exception
    html = _html(at)
    assert 'class="etp-verdict"' in html
    # the AI panel is present, labelled with the exact phrase, and kept apart
    assert "AI observation — not archaeological evidence." in html and 'class="etp-ai"' in html
    for section in ("Artifact &amp; provenance", "Inscription detection", "Script assessment", "Dating evidence",
                    "Confidence · archaeological", "Reasoning", "Evidence layers", "Warnings and limitations"):
        assert section in html, section
    if "None: no reference has been verified" in html:          # empty verified layer: no verified badge on it
        layer = html.split('class="etp-layer verified"')[1].split("</div>")[0]
        assert "b-verified" not in layer and "verified layer · empty" in layer
    assert not at.success


def test_region_input_is_validated(apptest, live_research):
    if not live_research["records"]:
        pytest.skip("no research records")
    at = apptest("analyze.py").run()
    at.radio(key="mode").set_value("A registered research photograph").run()
    at.text_area(key="regions").set_value("0.9,0.9,0.5,0.5").run()
    assert not at.exception and any("Region not accepted" in e.value for e in at.error)


def test_dataset_page_is_honest_about_training(apptest):
    from src.dataset.readiness import evaluate

    html = _html(apptest("views/dataset.py").run())
    if not evaluate().training_ready:
        assert "BLOCKED" in html and "READY" not in html
        assert "Training becomes available only after sufficient expert-labelled archaeological data is available." in html


def test_evidence_page_never_shows_unresolved_as_verified(apptest):
    html = _html(apptest("views/evidence.py").run())
    for rid in ("R3", "R5"):
        card = html.split(f'color:var(--sand)">{rid}</b>')[1].split("</article>")[0]
        assert "b-unresolved" in card and "b-verified" not in card


def test_workflow_page_uses_the_existing_stages(apptest):
    from src.workflow import workflow_status

    html = _html(apptest("views/workflow.py").run())
    for s in workflow_status(decode_images=False).stages:
        assert f'<span class="name">{s.name}</span>' in html


def test_sherd_is_labelled_illustrative_and_carries_no_letterforms():
    from ui.sherd3d import sherd_html

    page = sherd_html(400)
    assert "Illustrative visualization" in page and "not an archaeological artifact" in page
    assert "not a photograph or model of any real artifact" in page            # screen-reader label
    assert "prefers-reduced-motion" in page and "IntersectionObserver" in page
    assert "<text" not in page                                                  # no glyphs drawn as text


def test_viewer_escapes_text_and_draws_only_given_regions():
    from PIL import Image
    from ui import viewer

    captured = {}
    orig = viewer.st.iframe
    viewer.st.iframe = lambda html, height=None: captured.setdefault("html", html)
    try:
        viewer.render_viewer(Image.new("RGB", (40, 30)), [], alt='x"><script>alert(1)</script>', meta="<b>m</b>")
    finally:
        viewer.st.iframe = orig
    html = captured["html"]
    assert "<script>alert(1)</script>" not in html and "&lt;b&gt;m&lt;/b&gt;" in html
    assert "regs=[]" in html.replace(" ", "") and "No region is marked" in html


def test_badges_never_rely_on_colour_alone():
    from ui.components import BADGES, badge, reference_badge

    for kind, (_cls, glyph, label) in BADGES.items():
        if kind == "neutral":
            continue
        out = badge(kind)
        assert glyph in out and label in out
    assert "Unresolved" in reference_badge("verified_against_source", "unresolved")   # unresolved always wins
