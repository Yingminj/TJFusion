import argparse
import base64
import json
import time
import uuid
from pathlib import Path

import cv2
import numpy as np
import zmq


def encode_file_to_base64(path: Path) -> str:
    return base64.b64encode(path.read_bytes()).decode("utf-8")


def encode_rgb_to_base64_png(image_rgb: np.ndarray) -> str:
    image_bgr = cv2.cvtColor(image_rgb, cv2.COLOR_RGB2BGR)
    ok, buffer = cv2.imencode(".png", image_bgr)
    if not ok:
        raise RuntimeError("Failed to encode generated RGB image as PNG.")
    return base64.b64encode(buffer.tobytes()).decode("utf-8")


def decode_base64_image_to_bgr(image_b64: str) -> np.ndarray:
    image_bytes = base64.b64decode(image_b64)
    array = np.frombuffer(image_bytes, dtype=np.uint8)
    image_bgr = cv2.imdecode(array, cv2.IMREAD_COLOR)
    if image_bgr is None:
        raise RuntimeError("Failed to decode annotated_image_b64.")
    return image_bgr


def build_dummy_rgb(width: int, height: int) -> np.ndarray:
    # Build a deterministic color gradient image for repeatable tests.
    x = np.linspace(0, 255, width, dtype=np.uint8)
    y = np.linspace(0, 255, height, dtype=np.uint8)
    xx, yy = np.meshgrid(x, y)
    rgb = np.stack([xx, yy, ((xx.astype(np.uint16) + yy.astype(np.uint16)) // 2).astype(np.uint8)], axis=-1)
    return rgb


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="YOLO ZeroMQ test client (REQ).")
    parser.add_argument("--endpoint", default="tcp://127.0.0.1:5562", help="YOLO REP endpoint.")
    parser.add_argument("--rgb", type=str, default="test.jpg", help="Path to input RGB image file.")
    parser.add_argument("--timeout-ms", type=int, default=5000, help="Send/recv timeout in ms.")
    parser.add_argument("--count", type=int, default=1, help="How many requests to send.")
    parser.add_argument("--interval-sec", type=float, default=0.0, help="Sleep between requests.")
    parser.add_argument("--conf", type=float, default=0.8, help="YOLO confidence threshold.")
    parser.add_argument("--tracker", type=str, default="bytetrack.yaml", help="Tracker config name/path.")
    parser.add_argument("--persist", action="store_true", help="Enable tracker persistence.")
    parser.add_argument("--return-masks", action="store_true", help="Ask server to return masks.")
    parser.add_argument(
        "--return-annotated-image",
        action="store_true",
        help="Ask server to return annotated image.",
    )
    parser.add_argument(
        "--prompts",
        type=str,
        default="",
        help="Comma-separated labels to filter (e.g. cup,drawer).",
    )
    parser.add_argument("--dummy-width", type=int, default=640, help="Width for auto-generated test image.")
    parser.add_argument("--dummy-height", type=int, default=480, help="Height for auto-generated test image.")
    parser.add_argument("--save-json", type=str, default="", help="Save response JSON to this file.")
    parser.add_argument(
        "--save-annotated",
        type=str,
        default="",
        help="Save response annotated image to this file (jpg/png).",
    )
    return parser.parse_args()


def build_request(args: argparse.Namespace, rgb_b64: str, request_id: str) -> dict:
    prompts = [p.strip() for p in args.prompts.split(",") if p.strip()]
    return {
        "request_id": request_id,
        "rgb_image": rgb_b64,
        "conf": float(args.conf),
        "tracker": args.tracker,
        "persist": bool(args.persist),
        "return_masks": bool(args.return_masks),
        "return_annotated_image": bool(args.return_annotated_image),
        "prompts": prompts,
    }


def load_or_create_rgb_b64(args: argparse.Namespace) -> str:
    if args.rgb:
        image_path = Path(args.rgb).expanduser().resolve()
        if not image_path.exists():
            raise FileNotFoundError(f"RGB image not found: {image_path}")
        print(f"[INFO] Using RGB file: {image_path}")
        return encode_file_to_base64(image_path)

    rgb = build_dummy_rgb(args.dummy_width, args.dummy_height)
    print(f"[INFO] Using auto-generated RGB image: {args.dummy_width}x{args.dummy_height}")
    return encode_rgb_to_base64_png(rgb)


def main() -> None:
    args = parse_args()
    if args.count <= 0:
        raise ValueError("--count must be > 0")
    if args.timeout_ms <= 0:
        raise ValueError("--timeout-ms must be > 0")

    rgb_b64 = load_or_create_rgb_b64(args)

    context = zmq.Context()
    socket = context.socket(zmq.REQ)
    socket.setsockopt(zmq.RCVTIMEO, int(args.timeout_ms))
    socket.setsockopt(zmq.SNDTIMEO, int(args.timeout_ms))
    socket.setsockopt(zmq.LINGER, 0)
    socket.connect(args.endpoint)

    print(f"[INFO] Connected to {args.endpoint}")

    try:
        for i in range(args.count):
            request_id = str(uuid.uuid4())
            request_data = build_request(args, rgb_b64, request_id)

            print(f"[SEND] {i + 1}/{args.count} request_id={request_id}")
            t0 = time.time()
            socket.send_json(request_data)

            try:
                response = socket.recv_json()
            except zmq.error.Again as exc:
                raise TimeoutError(
                    f"No response within {args.timeout_ms} ms from {args.endpoint}"
                ) from exc

            elapsed_ms = (time.time() - t0) * 1000.0
            status = response.get("status", "unknown")
            detections = response.get("detections", []) or []
            print(
                f"[RECV] status={status} detections={len(detections)} "
                f"server_elapsed={response.get('elapsed_sec', 'n/a')}s client_rtt={elapsed_ms:.1f}ms"
            )
            print(json.dumps(response, indent=2, ensure_ascii=False))

            if args.save_json:
                output_path = Path(args.save_json).expanduser().resolve()
                output_path.parent.mkdir(parents=True, exist_ok=True)
                output_path.write_text(
                    json.dumps(response, indent=2, ensure_ascii=False),
                    encoding="utf-8",
                )
                print(f"[SAVE] JSON -> {output_path}")

            if args.save_annotated:
                annotated_b64 = response.get("annotated_image_b64", "")
                if annotated_b64:
                    annotated = decode_base64_image_to_bgr(annotated_b64)
                    image_path = Path(args.save_annotated).expanduser().resolve()
                    image_path.parent.mkdir(parents=True, exist_ok=True)
                    ok = cv2.imwrite(str(image_path), annotated)
                    if not ok:
                        raise RuntimeError(f"Failed to write annotated image: {image_path}")
                    print(f"[SAVE] Annotated image -> {image_path}")
                else:
                    print("[WARN] Response has no annotated_image_b64, skip saving image.")

            if i < args.count - 1 and args.interval_sec > 0:
                time.sleep(args.interval_sec)
    finally:
        socket.close()
        context.term()


if __name__ == "__main__":
    main()
