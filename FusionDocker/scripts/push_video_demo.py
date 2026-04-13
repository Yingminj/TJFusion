#!/usr/bin/env python3
from __future__ import annotations

import argparse
import math
import sys
import time
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from fusion_docker.video_stream_client import (  # noqa: E402
    encode_image_bytes_to_base64,
    post_video_stream_frame,
)


def build_demo_frame(
    title: str,
    *,
    width: int,
    height: int,
    frame_index: int,
) -> np.ndarray:
    canvas = np.zeros((height, width, 3), dtype=np.uint8)

    for y in range(height):
        ratio = y / max(height - 1, 1)
        canvas[y, :, 0] = int(30 + 120 * ratio)
        canvas[y, :, 1] = int(80 + 90 * (1.0 - ratio))
        canvas[y, :, 2] = int(140 + 90 * math.sin(frame_index / 12.0))

    center_x = int(width * (0.5 + 0.28 * math.sin(frame_index / 14.0)))
    center_y = int(height * (0.5 + 0.18 * math.cos(frame_index / 18.0)))
    radius = max(min(width, height) // 8, 20)
    cv2.circle(canvas, (center_x, center_y), radius, (30, 220, 255), -1, cv2.LINE_AA)
    cv2.circle(canvas, (center_x, center_y), radius + 10, (255, 255, 255), 2, cv2.LINE_AA)

    bar_width = max(int(width * 0.7), 10)
    phase = (math.sin(frame_index / 10.0) + 1.0) / 2.0
    filled = int(bar_width * phase)
    cv2.rectangle(canvas, (30, height - 56), (30 + bar_width, height - 28), (50, 70, 90), -1)
    cv2.rectangle(canvas, (30, height - 56), (30 + filled, height - 28), (92, 255, 186), -1)

    cv2.putText(canvas, title, (30, 48), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (255, 255, 255), 2, cv2.LINE_AA)
    cv2.putText(
        canvas,
        f"frame={frame_index}",
        (30, 92),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.8,
        (103, 246, 255),
        2,
        cv2.LINE_AA,
    )
    cv2.putText(
        canvas,
        time.strftime("%Y-%m-%d %H:%M:%S"),
        (30, height - 76),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.65,
        (255, 209, 102),
        2,
        cv2.LINE_AA,
    )
    return canvas


def main() -> None:
    parser = argparse.ArgumentParser(description="Push demo video frames to the FusionDocker web dashboard.")
    parser.add_argument("--dashboard", default="http://127.0.0.1:8765", help="Dashboard base URL.")
    parser.add_argument("--title", default="Demo Stream", help="Base stream title.")
    parser.add_argument("--source", default="push_video_demo", help="Source label shown in the dashboard.")
    parser.add_argument("--fps", type=float, default=6.0, help="Target upload FPS.")
    parser.add_argument("--width", type=int, default=640, help="Frame width.")
    parser.add_argument("--height", type=int, default=360, help="Frame height.")
    parser.add_argument("--streams", type=int, default=2, help="How many demo streams to publish in parallel.")
    parser.add_argument("--jpeg-quality", type=int, default=85, help="JPEG quality.")
    args = parser.parse_args()

    interval = 1.0 / max(args.fps, 0.1)
    frame_index = 0
    total_raw_bytes = 0
    total_b64_bytes = 0
    stats_started_at = time.time()

    print(f"[demo] dashboard={args.dashboard}")
    print(f"[demo] streams={args.streams}, fps={args.fps}, size={args.width}x{args.height}")
    print("[demo] Press Ctrl+C to stop.")

    try:
        while True:
            loop_start = time.time()
            for stream_idx in range(max(args.streams, 1)):
                title = args.title if args.streams == 1 else f"{args.title} {stream_idx + 1}"
                frame = build_demo_frame(
                    title,
                    width=args.width,
                    height=args.height,
                    frame_index=frame_index + stream_idx * 7,
                )
                ok, buf = cv2.imencode(
                    ".jpg",
                    frame,
                    [int(cv2.IMWRITE_JPEG_QUALITY), int(args.jpeg_quality)],
                )
                if not ok:
                    raise RuntimeError("Failed to encode demo frame.")

                jpg_bytes = buf.tobytes()
                frame_b64 = encode_image_bytes_to_base64(jpg_bytes)
                raw_size = len(jpg_bytes)
                b64_size = len(frame_b64.encode("utf-8"))
                total_raw_bytes += raw_size
                total_b64_bytes += b64_size

                response = post_video_stream_frame(
                    args.dashboard,
                    title=title,
                    frame_base64=frame_b64,
                    mime_type="image/jpeg",
                    source=args.source,
                )
                if frame_index % 30 == 0:
                    elapsed = max(time.time() - stats_started_at, 1e-6)
                    print(
                        f"[demo] pushed {response['title']} at {response['updated_at']} | "
                        f"jpg={raw_size / 1024:.1f} KB | "
                        f"base64={b64_size / 1024:.1f} KB | "
                        f"avg_upload={(total_b64_bytes / elapsed) / 1024:.1f} KB/s"
                    )

            frame_index += 1
            remaining = interval - (time.time() - loop_start)
            if remaining > 0:
                time.sleep(remaining)
    except KeyboardInterrupt:
        print("\n[demo] stopped")


if __name__ == "__main__":
    main()
