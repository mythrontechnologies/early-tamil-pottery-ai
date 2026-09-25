"""Streamlit UI tests (streamlit.testing AppTest). The annotation store is redirected to
tmp_path; every page except the annotation tool is read-only.

Besides "it renders", these pin the UI's integrity rules: AI output is always labelled and
never styled as success, unresolved sources are never shown as verified, the training state
is shown honestly, the illustrative 3D sherd is always labelled as illustrative and has a 2D
fallback, derived displays say so, and the evidence chain reads only recorded fields.
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
    for section in ("Artifact &amp; provenance", "Script", "Reading", "Translation", "Dating", "Evidence chain",
                    "Inscription region", "Script assessment", "Chronological estimate", "Reasoning", "Evidence layers",
                    "Warnings and limitations"):
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
        assert f'<span class="t">{s.name}</span>' in html


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


# -- V3: 3D, derived displays, evidence chain, inspector, palette, modes, annotation lab ---------------

def _capture_iframe(module, fn):
    captured = {}
    orig = module.st.iframe
    module.st.iframe = lambda html, height=None: captured.setdefault("html", html)
    try:
        fn()
    finally:
        module.st.iframe = orig
    return captured["html"]


def test_3d_scene_is_labelled_lazy_and_has_a_2d_fallback():
    from ui import scene3d

    page = scene3d.scene_html(520)
    assert scene3d.LABEL == "Illustrative 3D visualization — not an archaeological artifact" and scene3d.LABEL in page
    assert scene3d.SR_TEXT in page and scene3d.FALLBACK == "3D unavailable — switching to accessible 2D inspection."
    assert scene3d.FALLBACK in page
    assert "prefers-reduced-motion" in page and "etp.reduceMotion" in page      # OS setting and in-app toggle
    assert "IntersectionObserver" in page and "visibilitychange" in page        # lazy start, paused when hidden
    assert "no3d" in page and "/app/static/vendor/three" in page                 # forced 2D; vendored, offline
    assert "<text" not in page and "fillText" not in page                       # no glyphs drawn anywhere
    assert "__etpPalette" in page                                               # Ctrl+K reaches the palette


def test_vendored_three_is_present_and_licensed():
    three = APP / "static" / "vendor" / "three"
    assert (three / "three.module.min.js").stat().st_size > 100_000
    assert (three / "OrbitControls.js").exists() and "MIT" in (three / "LICENSE").read_text(encoding="utf-8")
    cfg = (ROOT / ".streamlit" / "config.toml").read_text(encoding="utf-8")
    assert "enableStaticServing = true" in cfg


def test_25d_inspection_is_marked_derived_and_escapes_text():
    import json

    from PIL import Image
    from ui import inspect3d

    html = _capture_iframe(inspect3d, lambda: inspect3d.render_inspection(
        Image.new("RGB", (40, 30)), [{"x": .1, "y": .1, "width": .2, "height": .2, "source": "ai_prediction"}],
        alt='x"><script>alert(1)</script>'))
    assert inspect3d.LABEL in html and "Derived display — original source preserved." in html
    assert "<script>alert(1)</script>" not in html and "curvature not measured" in html
    assert json.dumps("AI observation — not evidence")[1:-1] in html             # AI regions keep their label (JSON)


def _result(**over):
    r = {"image": {"registered": False, "width_px": 40, "height_px": 30, "sha256": "0" * 64},
         "image_quality": {"flags": []}, "script": {"value": "unknown", "statement": "Script not determined."},
         "transcription": {"human_reading": {"value": "not_available"},
                           "statement": "No reliable transcription established."},
         "evidence": {"identification": {}, "references": {}},
         "age": {"state": "insufficient", "display": "Insufficient evidence"},
         "regions": [{"source": "ai_prediction", "x": 0, "y": 0, "width": 1, "height": 1}],
         "reasoning": [], "confidence": {"archaeological": "insufficient"}}
    r.update(over)
    return r


def test_evidence_chain_says_insufficient_and_excludes_ai():
    from ui.chain import evidence_chain, render_chain

    nodes = evidence_chain(_result())
    assert [n["key"] for n in nodes] == ["observation", "region", "script", "reading", "linguistic", "context",
                                         "chronology", "reference"]
    assert all(n["status"] == ("insufficient", "Insufficient evidence") for n in nodes[1:])   # AI region is not evidence
    html = render_chain(nodes)
    assert html.count("<details>") == 8 and "AI observations are not part of the evidence chain" in html
    assert "b-verified" not in html


def test_evidence_chain_reads_reference_status_from_the_registry():
    from ui.chain import evidence_chain

    unver = {"R3": {"verification_status": "unverified", "citation": "c"}}
    ref = evidence_chain(_result(evidence={"identification": {}, "references": unver}))[-1]
    assert ref["status"] == ("unverified", "Unverified")
    both = {**unver, "R1": {"verification_status": "verified_against_source", "citation": "d"}}
    assert evidence_chain(_result(evidence={"identification": {}, "references": both}))[-1]["status"][1] == "Partly verified"


def test_inspector_uses_records_and_hides_technical_detail_outside_research(live_research):
    from ui.inspector import artifact_facts, render_inspector

    assert artifact_facts("NO_SUCH_ARTIFACT") is None
    if not live_research["records"]:
        pytest.skip("no research records")
    rec = live_research["records"][0]
    f = artifact_facts(rec["artifact_id"])
    assert f["artifact_id"] == rec["artifact_id"] and f["licence"] == rec.get("license", "not recorded")
    assert "etp-tech" in render_inspector(f, research=True) and "etp-tech" not in render_inspector(f, research=False)


def test_palette_offers_every_command_and_a_skip_link():
    from ui import palette

    html = _capture_iframe(palette, lambda: palette.render_palette(["SHERD_A"], "research"))
    for label in ("Analyze artifact", "Open dataset", "Open annotation lab", "Open evidence", "Open workflow",
                  "Open about", "Search artifact", "Reset interface", "Skip to main content", "Presentation mode"):
        assert label in html, label
    assert '"SHERD_A"' in html and "aria-activedescendant" in html and "Escape" in html


def test_blocked_state_explains_why():
    from ui.components import blocked_state

    html = blocked_state("blocked", "Training", "Awaiting expert data", ["G1 fails"])
    assert "Why is this blocked?" in html and "<details" in html and "G1 fails" in html


@pytest.mark.parametrize(("ui_mode", "shown"), [("Research", True), ("Presentation", False)])
def test_presentation_mode_hides_research_detail(apptest, ui_mode, shown):
    at = apptest("views/dataset.py")
    at.session_state["ui_mode"] = ui_mode
    at.run()
    assert not at.exception
    assert ("Provenance table" in _html(at)) is shown


def test_annotation_lab_marks_saves_and_keeps_history(apptest, tmp_path, live_research):
    import json

    if not live_research["records"]:
        pytest.skip("no research records")
    at = apptest("annotate.py").run()
    at.slider(key="zx").set_value((0.2, 0.6)).run()
    next(b for b in at.button if b.label == "Add region from zoom window").click().run()
    at.segmented_control(key="lab_view").set_value("2.5D inspection").run()
    assert not at.exception
    at.sidebar.text_input(key="annotator_id").set_value("SYNTHETIC_lab").run()
    next(b for b in at.button if "Save" in b.label).click().run()
    assert not at.exception and at.success
    [saved] = [json.loads(x) for x in (tmp_path / "annotations.jsonl").read_text(encoding="utf-8").splitlines()]
    assert saved["inscription"]["regions"][0]["x"] == 0.2 and saved["inscription"]["script_type"] == "unknown"
    assert any("1 record(s) in the revision history" in x.label for x in at.expander)


def test_3d_render_loops_cannot_double_schedule():
    """controls.update() fires 'change' -> kick(); a frame must hold its raf slot while it runs, or
    every frame schedules two and the page locks up (found in browser testing)."""
    from PIL import Image
    from ui import inspect3d, scene3d

    page = scene3d.scene_html(400)
    assert "raf = -1;" in page and "raf = needsLoop() ? requestAnimationFrame(frame) : 0;" in page
    html = _capture_iframe(inspect3d, lambda: inspect3d.render_inspection(Image.new("RGB", (8, 8)), [], alt="x"))
    assert "raf = -1;" in html and "raf = moving && !reduce ? requestAnimationFrame(frame) : 0;" in html
    start = page.index("const start = async")
    assert "setAuto(!ETP.reduce);" not in page[start:page.index("let visible = true, raf")]   # no kick() before raf exists


def test_3d_views_fall_back_when_the_browser_refuses_a_context():
    """A blocked or lost WebGL context must end in the labelled 2D view, never a blank stage."""
    from PIL import Image
    from ui import inspect3d, scene3d

    page = scene3d.scene_html(400)
    assert "catch (e) { ETP.fallback('WebGL context unavailable'); return; }" in page
    assert "webglcontextlost" in page and "ETP.stats.mode === '2d'" in page
    html = _capture_iframe(inspect3d, lambda: inspect3d.render_inspection(Image.new("RGB", (8, 8)), [], alt="x"))
    assert "try { renderer = new THREE.WebGLRenderer" in html and "webglcontextlost" in html
