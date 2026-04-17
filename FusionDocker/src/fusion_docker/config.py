from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml

from fusion_docker.models import (
    AppConfig,
    BridgeInputMapping,
    BridgeLaunchEntry,
    BridgeSchemaCheckConfig,
    BridgeSchemaLink,
    BridgeServiceConfig,
    DockerLaunchConfig,
    DockerTargetEntry,
    ZmqEndpointConfig,
)

DEFAULT_APP_CONFIG = Path("/app/configs/app.yaml")
DEFAULT_ACTION_LIBRARY = Path("/app/configs/action_library.yaml")
DEFAULT_OBJECT_DIR = Path("/app/configs/objects")
DEFAULT_BRIDGE_CONFIG = Path("/app/configs/bridge.sam3_flowpose.yaml")
DEFAULT_DOCKER_LAUNCH_CONFIG = Path("/app/configs/docker_launch.yaml")


def get_runtime_paths() -> tuple[Path, Path, Path]:
    app_config = Path(os.getenv("FUSION_APP_CONFIG", str(DEFAULT_APP_CONFIG)))
    action_library = Path(
        os.getenv("FUSION_ACTION_LIBRARY", str(DEFAULT_ACTION_LIBRARY))
    )
    object_dir = Path(os.getenv("FUSION_OBJECT_DIR", str(DEFAULT_OBJECT_DIR)))
    return app_config, action_library, object_dir


def get_bridge_config_path() -> Path:
    return Path(os.getenv("FUSION_BRIDGE_CONFIG", str(DEFAULT_BRIDGE_CONFIG)))


def get_docker_launch_config_path() -> Path:
    return Path(
        os.getenv("FUSION_DOCKER_LAUNCH_CONFIG", str(DEFAULT_DOCKER_LAUNCH_CONFIG))
    )


def _expand_config_path_value(value: str) -> str:
    return os.path.expanduser(os.path.expandvars(value))


def load_yaml_file(path: str | Path) -> dict[str, Any]:
    resolved = Path(path)
    if not resolved.exists():
        raise FileNotFoundError(f"YAML file not found: {resolved}")
    with resolved.open("r", encoding="utf-8") as handle:
        content = yaml.safe_load(handle) or {}
    if not isinstance(content, dict):
        raise ValueError(f"YAML root must be a mapping: {resolved}")
    return content


def load_app_config(path: str | Path) -> AppConfig:
    raw = load_yaml_file(path)
    service_name = str(raw.get("service_name", "fusion_docker"))
    poll_timeout_ms = int(raw.get("poll_timeout_ms", 200))
    inputs = _build_channels(raw.get("inputs", {}), section_name="inputs")
    outputs = _build_channels(raw.get("outputs", {}), section_name="outputs")
    if not outputs:
        raise ValueError("At least one output channel is required")
    return AppConfig(
        service_name=service_name,
        poll_timeout_ms=poll_timeout_ms,
        inputs=inputs,
        outputs=outputs,
    )


