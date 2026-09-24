"""Schema and configuration loading, and field-kind introspection.

The JSON Schema is the single source of truth for field names, order and types.
Nothing in this package hard-codes a field list; everything is derived from the
schema file so that the two cannot drift apart.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

import yaml

ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PATH = ROOT / "data" / "metadata" / "schema" / "image_record.schema.json"
CONFIG_PATH = ROOT / "configs" / "project.yaml"

#: The canonical research dataset. Anything else is not research data.
RESEARCH_RECORDS_PATH = ROOT / "data" / "metadata" / "records.jsonl"
RESEARCH_DATA_ROOT = ROOT / "data" / "raw"

#: Explicit absence markers. Empty strings are never permitted (schema enforces).
SENTINELS: frozenset[str] = frozenset({"unknown", "not_available", "not_applicable"})

FieldKind = Literal["string", "int", "array_str", "array_obj"]


class SchemaError(RuntimeError):
    """The schema file is missing or unusable."""


@lru_cache(maxsize=1)
def load_schema(path: str | None = None) -> dict[str, Any]:
    p = Path(path) if path else SCHEMA_PATH
    if not p.exists():
        raise SchemaError(f"schema not found: {p}")
    return json.loads(p.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def load_config(path: str | None = None) -> dict[str, Any]:
    p = Path(path) if path else CONFIG_PATH
    if not p.exists():
        raise SchemaError(f"config not found: {p}")
    return yaml.safe_load(p.read_text(encoding="utf-8"))


def _resolve(schema: dict[str, Any], node: dict[str, Any]) -> dict[str, Any]:
    """Resolve a single-level local ``$ref`` into ``#/$defs/...``."""
    ref = node.get("$ref")
    if not ref:
        return node
    if not ref.startswith("#/$defs/"):
        raise SchemaError(f"unsupported $ref (only #/$defs/ is handled): {ref}")
    name = ref.removeprefix("#/$defs/")
    try:
        return schema["$defs"][name]
    except KeyError as exc:
        raise SchemaError(f"dangling $ref: {ref}") from exc


def field_order(schema: dict[str, Any] | None = None) -> list[str]:
    """Field names in schema declaration order. This is the CSV column order."""
    schema = schema or load_schema()
    return list(schema["properties"])


def required_fields(schema: dict[str, Any] | None = None) -> list[str]:
    schema = schema or load_schema()
    return list(schema["required"])


def field_kinds(schema: dict[str, Any] | None = None) -> dict[str, FieldKind]:
    """Map each field to the kind that governs its CSV encoding.

    Derived from the schema rather than declared, so adding a field to the schema
    automatically teaches the converter how to handle it.
    """
    schema = schema or load_schema()
    kinds: dict[str, FieldKind] = {}

    for name, raw in schema["properties"].items():
        node = _resolve(schema, raw)
        types = node.get("type")
        types = [types] if isinstance(types, str) else (types or [])

        if "array" in types:
            item = _resolve(schema, node.get("items", {}))
            kinds[name] = "array_obj" if item.get("type") == "object" else "array_str"
        elif "integer" in types:
            kinds[name] = "int"
        else:
            # Strings, enums, and oneOf-of-string-patterns all encode as plain text.
            kinds[name] = "string"

    return kinds


def enum_values(field: str, schema: dict[str, Any] | None = None) -> list[str] | None:
    """Permitted values for an enum field, or None if the field is not an enum."""
    schema = schema or load_schema()
    node = _resolve(schema, schema["properties"].get(field, {}))
    return list(node["enum"]) if "enum" in node else None


def is_sentinel(value: Any) -> bool:
    return isinstance(value, str) and value in SENTINELS


def has_real_value(record: dict[str, Any], field: str) -> bool:
    """True when the field carries actual information rather than absence.

    A field is 'real' when present, non-null, not a sentinel, and not empty.
    """
    if field not in record:
        return False
    value = record[field]
    if value is None or is_sentinel(value):
        return False
    if isinstance(value, str) and not value.strip():
        return False
    return not (isinstance(value, (list, tuple)) and not value)
