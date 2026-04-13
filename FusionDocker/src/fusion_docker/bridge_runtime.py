from __future__ import annotations

from pathlib import Path
from typing import Any

import fusion_docker.bridges  # noqa: F401
from fusion_docker.bridges.registry import load_bridge_runtime
from fusion_docker.console import print_status


def apply_bridge_cli_overrides(
    config: Any,
    *,
    req_timeout_ms: int | None = None,
    rgb_jpg_quality: int | None = None,
    listen_host: str | None = None,
    listen_port: int | None = None,
) -> None:
    if req_timeout_ms is not None and hasattr(config, "req_timeout_ms"):
        config.req_timeout_ms = req_timeout_ms
    if rgb_jpg_quality is not None and hasattr(config, "rgb_jpg_quality"):
        config.rgb_jpg_quality = rgb_jpg_quality
    if listen_host is not None and hasattr(config, "listen_host"):
        config.listen_host = listen_host
    if listen_port is not None and hasattr(config, "listen_port"):
        config.listen_port = listen_port


def run_bridge_from_config(
    config_path: str | Path,
    *,
    verbose: bool = False,
    save_json: bool = False,
    req_timeout_ms: int | None = None,
    rgb_jpg_quality: int | None = None,
    listen_host: str | None = None,
    listen_port: int | None = None,
) -> None:
    definition, config = load_bridge_runtime(config_path)
    apply_bridge_cli_overrides(
        config,
        req_timeout_ms=req_timeout_ms,
        rgb_jpg_quality=rgb_jpg_quality,
        listen_host=listen_host,
        listen_port=listen_port,
    )
    print_status(
        "MODE",
        f"Bridge type={definition.kind} config={Path(config_path).expanduser().resolve()}",
        color="cyan",
    )
    definition.run(config, verbose=verbose, save_json=save_json)
