"""Phase 2 integration test: the bridge's protocol path drives a real
BaseModelServer over NumPy multipart, with schema validation and store
write-back.

Run from the repo root with both packages on PYTHONPATH::

    PYTHONPATH="protocol;FusionDocker/src" python FusionDocker/tests/test_phase2_protocol_node.py
"""

from __future__ import annotations

import threading
import time

import numpy as np

import zmq

from tjfusion_protocol.envelope import Message
from tjfusion_protocol.server import BaseModelServer

from fusion_docker.bridge_service import _PipelineContext, _run_single_model
from fusion_docker.models import ModelNode


# A trivial real server speaking the standard protocol.
class _EchoDepthServer(BaseModelServer):
    data_type = "depth"

    def infer(self, request: Message) -> Message:
        left = request.arrays["left"]
        # Pretend depth = mean over channels, as float32.
        depth = left.mean(axis=2).astype(np.float32)
        return self.ok(request, arrays={"depth": depth}, fields={"unit": "m"})


def _make_ctx(store: dict) -> _PipelineContext:
    # Only the fields touched by the generic adapter + protocol path are needed.
    return _PipelineContext(
        rgb=None, depth=None, rgb_jpg_bytes=b"", rgb_b64="", depth_b64="",
        prompts=[], source_meta={}, request_id="req-phase2", start_time=time.time(),
        obj_ids=[], obj_id_map={}, return_masks=False, clear_previous=False,
        store=store, output_keys=[], node_index={},
    )


def main() -> None:
    bind = "tcp://127.0.0.1:5599"
    server = _EchoDepthServer(bind_addr=bind)
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    time.sleep(0.4)  # let the REP socket bind

    left = (np.random.rand(8, 8, 3) * 255).astype(np.uint8)
    right = (np.random.rand(8, 8, 3) * 255).astype(np.uint8)

    store = {
        "request_id": "req-phase2",
        "ir_left": left,
        "ir_right": right,
        "ir_left_intrinsics": [[50, 0, 4], [0, 50, 4], [0, 0, 1]],
        "baseline_m": 0.05,
    }
    ctx = _make_ctx(store)

    node = ModelNode(
        name="fast_foundation",
        kind="generic",
        data_type="depth",
        endpoint=bind,
        timeout_ms=3000,
        inputs=["ir_left", "ir_right", "ir_left_intrinsics", "baseline_m"],
        request_map={
            "left": "$ir_left",
            "right": "$ir_right",
            "ir_left_intrinsics": "$ir_left_intrinsics",
            "baseline_m": "$baseline_m",
        },
        response_map={"depth": "depth"},
    )

    context = zmq.Context.instance()
    _run_single_model(node, context, ctx, default_timeout_ms=3000)

    result = ctx.model_results.get("fast_foundation")
    assert result is not None, "node produced no result"
    assert result["ok"], f"node failed: {result}"
    print("PASS node ok:", result["summary"])

    depth = ctx.store.get("depth")
    assert isinstance(depth, np.ndarray), f"depth not written back as ndarray: {type(depth)}"
    assert depth.dtype == np.float32 and depth.shape == (8, 8)
    expected = left.mean(axis=2).astype(np.float32)
    assert np.array_equal(depth, expected), "depth array roundtrip mismatch"
    print("PASS depth written back to store, lossless float32", depth.shape)

    print("\nPhase 2 protocol-node integration test passed.")


if __name__ == "__main__":
    main()
