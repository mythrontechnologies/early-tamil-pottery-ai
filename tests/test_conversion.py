"""CSV <-> JSONL conversion tests.

The property that matters is losslessness in both directions. A conversion layer that
quietly drops a semicolon, a Tamil character or the difference between "absent" and
"null" corrupts research metadata in a way nobody notices until much later.
"""

from __future__ import annotations

import json

import pytest

from src.dataset.convert import (
    EMPTY_LIST_TOKEN,
    NULL_TOKEN,
    ConversionError,
    csv_to_jsonl,
    jsonl_to_csv,
    read_csv,
    read_jsonl,
    record_to_row,
    row_to_record,
    write_csv,
    write_jsonl,
)
from src.dataset.schema import field_order


class TestRoundTrip:
    def test_jsonl_csv_jsonl_is_identity(self, tmp_path, fixtures_dir):
        src = fixtures_dir / "conversion" / "roundtrip.jsonl"
        csv_path, back = tmp_path / "a.csv", tmp_path / "b.jsonl"

        jsonl_to_csv(src, csv_path)
        csv_to_jsonl(csv_path, back)

        assert read_jsonl(back) == read_jsonl(src)

    def test_csv_jsonl_csv_is_byte_identical(self, tmp_path, fixtures_dir):
        src = fixtures_dir / "conversion" / "roundtrip.jsonl"
        first, mid, second = tmp_path / "1.csv", tmp_path / "m.jsonl", tmp_path / "2.csv"

        jsonl_to_csv(src, first)
        csv_to_jsonl(first, mid)
        jsonl_to_csv(mid, second)

        assert first.read_bytes() == second.read_bytes()

    def test_round_trip_of_every_valid_fixture(self, tmp_path, fixtures_dir):
        for src in sorted((fixtures_dir / "valid").glob("*.jsonl")):
            csv_path, back = tmp_path / f"{src.stem}.csv", tmp_path / f"{src.stem}.back.jsonl"
            jsonl_to_csv(src, csv_path)
            csv_to_jsonl(csv_path, back)
            assert read_jsonl(back) == read_jsonl(src), src.name

    def test_single_record_round_trip(self, base_record):
        assert row_to_record(record_to_row(base_record)) == base_record


class TestEncodingRules:
    def test_absent_key_becomes_empty_cell_and_back(self, make_record):
        record = make_record(site=...)
        row = record_to_row(record)
        assert row["site"] == ""
        assert "site" not in row_to_record(row)

    def test_null_integer_uses_an_explicit_token(self, make_record):
        record = make_record(character_count_visible=None)
        row = record_to_row(record)
        assert row["character_count_visible"] == NULL_TOKEN
        assert row_to_record(row)["character_count_visible"] is None

    def test_absent_and_null_integers_stay_distinct(self, make_record):
        absent = record_to_row(make_record(dating_lower_year=...))
        null = record_to_row(make_record(dating_lower_year=None))
        assert absent["dating_lower_year"] == ""
        assert null["dating_lower_year"] == NULL_TOKEN
        assert "dating_lower_year" not in row_to_record(absent)
        assert row_to_record(null)["dating_lower_year"] is None

    def test_empty_list_uses_an_explicit_token(self, make_record):
        row = record_to_row(make_record(alternative_readings=[], inscription_regions=[]))
        assert row["alternative_readings"] == EMPTY_LIST_TOKEN
        assert row["inscription_regions"] == EMPTY_LIST_TOKEN
        back = row_to_record(row)
        assert back["alternative_readings"] == []
        assert back["inscription_regions"] == []

    def test_enum_array_joins_on_semicolon(self, make_record):
        row = record_to_row(make_record(dating_basis=["stratigraphy", "palaeography"]))
        assert row["dating_basis"] == "stratigraphy;palaeography"

    def test_free_text_array_survives_a_semicolon(self, make_record):
        """The reason alternative_readings is JSON-encoded rather than joined."""
        readings = ["Reading A; with a semicolon", "Reading B"]
        record = make_record(alternative_readings=readings)
        assert row_to_record(record_to_row(record))["alternative_readings"] == readings

    @pytest.mark.parametrize("sentinel", ["unknown", "not_available", "not_applicable"])
    def test_sentinels_survive_verbatim(self, make_record, sentinel):
        record = make_record(site=sentinel, pottery_type="unknown")
        row = record_to_row(record)
        assert row["site"] == sentinel
        assert row_to_record(row)["site"] == sentinel

    def test_dating_text_is_preserved_exactly(self, make_record):
        verbatim = 'c. 2nd century BCE - 1st century CE; "as published", with, commas'
        record = make_record(dating_text=verbatim)
        assert row_to_record(record_to_row(record))["dating_text"] == verbatim

    @pytest.mark.parametrize("year", [-600, -200, -1, 1, 300, 600])
    def test_signed_years_preserved(self, make_record, year):
        record = make_record(dating_lower_year=year)
        assert row_to_record(record_to_row(record))["dating_lower_year"] == year

    def test_unicode_survives(self, make_record, tmp_path):
        text = "சோதனை — FIXTURE"
        record = make_record(translation_ta=text)
        src = tmp_path / "u.jsonl"
        write_jsonl(src, [record])
        jsonl_to_csv(src, tmp_path / "u.csv")
        csv_to_jsonl(tmp_path / "u.csv", tmp_path / "u2.jsonl")
        assert read_jsonl(tmp_path / "u2.jsonl")[0]["translation_ta"] == text

    def test_regions_round_trip_with_nested_objects(self, make_record):
        regions = [
            {"x": 1, "y": 2, "w": 3, "h": 4, "region_label": "inscription"},
            {"x": 5, "y": 6, "w": 7, "h": 8, "region_label": "graffiti", "notes": "n"},
        ]
        record = make_record(inscription_regions=regions, image_width_px=None,
                             image_height_px=None)
        assert row_to_record(record_to_row(record))["inscription_regions"] == regions


