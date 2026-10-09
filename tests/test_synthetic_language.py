"""The FICTIONAL synthetic language (src.synthetic.lexicon) and its place in the synthetic pipeline.

SYNTHETIC LANGUAGE — NOT TAMIL-BRAHMI. Every word, reading and sentence here is invented for engineering
demonstration; nothing is a reading of any real inscription.
"""

from __future__ import annotations

import inspect
import io
import itertools
import json
import re
import shutil
import threading
import urllib.request
from http.server import ThreadingHTTPServer

import numpy as np
import pytest
from conftest import ROOT
from test_expert_pilot import NOREFS, expert

from src.synthetic.lexicon import (
    BANNER,
    BY_CLASS,
    LEXICON,
    METHOD,
    SPEC_ID,
    STATUSES,
    decode,
    english,
    grammatical_interpretation,
    sample_sentence,
    target,
)

REF, REF_TL, REF_EN = "SG01 SG09 SG02", "pala taren maku", "The chief gives shelter."


# --------------------------------------------------------------------------- #
# The specification
# --------------------------------------------------------------------------- #


class TestReference:
    def test_transliteration(self):
        assert decode(REF).transliteration == REF_TL

    def test_translation(self):
        d = decode(REF)
        assert d.translation == REF_EN and d.status == "translated"
        assert d.status_text == "Translated under the fictional synthetic-language specification"
        assert (d.method, d.banner, d.spec) == ("Deterministic synthetic lexicon and grammar", BANNER, SPEC_ID)
        assert BANNER == "SYNTHETIC LANGUAGE — NOT TAMIL-BRAHMI" and SPEC_ID == "synthetic-language-1.0.0"

    def test_the_mapping_of_the_brief(self):
        assert [(LEXICON[g].reading, LEXICON[g].gloss, LEXICON[g].word_class) for g in REF.split()] == [
            ("pala", "shelter", "noun"), ("taren", "chief", "noun"), ("maku", "give", "verb")]
        assert [(g["glyph"], g["role"]) for g in decode(REF).gloss] == [("SG01", "object"), ("SG09", "agent"),
                                                                           ("SG02", "verb")]
        assert decode([["SG01", "SG09", "SG02"]]).to_dict() == decode(REF.split()).to_dict() == decode(REF).to_dict()


class TestLexicon:
    def test_complete_and_versioned(self):
        assert sorted(LEXICON) == [f"SG{i:02d}" for i in range(16)]
        assert {len(BY_CLASS[c]) for c in ("noun", "verb")} == {9, 4} and len(BY_CLASS["numeral"]) == 2
        assert len({e.reading for e in LEXICON.values()}) == 16                       # one reading per glyph
        for e in LEXICON.values():
            assert re.fullmatch(r"[a-z]+", e.reading) and e.gloss
            assert not re.search(r"[஀-௿]", e.reading + e.gloss)              # no Tamil script anywhere

    @pytest.mark.parametrize("glyphs", [list(p) for p in itertools.islice(itertools.product(BY_CLASS["noun"], repeat=2), 40)])
    def test_transliteration_follows_the_lexicon(self, glyphs):
        seq = [*glyphs, "SG13"]
        d = decode(seq)
        assert d.transliteration == " ".join(LEXICON[g].reading for g in seq)
        assert [g["reading"] for g in d.gloss] == [LEXICON[g].reading for g in seq]


@pytest.mark.parametrize(("seq", "expected"), [
    (REF, REF_EN),
    ("SG14 SG03 SG10 SG13", "The potter makes two jars."),
    ("SG00 SG15 SG11 SG05 SG12", "Three traders do not carry a pot."),
    ("SG01 SG09 SG02 SG12", "The chief does not give shelter."),
    ("SG07 SG09 SG08 / SG04 SG10 SG02", "The chief keeps a lamp. The potter gives a basket."),
    ("SG14 SG06 SG14 SG10 SG13 SG12", "Two potters do not make two boats."),
])
def test_valid_sequences_follow_the_grammar(seq, expected):
    d = decode(seq)
    assert (d.status, d.translation, d.untranslated, d.unknown_glyphs) == ("translated", expected, [], [])


