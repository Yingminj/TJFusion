from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from fusion_docker.bridges.base import BridgeDefinition


BridgeConfigMutator = Callable[[Any], Any]


@dataclass(slots=True)
class BridgeProfile:
    kind: str
    description: str
    aliases: tuple[str, ...] = field(default_factory=tuple)
    mutate_config: BridgeConfigMutator | None = None


def load_profiled_bridge_config(config_path: Path, profile: BridgeProfile):
    from fusion_docker.config import load_bridge_config

    config = load_bridge_config(config_path)
    if profile.mutate_config is not None:
        config = profile.mutate_config(config)
    return config


def run_profiled_bridge(
    config,
    *,
    verbose: bool = False,
    save_json: bool = False,
) -> None:
    from fusion_docker.bridge_service import run_bridge_service

    run_bridge_service(config, verbose=verbose, save_json=save_json)


def create_profiled_bridge_definition(profile: BridgeProfile) -> BridgeDefinition:
    def _load(config_path: Path):
        return load_profiled_bridge_config(config_path, profile)

    return BridgeDefinition(
        kind=profile.kind,
        description=profile.description,
        load_config=_load,
        run=run_profiled_bridge,
        aliases=profile.aliases,
    )
