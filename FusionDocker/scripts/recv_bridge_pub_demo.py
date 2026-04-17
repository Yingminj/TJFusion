#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json

import zmq


def main() -> None:
    parser = argparse.ArgumentParser(description="Receive siglip2 + tf results from multi_zmq_pub_bridge.")
    parser.add_argument("--endpoint", default="tcp://127.0.0.1:8899", help="ZMQ PUB endpoint to subscribe.")
    args = parser.parse_args()

    context = zmq.Context.instance()
    socket = context.socket(zmq.SUB)
    socket.setsockopt(zmq.SUBSCRIBE, b"")
    socket.connect(args.endpoint)

    print(f"[sub] listening on {args.endpoint}")
    try:
        while True:
            payload = socket.recv_json()
            request_id = payload.get("request_id", "")
            siglip = payload.get("siglip2", {}) or {}
            tf_items = payload.get("tf", []) or []
            print(
                json.dumps(
                    {
                        "frame_id": payload.get("frame_id"),
                        "best_category": siglip.get("best_category"),
                        "best_similarity": siglip.get("best_similarity"),
                        "tf_count": len(tf_items),
                        "tf": tf_items,
                    },
                    ensure_ascii=False,
                )
            )
    except KeyboardInterrupt:
        print("\n[sub] stopped")
    finally:
        socket.close(0)


if __name__ == "__main__":
    main()