def test_every_generated_sentence_decodes_and_the_grammar_is_unambiguous():
    rng = np.random.default_rng(7)
    for n in range(3, 9):
        for _ in range(300):
            s = sample_sentence(rng, n)
            assert len(s) == n and decode(s).status == "translated"
    letter = {"noun": "N", "verb": "V", "numeral": "U", "negation": "G"}
    clause = re.compile(r"U?NU?NVG?")

    def parses(word: str) -> int:                       # independent count of every segmentation into clauses
        ways = [1] + [0] * len(word)
        for j in range(1, len(word) + 1):
            ways[j] = sum(ways[i] for i in range(max(0, j - 6), j - 2) if clause.fullmatch(word[i:j]))
        return ways[-1]

    glyphs = sorted(LEXICON)
    for n in range(1, 5):                               # every sequence of up to 4 glyphs (69,904 sequences)
        for seq in itertools.product(glyphs, repeat=n):
            word = "".join(letter[LEXICON[g].word_class] for g in seq)
            assert parses(word) <= 1
            assert (decode(list(seq)).status == "translated") is (parses(word) == 1)


def test_english_agreement_rules():
    one, two = {"noun": "SG10", "numeral": None}, {"noun": "SG10", "numeral": "SG14"}
    obj = {"noun": "SG03", "numeral": "SG15"}
    assert english(obj, one, "SG05", False) == "The potter carries three jars."
    assert english(obj, two, "SG05", False) == "Two potters carry three jars."
    assert english(obj, one, "SG05", True) == "The potter does not carry three jars."
    assert english(obj, two, "SG05", True) == "Two potters do not carry three jars."


# --------------------------------------------------------------------------- #
# Unknown, invalid, incomplete, partial, empty
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("seq", ["SG01 SG16 SG02", "SG01 ?? SG02", "XX", "SG01 SG09 SG02 SG99"])
def test_unknown_glyphs_are_reported_never_translated(seq):
    d = decode(seq)
    assert d.status == "unknown_glyph" and d.translation is None and d.parse == []
    assert d.unknown_glyphs and all(u["glyph"] not in LEXICON for u in d.unknown_glyphs)
    assert "[?]" in d.transliteration and "no glyph is guessed" in d.reason


@pytest.mark.parametrize(("seq", "why"), [
    ("SG02 SG01 SG09", "expected the object"),                  # verb first
    ("SG01 SG09", "the verb is missing"),                       # incomplete
    ("SG01", "agent noun phrase is missing"),
    ("SG14 SG02 SG09 SG02", "a numeral must be followed by a noun"),
    ("SG01 SG09 SG12 SG02", "expected a verb"),                  # negation before the verb
    ("SG12", "expected the object"),
    ("SG01 SG09 SG10 SG02", "expected a verb"),                  # three noun phrases
])
def test_invalid_and_incomplete_sequences_get_no_sentence(seq, why):
    d = decode(seq)
    assert d.status == "invalid_sequence" and d.translation is None and why in d.reason
    assert d.transliteration                                    # the readings are still given, glyph by glyph


def test_partial_translates_only_the_complete_clauses():
    d = decode("SG01 SG09 SG02 SG14")
    assert (d.status, d.translation, d.untranslated) == ("partial", REF_EN, ["SG14"])
    d = decode("SG01 SG09 SG02 / SG03 SG10")
    assert (d.status, d.translation, d.untranslated) == ("partial", REF_EN, ["SG03", "SG10"])
    assert "not translated" in d.reason and "not translated" not in REF_EN


def test_nothing_read():
    for empty in ("", [], [[]]):
        d = decode(empty)
        assert (d.status, d.transliteration, d.translation) == ("insufficient_evidence", None, None)
    assert set(STATUSES) == {"translated", "partial", "unknown_glyph", "invalid_sequence", "insufficient_evidence"}