def load_bridge_config(path: str | Path) -> BridgeServiceConfig:
    raw = load_yaml_file(path)
    config_path = Path(path).expanduser().resolve()
    bridge_raw = raw.get("bridge")
    if bridge_raw is None:
        bridge_raw = raw.get("client", raw)
    if not isinstance(bridge_raw, dict):
        raise ValueError("Bridge config must be a mapping")
    sam3_raw = _coerce_optional_mapping(raw.get("sam3"), section_name="sam3")
    flowpose_raw = _coerce_optional_mapping(raw.get("flowpose"), section_name="flowpose")
    siglip2_raw = _coerce_optional_mapping(raw.get("siglip2"), section_name="siglip2")
    publisher_raw = _coerce_optional_mapping(raw.get("publisher"), section_name="publisher")
    bridge_type = str(bridge_raw.get("type", "")).strip().lower()

    prompts = bridge_raw.get("prompts", [])
    if prompts is None:
        prompts = []
    if not isinstance(prompts, list):
        raise ValueError("bridge.prompts must be a list")

    obj_ids = bridge_raw.get("obj_ids", [])
    if obj_ids is None:
        obj_ids = []
    if not isinstance(obj_ids, list):
        raise ValueError("bridge.obj_ids must be a list")

    obj_id_map = bridge_raw.get("obj_id_map", {})
    if obj_id_map is None:
        obj_id_map = {}
    if not isinstance(obj_id_map, dict):
        raise ValueError("bridge.obj_id_map must be a mapping")
    input_mapping = _parse_bridge_input_mapping(bridge_raw.get("input_mapping"))
    schema_check = _parse_bridge_schema_check(
        bridge_raw.get("schema_check"),
        config_dir=config_path.parent,
    )

    req_timeout_ms = int(bridge_raw.get("req_timeout_ms", 1000))
    sam3_timeout_raw = sam3_raw.get("timeout_ms", bridge_raw.get("sam3_req_timeout_ms"))
    sam3_timeout_ms = int(sam3_timeout_raw) if sam3_timeout_raw not in {None, ""} else None

    sam3_server_addr = str(
        sam3_raw.get("server_addr", bridge_raw.get("sam3_server_addr", ""))
    ).strip()
    flowpose_server_addr = str(
        flowpose_raw.get(
            "server_addr",
            bridge_raw.get(
                "flowpose_server_addr",
                bridge_raw.get("downstream_server_addr", ""),
            ),
        )
    ).strip()
    siglip2_server_addr = _coerce_tcp_addr(
        endpoint=siglip2_raw.get(
            "server_addr",
            bridge_raw.get(
                "siglip2_server_addr",
                bridge_raw.get("siglip_server_addr", ""),
            ),
        ),
        ip=siglip2_raw.get(
            "ip",
            bridge_raw.get(
                "siglip2_ip",
                bridge_raw.get("siglip_ip", ""),
            ),
        ),
        port=siglip2_raw.get(
            "port",
            bridge_raw.get(
                "siglip2_port",
                bridge_raw.get("siglip_port", ""),
            ),
        ),
    )
    flowpose_sidecar_server_addr = _coerce_tcp_addr(
        endpoint=flowpose_raw.get(
            "sidecar_server_addr",
            bridge_raw.get(
                "flowpose_sidecar_server_addr",
                bridge_raw.get("yomni_server_addr", ""),
            ),
        ),
        ip=flowpose_raw.get(
            "sidecar_ip",
            bridge_raw.get(
                "flowpose_sidecar_ip",
                bridge_raw.get("yomni_ip", ""),
            ),
        ),
        port=flowpose_raw.get(
            "sidecar_port",
            bridge_raw.get(
                "flowpose_sidecar_port",
                bridge_raw.get("yomni_port", ""),
            ),
        ),
    )
    default_run_sam3_flowpose = False if bridge_type == "siglip2_bridge" else True
    run_sam3_flowpose = bool(bridge_raw.get("run_sam3_flowpose", default_run_sam3_flowpose))
    source_mode = str(bridge_raw.get("source_mode", "")).strip().lower() or "external_json"
    if source_mode not in {"external_json", "zmq_source"}:
        raise ValueError("bridge.source_mode must be 'external_json' or 'zmq_source'")
    zmq_source_addr = str(
        bridge_raw.get("zmq_source_addr", bridge_raw.get("rgbd_endpoint", ""))
    ).strip()
    zmq_timeout_sec = float(bridge_raw.get("zmq_timeout_sec", 3.0))
    if zmq_timeout_sec <= 0:
        raise ValueError("bridge.zmq_timeout_sec must be greater than 0")
    if run_sam3_flowpose and (not sam3_server_addr or not flowpose_server_addr):
        raise ValueError(
            "Bridge config requires sam3_server_addr and flowpose_server_addr "
            "when bridge.run_sam3_flowpose=true"
        )
    if not run_sam3_flowpose and not siglip2_server_addr and not flowpose_sidecar_server_addr:
        raise ValueError(
            "Bridge config has no enabled pipeline. Set run_sam3_flowpose=true "
            "or configure siglip2_server_addr/flowpose_sidecar_server_addr."
        )
    if source_mode == "zmq_source" and not zmq_source_addr:
        raise ValueError("bridge.zmq_source_addr is required when source_mode=zmq_source")

    return BridgeServiceConfig(
        sam3_server_addr=sam3_server_addr,
        flowpose_server_addr=flowpose_server_addr,
        sam3_timeout_ms=sam3_timeout_ms,
        source_mode=source_mode,
        zmq_source_addr=zmq_source_addr,
        zmq_timeout_sec=zmq_timeout_sec,
        siglip2_server_addr=siglip2_server_addr,
        flowpose_sidecar_server_addr=flowpose_sidecar_server_addr,
        run_sam3_flowpose=run_sam3_flowpose,
        input_mapping=input_mapping,
        schema_check=schema_check,
        prompts=[str(prompt) for prompt in prompts],
        obj_ids=list(obj_ids),
        obj_id_map={str(key): value for key, value in obj_id_map.items()},
        return_masks=bool(bridge_raw.get("return_masks", True)),
        clear_previous=bool(bridge_raw.get("clear_previous", True)),
        output_json=str(bridge_raw.get("output_json", "response_sam3.json")),
        req_timeout_ms=req_timeout_ms,
        rgb_jpg_quality=int(bridge_raw.get("rgb_jpg_quality", 85)),
        listen_host=str(bridge_raw.get("listen_host", "0.0.0.0")),
        listen_port=int(bridge_raw.get("listen_port", 5556)),
        result_pub_addr=str(
            publisher_raw.get("result_pub_addr", bridge_raw.get("result_pub_addr", ""))
        ).strip(),
        result_pub_frame_id=str(
            publisher_raw.get(
                "result_pub_frame_id",
                bridge_raw.get("result_pub_frame_id", "camera_rgb_link"),
            )
        ),
        result_siglip_topic=str(
            publisher_raw.get(
                "result_siglip_topic",
                bridge_raw.get("result_siglip_topic", "/siglip2/result"),
            )
        ),
        result_tf_topic=str(
            publisher_raw.get(
                "result_tf_topic",
                bridge_raw.get("result_tf_topic", "/tf"),
            )
        ),
    )


