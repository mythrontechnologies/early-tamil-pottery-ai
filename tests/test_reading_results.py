"""Language / reading results: inscription status, transcription, transliteration, translation, completeness.

Readings and translations here are FIXTURE text written for the tests (marked as such); nothing is a real
reading of any artifact, and nothing is written to the research data (``world`` is a temporary store).
"""

from __future__ import annotations

import itertools
import json
import re
import sys

import pytest
from conftest import ROOT
from test_expert_pilot import NOREFS, annotation, expert

from src.inference import analyze, render, render_reading
from src.reasoning.engine import analyze_artifact
from src.reasoning.types import Attributed, InscriptionInput, ReasoningInputs
from src.synthetic.interpretation import GLYPH_GROUPS
from src.synthetic.interpretation import interpret as synthetic_interpret
from src.synthetic.reading import NOT_RUN, TRANSLATION, TRANSLITERATION, synthetic_reading_results
from src.translation.reading import (
    FIELDS,
    HUMAN_ONLY,
    NO_INSCRIPTION,
    NO_READING_TO_TRANSLATE,
    NO_READING_TO_TRANSLITERATE,
    NO_TRANSLATION,
    PROMOTED,
    PROPER_NAME,
    UNREGISTERED,
    reading_results,
)

TAMIL = re.compile(r"[஀-௿]")
FIXTURE_TRANSLATION = "FIXTURE translation for tests (not a real reading)"


def _f(block: dict) -> dict:
    assert [f["field"] for f in block["fields"]] == [k for k, _ in FIELDS]          # always all five, in order
    return {f["field"]: f for f in block["fields"]}


def _image(world, i: int = 0):
    return world["raw"] / world["records"][i]["image_path"]


def _run(world, i: int = 0, **kw) -> dict:
    return analyze(_image(world, i), records=world["records"], store=world["store"], **kw).to_dict()


def _expert_with(world, i: int, *, reading="கோ", completeness="complete", reading_conf="moderate",
                 translit="ko", scheme="iso_15919", translation=FIXTURE_TRANSLATION, itype="lexical_word",
                 state="expert_reviewed", alts=(), prov="expert"):
    art = world["arts"][i]
    a = (expert if prov == "expert" else annotation)(art, reading=reading, itype=itype, alts=alts, state=state)
    ins, it = a["inscription"], a["interpretation"]
    ins.update(reading_confidence=reading_conf, reading_completeness=completeness, transliteration=translit,
               transliteration_scheme=scheme if translit != "not_available" else "not_available")
    if translation and itype != "personal_name":
        it.update(translation=translation, translation_source="this_annotator", translation_confidence="moderate")
    world["store"].append(a, **NOREFS)
    return a


# --------------------------------------------------------------------------- #
# Real data: available, missing, partial, uncertain
# --------------------------------------------------------------------------- #


