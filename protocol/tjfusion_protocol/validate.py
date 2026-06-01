"""Validate a :class:`Message` against its per-type schema.

Schemas live in ``schemas/<data_type>.json`` and declare, separately for
``request`` and ``response``, the expected ``fields`` (small structured data)
and ``arrays`` (NumPy payloads, checked by dtype/ndim).  The envelope itself is
validated structurally (status/error consistency) regardless of type.

Validation is deliberately lightweight -- enough to catch field-naming drift
and wrong dtypes early (the exact failure mode we saw between the SAM3 schema
and the live bridge config), without pulling in a full JSON-Schema engine.
"""

from __future__ import annotations

import functools
import json
from pathlib import Path
from typing import Any

from tjfusion_protocol.envelope import DATA_TYPES, STATUS_ERROR, STATUS_OK, Message

_SCHEMA_DIR = Path(__file__).resolve().parent / "schemas"


class ValidationError(ValueError):
    """Raised when a message violates its data-type schema."""


@functools.lru_cache(maxsize=None)
def load_schema(data_type: str) -> dict[str, Any]:
    if data_type not in DATA_TYPES:
        raise ValidationError(f"Unknown data_type {data_type!r}.")
    path = _SCHEMA_DIR / f"{data_type}.json"
    if not path.exists():
        raise ValidationError(f"Schema file missing for {data_type!r}: {path}")
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _check_field_type(name: str, value: Any, declared: str, errors: list[str]) -> None:
    # Map our compact type names onto python-side checks. Anything we do not
    # recognise is accepted (forward-compatible).
    ok = True
    if declared == "string":
        ok = isinstance(value, str)
    elif declared == "number":
        ok = isinstance(value, (int, float)) and not isinstance(value, bool)
    elif declared == "boolean":
        ok = isinstance(value, bool)
    elif declared in ("list", "string_list", "number_list"):
        ok = isinstance(value, list)
    elif declared == "object":
        ok = isinstance(value, dict)
    elif declared == "matrix3x3":
        ok = (
            isinstance(value, list)
            and len(value) == 3
            and all(isinstance(row, list) and len(row) == 3 for row in value)
        )
    elif declared == "vector3":
        ok = isinstance(value, list) and len(value) == 3
    if not ok:
        errors.append(f"field '{name}' should be {declared}, got {type(value).__name__}")


def _validate_section(
    spec: dict[str, Any],
    message: Message,
    errors: list[str],
) -> None:
    field_specs = spec.get("fields", {}) or {}
    for name, fspec in field_specs.items():
        present = name in message.fields
        if fspec.get("required", False) and not present:
            errors.append(f"missing required field '{name}'")
            continue
        if present:
            declared = fspec.get("type")
            if declared:
                _check_field_type(name, message.fields[name], declared, errors)

    array_specs = spec.get("arrays", {}) or {}
    for name, aspec in array_specs.items():
        present = name in message.arrays
        if aspec.get("required", False) and not present:
            errors.append(f"missing required array '{name}'")
            continue
        if not present:
            continue
        arr = message.arrays[name]
        want_dtype = aspec.get("dtype")
        want_ndim = aspec.get("ndim")
        actual_dtype = getattr(arr, "dtype", None)
        actual_ndim = getattr(arr, "ndim", None)
        if want_dtype is not None and actual_dtype is not None:
            if str(actual_dtype) != str(want_dtype):
                errors.append(
                    f"array '{name}' dtype should be {want_dtype}, got {actual_dtype}"
                )
        if want_ndim is not None and actual_ndim is not None:
            if int(actual_ndim) != int(want_ndim):
                errors.append(
                    f"array '{name}' ndim should be {want_ndim}, got {actual_ndim}"
                )


def validate_message(
    message: Message,
    *,
    direction: str,
    strict: bool = True,
) -> list[str]:
    """Validate ``message`` for ``direction`` ('request' or 'response').

    Returns the list of problems found (empty == valid).  When ``strict`` and
    problems exist, raises :class:`ValidationError`.  Error responses skip body
    validation -- only the envelope must be coherent.
    """
    if direction not in ("request", "response"):
        raise ValueError("direction must be 'request' or 'response'")

    errors: list[str] = []

    # -- envelope coherence (type-independent) --------------------------
    if message.schema_version != "1.0":
        errors.append(f"unsupported schema_version {message.schema_version!r}")
    if message.status not in (STATUS_OK, STATUS_ERROR):
        errors.append(f"invalid status {message.status!r}")
    if message.status == STATUS_ERROR and not message.error:
        errors.append("error status requires a non-empty 'error' message")
    if message.status == STATUS_OK and message.error:
        errors.append("ok status must not carry an 'error' message")

    # An error response has no meaningful body -- stop after envelope checks.
    if message.status == STATUS_ERROR:
        if strict and errors:
            raise ValidationError("; ".join(errors))
        return errors

    schema = load_schema(message.data_type)
    section = schema.get(direction, {}) or {}
    _validate_section(section, message, errors)

    if strict and errors:
        raise ValidationError(
            f"{message.data_type} {direction} invalid: " + "; ".join(errors)
        )
    return errors
