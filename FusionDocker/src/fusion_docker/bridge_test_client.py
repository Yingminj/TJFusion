from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

import zmq

from fusion_docker.bridge_service import encode_png_base64
from fusion_docker.console import print_status, print_success

try:
    import cv2  # type: ignore[import-not-found]
except ImportError:  # pragma: no cover - exercised at runtime when dependency is absent
    cv2 = None

try:
    import numpy as np  # type: ignore[import-not-found]
except ImportError:  # pragma: no cover - exercised at runtime when dependency is absent
    np = None


def build_demo_images(width: int = 640, height: int = 480) -> tuple[Any, Any]:
    if cv2 is None or np is None:
        raise RuntimeError(
            "Bridge test client requires numpy and opencv-python-headless. "
            "Please install the project requirements first."
        )

    rgb = np.zeros((height, width, 3), dtype=np.uint8)
    rgb[:] = (22, 18, 30)
    cv2.rectangle(rgb, (60, 60), (width - 60, height - 60), (0, 180, 255), 4)
    cv2.putText(
        rgb,
        "Robot System",
        (40, height // 2),
        cv2.FONT_HERSHEY_SIMPLEX,
        1.2,
        (80, 255, 120),
        3,
        cv2.LINE_AA,
    )

    depth = np.full((height, width), 1200, dtype=np.uint16)
    depth[120:240, 120:280] = 900
    return rgb, depth


def send_test_bridge_request(
    endpoint: str,
    *,
    timeout_ms: int = 4000,
    width: int = 640,
    height: int = 480,
) -> dict[str, Any]:
    rgb, depth = build_demo_images(width=width, height=height)

    request_payload = {
        "request_id": str(uuid4()),
        "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "rgb_image": encode_png_base64(rgb),
        "depth_image": encode_png_base64(depth),
    }

    context = zmq.Context.instance()
    socket = context.socket(zmq.REQ)
    socket.setsockopt(zmq.RCVTIMEO, timeout_ms)
    socket.setsockopt(zmq.SNDTIMEO, timeout_ms)
    socket.setsockopt(zmq.LINGER, 0)
    socket.connect(endpoint)

    try:
        print_status("TEST", f"Sending test request to {endpoint}", color="cyan")
        socket.send_string(json.dumps(request_payload, ensure_ascii=False))
        response_raw = socket.recv_string()
        response = json.loads(response_raw)
        print_success(f"Bridge responded for request_id={request_payload['request_id']}")
        print(json.dumps(response, ensure_ascii=False, indent=2))
        return response
    finally:
        socket.close(0)


def main() -> None:
    parser = argparse.ArgumentParser(description="Send a test request to the bridge service.")
    parser.add_argument(
        "--endpoint",
        default="tcp://127.0.0.1:5556",
        help="External bridge endpoint, for example tcp://127.0.0.1:5556",
    )
    parser.add_argument("--timeout-ms", type=int, default=4000, help="REQ/REP timeout in ms")
    parser.add_argument("--width", type=int, default=640, help="Synthetic RGB image width")
    parser.add_argument("--height", type=int, default=480, help="Synthetic RGB image height")
    args = parser.parse_args()

    send_test_bridge_request(
        args.endpoint,
        timeout_ms=args.timeout_ms,
        width=args.width,
        height=args.height,
    )


if __name__ == "__main__":
    main()

