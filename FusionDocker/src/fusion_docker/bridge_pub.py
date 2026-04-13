from __future__ import annotations

import json
from typing import Any

from fusion_docker.bridge_pose import build_tf_payload_from_flowpose_result
from fusion_docker.console import print_status

try:
    import zmq
except ImportError:  # pragma: no cover
    zmq = None


def require_zmq() -> Any:
    if zmq is None:
        raise RuntimeError("ZMQ result publishing requires pyzmq.")
    return zmq


class BridgeResultPublisher:
    def __init__(
        self,
        addr: str,
        *,
        frame_id: str = "camera_rgb_link",
        siglip_topic: str = "/siglip2/result",
        tf_topic: str = "/tf",
    ) -> None:
        zmq_module = require_zmq()
        self._frame_id = frame_id
        self._siglip_topic = siglip_topic
        self._tf_topic = tf_topic
        self._context = zmq_module.Context.instance()
        self._socket = self._context.socket(zmq_module.PUB)
        self._socket.setsockopt(zmq_module.SNDHWM, 1)
        self._socket.setsockopt(zmq_module.LINGER, 0)
        self._socket.bind(addr)
        self.addr = addr

    def publish(self, result: dict[str, Any]) -> None:
        siglip_result = result.get("siglip2", {})
        if not isinstance(siglip_result, dict):
            siglip_result = {}
        frame_id = result.get(
            "frame_id",
            result.get("source_meta", {}).get("frame_id")
            if isinstance(result.get("source_meta"), dict)
            else None,
        )
        siglip_payload = {
            "frame_id": frame_id,
            "ok": bool(siglip_result.get("ok", False)),
            "best_category": siglip_result.get("best_category"),
            "best_similarity": siglip_result.get("best_similarity"),
        }
        tf_payload = {
            "frame_id": frame_id,
            "transforms": build_tf_payload_from_flowpose_result(result, frame_id=self._frame_id),
        }
        self._socket.send_string(
            f"{self._siglip_topic} {json.dumps(siglip_payload, ensure_ascii=False)}"
        )
        self._socket.send_string(
            f"{self._tf_topic} {json.dumps(tf_payload, ensure_ascii=False)}"
        )
        print_status(
            "PUB",
            (
                f"published frame_id={frame_id} "
                f"siglip_topic={self._siglip_topic} "
                f"siglip_ok={siglip_payload['ok']} "
                f"best_category={siglip_payload['best_category']} "
                f"tf_topic={self._tf_topic} "
                f"tf_count={len(tf_payload['transforms'])}"
            ),
            color="green",
        )

    def close(self) -> None:
        try:
            self._socket.close(0)
        except Exception:
            pass
