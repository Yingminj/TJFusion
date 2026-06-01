"""TJFusion shared wire protocol.

This package is the *single source of truth* for how every Docker model and the
FusionDocker bridge talk to each other.  It is intentionally dependency-light
(only ``numpy``) so it can be copied into any model image at build time.

Three concepts:

* **Envelope** -- the fixed outer header that is identical for all six data
  types (``schema_version``/``data_type``/``request_id``/``status``/``error``/
  ``elapsed_ms``).  Routing, timing and error handling read *only* the
  envelope, never the per-type body.  See :mod:`tjfusion_protocol.envelope`.

* **Codec** -- packs a header plus N NumPy arrays into a ZMQ multipart message
  (one JSON header frame + N raw binary frames).  No base64, no PNG/JPG; raw
  ``ndarray.tobytes()`` is lossless and fast on a local link.  See
  :mod:`tjfusion_protocol.codec`.

* **Schemas** -- one declarative contract per data type (``schemas/*.json``)
  describing the required ``fields`` and ``arrays`` for inputs and outputs.
  See :mod:`tjfusion_protocol.validate`.

Six core data types: ``rgb``, ``depth``, ``mask``, ``status``, ``pose``,
``action``.
"""

from __future__ import annotations

from tjfusion_protocol.codec import pack_message, unpack_message
from tjfusion_protocol.envelope import (
    SCHEMA_VERSION,
    DATA_TYPES,
    Message,
    make_error_response,
    make_ok_response,
    make_request,
)
from tjfusion_protocol.validate import ValidationError, validate_message

__all__ = [
    "SCHEMA_VERSION",
    "DATA_TYPES",
    "Message",
    "make_request",
    "make_ok_response",
    "make_error_response",
    "pack_message",
    "unpack_message",
    "validate_message",
    "ValidationError",
]
