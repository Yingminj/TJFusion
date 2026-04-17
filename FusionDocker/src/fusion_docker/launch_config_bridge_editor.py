from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


@dataclass(slots=True)
class LaunchConfigBridgeEditResult:
    launch_config_path: Path
    bridge_name: str
    config_path: str
    created: bool
    updated: bool
    bridge_count: int
    updated_files: list[Path] = field(default_factory=list)


def add_bridge_to_launch_config(
    *,
    launch_config_path: str | Path,
    bridge_name: str,
    bridge_config_path: str,
    enabled: bool = True,
    force: bool = False,
) -> LaunchConfigBridgeEditResult:
    config_path = Path(launch_config_path).expanduser().resolve()
    if not config_path.exists():
        raise FileNotFoundError(f"Launch config not found: {config_path}")

    name = str(bridge_name).strip()
    if not name:
        raise ValueError("Bridge name cannot be empty.")
    bridge_config = str(bridge_config_path).strip()
    if not bridge_config:
        raise ValueError("Bridge config path cannot be empty.")

    with config_path.open("r", encoding="utf-8") as handle:
        raw = yaml.safe_load(handle) or {}
    if not isinstance(raw, dict):
        raise ValueError("Launch config YAML root must be a mapping.")

    launcher_raw = raw.get("docker_launcher")
    if launcher_raw is None:
        launcher_raw = {}
        raw["docker_launcher"] = launcher_raw
    if not isinstance(launcher_raw, dict):
        raise ValueError("docker_launcher must be a mapping.")

    bridges_raw = launcher_raw.get("bridges")
    if bridges_raw is None:
        bridges: list[dict[str, Any]] = []
        launcher_raw["bridges"] = bridges
    elif isinstance(bridges_raw, list):
        bridges = bridges_raw
    else:
        raise ValueError("docker_launcher.bridges must be a list to append bridge entries.")

    created = False
    updated = False
    bridge_key = name.lower()
    existing_entry: dict[str, Any] | None = None
    for item in bridges:
        if not isinstance(item, dict):
            continue
        item_name = str(item.get("name", "")).strip().lower()
        if item_name == bridge_key:
            existing_entry = item
            break

    if existing_entry is None:
        bridges.append(
            {
                "name": name,
                "enabled": bool(enabled),
                "config": bridge_config,
            }
        )
        created = True
    else:
        existing_config = str(existing_entry.get("config", existing_entry.get("config_path", ""))).strip()
        existing_enabled = bool(existing_entry.get("enabled", True))
        if not force and (existing_config != bridge_config or existing_enabled != bool(enabled)):
            raise ValueError(
                f"Bridge '{name}' already exists in launch config. Use --force to update it."
            )
        if force:
            existing_entry["enabled"] = bool(enabled)
            existing_entry["config"] = bridge_config
            existing_entry.pop("config_path", None)
            updated = True

    with config_path.open("w", encoding="utf-8") as handle:
        yaml.safe_dump(raw, handle, sort_keys=False, allow_unicode=False)

    return LaunchConfigBridgeEditResult(
        launch_config_path=config_path,
        bridge_name=name,
        config_path=bridge_config,
        created=created,
        updated=updated,
        bridge_count=len(bridges),
        updated_files=[config_path],
    )
