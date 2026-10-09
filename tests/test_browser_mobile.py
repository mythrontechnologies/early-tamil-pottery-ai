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
* ``tests/browser/navigation.js``    one session moving through every page with the app's own navigation, in
                                     Research and Presentation mode, at phone / tablet / desktop width: the mode
                                     is kept, never emptied, and no page raises (text 100-200 %: no overflow).
* ``tests/browser/reading.js``       the language / reading results (inscription status, transcription,
                                     transliteration, translation, completeness) of a synthetic run and a research
                                     photograph, Research and Presentation, phone / tablet / desktop, text 100-200 %;
                                     and the replay's per-stage reading lines.

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


def _port_closed(port: int, wait: float = 30) -> bool:
    deadline = time.monotonic() + wait
    while True:
        with socket.socket() as s:
            if s.connect_ex(("127.0.0.1", port)) != 0:
                return True
        if time.monotonic() > deadline:
            return False
        time.sleep(0.5)


if sys.platform == "win32":
    import ctypes
    from ctypes import wintypes

    class _IoCounters(ctypes.Structure):
        _fields_ = [(f, ctypes.c_ulonglong) for f in ("ReadOperationCount", "WriteOperationCount",
                    "OtherOperationCount", "ReadTransferCount", "WriteTransferCount", "OtherTransferCount")]

    class _BasicLimits(ctypes.Structure):                      # JOBOBJECT_BASIC_LIMIT_INFORMATION
        _fields_ = [("PerProcessUserTimeLimit", ctypes.c_int64), ("PerJobUserTimeLimit", ctypes.c_int64),
                    ("LimitFlags", wintypes.DWORD), ("MinimumWorkingSetSize", ctypes.c_size_t),
                    ("MaximumWorkingSetSize", ctypes.c_size_t), ("ActiveProcessLimit", wintypes.DWORD),
                    ("Affinity", ctypes.c_size_t), ("PriorityClass", wintypes.DWORD),
                    ("SchedulingClass", wintypes.DWORD)]

    class _ExtendedLimits(ctypes.Structure):                   # JOBOBJECT_EXTENDED_LIMIT_INFORMATION
        _fields_ = [("BasicLimitInformation", _BasicLimits), ("IoInfo", _IoCounters),
                    ("ProcessMemoryLimit", ctypes.c_size_t), ("JobMemoryLimit", ctypes.c_size_t),
                    ("PeakProcessMemoryUsed", ctypes.c_size_t), ("PeakJobMemoryUsed", ctypes.c_size_t)]

    class _ThreadEntry(ctypes.Structure):                      # THREADENTRY32
        _fields_ = [("dwSize", wintypes.DWORD), ("cntUsage", wintypes.DWORD), ("th32ThreadID", wintypes.DWORD),
                    ("th32OwnerProcessID", wintypes.DWORD), ("tpBasePri", wintypes.LONG),
                    ("tpDeltaPri", wintypes.LONG), ("dwFlags", wintypes.DWORD)]

    _K32 = ctypes.WinDLL("kernel32", use_last_error=True)
    for _name, _args, _res in (
            ("CreateJobObjectW", [wintypes.LPVOID, wintypes.LPCWSTR], wintypes.HANDLE),
            ("SetInformationJobObject", [wintypes.HANDLE, ctypes.c_int, wintypes.LPVOID, wintypes.DWORD], wintypes.BOOL),
            ("AssignProcessToJobObject", [wintypes.HANDLE, wintypes.HANDLE], wintypes.BOOL),
            ("TerminateJobObject", [wintypes.HANDLE, wintypes.UINT], wintypes.BOOL),
            ("OpenProcess", [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD], wintypes.HANDLE),
            ("CreateToolhelp32Snapshot", [wintypes.DWORD, wintypes.DWORD], wintypes.HANDLE),
            ("Thread32First", [wintypes.HANDLE, ctypes.POINTER(_ThreadEntry)], wintypes.BOOL),
            ("Thread32Next", [wintypes.HANDLE, ctypes.POINTER(_ThreadEntry)], wintypes.BOOL),
            ("OpenThread", [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD], wintypes.HANDLE),
            ("ResumeThread", [wintypes.HANDLE], wintypes.DWORD),
            ("CloseHandle", [wintypes.HANDLE], wintypes.BOOL)):
        getattr(_K32, _name).argtypes, getattr(_K32, _name).restype = _args, _res

    def _ok(result: int, call: str) -> int:
        if not result or result == ctypes.c_void_p(-1).value:
            raise ctypes.WinError(ctypes.get_last_error(), f"{call} failed")
        return result

    def _job_owning(pid: int) -> int:
        """A job that ends ``pid`` and everything it starts when terminated, or when its last handle closes."""
        job = _ok(_K32.CreateJobObjectW(None, None), "CreateJobObjectW")
        limits = _ExtendedLimits()
        limits.BasicLimitInformation.LimitFlags = 0x2000          # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        _ok(_K32.SetInformationJobObject(job, 9, ctypes.byref(limits), ctypes.sizeof(limits)),  # ExtendedLimit
            "SetInformationJobObject")
        process = _ok(_K32.OpenProcess(0x0101, False, pid), "OpenProcess")   # PROCESS_SET_QUOTA | _TERMINATE
        try:
            _ok(_K32.AssignProcessToJobObject(job, process), "AssignProcessToJobObject")
        finally:
            _K32.CloseHandle(process)
        return job

    def _resume(pid: int) -> None:
        """Resume the (single, suspended) main thread of a process created with CREATE_SUSPENDED."""
        snapshot = _ok(_K32.CreateToolhelp32Snapshot(0x4, 0), "CreateToolhelp32Snapshot")   # TH32CS_SNAPTHREAD
        try:
            entry = _ThreadEntry(dwSize=ctypes.sizeof(_ThreadEntry))
            more = _K32.Thread32First(snapshot, ctypes.byref(entry))
            while more:
                if entry.th32OwnerProcessID == pid:
                    thread = _ok(_K32.OpenThread(0x0002, False, entry.th32ThreadID), "OpenThread")  # SUSPEND_RESUME
                    try:
                        if _K32.ResumeThread(thread) == 0xFFFFFFFF:
                            raise ctypes.WinError(ctypes.get_last_error(), "ResumeThread failed")
                    finally:
                        _K32.CloseHandle(thread)
                    return
                more = _K32.Thread32Next(snapshot, ctypes.byref(entry))
            raise RuntimeError(f"no thread found for process {pid}")
        finally:
            _K32.CloseHandle(snapshot)


