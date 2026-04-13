from __future__ import annotations

from dataclasses import dataclass

from fusion_docker.models import ObjectProfile, normalize_token


@dataclass(slots=True)
class MatchedAction:
    action_name: str
    current_state: str
    goal: str | None
    requested_action: str | None
    match_source: str


class StateMatcher:
    def match(
        self,
        profile: ObjectProfile,
        current_state: str | None,
        goal: str | None,
        requested_action: str | None = None,
    ) -> MatchedAction | None:
        normalized_state = profile.normalize_state(current_state)
        normalized_goal = normalize_token(goal)
        normalized_requested_action = normalize_token(requested_action)

        for rule in profile.action_rules:
            if not rule.matches(
                normalized_state,
                normalized_goal,
                normalized_requested_action,
            ):
                continue
            if not profile.supports_action(rule.action):
                continue
            return MatchedAction(
                action_name=rule.action,
                current_state=normalized_state,
                goal=normalized_goal or None,
                requested_action=normalized_requested_action or None,
                match_source="rule",
            )

        if normalized_requested_action and profile.supports_action(normalized_requested_action):
            return MatchedAction(
                action_name=normalized_requested_action,
                current_state=normalized_state,
                goal=normalized_goal or None,
                requested_action=normalized_requested_action,
                match_source="requested_action",
            )

        if normalized_goal and profile.supports_action(normalized_goal):
            return MatchedAction(
                action_name=normalized_goal,
                current_state=normalized_state,
                goal=normalized_goal,
                requested_action=normalized_requested_action or None,
                match_source="goal_fallback",
            )

        return None

