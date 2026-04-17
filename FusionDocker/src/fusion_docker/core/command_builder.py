from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from fusion_docker.core.geometry import compose_pose
from fusion_docker.core.state_matcher import MatchedAction
from fusion_docker.models import ActionTemplate, ObjectProfile, Pose


def build_robot_command(
    *,
    profile: ObjectProfile,
    matched_action: MatchedAction,
    template: ActionTemplate,
    object_id: str,
    object_pose: Pose,
    frame_id: str,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    trajectory: list[dict[str, Any]] = []
    for index, relative_pose in enumerate(template.pose_relative):
        absolute_pose = compose_pose(object_pose, relative_pose)
        trajectory.append(
            {
                "index": index,
                "time": template.time[index],
                "pose": list(absolute_pose),
                "gripper_state": template.gripper_state[index],
            }
        )

    command = {
        "command_id": str(uuid4()),
        "source": "fusion_docker",
        "timestamp": _utc_now(),
        "object_id": object_id,
        "object_type": profile.object_type,
        "display_name": profile.display_name,
        "action_name": matched_action.action_name,
        "frame_id": frame_id,
        "template_key": profile.template_key,
        "match_source": matched_action.match_source,
        "rotation_constraint": list(template.rotation_constraint),
        "object_pose": list(object_pose),
        "trajectory": trajectory,
    }
    if metadata:
        command["metadata"] = metadata
    return command


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

