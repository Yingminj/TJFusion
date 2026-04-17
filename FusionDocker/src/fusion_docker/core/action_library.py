from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from fusion_docker.core.geometry import coerce_pose
from fusion_docker.models import ActionTemplate, normalize_token


class ActionLibrary:
    def __init__(self, templates: dict[str, dict[str, ActionTemplate]]) -> None:
        self._templates = templates

    @classmethod
    def from_yaml(cls, path: str | Path) -> "ActionLibrary":
        resolved = Path(path)
        if not resolved.exists():
            raise FileNotFoundError(f"Action library not found: {resolved}")

        with resolved.open("r", encoding="utf-8") as handle:
            raw = yaml.safe_load(handle) or {}

        templates_raw = raw.get("templates", {})
        if not isinstance(templates_raw, dict):
            raise ValueError("Action library 'templates' must be a mapping")

        templates: dict[str, dict[str, ActionTemplate]] = {}
        for template_name, raw_actions in templates_raw.items():
            if not isinstance(raw_actions, dict):
                raise ValueError(f"Template must be a mapping: {template_name}")

            normalized_template = normalize_token(template_name)
            parsed_actions: dict[str, ActionTemplate] = {}
            for action_name, raw_spec in raw_actions.items():
                parsed_template = _parse_action_template(
                    template_name=normalized_template,
                    action_name=action_name,
                    raw_spec=raw_spec,
                )
                parsed_actions[parsed_template.action_name] = parsed_template
            templates[normalized_template] = parsed_actions

        return cls(templates)

    def get(self, template_name: str, action_name: str) -> ActionTemplate | None:
        template_map = self._templates.get(normalize_token(template_name))
        if not template_map:
            return None
        return template_map.get(normalize_token(action_name))


def _parse_action_template(
    *,
    template_name: str,
    action_name: str,
    raw_spec: Any,
) -> ActionTemplate:
    if not isinstance(raw_spec, dict):
        raise ValueError(f"Action template must be a mapping: {template_name}.{action_name}")

    normalized_action = normalize_token(raw_spec.get("action_name") or action_name)
    rotation_constraint = _coerce_triplet(
        raw_spec.get("rotation_constraint", [100.0, 100.0, 100.0]),
        label=f"{template_name}.{normalized_action}.rotation_constraint",
    )
    pose_relative = _coerce_pose_list(
        raw_spec.get("pose_relative", []),
        label=f"{template_name}.{normalized_action}.pose_relative",
    )
    gripper_state = _coerce_float_list(
        raw_spec.get("gripper_state", []),
        label=f"{template_name}.{normalized_action}.gripper_state",
    )
    time = _coerce_float_list(
        raw_spec.get("time", []),
        label=f"{template_name}.{normalized_action}.time",
    )

    if not pose_relative:
        raise ValueError(f"Action template has no pose_relative steps: {template_name}.{normalized_action}")
    if len(pose_relative) != len(gripper_state) or len(pose_relative) != len(time):
        raise ValueError(
            "pose_relative, gripper_state, and time must have the same length "
            f"for {template_name}.{normalized_action}"
        )

    return ActionTemplate(
        template_name=template_name,
        action_name=normalized_action,
        rotation_constraint=rotation_constraint,
        pose_relative=pose_relative,
        gripper_state=gripper_state,
        time=time,
    )


def _coerce_triplet(values: Any, *, label: str) -> tuple[float, float, float]:
    if not isinstance(values, list) or len(values) != 3:
        raise ValueError(f"{label} must contain 3 numeric values")
    return (float(values[0]), float(values[1]), float(values[2]))


def _coerce_pose_list(values: Any, *, label: str) -> list:
    if not isinstance(values, list):
        raise ValueError(f"{label} must be a list")
    return [coerce_pose(item, label=label) for item in values]


def _coerce_float_list(values: Any, *, label: str) -> list[float]:
    if not isinstance(values, list):
        raise ValueError(f"{label} must be a list")
    return [float(item) for item in values]

