from __future__ import annotations

import json
import time

import zmq


def main() -> None:
    context = zmq.Context.instance()
    sockets = {
        "realsense_rgb": bind_pub(context, "tcp://127.0.0.1:6001"),
        "realsense_depth": bind_pub(context, "tcp://127.0.0.1:6002"),
        "yomni_pose": bind_pub(context, "tcp://127.0.0.1:6003"),
        "siglip_state": bind_pub(context, "tcp://127.0.0.1:6004"),
        "task_goal": bind_pub(context, "tcp://127.0.0.1:6005"),
    }

    try:
        time.sleep(0.8)
        send(
            sockets["realsense_rgb"],
            "realsense.rgb",
            {
                "frame_id": "camera_color_optical_frame",
                "timestamp": "2026-03-16T10:00:00Z",
                "width": 1280,
                "height": 720,
                "encoding": "rgb8",
                "uri": "memory://demo/rgb/0001",
            },
        )
        send(
            sockets["realsense_depth"],
            "realsense.depth",
            {
                "frame_id": "camera_depth_optical_frame",
                "timestamp": "2026-03-16T10:00:00Z",
                "width": 1280,
                "height": 720,
                "encoding": "16UC1",
                "uri": "memory://demo/depth/0001",
            },
        )
        send(
            sockets["yomni_pose"],
            "yomni.pose",
            {
                "object_id": "drawer_1",
                "object_type": "drawer",
                "frame_id": "base_link",
                "pose": [0.42, 0.10, 0.75, 0.0, 0.0, 0.0, 1.0],
                "timestamp": "2026-03-16T10:00:01Z",
            },
        )
        send(
            sockets["siglip_state"],
            "siglip2.state",
            {
                "object_id": "drawer_1",
                "object_type": "drawer",
                "state": "closed",
                "labels": ["closed"],
                "timestamp": "2026-03-16T10:00:02Z",
            },
        )
        send(
            sockets["task_goal"],
            "fusion.goal",
            {
                "object_id": "drawer_1",
                "object_type": "drawer",
                "goal": "open",
                "goal_id": "demo-drawer-open-001",
                "timestamp": "2026-03-16T10:00:03Z",
            },
        )
        time.sleep(0.5)
    finally:
        for socket in sockets.values():
            socket.close(0)


def bind_pub(context: zmq.Context, endpoint: str) -> zmq.Socket:
    socket = context.socket(zmq.PUB)
    socket.bind(endpoint)
    return socket


def send(socket: zmq.Socket, topic: str, payload: dict) -> None:
    message = json.dumps(payload, ensure_ascii=False)
    socket.send_string(f"{topic} {message}")
    print(f"sent {topic}: {payload}")
    time.sleep(0.15)


if __name__ == "__main__":
    main()

