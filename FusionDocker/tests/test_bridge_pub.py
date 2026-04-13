from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from fusion_docker.bridge_pose import build_tf_payload_from_flowpose_result


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


if __name__ == "__main__":
    unittest.main()