def _parse_bridge_input_mapping(raw_mapping: Any) -> BridgeInputMapping:
    if raw_mapping is None:
        return BridgeInputMapping()
    if not isinstance(raw_mapping, dict):
        raise ValueError("bridge.input_mapping must be a mapping")

    default_mapping = BridgeInputMapping()
    rgb_keys = _coerce_mapping_keys(raw_mapping.get("rgb_keys"), default_mapping.rgb_keys)
    depth_keys = _coerce_mapping_keys(raw_mapping.get("depth_keys"), default_mapping.depth_keys)
    depth_raw_keys = _coerce_mapping_keys(
        raw_mapping.get("depth_raw_keys"),
        default_mapping.depth_raw_keys,
    )
    nested_payload_keys = _coerce_mapping_keys(
        raw_mapping.get("nested_payload_keys"),
        default_mapping.nested_payload_keys,
    )
    depth_shape_keys = _coerce_mapping_keys(
        raw_mapping.get("depth_shape_keys"),
        default_mapping.depth_shape_keys,
    )
    depth_height_keys = _coerce_mapping_keys(
        raw_mapping.get("depth_height_keys"),
        default_mapping.depth_height_keys,
    )
    depth_width_keys = _coerce_mapping_keys(
        raw_mapping.get("depth_width_keys"),
        default_mapping.depth_width_keys,
    )

    return BridgeInputMapping(
        rgb_keys=rgb_keys,
        depth_keys=depth_keys,
        depth_raw_keys=depth_raw_keys,
        nested_payload_keys=nested_payload_keys,
        depth_shape_keys=depth_shape_keys,
        depth_height_keys=depth_height_keys,
        depth_width_keys=depth_width_keys,
    )


def _coerce_optional_mapping(raw_value: Any, *, section_name: str) -> dict[str, Any]:
    if raw_value is None:
        return {}
    if not isinstance(raw_value, dict):
        raise ValueError(f"{section_name} config must be a mapping")
    return raw_value


def _coerce_mapping_keys(raw_value: Any, defaults: tuple[str, ...]) -> tuple[str, ...]:
    if raw_value is None:
        return defaults
    if not isinstance(raw_value, list):
        raise ValueError("bridge.input_mapping key list must be a list of strings")
    normalized = tuple(str(item).strip() for item in raw_value if str(item).strip())
    return normalized or defaults