class _ServerTree:
    """A server process and every process it starts, stopped together, even if pytest itself is killed.

    On Windows the venv's python.exe is a launcher that runs the real interpreter as a child, and a hard-killed
    pytest runs no teardown: the server outlived the run and kept its port. So the launcher starts suspended, joins
    a job object with JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE (all its descendants join too: the job allows no
    breakaway) and only then runs. stop() terminates the job; if pytest dies first, Windows closes the job handle,
    which ends the job's processes. Elsewhere the server leads its own process group, which stop() signals.
    """

    def __init__(self, cmd: list[str], cwd: Path) -> None:
        self.job: int | None = None
        if sys.platform == "win32":
            self.proc = subprocess.Popen(cmd, cwd=cwd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                         creationflags=0x4)                 # CREATE_SUSPENDED
            try:
                self.job = _job_owning(self.proc.pid)
                _resume(self.proc.pid)
            except BaseException:
                self.stop()
                raise
        else:
            self.proc = subprocess.Popen(cmd, cwd=cwd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                         start_new_session=True)

    def stop(self) -> None:
        if sys.platform == "win32":
            if self.job is not None:
                _K32.TerminateJobObject(self.job, 1)
                _K32.CloseHandle(self.job)
                self.job = None
            else:
                self.proc.kill()
            self.proc.wait(timeout=30)
            return
        import signal
        try:
            os.killpg(self.proc.pid, signal.SIGTERM)
            self.proc.wait(timeout=30)
        except subprocess.TimeoutExpired:
            os.killpg(self.proc.pid, signal.SIGKILL)
            self.proc.wait(timeout=30)
        except ProcessLookupError:
            pass


