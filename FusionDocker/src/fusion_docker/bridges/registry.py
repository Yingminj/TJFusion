from __future__ import annotations

from pathlib import Path
from typing import Any

from fusion_docker.bridges.base import BridgeDefinition
from fusion_docker.config import load_yaml_file

_BRIDGE_DEFINITIONS: list[BridgeDefinition] = []


def register_bridge(definition: BridgeDefinition) -> None:
    for existing in _BRIDGE_DEFINITIONS:
        if existing.supports(definition.kind):
            raise ValueError(f"Bridge kind already registered: {definition.kind}")
        if any(existing.supports(alias) for alias in definition.aliases):
            raise ValueError(
                f"Bridge alias conflict for {definition.kind}: {definition.aliases}"
            )
    _BRIDGE_DEFINITIONS.append(definition)


def list_bridges() -> list[BridgeDefinition]:
    return list(_BRIDGE_DEFINITIONS)


def get_bridge_definition(kind: str) -> BridgeDefinition:
    normalized = str(kind).strip().lower()
    for definition in _BRIDGE_DEFINITIONS:
        if definition.supports(normalized):
            return definition
    available = ", ".join(sorted(item.kind for item in _BRIDGE_DEFINITIONS))
    raise ValueError(f"Unknown bridge type '{kind}'. Available: {available}")


def detect_bridge_type(config_path: str | Path) -> str:
    raw = load_yaml_file(config_path)
    bridge_raw = raw.get("bridge")
    if bridge_raw is None:
        bridge_raw = raw.get("client", raw)
    if not isinstance(bridge_raw, dict):
        raise ValueError("Bridge config must be a mapping")
    return str(bridge_raw.get("type", "sam3_flowpose")).strip().lower() or "sam3_flowpose"


def load_bridge_runtime(config_path: str | Path) -> tuple[BridgeDefinition, Any]:
    resolved = Path(config_path).expanduser().resolve()
    bridge_type = detect_bridge_type(resolved)
    definition = get_bridge_definition(bridge_type)
    return definition, definition.load_config(resolved)
