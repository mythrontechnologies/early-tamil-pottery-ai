"""Browser regression tests: the analysis UI at phone width (opt-in: ``python -m pytest -m browser``).

They start the real Streamlit app on a free port and drive Chromium in true mobile emulation through
the ``playwright-cli`` tool (``npm install -g @playwright/cli``), so no Python browser package is
needed. They skip when that tool is missing, and the synthetic cases need the generated synthetic
dataset (``python -m src.synthetic generate``). Nothing here writes data: the app is only viewed.

* ``tests/browser/overflow.js``      no horizontal overflow at 390x844 and 360x800, with text at
                                     100-200 % (phones enlarge text), in every analysis state;
* ``tests/browser/pages.js``         every other page at phone / tablet / desktop width, text 100-200 %: no
                                     overflow, no exception, a heading (Milestone 11);
* ``tests/browser/accessibility.js`` keyboard operation (real and synthetic modes), the 2D / 2.5D and
                                     WebGL-failure fallbacks, reduced motion, and click-to-result time and
                                     frame rates of the synthetic demonstration and the 3D scene.

Regression: before the fix, enlarged text (125 %) pushed the synthetic analysis page 41-71 px wider
than the screen (no-wrap badges, non-wrapping flex headings, the 2D/2.5D control, long tokens).
"""

from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import sys
import time
import urllib.request
import uuid
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = Path(__file__).with_name("browser")
CLI = shutil.which("playwright-cli")
LIVE_SYNTHETIC = (ROOT / "data" / "synthetic" / "metadata" / "records.jsonl").exists()

pytestmark = [
    pytest.mark.browser,
    pytest.mark.skipif(CLI is None, reason="playwright-cli is not installed (npm install -g @playwright/cli)"),
    pytest.mark.skipif(not LIVE_SYNTHETIC, reason="no synthetic dataset (python -m src.synthetic generate)"),
]


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="module")
def app_url():
    port = _free_port()
    proc = subprocess.Popen(
        [sys.executable, "-m", "streamlit", "run", "app/main.py", "--server.port", str(port),
         "--server.headless", "true", "--browser.gatherUsageStats", "false"],
        cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    url = f"http://localhost:{port}"
    try:
        deadline = time.monotonic() + 180
        while True:
            try:
                with urllib.request.urlopen(url + "/_stcore/health", timeout=3) as r:
                    if r.read().strip() == b"ok":
                        break
            except OSError:
                pass
            if proc.poll() is not None or time.monotonic() > deadline:
                pytest.fail("the Streamlit app did not start")
            time.sleep(1)
        yield url
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=30)
        except subprocess.TimeoutExpired:
            proc.kill()


def run_probe(name: str, url: str, tmp_path: Path) -> dict:
    """Run tests/browser/<name> in a fresh, private playwright-cli session; return its JSON result."""
    script = tmp_path / name
    script.write_text((SCRIPTS / name).read_text(encoding="utf-8").replace("__BASE__", url), encoding="utf-8")
    session = f"-s=etpai-test-{uuid.uuid4().hex[:8]}"
    env = os.environ | {"MSYS_NO_PATHCONV": "1"}
    run = dict(capture_output=True, env=env, cwd=tmp_path)      # the tool's logs land in tmp, not the repo
    try:
        subprocess.run([CLI, session, "open", "about:blank"], check=True, timeout=180, **run)
        done = subprocess.run([CLI, session, "--raw", "run-code", f"--filename={script}"], text=True,
                              encoding="utf-8", timeout=1500, **run)
    finally:
        subprocess.run([CLI, session, "close"], timeout=120, **run)
    lines = [ln for ln in done.stdout.splitlines() if ln.startswith('"{')]
    assert lines, f"probe {name} returned no result:\n{done.stdout[-2000:]}\n{done.stderr[-2000:]}"
    return json.loads(json.loads(lines[-1]))


def test_no_horizontal_overflow_at_phone_width(app_url, tmp_path):
    cases = run_probe("overflow.js", app_url, tmp_path)
    for vp in ("390x844", "360x800"):
        for scale in ("100%", "125%", "150%", "200%"):
            assert f"{vp} synthetic results @{scale}" in cases        # every required case was measured
            assert f"{vp} research photograph @{scale}" in cases
    overflowing = {case: m for case, m in cases.items() if max(m["main"], m["doc"], m["frame"]) > 1}
    assert not overflowing, f"horizontal overflow (px) at phone width: {overflowing}"


def test_keyboard_fallbacks_motion_and_performance(app_url, tmp_path):
    r = run_probe("accessibility.js", app_url, tmp_path)
    k = r["keyboard"]
    assert k["skip_hidden_until_focus"] and k["first_tab_is_skip_link"]
    assert k["radio_reachable_by_tab"] and k["research_photo_chosen_with_arrow_keys"] and k["result_shown"]
    assert k["stage_view_reachable_by_tab"] and k["stage_view_switches_to_25d_by_keyboard"]
    assert k["focused_elements_past_right_edge"] == [] and k["page_never_scrolled_sideways"]
    sk = r["synthetic_keyboard"]
    assert sk["mode_switch_reachable_by_tab"] and sk["default_mode_is_real"] and sk["mode_switched_by_keyboard"]
    assert sk["run_reachable_by_tab"] and sk["run_with_enter"] and sk["replay_controls"] == [True] * 4
    assert sk["replay_announces"] == "polite" and sk["skip_with_keyboard_shows_all"] == 8
    f = r["fallbacks"]
    assert f["viewer_2d"] == {"focusable": True, "named": True, "image_alt": True, "toolbar": True}
    assert f["inspection_25d"] == {"focusable": True, "named": True, "flat_2d_fallback": True, "toggle_2d": True}
    w = f["webgl_failure"]                                     # WebGL unavailable -> accessible 2D fallback
    assert w["webgl"] is False and w["mode"] == "2d" and w["fallback"] and w["msg"].startswith("3D unavailable")
    m = r["motion"]
    assert m["reduce"]["entrance_animation"] == "none" and m["reduce"]["inspection_sees_reduce"] is True
    assert m["reduce"]["replay"] == {"on": 8, "play": "Play"}   # whole replay shown at once, nothing animating
    assert m["no-preference"]["entrance_animation"] == "etp-rise"   # the check can fail
    perf = r["performance"]
    assert perf["click_to_result_ms"] < 15000                   # responsive: well under the run-once budget
    assert perf["replay_fps"] >= 30 and perf["scene_3d"]["mode"] == "3d" and perf["scene_3d"]["fps"] >= 30


def test_every_page_fits_and_renders_at_every_text_size(app_url, tmp_path):
    """Milestone 11: Overview, Annotation, Dataset, Evidence, Workflow and About at phone (390), tablet (768)
    and desktop (1280) width, text at 100-200 %: no horizontal overflow, no Streamlit exception, a heading."""
    cases = run_probe("pages.js", app_url, tmp_path)
    for vp in ("390x844", "768x1024", "1280x800"):
        for page in ("overview", "annotation", "dataset", "evidence", "workflow", "about"):
            for scale in ("100%", "125%", "150%", "175%", "200%"):
                assert f"{vp} {page} @{scale}" in cases
    broken = {c: m for c, m in cases.items() if m["exception"] or not m["heading"]}
    assert not broken, f"pages with an exception or no heading: {broken}"
    overflowing = {c: m for c, m in cases.items() if max(m["main"], m["doc"], m["frame"]) > 1}
    assert not overflowing, f"horizontal overflow (px): {overflowing}"
