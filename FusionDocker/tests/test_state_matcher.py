from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from fusion_docker.core.state_matcher import StateMatcher
from fusion_docker.models import ActionRule, ObjectProfile


class StateMatcherTest(unittest.TestCase):
    def setUp(self) -> None:
        self.profile = ObjectProfile(
            object_type="drawer",
            display_name="Drawer",
            template_key="drawer_handle",
            aliases={"drawer"},
            affordances={"open", "close", "place"},
            default_state="closed",
            state_aliases={
                "closed": {"closed", "shut"},
                "open": {"open", "opened"},
            },
            action_rules=[
                ActionRule(current_state={"closed"}, goal={"open"}, action="open"),
                ActionRule(current_state={"open"}, goal={"close"}, action="close"),
            ],
        )
        self.matcher = StateMatcher()

    def test_rule_match_from_state_and_goal(self) -> None:
        matched = self.matcher.match(
            profile=self.profile,
            current_state="closed",
            goal="open",
            requested_action=None,
        )
        self.assertIsNotNone(matched)
        self.assertEqual(matched.action_name, "open")
        self.assertEqual(matched.match_source, "rule")

    def test_requested_action_fallback(self) -> None:
        matched = self.matcher.match(
            profile=self.profile,
            current_state="closed",
            goal=None,
            requested_action="place",
        )
        self.assertIsNotNone(matched)
        self.assertEqual(matched.action_name, "place")
        self.assertEqual(matched.match_source, "requested_action")


if __name__ == "__main__":
    unittest.main()

