"""Deterministic CSV <-> JSONL conversion.

Annotators work in spreadsheets; the pipeline works in JSON Lines. This module is the
contract between the two. It is **lossless and deterministic in both directions**: the
round trips ``JSONL -> CSV -> JSONL`` and ``CSV -> JSONL -> CSV`` are identity.

Encoding rules
--------------

Column order is the schema's field declaration order, always, for every file.

=============  ==================================  ==================================
Field kind     JSON value                          CSV cell
=============  ==================================  ==================================
any            key absent                          ``""`` (empty cell)
string         ``"unknown"``                       ``unknown``  (verbatim)
int            ``null``                            ``null``     (literal token)
int            ``-200``                            ``-200``
array_str      ``[]``                              ``[]``       (literal token)
array_str      ``["a", "b"]``                      ``a;b``  or compact JSON - see below
array_obj      ``[]``                              ``[]``
array_obj      ``[{...}]``                         compact JSON, keys sorted
=============  ==================================  ==================================

Two details that matter:

* **Empty cell means "key absent", not "empty string".** The schema forbids empty
  strings, so there is no ambiguity to resolve: absence is the only thing a blank cell
  can mean. To record a value as null, write the literal ``null``; to record it as
  unknown, write ``unknown``.
* **Only enum-valued arrays use semicolon joining.** ``dating_basis`` holds enum values
  that cannot contain a semicolon, so ``stratigraphy;palaeography`` is safe.
  ``alternative_readings`` holds free text that *can* contain a semicolon, so it is
  encoded as compact JSON instead. Joining it on ``;`` would silently split a reading in
  half on the round trip - a quiet corruption of research data, which is exactly what
  this layer exists to prevent.

Files are written UTF-8 without a BOM and with ``\\n`` line endings so output is
byte-identical across runs and platforms. Reading accepts a BOM (``utf-8-sig``) so that
spreadsheets which insist on adding one still load.
"""

from __future__ import annotations

import csv
import json
import sys
from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import Any

from .schema import enum_values, field_kinds, field_order, load_schema

#: Token for an empty list, distinguishing it from an absent key.
EMPTY_LIST_TOKEN = "[]"
#: Token for JSON null in an integer column.
NULL_TOKEN = "null"

# CSV cells can be long (a JSON-encoded region list). Raise the field limit,
# clamping to what the platform's C long can hold.
try:
    csv.field_size_limit(sys.maxsize)
except OverflowError:  # pragma: no cover - platform dependent
    csv.field_size_limit(2**31 - 1)


class ConversionError(ValueError):
    """A cell could not be decoded. Conversion never guesses; it fails loudly."""


def _joins_on_semicolon(name: str, schema: dict[str, Any]) -> bool:
    """True when an array field's items are enum-constrained and so semicolon-safe."""
    node = schema["properties"][name]
    items = node.get("items", {})
    return "enum" in items


# --------------------------------------------------------------------------- #
# record  ->  row
# --------------------------------------------------------------------------- #


def record_to_row(record: dict[str, Any], schema: dict[str, Any] | None = None) -> dict[str, str]:
    schema = schema or load_schema()
    kinds = field_kinds(schema)
    row: dict[str, str] = {}

    for name in field_order(schema):
        if name not in record:
            row[name] = ""
            continue

        value = record[name]
        kind = kinds[name]

        if kind == "int":
            row[name] = NULL_TOKEN if value is None else str(value)

        elif kind == "array_str":
            if not isinstance(value, list):
                raise ConversionError(f"{name}: expected a list, got {type(value).__name__}")
            if not value:
                row[name] = EMPTY_LIST_TOKEN
            elif _joins_on_semicolon(name, schema):
                row[name] = ";".join(str(v) for v in value)
            else:
                row[name] = json.dumps(value, ensure_ascii=False, separators=(",", ":"))

        elif kind == "array_obj":
            if not isinstance(value, list):
                raise ConversionError(f"{name}: expected a list, got {type(value).__name__}")
            row[name] = (
                EMPTY_LIST_TOKEN
                if not value
                else json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            )

        else:  # string
            row[name] = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)

    # Fields not in the schema would be dropped silently; refuse instead.
    if extra := set(record) - set(row):
        raise ConversionError(
            f"record has fields absent from the schema: {sorted(extra)}. "
            "Fix the record or update the schema; conversion will not discard data."
        )
    return row


# --------------------------------------------------------------------------- #
# row  ->  record
# --------------------------------------------------------------------------- #