class TestDeterminism:
    def test_csv_column_order_is_schema_order(self, tmp_path, base_record):
        src = tmp_path / "s.jsonl"
        write_jsonl(src, [base_record])
        jsonl_to_csv(src, tmp_path / "s.csv")
        header = (tmp_path / "s.csv").read_text(encoding="utf-8").splitlines()[0]
        assert header.split(",") == field_order()

    def test_jsonl_key_order_is_schema_order(self, tmp_path, base_record):
        shuffled = dict(reversed(list(base_record.items())))
        out = tmp_path / "o.jsonl"
        write_jsonl(out, [shuffled])
        written = json.loads(out.read_text(encoding="utf-8").splitlines()[0])
        assert list(written) == [f for f in field_order() if f in base_record]

    def test_repeated_writes_are_byte_identical(self, tmp_path, base_record):
        a, b = tmp_path / "a.jsonl", tmp_path / "b.jsonl"
        write_jsonl(a, [base_record])
        write_jsonl(b, [base_record])
        assert a.read_bytes() == b.read_bytes()

    def test_line_endings_are_lf(self, tmp_path, base_record):
        out = tmp_path / "lf.csv"
        write_csv(out, [record_to_row(base_record)])
        assert b"\r\n" not in out.read_bytes()

    def test_csv_with_bom_is_readable(self, tmp_path, base_record):
        """Spreadsheets often add a BOM; reading must tolerate it."""
        out = tmp_path / "bom.csv"
        write_csv(out, [record_to_row(base_record)])
        out.write_bytes(b"\xef\xbb\xbf" + out.read_bytes())
        assert row_to_record(read_csv(out)[0]) == base_record


class TestFailsLoudly:
    def test_unknown_column_rejected(self, base_record):
        row = record_to_row(base_record) | {"not_a_field": "x"}
        with pytest.raises(ConversionError, match="absent from the schema"):
            row_to_record(row)

    def test_unknown_field_rejected(self, base_record):
        with pytest.raises(ConversionError, match="absent from the schema"):
            record_to_row(base_record | {"artifcat_id": "typo"})

    def test_non_integer_in_integer_column_rejected(self, base_record):
        row = record_to_row(base_record) | {"image_width_px": "wide"}
        with pytest.raises(ConversionError, match="expected an integer"):
            row_to_record(row)

    def test_malformed_json_cell_rejected(self, base_record):
        row = record_to_row(base_record) | {"inscription_regions": "{not json"}
        with pytest.raises(ConversionError, match="not valid JSON"):
            row_to_record(row)

    def test_malformed_jsonl_line_rejected(self, tmp_path):
        bad = tmp_path / "bad.jsonl"
        bad.write_text('{"image_id": "A"}\n{oops\n', encoding="utf-8")
        with pytest.raises(ConversionError, match="invalid JSON"):
            read_jsonl(bad)

    def test_blank_lines_ignored(self, tmp_path, base_record):
        out = tmp_path / "blanks.jsonl"
        out.write_text(
            json.dumps(base_record, ensure_ascii=False) + "\n\n\n", encoding="utf-8"
        )
        assert len(read_jsonl(out)) == 1
