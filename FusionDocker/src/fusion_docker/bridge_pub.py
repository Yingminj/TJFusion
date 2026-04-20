from __future__ import annotations

import json
from collections import Counter, deque
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
        siglip_vote_window: int = 1,
    ) -> None:
        zmq_module = require_zmq()
        self._frame_id = frame_id
        self._siglip_topic = siglip_topic
        self._tf_topic = tf_topic
        self._siglip_vote_window = max(1, int(siglip_vote_window))
        self._siglip_recent_categories: deque[str] = deque(maxlen=self._siglip_vote_window)
        self._context = zmq_module.Context.instance()
        self._socket = self._context.socket(zmq_module.PUB)
        self._socket.setsockopt(zmq_module.SNDHWM, 1)
        self._socket.setsockopt(zmq_module.LINGER, 0)
        self._socket.bind(addr)
        self.addr = addr

    def _select_smoothed_best_category(self, current: Any) -> Any:
        if not isinstance(current, str):
            return current
        normalized = current.strip()
        if not normalized:
            return current
        if self._siglip_vote_window <= 1:
            return normalized

        self._siglip_recent_categories.append(normalized)
        counts = Counter(self._siglip_recent_categories)
        max_count = max(counts.values(), default=0)
        winners = {name for name, freq in counts.items() if freq == max_count}
        for name in reversed(self._siglip_recent_categories):
            if name in winners:
                return name
        return normalized

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
        tf_payload = {
            "frame_id": frame_id,
            "transforms": build_tf_payload_from_flowpose_result(result, frame_id=self._frame_id),
        }
        if not tf_payload["transforms"]:
            return

        best_category = self._select_smoothed_best_category(siglip_result.get("best_category"))
        best_similarity = siglip_result.get("best_similarity")
        siglip_ok = bool(siglip_result.get("ok", False))

        siglip_payload = {
            "frame_id": frame_id,
            "ok": siglip_ok,
            "best_category": best_category,
            "best_similarity": best_similarity,
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
