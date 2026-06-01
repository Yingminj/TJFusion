"""Roundtrip + validation tests for the shared protocol.

Run from the ``protocol/`` dir with::

    python -m tests.test_protocol      # or: pytest -q
"""

from __future__ import annotations

import numpy as np

from tjfusion_protocol import (
    DATA_TYPES,
    Message,
    make_ok_response,
    make_request,
    pack_message,
    unpack_message,
    validate_message,
)
from tjfusion_protocol.validate import ValidationError, load_schema


def test_codec_roundtrip_lossless_float32():
    depth = (np.random.rand(48, 64) * 5.0).astype(np.float32)
    color = (np.random.rand(48, 64, 3) * 255).astype(np.uint8)
    msg = make_ok_response(
        "depth",
        request_id="req-1",
        fields={"unit": "m"},
        arrays={"depth": depth},
    )
    msg.arrays["_color_probe"] = color  # extra array to exercise ordering

    frames = pack_message(msg)
    assert len(frames) == 3  # header + 2 arrays

    back = unpack_message(frames)
    assert back.data_type == "depth"
    assert back.request_id == "req-1"
    assert back.fields["unit"] == "m"
    # lossless: float32 depth survives exactly
    assert np.array_equal(back.arrays["depth"], depth)
    assert back.arrays["depth"].dtype == np.float32
    assert np.array_equal(back.arrays["_color_probe"], color)


def test_frame_count_mismatch_detected():
    msg = make_ok_response("rgb", request_id="x", arrays={"color": np.zeros((2, 2, 3), np.uint8)})
    frames = pack_message(msg)
    try:
        unpack_message(frames[:1])  # drop the array frame
    except ValueError as exc:
        assert "frame count mismatch" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("expected ValueError")


def test_all_six_schemas_load():
    for dt in DATA_TYPES:
        schema = load_schema(dt)
        assert schema["data_type"] == dt
        assert "request" in schema and "response" in schema


def test_validate_depth_request_ok():
    req = make_request(
        "depth",
        fields={"intrinsics": [[1, 0, 0], [0, 1, 0], [0, 0, 1]], "baseline_m": 0.05},
        arrays={
            "left": np.zeros((4, 4, 3), np.uint8),
            "right": np.zeros((4, 4, 3), np.uint8),
        },
    )
    assert validate_message(req, direction="request", strict=True) == []


def test_validate_missing_required_array():
    req = make_request(
        "depth",
        fields={"intrinsics": [[1, 0, 0], [0, 1, 0], [0, 0, 1]], "baseline_m": 0.05},
        arrays={"left": np.zeros((4, 4, 3), np.uint8)},  # missing 'right'
    )
    try:
        validate_message(req, direction="request", strict=True)
    except ValidationError as exc:
        assert "right" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("expected ValidationError")


def test_validate_wrong_dtype():
    req = make_request(
        "depth",
        fields={"intrinsics": [[1, 0, 0], [0, 1, 0], [0, 0, 1]], "baseline_m": 0.05},
        arrays={
            "left": np.zeros((4, 4, 3), np.float32),  # should be uint8
            "right": np.zeros((4, 4, 3), np.uint8),
        },
    )
    errors = validate_message(req, direction="request", strict=False)
    assert any("dtype" in e for e in errors)


def test_error_envelope_skips_body():
    msg = Message(data_type="pose", status="error", request_id="e", error="boom")
    # No 'objects' field, but error responses only need a coherent envelope.
    assert validate_message(msg, direction="response", strict=True) == []


def _run_all():
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"PASS {fn.__name__}")
    print(f"\nAll {len(fns)} tests passed.")


if __name__ == "__main__":
    _run_all()
