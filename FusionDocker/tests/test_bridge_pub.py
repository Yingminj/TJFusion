from __future__ import annotations

import sys
import unittest
from collections import deque
from types import SimpleNamespace
from unittest.mock import patch
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from fusion_docker.bridge_pose import build_tf_payload_from_flowpose_result
from fusion_docker.bridge_pub import BridgeResultPublisher


class BridgePubTest(unittest.TestCase):
    def test_build_tf_payload_from_flowpose_result_converts_pose_matrix(self) -> None:
        payload = {
            "status": "ok",
            "objects": [
                {
                    "name": "cup",
                    "pose": [
                        [1.0, 0.0, 0.0, 0.1],
                        [0.0, 1.0, 0.0, 0.2],
                        [0.0, 0.0, 1.0, 0.3],
                        [0.0, 0.0, 0.0, 1.0],
                    ],
                }
            ],
        }

        transforms = build_tf_payload_from_flowpose_result(payload, frame_id="camera_rgb_link")

        self.assertEqual(len(transforms), 1)
        self.assertEqual(transforms[0]["frame_id"], "camera_rgb_link")
        self.assertEqual(transforms[0]["child_frame_id"], "cup_1")
        self.assertAlmostEqual(transforms[0]["translation"]["x"], 0.1)
        self.assertAlmostEqual(transforms[0]["translation"]["y"], 0.2)
        self.assertAlmostEqual(transforms[0]["translation"]["z"], 0.3)

    def test_select_smoothed_best_category_uses_majority_and_recent_tie_break(self) -> None:
        publisher = BridgeResultPublisher.__new__(BridgeResultPublisher)
        publisher._siglip_vote_window = 3
        publisher._siglip_recent_categories = deque(maxlen=3)

        self.assertEqual(publisher._select_smoothed_best_category("A"), "A")
        self.assertEqual(publisher._select_smoothed_best_category("B"), "B")
        self.assertEqual(publisher._select_smoothed_best_category("A"), "A")
        # window=[B, A, C] => all frequency=1, tie break chooses most recent C
        self.assertEqual(publisher._select_smoothed_best_category("C"), "C")

    def test_publish_sync_with_pose_buffers_siglip_until_pose_then_clears(self) -> None:
        class _FakeSocket:
            def __init__(self) -> None:
                self.sent: list[str] = []

            def send_string(self, message: str) -> None:
                self.sent.append(message)

        publisher = BridgeResultPublisher.__new__(BridgeResultPublisher)
        publisher._frame_id = "camera_rgb_link"
        publisher._siglip_topic = "/siglip2/result"
        publisher._tf_topic = "/tf"
        publisher._siglip_vote_window = 3
        publisher._siglip_recent_categories = deque(maxlen=3)
        publisher._siglip_sync_with_pose = True
        publisher._siglip_pose_wait_timeout_sec = 0.0
        publisher._siglip_pending_samples = deque(maxlen=3)
        publisher._siglip_buffer_start_monotonic = None
        publisher._socket = _FakeSocket()

        with patch(
            "fusion_docker.bridge_pub.build_tf_payload_from_flowpose_result",
            side_effect=[
                [],
                [
                    {
                        "frame_id": "camera_rgb_link",
                        "child_frame_id": "obj_1",
                        "translation": {"x": 0.0, "y": 0.0, "z": 0.0},
                        "rotation": {"x": 0.0, "y": 0.0, "z": 0.0, "w": 1.0},
                    }
                ],
            ],
        ):
            publisher.publish({"frame_id": "f1", "siglip2": {"ok": True, "best_category": "A"}})
            self.assertEqual(len(publisher._socket.sent), 0)
            self.assertEqual(len(publisher._siglip_pending_samples), 1)

            publisher.publish({"frame_id": "f2", "siglip2": {"ok": True, "best_category": "B"}})

        self.assertEqual(len(publisher._socket.sent), 2)
        self.assertTrue(publisher._socket.sent[0].startswith("/siglip2/result "))
        self.assertIn('"best_category": "B"', publisher._socket.sent[0])
        self.assertEqual(len(publisher._siglip_pending_samples), 0)

    def test_publish_sync_with_pose_timeout_forces_publish_without_pose(self) -> None:
        class _FakeSocket:
            def __init__(self) -> None:
                self.sent: list[str] = []

            def send_string(self, message: str) -> None:
                self.sent.append(message)

        publisher = BridgeResultPublisher.__new__(BridgeResultPublisher)
        publisher._frame_id = "camera_rgb_link"
        publisher._siglip_topic = "/siglip2/result"
        publisher._tf_topic = "/tf"
        publisher._siglip_vote_window = 3
        publisher._siglip_recent_categories = deque(maxlen=3)
        publisher._siglip_sync_with_pose = True
        publisher._siglip_pose_wait_timeout_sec = 1.0
        publisher._siglip_pending_samples = deque(maxlen=3)
        publisher._siglip_buffer_start_monotonic = None
        publisher._socket = _FakeSocket()

        fake_time = SimpleNamespace(now=100.0)

        def _monotonic() -> float:
            return fake_time.now

        with (
            patch(
                "fusion_docker.bridge_pub.build_tf_payload_from_flowpose_result",
                return_value=[],
            ),
            patch("fusion_docker.bridge_pub.time.monotonic", side_effect=_monotonic),
        ):
            publisher.publish({"frame_id": "f1", "siglip2": {"ok": True, "best_category": "A"}})
            self.assertEqual(len(publisher._socket.sent), 0)

            fake_time.now = 101.2
            publisher.publish({"frame_id": "f2", "siglip2": {"ok": False}})

        self.assertEqual(len(publisher._socket.sent), 2)
        self.assertIn('"best_category": "A"', publisher._socket.sent[0])
        self.assertIn('"ok": true', publisher._socket.sent[0].lower())
        self.assertIn('"transforms": []', publisher._socket.sent[1])
        self.assertEqual(len(publisher._siglip_pending_samples), 0)


if __name__ == "__main__":
    unittest.main()