def test_model_confidence_is_not_translation_confidence():
    d = decode(REF).to_dict()
    assert "confidence" not in {k for k in d if k != "confidence_note"} and "not a translation confidence" in d["confidence_note"]


# --------------------------------------------------------------------------- #
# Inference: predicted codes only; no ground truth, id or file name
# --------------------------------------------------------------------------- #


def _brahmi(tiny):
    return next(r for r in tiny["records"] if r["script_type"] == "synthetic_tamil_brahmi_like")


class TestPipelineIsolation:
    def test_ocr_errors_are_kept_not_corrected(self, tiny_synthetic, tiny_synthetic_pipeline, monkeypatch):
        import src.synthetic.pipeline as pipeline_mod

        rec = _brahmi(tiny_synthetic)
        monkeypatch.setattr(pipeline_mod, "read_glyphs", lambda _m, glyphs: ([["SG01", "SG09", "SG05"]], [0.9] * 3))
        a = tiny_synthetic_pipeline["pipeline"].run(tiny_synthetic["root"] / rec["image_path"],
                                                   record=rec | {"synthetic_glyph_sequence": [REF.split()],
                                                                 "synthetic_language_target": target([REF.split()])})
        if a["ocr"]["status"] != "read":
            pytest.skip("the tiny detector found no glyph row on this image")
        assert a["synthetic_language"]["translation"] == "The chief carries shelter."          # what was READ
        gt = a["ground_truth_check"]
        assert gt["true_synthetic_translation"] == REF_EN and gt["synthetic_translation_correct"] is False

    def test_ids_file_names_and_ground_truth_cannot_influence_the_prediction(self, tiny_synthetic, tiny_synthetic_pipeline,
                                                                              tmp_path):
        rec = _brahmi(tiny_synthetic)
        src = tiny_synthetic["root"] / rec["image_path"]
        renamed = tmp_path / "SYNTH-A9999-V9_renamed.jpg"
        shutil.copyfile(src, renamed)
        pipe = tiny_synthetic_pipeline["pipeline"]
        leak = {"synthetic_language_target": {"spec": SPEC_ID, "status": "translated", "transliteration": "LEAKED",
                                              "translation": "LEAKED SENTENCE."},
                "synthetic_glyph_sequence": [["SG00", "SG10", "SG13"]], "artifact_id": "SYNTH-A9999", "image_id": "X"}
        runs = [pipe.run(src, record=None)["synthetic_language"],
                pipe.run(renamed, record=None)["synthetic_language"],
                pipe.run(src, record=rec)["synthetic_language"],
                pipe.run(src, record=rec | leak)["synthetic_language"]]
        assert all(r == runs[0] for r in runs)
        assert "LEAKED" not in json.dumps(runs) and "SYNTH-A9999" not in json.dumps(runs)

    def test_the_decoder_sees_only_glyph_codes(self):
        assert list(inspect.signature(decode).parameters) == ["sequence"]
        import src.synthetic.pipeline as pipeline_mod

        src = inspect.getsource(pipeline_mod.SyntheticPipeline.run)
        assert re.findall(r"decode_language\(([^)]*)\)", src) == ['state["ocr"]["words"]']


# --------------------------------------------------------------------------- #
# Dataset: generator, metadata and benchmark targets agree
# --------------------------------------------------------------------------- #


