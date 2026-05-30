#!/usr/bin/env python3
"""Demo receiver for bridge result publisher outputs.

Receives raw pipeline outputs (pose + status) from the unified
custom_pipeline bridge via ZMQ multipart messages.
"""
from __future__ import annotations

import argparse
import json

import zmq


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Receive pose + status results from custom_pipeline bridge."
    )
    parser.add_argument(
        "--endpoint", default="tcp://127.0.0.1:8899",
        help="ZMQ PUB endpoint to subscribe.",
    )
    parser.add_argument(
        "--topic", default=["/fusion/pose", "/fusion/status"],
        nargs="+",
        help="ZMQ SUB topics to subscribe (default: pose and status).",
    )
    args = parser.parse_args()

    context = zmq.Context.instance()
    socket = context.socket(zmq.SUB)
    for t in args.topic:
        socket.setsockopt(zmq.SUBSCRIBE, t.encode("utf-8"))
    socket.connect(args.endpoint)

    print(f"[sub] listening on {args.endpoint}  topics={args.topic}")
    try:
        while True:
            parts = socket.recv_multipart()
            topic = parts[0].decode("utf-8")
            payload = json.loads(parts[-1].decode("utf-8"))

            if "/fusion/pose" in topic:
                objects = payload.get("objects", [])
                print(f"[pose] {len(objects)} objects: {[o.get('name','?') for o in objects]}")
            elif "/fusion/status" in topic:
                cat = payload.get("best_category", "-")
                sim = payload.get("best_similarity", 0)
                print(f"[status] {cat} (similarity={sim:.3f})")
            else:
                print(f"[{topic}] {json.dumps(payload, ensure_ascii=False)[:200]}")
    except KeyboardInterrupt:
        print("\n[sub] stopped")
    finally:
        socket.close(0)


if __name__ == "__main__":
    main()