class TestRealReadings:
    def test_available_reading_transliteration_and_translation(self, world):
        a = _expert_with(world, 0)
        d = _run(world)
        f = _f(d["reading_results"])
        assert d["reading_results"]["statement"] == HUMAN_ONLY and d["reading_results"]["synthetic"] is False
        assert f["inscription_status"]["value"] == "yes" and f["inscription_status"]["state"] == "established"
        t = f["transcription"]
        assert (t["value"], t["state"], t["tier"], t["confidence"]) == ("கோ", "established", "expert_reviewed", "moderate")
        assert f"annotation {a['annotation_id']}" in t["evidence"] and t["caveats"] == []
        tl = f["transliteration"]
        assert (tl["value"], tl["state"]) == ("ko", "established") and "scheme: iso_15919" in tl["evidence"]
        tr = f["translation"]
        assert (tr["value"], tr["state"], tr["tier"]) == (FIXTURE_TRANSLATION, "established", "expert_reviewed")
        assert "source: the annotator's own observation" in tr["evidence"]
        assert f["completeness"]["value"] == "complete" and f["completeness"]["display"].startswith("Complete")
        assert "LANGUAGE / READING RESULTS" in render(analyze(_image(world), records=world["records"], store=world["store"]))

    def test_partial_and_uncertain_reading_is_shown_honestly(self, world):
        _expert_with(world, 1, completeness="partial", reading_conf="low", alts=("கா",))
        f = _f(_run(world, 1)["reading_results"])
        t = f["transcription"]
        assert t["state"] == "established" and t["value"] == "கோ"
        caveats = " ".join(t["caveats"])
        assert "Partial" in caveats and "lost or doubtful signs are not supplied" in caveats
        assert "Uncertain reading" in caveats and "low" in caveats and "கா" in caveats
        assert f["completeness"]["value"] == "partial" and f["completeness"]["display"].startswith("Partial")
        assert any("Limited to what is read" in c for c in f["translation"]["caveats"])
        assert any("uncertain reading" in c for c in f["translation"]["caveats"])

    def test_reading_without_translation_says_so(self, world):
        _expert_with(world, 2, translation=None, translit="not_available")
        f = _f(_run(world, 2)["reading_results"])
        assert f["transcription"]["state"] == "established"
        assert f["transliteration"]["state"] == "not_established" and f["transliteration"]["explanation"]
        tr = f["translation"]
        assert tr["state"] == "not_established" and tr["display"] == NO_TRANSLATION and tr["value"] is None
        assert "never derived from a classifier or an OCR draft" in tr["explanation"]

    def test_personal_name_has_no_literal_translation(self, world):
        _expert_with(world, 3, itype="personal_name", reading="சாதன்")
        tr = _f(_run(world, 3)["reading_results"])["translation"]
        assert tr["state"] == "not_applicable" and tr["display"] == PROPER_NAME and tr["value"] is None

    def test_missing_everything_is_explained(self, world):
        f = _f(_run(world, 4)["reading_results"])
        assert all(x["state"] != "established" for x in f.values())
        assert f["transcription"]["explanation"] == "No human annotation of this artifact has been recorded."
        assert f["transliteration"]["display"] == NO_READING_TO_TRANSLITERATE
        assert f["translation"]["display"] == NO_READING_TO_TRANSLATE
        assert f["completeness"]["value"] == "unknown" and f["completeness"]["explanation"]

    def test_illegible_and_no_inscription(self, world):
        a = expert(world["arts"][5], reading=None)
        a["inscription"].update(reading_completeness="illegible")
        world["store"].append(a, **NOREFS)
        f = _f(_run(world, 5)["reading_results"])
        assert f["transcription"]["display"].startswith("Illegible") and f["transcription"]["state"] == "not_established"
        assert f["translation"]["display"] == NO_READING_TO_TRANSLATE
        world["store"].append(expert(world["arts"][0], script="none"), **NOREFS)
        g = _f(_run(world, 0)["reading_results"])
        assert g["inscription_status"]["value"] == "no"
        assert all(g[k]["display"] == NO_INSCRIPTION and g[k]["state"] == "not_applicable"
                   for k in ("transcription", "transliteration", "translation", "completeness"))

    def test_tiers_keep_ai_project_expert_and_promoted_apart(self, world):
        _expert_with(world, 1, prov="project", state="unreviewed")
        assert _f(_run(world, 1)["reading_results"])["transcription"]["tier_label"] == "Project annotation (not expert-reviewed)"
        _expert_with(world, 2, state="unreviewed")
        assert _f(_run(world, 2)["reading_results"])["transcription"]["tier"] == "expert_annotation"
        promoted = {"label_source": "expert_annotation", "inscription_present": "yes", "transcription": "கோ",
                    "transliteration": "ko", "translation_en": FIXTURE_TRANSLATION, "reading_source": "expert annotation(s)"}
        block = reading_results(dataset_type="research", reading={"value": "not_available", "provenance": "none"},
                                interpretation={"state": "no_reading"}, basis=None, record=promoted)
        f = _f(block)
        assert {f[k]["tier"] for k in ("inscription_status", "transcription", "transliteration", "translation")} == {
            "promoted_ground_truth"} and PROMOTED in f["transcription"]["evidence"]
        # the same values without the promotion stamp are not ground truth
        unstamped = _f(reading_results(dataset_type="research", reading={"value": "not_available", "provenance": "none"},
                                       interpretation={"state": "no_reading"}, basis=None,
                                       record=promoted | {"label_source": "unknown"}))
        assert unstamped["transcription"]["state"] == "not_established"

    def test_unregistered_image(self, world):
        import io

        from PIL import Image

        buf = io.BytesIO()
        Image.new("RGB", (80, 80), (5, 6, 7)).save(buf, format="PNG")
        d = analyze(buf.getvalue(), records=world["records"], store=world["store"]).to_dict()
        assert d["reading_results"]["statement"] == UNREGISTERED
        assert all(f["state"] != "established" for f in d["reading_results"]["fields"])


