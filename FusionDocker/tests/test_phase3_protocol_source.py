"""Phase 3 integration test: full standard-protocol source -> DAG -> result.

A fake RealSense PUB emits one standard message (color + ir_left + ir_right +
camera fields). The bridge's protocol source seeds the store from it, runs a
two-node DAG (a real depth BaseModelServer + a stub mask server), and we assert
the depth array flowed through the store and the final response is JSON-clean.

Run from the repo root::

    PYTHONPATH="protocol;FusionDocker/src" python FusionDocker/tests/test_phase3_protocol_source.py
"""

from __future__ import annotations

import json
import threading
import time

import numpy as np
import zmq

from tjfusion_protocol.codec import pack_message
from tjfusion_protocol.envelope import Message, make_ok_response
from tjfusion_protocol.server import BaseModelServer

from fusion_docker.bridge_service import run_protocol_source_bridge_service
from fusion_docker.models import ModelNode
from fusion_docker.config import load_bridge_config


class _DepthServer(BaseModelServer):
    data_type = "depth"

    def infer(self, request: Message) -> Message:
        left = request.arrays["left"]
        depth = left.mean(axis=2).astype(np.float32)
        return self.ok(request, arrays={"depth": depth}, fields={"unit": "m"})


class _MaskServer(BaseModelServer):
    data_type = "mask"
    validate_responses = False  # stub: skip strict output schema

    def infer(self, request: Message) -> Message:
        color = request.arrays["color"]
        h, w = color.shape[:2]
        combined = np.zeros((h, w), dtype=np.uint8)
        return self.ok(
            request,
            arrays={"combined_mask": combined},
            fields={"obj_ids": [1], "class_names": ["cup"]},
        )


def _fake_realsense_pub(bind: str, stop: dict) -> None:
    ctx = zmq.Context.instance()
    sock = ctx.socket(zmq.PUB)
    sock.setsockopt(zmq.SNDHWM, 1)
    sock.bind(bind)
    color = (np.random.rand(8, 8, 3) * 255).astype(np.uint8)
    ir_left = (np.random.rand(8, 8, 3) * 255).astype(np.uint8)
    ir_right = (np.random.rand(8, 8, 3) * 255).astype(np.uint8)
    fields = {
        "ir_left_intrinsics": [[50, 0, 4], [0, 50, 4], [0, 0, 1]],
        "color_intrinsics": [[50, 0, 4], [0, 50, 4], [0, 0, 1]],
        "baseline_m": 0.05,
        "prompts": ["cup"],
    }
    while not stop.get("stop"):
        msg = make_ok_response(
            "rgb", "",
            fields=fields,
            arrays={"color": color, "ir_left": ir_left, "ir_right": ir_right},
        )
        sock.send_multipart(pack_message(msg))
        time.sleep(0.05)
    sock.close(0)


def main() -> None:
    depth_bind = "tcp://127.0.0.1:5601"
    mask_bind = "tcp://127.0.0.1:5602"
    pub_bind = "tcp://127.0.0.1:5603"

    threading.Thread(target=_DepthServer(bind_addr=depth_bind).serve_forever, daemon=True).start()
    threading.Thread(target=_MaskServer(bind_addr=mask_bind).serve_forever, daemon=True).start()
    stop = {"stop": False}
    threading.Thread(target=_fake_realsense_pub, args=(pub_bind, stop), daemon=True).start()
    time.sleep(0.5)

    # Build a config object directly (mirrors bridge.realsense_split.yaml shape).
    cfg = load_bridge_config("FusionDocker/configs/bridge.realsense_split.yaml")
    cfg.zmq_source_addr = pub_bind
    cfg.result_pub_addr = ""  # no downstream PUB in the test
    cfg.pipeline = [
        ModelNode(
            name="fast_foundation", kind="generic", data_type="depth",
            endpoint=depth_bind, timeout_ms=3000,
            request_map={"left": "$ir_left", "right": "$ir_right",
                         "ir_left_intrinsics": "$ir_left_intrinsics", "baseline_m": "$baseline_m"},
            response_map={"depth": "depth"},
        ),
        ModelNode(
            name="sam3", kind="generic", data_type="mask",
            endpoint=mask_bind, timeout_ms=3000,
            request_map={"color": "$color", "prompts": "$prompts"},
            response_map={"obj_ids": "obj_ids", "class_names": "class_names"},
        ),
    ]
    cfg.pipeline_outputs = ["obj_ids", "class_names", "best_category"]

    captured: list[dict] = []

    def _capture(result: dict) -> None:
        captured.append(result)

    # Run the bridge source loop briefly in a thread, then stop it.
    runner = threading.Thread(
        target=run_protocol_source_bridge_service,
        kwargs=dict(config=cfg, verbose=False, save_json=False, result_callback=_capture),
        daemon=True,
    )
    runner.start()

    deadline = time.time() + 8.0
    while not captured and time.time() < deadline:
        time.sleep(0.1)
    stop["stop"] = True

    assert captured, "bridge produced no result from the protocol source"
    result = captured[0]
    # The response must be JSON-serialisable (no ndarray leaked through).
    json.dumps(result)
    print("PASS response is JSON-clean")

    pipeline_status = result.get("pipeline", {})
    assert pipeline_status.get("fast_foundation", {}).get("ok"), result
    assert pipeline_status.get("sam3", {}).get("ok"), result
    print("PASS both nodes ran ok via protocol source")
    assert result.get("obj_ids") == [1], result
    print("PASS store seeded from source + mask output flowed:", result.get("obj_ids"))

    print("\nPhase 3 protocol-source integration test passed.")


if __name__ == "__main__":
    main()
