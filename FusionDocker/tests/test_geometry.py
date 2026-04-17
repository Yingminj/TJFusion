from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from fusion_docker.core.geometry import compose_pose


class GeometryTest(unittest.TestCase):
    def test_identity_pose_keeps_relative_pose(self) -> None:
        base_pose = (0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 1.0)
        relative_pose = (0.1, -0.2, 0.3, 0.0, 0.0, 0.0, 1.0)
        self.assertEqual(compose_pose(base_pose, relative_pose), relative_pose)


if __name__ == "__main__":
    unittest.main()

