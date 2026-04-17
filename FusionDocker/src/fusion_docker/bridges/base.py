from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable


BridgeConfigLoader = Callable[[Path], Any]
BridgeRunner = Callable[..., None]


@dataclass(slots=True)
class BridgeDefinition:
    kind: str
    description: str
    load_config: BridgeConfigLoader
    run: BridgeRunner
    aliases: tuple[str, ...] = field(default_factory=tuple)

    def supports(self, name: str) -> bool:
        normalized = str(name).strip().lower()
        return normalized == self.kind or normalized in self.aliases