# --------------------------------------------------------------------------- #
# Never derived from AI: classifier, OCR, AI-prediction translations
# --------------------------------------------------------------------------- #


class TestNeverFromAI:
    def test_confident_classifier_and_ocr_never_make_a_reading_or_translation(self, world):
        from test_inference import _FakeClassifier, _FakeOCR

        d = _run(world, 0, classifier=_FakeClassifier(), transcriber=_FakeOCR("ka ta", 0.99))
        block = d["reading_results"]
        f = _f(block)
        assert all(x["state"] != "established" for x in f.values())
        assert f["translation"]["display"] == NO_READING_TO_TRANSLATE
        assert [x["text"] for x in block["ai_drafts"]] == ["ka ta"]
        assert all(x["note"].startswith("AI draft — not a reading") for x in block["ai_drafts"])
        assert "ka ta" not in json.dumps(block["fields"], ensure_ascii=False)
        assert "AI draft: ka ta" in "\n".join(render_reading(block))

    def test_ai_prediction_translation_is_ignored(self):
        ins = InscriptionInput(inscription_present=Attributed("yes", "expert_annotation"),
                               reading=Attributed("கோ", "expert_annotation", "moderate", "this_annotator", "ann_x"),
                               interpretation_type=Attributed("lexical_word", "ai_prediction"),
                               translation=Attributed("AI GUESS", "ai_prediction", "high", "model_x"))
        r = analyze_artifact(ReasoningInputs("A", inscription=ins))
        block = reading_results(dataset_type="research", reading=r.reading, interpretation=r.interpretation,
                                basis={"annotation_id": "ann_x", "review_state": "unreviewed", "inscription": {}})
        tr = _f(block)["translation"]
        assert tr["state"] == "not_established" and "AI GUESS" not in json.dumps(block)


# --------------------------------------------------------------------------- #
# Synthetic: transcription only; never a transliteration or a translation
# --------------------------------------------------------------------------- #


def _fake_synthetic(words, cls="synthetic_tamil_brahmi_like"):
    text = " / ".join(" ".join(w) for w in words)
    read = bool(words)
    return {"classification": {"display_label": "Synthetic Tamil-Brahmi-like class", "label": cls, "confidence": 0.8},
            "inscription": {"regions": [{"confidence": 0.9}] if read else [], "rows": [{}] if read else []},
            "ocr": ({"status": "read", "transcription": text, "glyph_count": sum(map(len, words)),
                     "mean_glyph_score": 0.93, "segmentation": "learned_centers"} if read else
                    {"status": "no_reading", "reason": "no glyph row detected or segmented", "transcription": ""}),
            "interpretation": synthetic_interpret(words, cls).to_dict()}


