"""Result publisher: forwards raw pipeline outputs to ZMQ PUB with zero processing.

All data post-processing (TF construction, status extraction, pose conversion,
etc.) is the responsibility of the downstream consumer (MarvinDocker).
This publisher simply passes through the pipeline outputs as-is on
appropriate ZMQ topics.
"""

from __future__ import annotations

import json
from typing import Any

from fusion_docker.console import print_status

try:
    import zmq
except ImportError:  # pragma: no cover
    zmq = None


def _require_zmq() -> Any:
    if zmq is None:
        raise RuntimeError("BridgeResultPublisher requires pyzmq.")
    return zmq


# ---------------------------------------------------------------------------
# Publisher
# ---------------------------------------------------------------------------

class BridgeResultPublisher:
    """Publishes raw pipeline outputs on separate ZMQ PUB topics.

    **No data post-processing is performed.**  The publisher distributes
    raw model outputs on different topics so downstream consumers can
    transform them independently (e.g. into ROS2 messages).

    Topics
    ------
    ``pose_topic``
        Receives raw ``objects`` list from pose-estimation models
        (FlowPose, Yomni, etc.).  Each object may contain raw pose
        matrices / arrays and metadata like ``name`` and ``id``.

    ``status_topic``
        Receives classification / scene-state data from models such as
        SigLIP2.  Typical keys: ``best_category``, ``best_similarity``,
        ``state_list``.
    """

    def __init__(
        self,
        addr: str,
        *,
        pose_topic: str = "/fusion/pose",
        status_topic: str = "/fusion/status",
    ) -> None:
        zmq_module = _require_zmq()
        self._pose_topic = pose_topic
        self._status_topic = status_topic
        self._context = zmq_module.Context.instance()
        self._socket = self._context.socket(zmq_module.PUB)
        self._socket.setsockopt(zmq_module.SNDHWM, 1)
        self._socket.setsockopt(zmq_module.LINGER, 0)
        self._socket.bind(addr)
        self.addr = addr

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def publish(self, result: dict[str, Any]) -> None:
        """Forward raw pipeline *result* on topic-mapped ZMQ channels."""

        # ── Pose data (raw objects list) ──────────────────────────
        if result.get("objects") is not None:
            self._pub_raw(
                self._pose_topic,
                {
                    "request_id": result.get("request_id", ""),
                    "objects": result["objects"],
                },
            )

        # ── Status / classification data ──────────────────────────
        status_fields = ("best_category", "best_similarity", "state_list", "total_category")
        if any(key in result for key in status_fields):
            status_payload: dict[str, Any] = {
                "request_id": result.get("request_id", ""),
            }
            for key in status_fields:
                if key in result:
                    status_payload[key] = result[key]
            self._pub_raw(self._status_topic, status_payload)

        # One-line summary
        pose_count = (
            len(result["objects"])
            if isinstance(result.get("objects"), list)
            else (1 if result.get("objects") is not None else 0)
        )
        best_cat = result.get("best_category") or "-"
        print_status(
            "PUB",
            (
                f"pose={pose_count} objects  "
                f"status={best_cat}"
            ),
            color="green",
        )

    def close(self) -> None:
        try:
            self._socket.close(0)
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _pub_raw(self, topic: str, payload: dict[str, Any]) -> None:
        """Send *payload* as a ZMQ multipart message [topic, json]."""
        self._socket.send_multipart(
            [
                topic.encode("utf-8"),
                json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            ]
        )