def _parse_bridge_schema_check(
    raw_schema_check: Any,
    *,
    config_dir: Path,
) -> BridgeSchemaCheckConfig:
    if raw_schema_check is None:
        return BridgeSchemaCheckConfig(enabled=False)
    if not isinstance(raw_schema_check, dict):
        raise ValueError("bridge.schema_check must be a mapping")

    docker_model_root = str(raw_schema_check.get("docker_model_root", "")).strip()
    if docker_model_root:
        docker_model_root_path = Path(_expand_config_path_value(docker_model_root))
        if not docker_model_root_path.is_absolute():
            docker_model_root_path = (config_dir / docker_model_root_path).resolve()
        docker_model_root = str(docker_model_root_path)

    links_raw = raw_schema_check.get("links", [])
    if links_raw is None:
        links_raw = []
    if not isinstance(links_raw, list):
        raise ValueError("bridge.schema_check.links must be a list")

    links: list[BridgeSchemaLink] = []
    for index, link_raw in enumerate(links_raw):
        if not isinstance(link_raw, dict):
            raise ValueError(f"bridge.schema_check.links[{index}] must be a mapping")

        from_docker = str(
            link_raw.get("from", link_raw.get("upstream", ""))
        ).strip()
        to_docker = str(
            link_raw.get("to", link_raw.get("downstream", ""))
        ).strip()
        if not from_docker or not to_docker:
            raise ValueError(
                f"bridge.schema_check.links[{index}] requires both 'from' and 'to'"
            )

        field_map_raw = link_raw.get("field_map", {})
        if field_map_raw is None:
            field_map_raw = {}
        if not isinstance(field_map_raw, dict):
            raise ValueError(
                f"bridge.schema_check.links[{index}].field_map must be a mapping"
            )
        field_map = {
            str(dst_key).strip(): str(src_key).strip()
            for dst_key, src_key in field_map_raw.items()
            if str(dst_key).strip() and str(src_key).strip()
        }

        provides_raw = link_raw.get("provides", [])
        if provides_raw is None:
            provides_raw = []
        if not isinstance(provides_raw, list):
            raise ValueError(
                f"bridge.schema_check.links[{index}].provides must be a list"
            )
        provides = tuple(
            str(item).strip() for item in provides_raw if str(item).strip()
        )

        links.append(
            BridgeSchemaLink(
                from_docker=from_docker,
                to_docker=to_docker,
                field_map=field_map,
                provides=provides,
            )
        )

    enabled_raw = raw_schema_check.get("enabled")
    if enabled_raw is None:
        enabled = len(links) > 0
    else:
        enabled = bool(enabled_raw)

    return BridgeSchemaCheckConfig(
        enabled=enabled,
        docker_model_root=docker_model_root,
        strict=bool(raw_schema_check.get("strict", False)),
        links=links,
    )


def _coerce_tcp_addr(endpoint: Any, ip: Any, port: Any) -> str:
    endpoint_value = str(endpoint or "").strip()
    if endpoint_value:
        return endpoint_value

    ip_value = str(ip or "").strip()
    port_value = str(port or "").strip()
    if not ip_value or not port_value:
        return ""
    return f"tcp://{ip_value}:{port_value}"