class TestDataset:
    def test_every_record_carries_the_spec_target_of_its_true_sequence(self, tiny_synthetic):
        from src.synthetic.dataset import validate_synthetic_records

        recs = tiny_synthetic["records"]
        for r in recs:
            assert r["synthetic_language_target"] == target(r["synthetic_glyph_sequence"])
            assert r["transcription"] == r["translation"] == "not_applicable"           # archaeological fields untouched
        brahmi = [r for r in recs if r["script_type"] == "synthetic_tamil_brahmi_like"]
        assert brahmi and all(r["synthetic_language_target"]["status"] == "translated"
                              for r in brahmi if sum(map(len, r["synthetic_glyph_sequence"])) >= 3)
        assert all(r["synthetic_language_target"]["status"] == "insufficient_evidence"
                   for r in recs if r["script_type"] != "synthetic_tamil_brahmi_like")
        tampered = [dict(recs[0]) | {"synthetic_language_target": {"spec": SPEC_ID, "status": "translated",
                                                                    "transliteration": "x", "translation": "Y."}}]
        assert any(f.rule == "S7" for f in validate_synthetic_records(tampered))

    @pytest.mark.skipif(not (ROOT / "data" / "synthetic" / "metadata" / "records.jsonl").exists(), reason="no live synthetic dataset")
    def test_live_dataset_is_consistent_and_keeps_the_reference_example(self):
        recs = [json.loads(line) for line in (ROOT / "data" / "synthetic" / "metadata" / "records.jsonl").open(encoding="utf-8")]
        assert all(r["synthetic_language_target"] == target(r["synthetic_glyph_sequence"]) for r in recs)
        ref = [r for r in recs if r["image_id"] == "SYNTH-A0007-V1"]
        assert ref and ref[0]["synthetic_glyph_sequence"] == [REF.split()]
        assert ref[0]["synthetic_language_target"]["translation"] == REF_EN


# --------------------------------------------------------------------------- #
# Interfaces: CLI and API agree; real data is never decoded
# --------------------------------------------------------------------------- #


def test_cli_and_api_return_the_same_reading(tiny_synthetic, tiny_synthetic_pipeline, monkeypatch, capsys):
    import src.inference as inference
    import src.inference.__main__ as cli
    from src.inference.server import make_handler
    from src.synthetic.__main__ import main as synthetic_cli

    monkeypatch.setattr(inference, "synthetic_index", lambda: tiny_synthetic_pipeline["index"])
    monkeypatch.setattr(cli, "_pipeline", lambda device="auto": tiny_synthetic_pipeline["pipeline"])
    rec = _brahmi(tiny_synthetic)
    path = tiny_synthetic["root"] / rec["image_path"]
    assert cli.main(["synthetic", "--image", str(path), "--json"]) == 0
    from_cli = json.loads(capsys.readouterr().out)
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(50 * 2**20, None, tiny_synthetic_pipeline["pipeline"]))
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    try:
        req = urllib.request.Request(f"http://127.0.0.1:{httpd.server_address[1]}/synthetic/analyze", data=path.read_bytes(),
                                     method="POST", headers={"Content-Type": "image/jpeg"})
        with urllib.request.urlopen(req, timeout=120) as resp:
            from_api = json.loads(resp.read().decode("utf-8"))["synthetic_analysis"]
    finally:
        httpd.shutdown()
        httpd.server_close()
    assert from_cli["synthetic_language"] == from_api["synthetic_language"]
    assert from_cli["reading_results"] == from_api["reading_results"]
    assert synthetic_cli(["translate", "SG01", "SG09", "SG02", "--json"]) == 0
    assert json.loads(capsys.readouterr().out) == decode(REF).to_dict()
    assert synthetic_cli(["translate", "SG01", "SG09", "SG02"]) == 0
    text = capsys.readouterr().out
    for line in (BANNER, "Transcription:    SG01 SG09 SG02", "Transliteration:  pala taren maku",
                 "Translation:      The chief gives shelter.", f"Method:           {METHOD}"):
        assert line in text


def test_research_mode_never_applies_the_synthetic_lexicon(world):
    from src.inference import analyze

    world["store"].append(expert(world["arts"][0], reading="கோ"), **NOREFS)
    d = analyze(world["raw"] / world["records"][0]["image_path"], records=world["records"], store=world["store"]).to_dict()
    assert d["dataset_type"] == "research" and d["synthetic_analysis"] is None
    assert d["reading_results"]["synthetic"] is False and "language" not in d["reading_results"]
    text = json.dumps(d, ensure_ascii=False)
    assert not re.compile(r'(?<![a-z])(pala|taren|maku)(?![a-z])').search(text) and BANNER not in text and SPEC_ID not in text
    import src.translation.reading as real_reading

    assert "lexicon" not in inspect.getsource(real_reading)
    buf = io.BytesIO()
    from PIL import Image

    Image.new("RGB", (64, 64), (1, 2, 3)).save(buf, format="PNG")
    u = analyze(buf.getvalue(), records=world["records"], store=world["store"]).to_dict()
    assert not re.compile(r'(?<![a-z])(pala|taren|maku)(?![a-z])').search(json.dumps(u)) and u["reading_results"]["synthetic"] is False