def row_to_record(row: dict[str, str], schema: dict[str, Any] | None = None) -> dict[str, Any]:
    schema = schema or load_schema()
    kinds = field_kinds(schema)
    record: dict[str, Any] = {}

    for name in field_order(schema):
        cell = row.get(name)
        if cell is None or cell == "":
            continue  # absent, by the rule above

        kind = kinds[name]

        if kind == "int":
            if cell.strip().lower() == NULL_TOKEN:
                record[name] = None
            else:
                try:
                    record[name] = int(cell.strip())
                except ValueError as exc:
                    raise ConversionError(
                        f"{name}: expected an integer or '{NULL_TOKEN}', got {cell!r}"
                    ) from exc

        elif kind == "array_str":
            if cell == EMPTY_LIST_TOKEN:
                record[name] = []
            elif _joins_on_semicolon(name, schema):
                record[name] = [part.strip() for part in cell.split(";") if part.strip()]
            else:
                record[name] = _load_json_cell(name, cell, list)

        elif kind == "array_obj":
            record[name] = [] if cell == EMPTY_LIST_TOKEN else _load_json_cell(name, cell, list)

        else:
            record[name] = cell

    if extra := {k for k in row if k not in kinds and k.strip()}:
        raise ConversionError(
            f"CSV has columns absent from the schema: {sorted(extra)}. "
            "Conversion will not discard data."
        )
    return record


def _load_json_cell(name: str, cell: str, expected: type) -> Any:
    try:
        value = json.loads(cell)
    except json.JSONDecodeError as exc:
        raise ConversionError(f"{name}: cell is not valid JSON ({exc.msg}): {cell!r}") from exc
    if not isinstance(value, expected):
        raise ConversionError(
            f"{name}: expected JSON {expected.__name__}, got {type(value).__name__}"
        )
    return value


# --------------------------------------------------------------------------- #
# file I/O
# --------------------------------------------------------------------------- #


def read_jsonl(path: Path | str) -> list[dict[str, Any]]:
    path = Path(path)
    records: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as fh:
        for lineno, line in enumerate(fh, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise ConversionError(f"{path}:{lineno}: invalid JSON - {exc.msg}") from exc
    return records


def write_jsonl(
    path: Path | str,
    records: Iterable[dict[str, Any]],
    schema: dict[str, Any] | None = None,
) -> int:
    """Write JSONL with keys in schema order. Deterministic byte-for-byte."""
    schema = schema or load_schema()
    order = field_order(schema)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    count = 0
    with path.open("w", encoding="utf-8", newline="\n") as fh:
        for record in records:
            ordered = {k: record[k] for k in order if k in record}
            ordered.update({k: v for k, v in sorted(record.items()) if k not in ordered})
            fh.write(json.dumps(ordered, ensure_ascii=False) + "\n")
            count += 1
    return count


def read_csv(path: Path | str) -> list[dict[str, str]]:
    path = Path(path)
    with path.open("r", encoding="utf-8-sig", newline="") as fh:
        return [dict(row) for row in csv.DictReader(fh)]


def write_csv(
    path: Path | str,
    rows: Sequence[dict[str, str]],
    schema: dict[str, Any] | None = None,
) -> int:
    schema = schema or load_schema()
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(
            fh, fieldnames=field_order(schema), lineterminator="\n", extrasaction="raise"
        )
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
    return len(rows)


def jsonl_to_csv(src: Path | str, dst: Path | str, schema: dict[str, Any] | None = None) -> int:
    schema = schema or load_schema()
    records = read_jsonl(src)
    return write_csv(dst, [record_to_row(r, schema) for r in records], schema)


def csv_to_jsonl(src: Path | str, dst: Path | str, schema: dict[str, Any] | None = None) -> int:
    schema = schema or load_schema()
    rows = read_csv(src)
    return write_jsonl(dst, [row_to_record(r, schema) for r in rows], schema)


def load_records(path: Path | str) -> list[dict[str, Any]]:
    """Read records from .jsonl, .json (array or single object), or .csv."""
    path = Path(path)
    suffix = path.suffix.lower()
    if suffix == ".jsonl":
        return read_jsonl(path)
    if suffix == ".csv":
        return [row_to_record(r) for r in read_csv(path)]
    if suffix == ".json":
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return [data]
        if isinstance(data, list):
            return data
        raise ConversionError(f"{path}: expected a JSON object or array")
    raise ConversionError(f"{path}: unsupported extension {suffix!r} (use .jsonl, .json or .csv)")


__all__ = [
    "EMPTY_LIST_TOKEN",
    "NULL_TOKEN",
    "ConversionError",
    "csv_to_jsonl",
    "enum_values",
    "jsonl_to_csv",
    "load_records",
    "read_csv",
    "read_jsonl",
    "record_to_row",
    "row_to_record",
    "write_csv",
    "write_jsonl",
]