def load_docker_launch_config(path: str | Path) -> DockerLaunchConfig:
    raw = load_yaml_file(path)
    config_path = Path(path).expanduser().resolve()
    config_dir = config_path.parent
    launch_raw = raw.get("docker_launcher")
    if launch_raw is None:
        launch_raw = raw.get("launcher", raw)
    if not isinstance(launch_raw, dict):
        raise ValueError("Docker launch config must be a mapping")

    docker_model_root = launch_raw.get("docker_model_root")
    if docker_model_root is not None:
        docker_model_root = str(docker_model_root).strip() or None
        if docker_model_root is not None:
            docker_model_root = _expand_config_path_value(docker_model_root)
    docker_targets = _parse_docker_target_entries(
        launch_raw,
        default_docker_model_root=docker_model_root,
    )
    selected_dockers = _coerce_docker_names(launch_raw.get("selected_dockers", []))
    if docker_targets:
        docker_names = [entry.name for entry in docker_targets]
        docker_groups = _build_groups_from_target_entries(docker_targets)
    else:
        docker_groups = _coerce_docker_groups(launch_raw)
        docker_names = _flatten_docker_groups(docker_groups)
        if not docker_names:
            docker_names = _coerce_docker_names(
                launch_raw.get("dockers", launch_raw.get("docker_names", []))
            )
    if selected_dockers:
        docker_names = selected_dockers
    remote_enabled, remote_host, remote_user, remote_docker_model_root, remote_ssh_port, remote_password = (
        _parse_remote_settings(launch_raw)
    )
    dashboard_mode, ui_host, ui_port, ui_log_lines = _parse_dashboard_settings(launch_raw)
    bridge_schema_default = _parse_optional_bridge_schema_check(
        launch_raw.get("bridge_schema_check"),
        config_dir=config_dir,
    )
    bridge_entries = _parse_bridge_entries(
        launch_raw,
        config_dir=config_dir,
        default_schema_check=bridge_schema_default,
    )
    bridge_enabled = bridge_entries[0].enabled if bridge_entries else True
    bridge_config_path = bridge_entries[0].config_path if bridge_entries else None

    return DockerLaunchConfig(
        docker_model_root=docker_model_root,
        docker_names=docker_names,
        docker_groups=docker_groups,
        docker_targets=docker_targets,
        remote_enabled=remote_enabled,
        remote_host=remote_host,
        remote_user=remote_user,
        remote_docker_model_root=remote_docker_model_root,
        remote_ssh_port=remote_ssh_port,
        remote_password=remote_password,
        use_tmux=bool(launch_raw.get("tmux", True)),
        monitor=bool(launch_raw.get("monitor", True)),
        replace_session=bool(launch_raw.get("replace_session", False)),
        poll_interval=float(launch_raw.get("poll_interval", 0.5)),
        dashboard_mode=dashboard_mode,
        ui_host=ui_host,
        ui_port=ui_port,
        ui_log_lines=ui_log_lines,
        bridge_entries=bridge_entries,
        bridge_enabled=bridge_enabled,
        bridge_config_path=bridge_config_path,
    )


def _build_channels(
    raw_channels: dict[str, Any],
    *,
    section_name: str,
) -> dict[str, ZmqEndpointConfig]:
    if not isinstance(raw_channels, dict):
        raise ValueError(f"{section_name} must be a mapping")

    channels: dict[str, ZmqEndpointConfig] = {}
    for name, raw_config in raw_channels.items():
        if not isinstance(raw_config, dict):
            raise ValueError(f"Channel config must be a mapping: {section_name}.{name}")

        mode = str(raw_config.get("mode", "connect")).strip().lower()
        if mode not in {"bind", "connect"}:
            raise ValueError(
                f"Channel mode must be 'bind' or 'connect': {section_name}.{name}"
            )

        endpoint = str(raw_config.get("endpoint", "")).strip()
        topic = str(raw_config.get("topic", "")).strip()
        if not endpoint or not topic:
            raise ValueError(
                f"Channel requires both endpoint and topic: {section_name}.{name}"
            )

        channels[name] = ZmqEndpointConfig(
            name=name,
            endpoint=endpoint,
            topic=topic,
            mode=mode,
        )
    return channels


def _coerce_docker_names(raw_dockers: Any) -> list[str]:
    if raw_dockers is None:
        return []
    if not isinstance(raw_dockers, list):
        raise ValueError("docker_launcher.dockers must be a list")

    docker_names: list[str] = []
    for entry in raw_dockers:
        if isinstance(entry, str):
            name = entry.strip()
            if name:
                docker_names.append(name)
            continue
        if isinstance(entry, dict):
            enabled = bool(entry.get("enabled", True))
            name = str(entry.get("name", "")).strip()
            if enabled and name:
                docker_names.append(name)
            continue
        raise ValueError("Each docker entry must be a string or mapping")
    return docker_names


def _coerce_docker_groups(launch_raw: dict[str, Any]) -> dict[str, list[str]]:
    raw_groups = launch_raw.get("groups")
    if raw_groups is None:
        raw_groups = {
            key: value
            for key, value in (
                ("vision", launch_raw.get("vision")),
                ("inference", launch_raw.get("inference")),
                ("action", launch_raw.get("action")),
            )
            if value is not None
        }

    if not raw_groups:
        return {}
    if not isinstance(raw_groups, dict):
        raise ValueError("docker_launcher.groups must be a mapping")

    parsed_groups: dict[str, list[str]] = {}
    for group_name, raw_dockers in raw_groups.items():
        normalized_group = str(group_name).strip().lower()
        if not normalized_group:
            continue
        parsed_groups[normalized_group] = _coerce_docker_names(raw_dockers)
    return parsed_groups


