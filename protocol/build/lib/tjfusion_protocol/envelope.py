"""Standard message envelope shared by every TJFusion service.

The *envelope* is the fixed outer wrapper printed on the "outside" of every
message.  It is identical for all six data types so that generic machinery (the
bridge router, loggers, error handling) can read it without knowing anything
about the model inside.

A :class:`Message` carries:

* envelope keys -- ``schema_version``, ``data_type``, ``request_id``,
  ``status``, ``error``, ``elapsed_ms``
* ``fields``  -- small, JSON-serialisable structured data (intrinsics, poses,
  labels, prompts ...). Goes inside the JSON header frame.
* ``arrays``  -- named NumPy arrays (color/depth/mask ...). These are *not* in
  the JSON; the codec sends them as separate raw binary frames. ``fields`` only
  ever holds their descriptors (name/dtype/shape), filled in by the codec.

This module has no third-party dependency at all; :mod:`numpy` only appears in
the codec.  Keeping it pure makes it trivial to vendor into any image.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any

SCHEMA_VERSION = "1.0"

#: The six canonical data types.  A model declares exactly one of these.
DATA_TYPES: tuple[str, ...] = (
    "rgb",
    "depth",
    "mask",
    "status",
    "pose",
    "action",
)

STATUS_OK = "ok"
STATUS_ERROR = "error"


@dataclass(slots=True)
class Message:
    """An in-memory message: envelope + structured ``fields`` + ``arrays``.

    ``arrays`` maps a logical name (e.g. ``"depth"``) to anything array-like
    (typically a ``numpy.ndarray``).  The codec turns each into a binary frame
    and records a descriptor in the serialised header; the envelope module
    itself never imports numpy, so the type is left as ``Any`` here.
    """

    data_type: str
    status: str = STATUS_OK
    request_id: str = ""
    error: str | None = None
    elapsed_ms: float | None = None
    schema_version: str = SCHEMA_VERSION
    fields: dict[str, Any] = field(default_factory=dict)
    arrays: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.data_type not in DATA_TYPES:
            raise ValueError(
                f"Unknown data_type {self.data_type!r}. "
                f"Expected one of {DATA_TYPES}."
            )
        if not self.request_id:
            self.request_id = uuid.uuid4().hex

    # -- convenience -----------------------------------------------------

    @property
    def ok(self) -> bool:
        return self.status == STATUS_OK

    def header_dict(self, array_descriptors: list[dict[str, Any]]) -> dict[str, Any]:
        """Build the JSON header frame for this message.

        ``array_descriptors`` is supplied by the codec (it owns numpy) and is a
        list of ``{"name","dtype","shape"}`` entries in frame order.
        """
        return {
            "schema_version": self.schema_version,
            "data_type": self.data_type,
            "request_id": self.request_id,
            "status": self.status,
            "error": self.error,
            "elapsed_ms": self.elapsed_ms,
            "fields": self.fields,
            "arrays": array_descriptors,
        }


# -- factory helpers (the public API most callers use) -------------------


def make_request(
    data_type: str,
    *,
    request_id: str | None = None,
    fields: dict[str, Any] | None = None,
    arrays: dict[str, Any] | None = None,
) -> Message:
    """Create an outbound *request* message for ``data_type``."""
    return Message(
        data_type=data_type,
        status=STATUS_OK,
        request_id=request_id or "",
        fields=dict(fields or {}),
        arrays=dict(arrays or {}),
    )


def make_ok_response(
    data_type: str,
    request_id: str,
    *,
    fields: dict[str, Any] | None = None,
    arrays: dict[str, Any] | None = None,
    elapsed_ms: float | None = None,
) -> Message:
    """Create a successful response message echoing ``request_id``."""
    return Message(
        data_type=data_type,
        status=STATUS_OK,
        request_id=request_id,
        error=None,
        elapsed_ms=elapsed_ms,
        fields=dict(fields or {}),
        arrays=dict(arrays or {}),
    )


def make_error_response(
    data_type: str,
    request_id: str,
    error: str,
    *,
    elapsed_ms: float | None = None,
) -> Message:
    """Create an error response.  Body is empty; ``error`` holds the reason."""
    return Message(
        data_type=data_type,
        status=STATUS_ERROR,
        request_id=request_id or "",
        error=str(error),
        elapsed_ms=elapsed_ms,
    )


class _Timer:
    """Small helper to fill ``elapsed_ms``.  Usage::

    with elapsed() as t:
        ...
    msg.elapsed_ms = t.ms
    """

    __slots__ = ("_t0", "ms")

    def __enter__(self) -> "_Timer":
        self._t0 = time.perf_counter()
        self.ms = 0.0
        return self

    def __exit__(self, *exc: object) -> None:
        self.ms = round((time.perf_counter() - self._t0) * 1000.0, 3)


def elapsed() -> _Timer:
    return _Timer()
