from __future__ import annotations

from functools import cache
from pathlib import Path
from typing import Mapping
import json
import sys

from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError, ValidationError


@cache
def _schema_validator(schema_name: str) -> Draft202012Validator:
    candidates = (
        Path(__file__).resolve().parents[1] / "schemas" / schema_name,
        Path(sys.prefix) / "share" / "anarchi-kiln" / "schemas" / schema_name,
    )
    schema_path = next((path for path in candidates if path.is_file()), None)

    if schema_path is None:
        raise RuntimeError("Kiln JSON Schema is not installed: " + schema_name)

    try:
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(schema)
    except (OSError, UnicodeError, json.JSONDecodeError, SchemaError) as error:
        raise RuntimeError("Kiln JSON Schema is malformed: " + schema_name) from error

    return Draft202012Validator(schema)


def validate_schema_payload(schema_name: str, payload: Mapping, label: str) -> None:
    """Apply the packaged canonical Schema in addition to runtime policy checks."""
    try:
        _schema_validator(schema_name).validate(payload)
    except ValidationError as error:
        location = ".".join(str(part) for part in error.absolute_path) or "root"
        raise RuntimeError(label + " fails JSON Schema at " + location) from error