def _flatten_docker_groups(docker_groups: dict[str, list[str]]) -> list[str]:
    docker_names: list[str] = []
    for group_name in ("vision", "inference", "action"):
        docker_names.extend(docker_groups.get(group_name, []))

    seen = set(docker_names)
    for group_name, group_dockers in docker_groups.items():
        if group_name in {"vision", "inference", "action"}:
            continue
        for docker_name in group_dockers:
            if docker_name not in seen:
                docker_names.append(docker_name)
                seen.add(docker_name)
    return docker_names


def _parse_docker_target_entries(
    launch_raw: dict[str, Any],
    *,
    default_docker_model_root: str | None,
) -> list[DockerTargetEntry]:
    raw_targets = launch_raw.get("docker_targets")
    if raw_targets is None:
        return []
    if not isinstance(raw_targets, list):
        raise ValueError("docker_launcher.docker_targets must be a list")

    targets: list[DockerTargetEntry] = []
    seen_names: set[str] = set()
    for index, raw_target in enumerate(raw_targets, start=1):
        if not isinstance(raw_target, dict):
            raise ValueError("Each docker_targets entry must be a mapping")

        name = str(raw_target.get("name", "")).strip()
        if not name:
            raise ValueError(f"docker_targets[{index}] requires 'name'")

        normalized_name = name.lower()
        if normalized_name in seen_names:
            raise ValueError(f"Duplicate docker target name in docker_targets: {name}")
        seen_names.add(normalized_name)

        group = str(raw_target.get("group", "ungrouped")).strip().lower() or "ungrouped"
        location = str(raw_target.get("location", "local")).strip().lower() or "local"
        if location == "localhost":
            location = "local"
        if location not in {"local", "remote"}:
            raise ValueError(
                f"docker_targets[{index}].location must be 'localhost', 'local', or 'remote'"
            )

        docker_model_root = raw_target.get("docker_model_root")
        if docker_model_root is None:
            docker_model_root = default_docker_model_root
        if docker_model_root is not None:
            docker_model_root = str(docker_model_root).strip() or None
            if docker_model_root is not None:
                docker_model_root = _expand_config_path_value(docker_model_root)

        remote_raw = raw_target.get("remote", {})
        if remote_raw is None:
            remote_raw = {}
        if not isinstance(remote_raw, dict):
            raise ValueError(f"docker_targets[{index}].remote must be a mapping")

        remote_host = str(
            remote_raw.get("host", raw_target.get("remote_host", raw_target.get("remote_ip", "")))
        ).strip() or None
        remote_user = str(
            remote_raw.get(
                "user",
                raw_target.get("remote_user", raw_target.get("remote_username", "")),
            )
        ).strip() or None
        remote_docker_model_root = str(
            remote_raw.get(
                "docker_model_root",
                raw_target.get(
                    "remote_docker_model_root",
                    raw_target.get("remote_model_root", ""),
                ),
            )
        ).strip() or None
        ssh_port_raw = remote_raw.get("ssh_port", raw_target.get("remote_ssh_port", 22))
        remote_ssh_port = int(ssh_port_raw)
        if remote_ssh_port <= 0 or remote_ssh_port > 65535:
            raise ValueError(f"docker_targets[{index}].remote_ssh_port must be between 1 and 65535")
        remote_password = str(
            remote_raw.get(
                "password",
                raw_target.get("remote_password", ""),
            )
        ).strip() or None

        if location == "remote" and (not remote_host or not remote_user or not remote_docker_model_root):
            raise ValueError(
                f"docker_targets[{index}] with location=remote requires remote host/user/docker_model_root"
            )

        targets.append(
            DockerTargetEntry(
                name=name,
                group=group,
                location=location,
                docker_model_root=docker_model_root,
                remote_host=remote_host if location == "remote" else None,
                remote_user=remote_user if location == "remote" else None,
                remote_docker_model_root=(
                    remote_docker_model_root if location == "remote" else None
                ),
                remote_ssh_port=remote_ssh_port,
                remote_password=remote_password if location == "remote" else None,
            )
        )
    return targets