def test_research_gates_and_split_policy_are_unchanged():
    from src.dataset.splits import SplitSettings

    assert SplitSettings.from_config().distinct_by_construction is False          # research: a human must clear pairs
    import src.dataset.readiness as readiness

    assert "lexicon" not in inspect.getsource(readiness) and "distinct_by_construction" not in inspect.getsource(readiness)


# --------------------------------------------------------------------------- #
# Grammatical interpretation (replaces the retired placeholder categories)
# --------------------------------------------------------------------------- #

RETIRED = re.compile(r"synthetic_(personal_name|name_and_title|ownership_formula|numeral|symbolic_mark)_like|name-like|personal_name")


class TestGrammaticalInterpretation:
    def test_reference_roles(self):
        it = grammatical_interpretation(decode(REF))
        assert [(c["agent"], c["action"], c["object"]) for c in it["clauses"]] == [("chief", "gives", "shelter")]
        assert it["summary"] == "agent: chief · action: gives · object: shelter" and it["spec"] == SPEC_ID
        assert BANNER in it["statement"] and "no person, personal name or real-world identity" in it["statement"]
        assert "translation" not in it                                   # a separate field from the translation

    @pytest.mark.parametrize(("seq", "roles"), [
        ("SG14 SG03 SG14 SG10 SG13 SG12", [("two potters", "do not make", "two jars")]),
        ("SG07 SG09 SG08 / SG04 SG10 SG02", [("chief", "keeps", "lamp"), ("potter", "gives", "basket")]),
        ("SG01 SG09 SG02 SG14", [("chief", "gives", "shelter")]),                          # partial: complete clauses only
    ])
    def test_roles_follow_the_parse(self, seq, roles):
        assert [(c["agent"], c["action"], c["object"]) for c in grammatical_interpretation(decode(seq))["clauses"]] == roles

    @pytest.mark.parametrize("seq", ["", "SG02 SG01 SG09", "SG01 SG77 SG02", "SG01 SG09"])
    def test_nothing_is_interpreted_without_a_clause(self, seq):
        it = grammatical_interpretation(decode(seq))
        assert it["clauses"] == [] and it["summary"].startswith("no grammatical interpretation")

    def test_the_pipeline_no_longer_reports_placeholder_categories(self, tiny_synthetic, tiny_synthetic_pipeline):
        from src.synthetic.demo import render_demo

        rec = _brahmi(tiny_synthetic)
        a = tiny_synthetic_pipeline["pipeline"].run(tiny_synthetic["root"] / rec["image_path"], record=rec)
        assert a["interpretation"]["kind"] == "synthetic_grammatical_interpretation"
        assert a["interpretation"] == grammatical_interpretation(a["synthetic_language"])
        current = json.dumps(a, ensure_ascii=False) + render_demo(a)
        assert not RETIRED.search(current)
        chain = {n["key"]: n for n in a["evidence_chain"]}
        assert chain["interpretation"]["value"] == a["interpretation"]["summary"] and len(chain) == 8
        assert a["ground_truth_check"]["interpretation_correct"] in (True, False)

    def test_the_ui_shows_roles_and_survives_a_stored_legacy_result(self):
        import sys

        sys.path.insert(0, str(ROOT / "app"))
        from ui.synthetic_demo import _interpretation

        html = _interpretation(grammatical_interpretation(decode(REF)))
        assert "Agent: chief · Action: gives · Object: shelter" in html and "not Tamil-Brahmi" in html
        legacy = {"category": "synthetic_personal_name_like", "placeholder": "x", "rule": "R4"}
        assert "Not available for this stored result" in _interpretation(legacy)
        assert not RETIRED.search(_interpretation(legacy))