class TestSyntheticReadings:
    def test_glyph_ids_get_no_transliteration_and_no_translation(self):
        f = _f(synthetic_reading_results(_fake_synthetic([["SG01", "SG09", "SG02"]])))
        assert f["transcription"]["value"] == "SG01 SG09 SG02" and f["transcription"]["tier"] == "synthetic_model"
        assert f["transliteration"]["display"] == TRANSLITERATION and f["transliteration"]["state"] == "not_applicable"
        assert f["translation"]["display"] == "Not available — synthetic glyph identifiers have no established linguistic meaning."
        assert f["translation"]["display"] == TRANSLATION and f["translation"]["value"] is None
        assert "synthetic_personal_name_like" in f["translation"]["explanation"]
        assert "not a meaning or a translation" in f["translation"]["explanation"]
        assert all(x["synthetic"] for x in f.values())

    def test_no_sequence_ever_produces_a_translation_word_or_name(self):
        codes = sorted(GLYPH_GROUPS)
        cases = [[]] + [[list(c)] for c in itertools.combinations(codes, 2)] + [[[a], [b, c]] for a, b, c in
                                                                             itertools.islice(itertools.permutations(codes, 3), 300)]
        for words in cases:
            for cls in ("synthetic_tamil_brahmi_like", "synthetic_graffiti_like", "synthetic_none", "synthetic_uncertain"):
                block = synthetic_reading_results(_fake_synthetic(words, cls))
                f = _f(block)
                assert f["translation"]["value"] is None and f["translation"]["display"] == TRANSLATION
                assert f["transliteration"]["value"] is None and f["transliteration"]["state"] == "not_applicable"
                values = [x["value"] for x in f.values() if x["value"] is not None]
                text = json.dumps(block, ensure_ascii=False)
                assert not TAMIL.search(text)
                for v in values:                     # every value is a glyph-code string or a fixed status token
                    assert re.fullmatch(r"(SG\d\d( / | )?)+|synthetic_[a-z_]+|unknown|not_applicable", str(v)), v

    def test_without_the_pipeline(self):
        f = _f(synthetic_reading_results(None))
        assert f["transcription"]["display"] == NOT_RUN and f["translation"]["display"] == TRANSLATION

    def test_pipeline_and_analyze_carry_the_block(self, tiny_synthetic, tiny_synthetic_pipeline):
        from test_synthetic_pipeline import _brahmi

        rec = _brahmi(tiny_synthetic)
        pipe = tiny_synthetic_pipeline["pipeline"]
        a = pipe.run(tiny_synthetic["root"] / rec["image_path"], record=rec)
        f = _f(a["reading_results"])
        assert f["translation"]["display"] == TRANSLATION and a["reading_results"]["synthetic"] is True
        if a["ocr"]["status"] == "read":
            assert f["transcription"]["value"] == a["ocr"]["transcription"]
        interp = next(s for s in a["stages"] if s["key"] == "interpret")
        assert "translation not available" in interp["summary"] and "no meaning" in interp["summary"]
        d = analyze(tiny_synthetic["root"] / rec["image_path"], records=[], synthetic_records=tiny_synthetic_pipeline["index"],
                    synthetic_pipeline=pipe).to_dict()
        assert d["reading_results"] == d["synthetic_analysis"]["reading_results"]
        d2 = analyze(tiny_synthetic["root"] / rec["image_path"], records=[],
                     synthetic_records=tiny_synthetic_pipeline["index"]).to_dict()
        assert _f(d2["reading_results"])["transcription"]["display"] == NOT_RUN
        from src.synthetic.demo import render_demo

        text = render_demo(a)
        assert "Language / reading results (SYNTHETIC DEMONSTRATION" in text and TRANSLATION in text


# --------------------------------------------------------------------------- #
# UI: the section, the replay, Research / Presentation / Synthetic modes
# --------------------------------------------------------------------------- #


def _ui():
    if str(ROOT / "app") not in sys.path:
        sys.path.insert(0, str(ROOT / "app"))
    from ui.reading import reading_results_html
    from ui.synthetic3d import replay_html

    return reading_results_html, replay_html