def _build_groups_from_target_entries(
    targets: list[DockerTargetEntry],
) -> dict[str, list[str]]:
    groups: dict[str, list[str]] = {}
    for entry in targets:
        group = entry.group.strip().lower() or "ungrouped"
        groups.setdefault(group, []).append(entry.name)
    return groups


def _parse_dashboard_settings(launch_raw: dict[str, Any]) -> tuple[str, str, int, int]:
    dashboard_raw = launch_raw.get("dashboard", launch_raw.get("ui", {}))
    if dashboard_raw is None:
        dashboard_raw = {}
    if not isinstance(dashboard_raw, dict):
        raise ValueError("docker_launcher.dashboard must be a mapping")

    dashboard_mode = str(
        dashboard_raw.get("mode", launch_raw.get("dashboard_mode", "terminal"))
    ).strip().lower()
    if not dashboard_mode:
        dashboard_mode = "terminal"
    if dashboard_mode not in {"terminal", "web"}:
        raise ValueError("docker_launcher.dashboard.mode must be 'terminal' or 'web'")

    ui_host = str(dashboard_raw.get("host", launch_raw.get("ui_host", "127.0.0.1"))).strip()
    if not ui_host:
        ui_host = "127.0.0.1"

    ui_port = int(dashboard_raw.get("port", launch_raw.get("ui_port", 8765)))
    if ui_port <= 0 or ui_port > 65535:
        raise ValueError("docker_launcher.dashboard.port must be between 1 and 65535")

    ui_log_lines = int(dashboard_raw.get("log_lines", launch_raw.get("ui_log_lines", 300)))
    if ui_log_lines <= 0:
        raise ValueError("docker_launcher.dashboard.log_lines must be greater than 0")

    return dashboard_mode, ui_host, ui_port, ui_log_lines


def _parse_remote_settings(
    launch_raw: dict[str, Any],
) -> tuple[bool, str | None, str | None, str | None, int, str | None]:
    remote_raw = launch_raw.get("remote", {})
    if remote_raw is None:
        remote_raw = {}
    if not isinstance(remote_raw, dict):
        raise ValueError("docker_launcher.remote must be a mapping")

    remote_host = str(
        remote_raw.get(
            "host",
            remote_raw.get(
                "ip",
                launch_raw.get("remote_host", launch_raw.get("remote_ip", "")),
            ),
        )
    ).strip() or None
    remote_user = str(
        remote_raw.get(
            "user",
            remote_raw.get(
                "username",
                launch_raw.get("remote_user", launch_raw.get("remote_username", "")),
            ),
        )
    ).strip() or None
    remote_docker_model_root = str(
        remote_raw.get(
            "docker_model_root",
            remote_raw.get(
                "model_root",
                launch_raw.get(
                    "remote_docker_model_root",
                    launch_raw.get("remote_model_root", ""),
                ),
            ),
        )
    ).strip() or None
    if remote_docker_model_root is not None:
        remote_docker_model_root = _expand_config_path_value(remote_docker_model_root)

    ssh_port_raw = remote_raw.get("ssh_port", launch_raw.get("remote_ssh_port", 22))
    remote_ssh_port = int(ssh_port_raw)
    if remote_ssh_port <= 0 or remote_ssh_port > 65535:
        raise ValueError("docker_launcher.remote.ssh_port must be between 1 and 65535")
    remote_password = str(
        remote_raw.get(
            "password",
            launch_raw.get("remote_password", ""),
        )
    ).strip() or None

    remote_enabled_raw = remote_raw.get("enabled")
    if remote_enabled_raw is None:
        remote_enabled = bool(remote_host or remote_user or remote_docker_model_root)
    else:
        remote_enabled = bool(remote_enabled_raw)

    if remote_enabled and (not remote_host or not remote_user or not remote_docker_model_root):
        raise ValueError(
            "docker_launcher.remote requires host, user, and docker_model_root when enabled"
        )

    return (
        remote_enabled,
        remote_host,
        remote_user,
        remote_docker_model_root,
        remote_ssh_port,
        remote_password,
    )

def _parse_optional_bridge_schema_check(
    raw_schema_check: Any,
    *,
    config_dir: Path,
) -> BridgeSchemaCheckConfig | None:
    if raw_schema_check is None:
        return None
    return _parse_bridge_schema_check(raw_schema_check, config_dir=config_dir)