# --------------------------------------------------------------------------- #
# Near-duplicate grouping of the synthetic split
# --------------------------------------------------------------------------- #


class TestNearDuplicateGrouping:
    def test_components_are_kept_in_one_partition_with_class_counts_unchanged(self, tiny_synthetic, monkeypatch):
        from collections import Counter

        import src.synthetic.dataset as sd
        from src.dataset.splits import make_split

        ds = sd.load_synthetic_dataset(tiny_synthetic["root"], verify_hashes=False)
        cls = {r.artifact_id: r.script_type for r in ds.records}
        settings = sd.split_settings(tiny_synthetic["cfg"], sd.SyntheticPaths.at(tiny_synthetic["root"]))
        manifest = make_split(ds, sd.synthetic_class_spec(), settings, strategy="holdout")
        before = Counter((p, cls[a]) for a, p in manifest.assignments.items())
        by_part = {p: sorted(manifest.artifacts_in(p)) for p in ("train", "val", "test")}
        comps = [sorted([by_part["train"][0], by_part["test"][0], by_part["val"][0]]),
                 sorted([by_part["test"][1], by_part["train"][1]])]
        monkeypatch.setattr(sd, "near_duplicate_components", lambda _ds: (comps, []))
        report = sd.group_near_duplicates(manifest, ds, settings.seed)
        a = manifest.assignments
        assert all(len({a[x] for x in c}) == 1 for c in comps) and report["moved"] >= 2
        assert Counter((p, cls[x]) for x, p in a.items()) == before        # per-class partition sizes restored
        assert any("near-duplicate grouping (synthetic only)" in w for w in manifest.warnings)

    def test_research_settings_still_refuse_the_same_pairs(self, tiny_synthetic, monkeypatch):
        import dataclasses

        import src.dataset.near_duplicates as nd
        import src.synthetic.dataset as sd
        from src.dataset.splits import SplitSettings, check_splittable

        ds = sd.load_synthetic_dataset(tiny_synthetic["root"], verify_hashes=False)
        arts = sorted({r.artifact_id for r in ds.records})
        fake = nd.NearDuplicate(f"{arts[0]}-V1", arts[0], f"{arts[1]}-V1", arts[1], 4)
        monkeypatch.setattr(nd, "dataset_near_duplicates", lambda *_a, **_k: ([fake], []))
        synthetic = sd.split_settings(tiny_synthetic["cfg"], sd.SyntheticPaths.at(tiny_synthetic["root"]))
        research = dataclasses.replace(synthetic, distinct_by_construction=False)
        _, problems = check_splittable(ds, sd.synthetic_class_spec(), research, "holdout")
        assert any("near-duplicate photographs across artifacts" in p for p in problems)
        _, problems = check_splittable(ds, sd.synthetic_class_spec(), synthetic, "holdout")
        assert not any("near-duplicate" in p for p in problems)
        assert SplitSettings.from_config().distinct_by_construction is False

    @pytest.mark.skipif(not (ROOT / "data" / "synthetic" / "metadata" / "records.jsonl").exists(), reason="no live synthetic dataset")
    def test_live_split_has_no_component_across_partitions(self):
        import src.synthetic.dataset as sd

        ds = sd.load_synthetic_dataset(ROOT / "data" / "synthetic", verify_hashes=False)
        manifest = sd.find_manifest(ds, ROOT / "data" / "synthetic")
        comps, pairs = sd.near_duplicate_components(ds)
        a = manifest.assignments
        assert all(len({a[x] for x in c}) == 1 for c in comps)
        assert all(a[p.artifact_a] == a[p.artifact_b] for p in pairs)
        assert any("near-duplicate grouping (synthetic only)" in w for w in manifest.warnings)
