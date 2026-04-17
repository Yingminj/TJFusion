from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from fusion_docker.core.action_library import ActionLibrary
from fusion_docker.core.command_builder import build_robot_command
from fusion_docker.core.geometry import coerce_pose
from fusion_docker.core.object_registry import ObjectRegistry
from fusion_docker.core.state_matcher import StateMatcher
from fusion_docker.models import Pose, normalize_token


@dataclass(slots=True)
class TrackedObject:
    object_id: str
    object_type: str | None = None
    frame_id: str = "base_link"
    pose: Pose | None = None
    raw_state: str | None = None
    current_state: str | None = None
    goal: str | None = None
    requested_action: str | None = None
    goal_revision: str | None = None
    pose_payload: dict[str, Any] = field(default_factory=dict)
    state_payload: dict[str, Any] = field(default_factory=dict)
    goal_payload: dict[str, Any] = field(default_factory=dict)
    last_command_signature: str | None = None


class FusionEngine:
    def __init__(
        self,
        *,
        object_registry: ObjectRegistry,
        action_library: ActionLibrary,
        state_matcher: StateMatcher,
    ) -> None:
        self._object_registry = object_registry
        self._action_library = action_library
        self._state_matcher = state_matcher
        self._tracked_objects: dict[str, TrackedObject] = {}
        self._latest_rgb: dict[str, Any] | None = None
        self._latest_depth: dict[str, Any] | None = None

    def handle_event(self, input_name: str, payload: dict[str, Any]) -> dict[str, Any] | None:
        if input_name == "realsense_rgb":
            self._latest_rgb = _compact_sensor_payload(payload)
            return None
        if input_name == "realsense_depth":
            self._latest_depth = _compact_sensor_payload(payload)
            return None

        object_id = str(payload.get("object_id") or payload.get("id") or "").strip()
        if not object_id:
            return None

        tracked = self._tracked_objects.setdefault(object_id, TrackedObject(object_id=object_id))
        tracked.object_type = normalize_token(payload.get("object_type")) or tracked.object_type
        tracked.frame_id = str(payload.get("frame_id") or tracked.frame_id or "base_link")

        if input_name == "yomni_pose":
            self._update_pose(tracked, payload)
        elif input_name == "siglip_state":
            self._update_state(tracked, payload)
        elif input_name == "task_goal":
            self._update_goal(tracked, payload)
        else:
            return None

        return self._maybe_build_command(tracked)

    def _update_pose(self, tracked: TrackedObject, payload: dict[str, Any]) -> None:
        pose_values = payload.get("pose")
        if pose_values is None and payload.get("position") and payload.get("orientation"):
            pose_values = list(payload["position"]) + list(payload["orientation"])
        if pose_values is None:
            return
        tracked.pose = coerce_pose(pose_values, label=f"{tracked.object_id}.pose")
        tracked.pose_payload = payload

    def _update_state(self, tracked: TrackedObject, payload: dict[str, Any]) -> None:
        raw_state = payload.get("state")
        if not raw_state:
            labels = payload.get("labels", [])
            if isinstance(labels, list) and labels:
                raw_state = labels[0]
        tracked.raw_state = str(raw_state or "").strip() or tracked.raw_state
        tracked.current_state = normalize_token(tracked.raw_state)
        tracked.state_payload = payload

    def _update_goal(self, tracked: TrackedObject, payload: dict[str, Any]) -> None:
        tracked.goal = normalize_token(payload.get("goal") or payload.get("desired_state"))
        tracked.requested_action = normalize_token(
            payload.get("action") or payload.get("requested_action")
        )
        tracked.goal_revision = str(
            payload.get("goal_id")
            or payload.get("timestamp")
            or f"{tracked.goal}:{tracked.requested_action}"
        )
        tracked.goal_payload = payload

    def _maybe_build_command(self, tracked: TrackedObject) -> dict[str, Any] | None:
        if tracked.pose is None:
            return None
        if not tracked.goal and not tracked.requested_action:
            return None

        profile = self._object_registry.resolve(
            object_type=tracked.object_type,
            object_id=tracked.object_id,
        )
        if profile is None:
            return None

        current_state = profile.normalize_state(tracked.current_state or tracked.raw_state)
        matched_action = self._state_matcher.match(
            profile=profile,
            current_state=current_state,
            goal=tracked.goal,
            requested_action=tracked.requested_action,
        )
        if matched_action is None:
            return None

        template = self._action_library.get(profile.template_key, matched_action.action_name)
        if template is None:
            return None

        signature = "|".join(
            [
                tracked.object_id,
                current_state,
                matched_action.action_name,
                tracked.goal or "",
                tracked.requested_action or "",
                tracked.goal_revision or "",
            ]
        )
        if signature == tracked.last_command_signature:
            return None

        command = build_robot_command(
            profile=profile,
            matched_action=matched_action,
            template=template,
            object_id=tracked.object_id,
            object_pose=tracked.pose,
            frame_id=tracked.frame_id,
            metadata={
                "goal": tracked.goal,
                "requested_action": tracked.requested_action,
                "current_state": current_state,
                "latest_rgb": self._latest_rgb,
                "latest_depth": self._latest_depth,
            },
        )
        tracked.last_command_signature = signature
        return command


def _compact_sensor_payload(payload: dict[str, Any]) -> dict[str, Any]:
    keep_fields = {
        "frame_id",
        "timestamp",
        "width",
        "height",
        "encoding",
        "sequence",
        "uri",
    }
    return {key: value for key, value in payload.items() if key in keep_fields}