def _clone_bridge_schema_check(
    raw: BridgeSchemaCheckConfig | None,
) -> BridgeSchemaCheckConfig | None:
    if raw is None:
        return None
    return BridgeSchemaCheckConfig(
        enabled=bool(raw.enabled),
        docker_model_root=str(raw.docker_model_root),
        strict=bool(raw.strict),
        links=[
            BridgeSchemaLink(
                from_docker=str(link.from_docker),
                to_docker=str(link.to_docker),
                field_map={str(key): str(value) for key, value in dict(link.field_map).items()},
                provides=tuple(str(item) for item in tuple(link.provides)),
            )
            for link in raw.links
        ],
    )


def _parse_bridge_entries(
    launch_raw: dict[str, Any],
    *,
    config_dir: Path,
    default_schema_check: BridgeSchemaCheckConfig | None = None,
) -> list[BridgeLaunchEntry]:
    raw_bridges = launch_raw.get("bridges")
    if raw_bridges is None and "bridge" in launch_raw:
        raw_bridges = [launch_raw.get("bridge")]

    if raw_bridges is None:
        return []

    normalized_entries: list[Any]
    if isinstance(raw_bridges, dict):
        if _looks_like_single_bridge_mapping(raw_bridges):
            normalized_entries = [raw_bridges]
        else:
            normalized_entries = []
            for bridge_name, raw_entry in raw_bridges.items():
                if isinstance(raw_entry, dict):
                    entry = dict(raw_entry)
                    entry.setdefault("name", str(bridge_name))
                    normalized_entries.append(entry)
                elif isinstance(raw_entry, str):
                    normalized_entries.append(
                        {
                            "name": str(bridge_name),
                            "config": raw_entry,
                        }
                    )
                else:
                    raise ValueError(
                        "Each docker_launcher.bridges entry must be a mapping or string"
                    )
    elif isinstance(raw_bridges, list):
        normalized_entries = list(raw_bridges)
    else:
        raise ValueError("docker_launcher.bridges must be a list or mapping")

    bridge_entries: list[BridgeLaunchEntry] = []
    seen_names: set[str] = set()
    for index, raw_entry in enumerate(normalized_entries, start=1):
        entry = _coerce_bridge_entry(
            raw_entry,
            index=index,
            config_dir=config_dir,
            default_schema_check=default_schema_check,
        )
        name_key = entry.name.strip().lower()
        if name_key in seen_names:
            raise ValueError(f"Duplicate bridge name in docker_launcher.bridges: {entry.name}")
        seen_names.add(name_key)
        bridge_entries.append(entry)
    return bridge_entries


def _coerce_bridge_entry(
    raw_entry: Any,
    *,
    index: int,
    config_dir: Path,
    default_schema_check: BridgeSchemaCheckConfig | None = None,
) -> BridgeLaunchEntry:
    if isinstance(raw_entry, str):
        config_path = raw_entry.strip() or None
        return BridgeLaunchEntry(
            name=f"Bridge {index}",
            enabled=True,
            config_path=config_path,
            schema_check=_clone_bridge_schema_check(default_schema_check),
        )

    if not isinstance(raw_entry, dict):
        raise ValueError("Each docker_launcher.bridges entry must be a mapping or string")

    bridge_name = str(raw_entry.get("name", f"Bridge {index}")).strip() or f"Bridge {index}"
    config_path = raw_entry.get("config", raw_entry.get("config_path"))
    if config_path is not None:
        config_path = str(config_path).strip() or None
    raw_schema_check = raw_entry.get("schema_check")
    if raw_schema_check is None:
        schema_check = _clone_bridge_schema_check(default_schema_check)
    else:
        schema_check = _parse_bridge_schema_check(raw_schema_check, config_dir=config_dir)
    return BridgeLaunchEntry(
        name=bridge_name,
        enabled=bool(raw_entry.get("enabled", True)),
        config_path=config_path,
        schema_check=schema_check,
    )


def _looks_like_single_bridge_mapping(raw_bridge: dict[str, Any]) -> bool:
    return any(
        key in raw_bridge
        for key in ("enabled", "config", "config_path", "name")
    )