@pytest.fixture(scope="module")
def app_url():
    port = _free_port()
    server = _ServerTree([sys.executable, "-m", "streamlit", "run", "app/main.py", "--server.port", str(port),
                          "--server.headless", "true", "--browser.gatherUsageStats", "false"], cwd=ROOT)
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
            if server.proc.poll() is not None or time.monotonic() > deadline:
                pytest.fail("the Streamlit app did not start")
            time.sleep(1)
        yield url
    finally:
        server.stop()
        assert _port_closed(port), f"the Streamlit server still listens on port {port} after the tests"


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


def test_view_mode_is_kept_across_in_app_navigation(app_url, tmp_path):
    """Regression: the view-mode switch was keyed on the mode, and Streamlit gives a widget on each page its own
    id. Inside one session a page switch dropped the chosen mode and a return visit left it None; the page's next
    run crashed in boot() ("'NoneType' object has no attribute 'lower'"), and so did clicking the selected mode.
    The other probes load each page fresh (one session per page), so they could not see it."""
    r = run_probe("navigation.js", app_url, tmp_path)
    pages = ("analysis", "annotation", "dataset", "evidence", "workflow", "about", "overview")
    for vp in ("390x844", "768x1024", "1280x800"):
        assert r["first_load"][vp] == "Research"                                   # fresh session: the default
        assert r["deselect"][vp] == {"shown": "Research", "exception": 0}          # cannot be emptied
        for mode, other in (("Research", "Presentation"), ("Presentation", "Research")):
            for page in pages + tuple(f"{p} (back)" for p in pages[-2::-1]):
                c = r["cases"][f"{vp} {mode} {page}"]
                assert c["linked"] and c["heading"] and c["exception"] == 0, (vp, mode, page, c)
                assert (c["on_arrival"], c["switched"], c["switched_back"]) == (mode, other, mode), (vp, mode, page, c)
                if page.startswith("analysis"):
                    assert c["synthetic_banner"], (vp, mode, page)
                if page == "analysis" and vp == "1280x800":
                    assert c["synthetic_result"], (vp, mode)                       # a synthetic run in this mode
                if "(back)" not in page:
                    for scale in ("100%", "125%", "150%", "175%", "200%"):
                        assert c["overflow"][scale] <= 1, (vp, mode, page, c["overflow"])


def test_language_reading_results_render_everywhere(app_url, tmp_path):
    """The translation is a field of its own, at every width and text size, in both view modes; synthetic glyph
    codes get no transliteration and no translation; nothing is invented for a research photograph."""
    from src.annotation.store import AnnotationStore
    from src.synthetic.reading import TRANSLATION, TRANSLITERATION
    from src.translation.reading import NO_READING_TO_TRANSLATE

    r = run_probe("reading.js", app_url, tmp_path)
    labels = ["Inscription / mark", "Transcription", "Transliteration", "Translation", "Reading completeness"]
    unannotated = AnnotationStore().all() == []
    for vp in ("390x844", "768x1024", "1280x800"):
        for data in ("synthetic", "research"):
            for mode in ("Research", "Presentation"):
                c = r[f"{vp} {data} {mode}"]
                assert c and c["visible"] and c["fields"] == labels, (vp, data, mode, c)
                assert c["offscreen"] == 0 and max(c["overflow"].values()) <= 1, (vp, data, mode, c)
                if data == "synthetic":
                    assert c["translation"] == TRANSLATION and c["transliteration"] == TRANSLITERATION
                    assert c["transcription"] and c["evidence"] is (mode == "Research")
                elif unannotated:                            # no human reading exists: stated, never invented
                    assert c["translation"] == NO_READING_TO_TRANSLATE
        stages = r[f"{vp} replay"]
        assert len(stages) == 8 and all(s["on"] for s in stages)
        by = {s["title"]: s["details"] for s in stages}
        assert by["INTERPRET"] == [f"Translation: {TRANSLATION}"]
        assert by["OCR"][1] == f"Transliteration: {TRANSLITERATION}" and by["OCR"][0].startswith("Transcription (synthetic): ")