class TestReadingUi:
    def test_section_shows_every_field_and_research_adds_evidence(self, world):
        html_of, _ = _ui()
        _expert_with(world, 0, completeness="partial", reading_conf="low")
        block = _run(world)["reading_results"]
        research, presentation = html_of(block, research=True), html_of(block, research=False)
        for page in (research, presentation):
            for label in ("Inscription / mark", "Transcription", "Transliteration", "Translation", "Reading completeness"):
                assert f'<div class="k">{label}</div>' in page
            assert FIXTURE_TRANSLATION in page and "Expert-reviewed" in page and "Partial" in page
            assert 'role="region"' in page and "b-synthetic" not in page
        assert "Evidence:" in research and "Evidence:" not in presentation

    def test_synthetic_section_and_replay(self):
        html_of, replay_html = _ui()
        a = _fake_synthetic([["SG01", "SG09", "SG02"]])
        block = synthetic_reading_results(a)
        page = html_of(block, research=False)
        assert TRANSLATION in page and "b-synthetic" in page and 'lang="zxx"' in page and "etp-reading-syn" in page
        a |= {"reading_results": block, "performance": {"total_seconds": 0.01},
              "stages": [{"key": k, "number": i + 1, "title": k.title(), "seconds": 0.001, "summary": "s"}
                         for i, k in enumerate(("load", "preprocess", "classify", "detect", "segment", "ocr", "interpret", "reason"))]}
        replay = replay_html(a)
        data = json.loads(replay.split("const DATA=", 1)[1].split(";\n", 1)[0])
        details = {s["title"]: s["details"] for s in data["stages"]}
        assert details["Ocr"] == [["Transcription (synthetic)", "SG01 SG09 SG02"], ["Transliteration", TRANSLITERATION]]
        assert details["Interpret"] == [["Translation", TRANSLATION]] and details["Load"] == []
        assert "s.details" in replay and "textContent" in replay

    @pytest.mark.parametrize("ui_mode", ["Research", "Presentation"])
    def test_analysis_page_research_photograph(self, ui_mode, live_research, tmp_path, monkeypatch):
        if not live_research["records"]:
            pytest.skip("no research records")
        from streamlit.testing.v1 import AppTest

        monkeypatch.setenv("ETPAI_ANNOTATIONS_PATH", str(tmp_path / "annotations.jsonl"))
        at = AppTest.from_file(str(ROOT / "app" / "analyze.py"), default_timeout=300)
        at.session_state["ui_mode"] = ui_mode
        at.run()
        at.radio(key="mode").set_value("A registered research photograph").run()
        assert not at.exception, [e.value for e in at.exception]
        html = "\n".join(x.proto.body for x in at.get("html"))
        assert "etp-reading" in html and "Reading completeness" in html and "Transliteration" in html
        assert NO_READING_TO_TRANSLATE in html                       # no human reading exists: stated, not invented
        assert "b-synthetic" not in html


LIVE_MODELS = (ROOT / "models" / "synthetic" / "vision").is_dir() and any(
    (ROOT / "models" / "synthetic" / "checkpoints").glob("*/best.pt"))


@pytest.mark.skipif(not LIVE_MODELS, reason="no trained synthetic models on this machine")
@pytest.mark.parametrize("ui_mode", ["Research", "Presentation"])
def test_synthetic_demonstration_page_shows_the_reading_results(ui_mode, tmp_path, monkeypatch):
    from streamlit.testing.v1 import AppTest

    monkeypatch.setenv("ETPAI_ANNOTATIONS_PATH", str(tmp_path / "annotations.jsonl"))
    at = AppTest.from_file(str(ROOT / "app" / "analyze.py"), default_timeout=300)
    at.query_params["data"] = "synthetic"
    at.session_state["ui_mode"] = ui_mode
    at.run()
    at.button(key="run_synthetic").click().run()
    assert not at.exception, [e.value for e in at.exception]
    html = "\n".join(x.proto.body for x in at.get("html"))
    assert "etp-reading-syn" in html and "Language and reading results, synthetic demonstration" in html
    assert html.count(TRANSLATION) >= 2                              # the panel and the section
    assert "Synthetic interpretation category · not a meaning" in html and not TAMIL.search(html.split("etp-reading", 1)[1])
    assert ('<div class="who">Evidence:' in html) is (ui_mode == "Research")
