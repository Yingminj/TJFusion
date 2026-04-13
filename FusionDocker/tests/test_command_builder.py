from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from fusion_docker.core.command_builder import build_robot_command
from fusion_docker.core.state_matcher import MatchedAction
from fusion_docker.models import ActionTemplate, ObjectProfile


class CommandBuilderTest(unittest.TestCase):
    def test_build_robot_command_contains_trajectory(self) -> None:
        profile = ObjectProfile(
            object_type="cup",
            display_name="Cup",
            template_key="cup_handle",
            affordances={"pick"},
        )
        matched = MatchedAction(
            action_name="pick",
            current_state="idle",
            goal="pick",
            requested_action=None,
            match_source="rule",
        )
        template = ActionTemplate(
            template_name="cup_handle",
            action_name="pick",
            rotation_constraint=(100.0, 100.0, 100.0),
            pose_relative=[(0.1, 0.0, 0.2, 0.0, 0.0, 0.0, 1.0)],
            gripper_state=[0.0],
            time=[0.0],
        )

        command = build_robot_command(
            profile=profile,
            matched_action=matched,
            template=template,
            object_id="cup_1",
            object_pose=(0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 1.0),
            frame_id="base_link",
        )

        self.assertEqual(command["action_name"], "pick")
        self.assertEqual(len(command["trajectory"]), 1)
        self.assertEqual(command["trajectory"][0]["pose"], [0.1, 0.0, 0.2, 0.0, 0.0, 0.0, 1.0])


if __name__ == "__main__":
    unittest.main()
