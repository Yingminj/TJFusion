from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from fusion_docker.docker_launcher import DockerRunTarget


@dataclass(slots=True)
class DockerConfiguredPort:
    docker_name: str
    folder_path: str
    config_path: str
    container_name: str
    host: str
    port: int | None


def read_docker_configured_port(target: DockerRunTarget) -> DockerConfiguredPort:
    if target.is_remote:
        raise ValueError("Remote docker config parsing is not supported by this command.")

    config_path, config_data = _load_service_config_document(target.folder_path)
    docker_block = config_data.get("docker", {})
    server_block = config_data.get("server", {})

    container_name = ""
    if isinstance(docker_block, dict):
        container_name = str(
            docker_block.get("container_name")
            or docker_block.get("name")
            or ""
        ).strip()

    host = "0.0.0.0"
    raw_port: Any = None
    if isinstance(server_block, dict):
        host = str(server_block.get("host", "")).strip() or "0.0.0.0"
        raw_port = server_block.get("port")

    port: int | None = None
    if raw_port not in {None, ""}:
        try:
            port = int(raw_port)
        except (TypeError, ValueError):
            port = None

    return DockerConfiguredPort(
        docker_name=target.folder_name,
        folder_path=str(target.folder_path),
        config_path=str(config_path),
        container_name=container_name,
        host=host,
        port=port,
    )


def _load_service_config_document(folder_path: Path) -> tuple[Path, dict[str, Any]]:
    config_path = _discover_service_config_path_local(folder_path)
    if config_path is None:
        raise RuntimeError(
            f"No YAML file with docker.container_name and server.host/port was found under '{folder_path}'."
        )
    try:
        raw_text = config_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise RuntimeError(f"Failed to read YAML file '{config_path}': {exc}") from exc
    try:
        parsed = yaml.safe_load(raw_text) if raw_text.strip() else {}
    except Exception as exc:
        raise RuntimeError(f"Failed to parse YAML file '{config_path}': {exc}") from exc
    if not isinstance(parsed, dict):
        raise RuntimeError(f"YAML file '{config_path}' must be a mapping object.")
    return config_path, parsed


def _discover_service_config_path_local(folder: Path) -> Path | None:
    if not folder.exists() or not folder.is_dir():
        return None
    preferred_path = (folder / "config.yaml").resolve()
    if preferred_path.exists() and preferred_path.is_file():
        return preferred_path
    candidates: list[tuple[Path, dict[str, Any]]] = []
    for file_path in sorted(
        [*folder.rglob("*.yaml"), *folder.rglob("*.yml")],
        key=lambda item: (len(item.relative_to(folder).parts), str(item.relative_to(folder))),
    ):
        if not file_path.is_file():
            continue
        try:
            text = file_path.read_text(encoding="utf-8", errors="replace")
            data = yaml.safe_load(text) if text.strip() else {}
        except Exception:
            continue
        if isinstance(data, dict):
            candidates.append((file_path, data))
    selected = _select_best_service_config_candidate(candidates)
    return selected[0] if selected is not None else None


def _select_best_service_config_candidate(
    candidates: list[tuple[Path, dict[str, Any]]],
) -> tuple[Path, dict[str, Any]] | None:
    if not candidates:
        return None

    def score(item: tuple[Path, dict[str, Any]]) -> tuple[int, int, str]:
        path, data = item
        docker_block = data.get("docker")
        server_block = data.get("server")
        total = 0
        if isinstance(docker_block, dict) and str(docker_block.get("name", "")).strip():
            total += 6
        if isinstance(docker_block, dict) and str(docker_block.get("container_name", "")).strip():
            total += 5
        if isinstance(server_block, dict) and str(server_block.get("host", "")).strip():
            total += 4
        if isinstance(server_block, dict) and server_block.get("port") not in {None, ""}:
            total += 4

        path_text = str(path).lower()
        name_bonus = 0
        if "config" in path_text:
            name_bonus += 2
        if "server" in path_text:
            name_bonus += 2
        if "docker" in path_text:
            name_bonus += 1

        depth = len(path.relative_to(path.anchor).parts)
        return total + name_bonus, -depth, path_text

    ranked = sorted(candidates, key=score, reverse=True)
    best_path, best_data = ranked[0]
    best_score = score((best_path, best_data))[0]
    if best_score <= 0:
        return None
    return best_path, best_data
