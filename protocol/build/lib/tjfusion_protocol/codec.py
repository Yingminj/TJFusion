"""ZMQ multipart codec: header JSON + raw NumPy frames (no base64/PNG/JPG).

Wire format of a single message::

    Frame 0 : header JSON (utf-8 bytes)
    Frame 1 : arrays[0].tobytes()   (C-contiguous raw bytes)
    Frame 2 : arrays[1].tobytes()
    ...
    Frame N : arrays[N-1].tobytes()

The header's ``"arrays"`` key is an ordered list of descriptors::

    {"name": "depth", "dtype": "float32", "shape": [480, 640]}

describing frames 1..N *in order*, so the receiver reconstructs each array with
``np.frombuffer(frame, dtype).reshape(shape)``.  This is lossless (float32 depth
survives intact) and fast -- ideal for a local link with plenty of bandwidth.

Both the bridge and every model server import these two functions, so the wire
format has exactly one implementation.
"""

from __future__ import annotations

import json
from typing import Any

import numpy as np

from tjfusion_protocol.envelope import Message

__all__ = ["pack_message", "unpack_message", "array_descriptor"]


def array_descriptor(name: str, arr: np.ndarray) -> dict[str, Any]:
    """Return the JSON-safe descriptor recorded in the header for ``arr``."""
    return {
        "name": name,
        "dtype": str(arr.dtype),
        "shape": [int(d) for d in arr.shape],
    }


def pack_message(message: Message) -> list[bytes]:
    """Serialise a :class:`Message` into ZMQ multipart frames.

    Array iteration order is the insertion order of ``message.arrays`` (dicts
    preserve it), and that exact order is mirrored in the header descriptor
    list, so packing and unpacking stay aligned.
    """
    array_frames: list[bytes] = []
    descriptors: list[dict[str, Any]] = []

    for name, value in message.arrays.items():
        arr = np.ascontiguousarray(value)
        descriptors.append(array_descriptor(name, arr))
        array_frames.append(arr.tobytes())

    header = message.header_dict(descriptors)
    header_frame = json.dumps(header, ensure_ascii=False).encode("utf-8")
    return [header_frame, *array_frames]


def unpack_message(frames: list[bytes]) -> Message:
    """Reconstruct a :class:`Message` from ZMQ multipart frames.

    Raises ``ValueError`` if the frame count does not match the header's array
    descriptors, which catches truncated or mis-ordered transmissions early.
    """
    if not frames:
        raise ValueError("Empty multipart message: expected at least a header frame.")

    header = json.loads(frames[0].decode("utf-8"))
    descriptors = header.get("arrays", []) or []

    expected = len(descriptors)
    got = len(frames) - 1
    if got != expected:
        raise ValueError(
            f"Array frame count mismatch: header declares {expected} array(s) "
            f"but {got} binary frame(s) were received."
        )

    arrays: dict[str, np.ndarray] = {}
    for index, descriptor in enumerate(descriptors, start=1):
        name = descriptor["name"]
        dtype = np.dtype(descriptor["dtype"])
        shape = tuple(int(d) for d in descriptor["shape"])
        buffer = frames[index]
        arr = np.frombuffer(buffer, dtype=dtype)
        expected_size = int(np.prod(shape)) if shape else 1
        if arr.size != expected_size:
            raise ValueError(
                f"Array '{name}' size mismatch: buffer has {arr.size} elements, "
                f"shape {shape} expects {expected_size}."
            )
        # ``frombuffer`` returns a read-only view over the frame; copy so the
        # caller owns a writable, independent array.
        arrays[name] = arr.reshape(shape).copy()

    message = Message(
        data_type=header["data_type"],
        status=header.get("status", "ok"),
        request_id=header.get("request_id", ""),
        error=header.get("error"),
        elapsed_ms=header.get("elapsed_ms"),
        schema_version=header.get("schema_version", "1.0"),
        fields=header.get("fields", {}) or {},
        arrays=arrays,
    )
    return message
