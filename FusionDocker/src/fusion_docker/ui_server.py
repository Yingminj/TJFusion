from __future__ import annotations

import base64
from collections import deque
from datetime import datetime, timezone
from html import escape
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path, PurePosixPath
import random
import re
import shlex
import shutil
import signal
from threading import RLock
import socket
import subprocess
import sys
import tempfile
import time
from typing import Any
from urllib.parse import parse_qs, urlparse
from uuid import uuid4

import yaml
import zmq

from fusion_docker.config import load_bridge_config, load_docker_launch_config
from fusion_docker.console import print_status, print_warning
from fusion_docker.docker_launcher import (
    DockerContainerInfo,
    DockerLaunchResult,
    DockerMatch,
    build_runtime_results,
    cleanup_launched_dockers,
    collect_runtime_statuses,
    describe_targets,
    discover_docker_targets,
    launch_single_match,
    match_requested_dockers,
    normalize_docker_name,
    read_result_logs,
    resolve_preferred_container,
    set_launch_env,
    stop_launch_result,
    _list_docker_containers,
)
from fusion_docker.models import (
    BridgeLaunchEntry,
    BridgeSchemaCheckConfig,
    BridgeSchemaLink,
    BridgeServiceConfig,
    DockerLaunchConfig,
    DockerTargetEntry,
)
from fusion_docker.ui.assets import get_static_asset, render_index_html
from fusion_docker.ui.auth import AuthPolicy
from fusion_docker.ui.status_cache import RuntimeStatusRefresher

STATUS_SUBPROCESS_TIMEOUT_S = 8.0

GROUP_ORDER = ("vision", "inference", "action", "ungrouped")
ANSI_CSI_RE = re.compile(r"\x1b\[([0-9;]*)m")
ANSI_ESCAPE_RE = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")
DOCKER_TEMPLATE_VAR_RE = re.compile(r"\$\{([^}]+)\}")
ZMQ_TEST_TIMEOUT_MS_DEFAULT = 4000
ZMQ_TEST_TIMEOUT_MS_MIN = 100
ZMQ_TEST_TIMEOUT_MS_MAX = 60000
ZMQ_TEST_HISTORY_LIMIT_DEFAULT = 40
ZMQ_TEST_HISTORY_LIMIT_MIN = 5
ZMQ_TEST_HISTORY_LIMIT_MAX = 200
DOCKER_CONSOLE_TIMEOUT_MS_DEFAULT = 15000
DOCKER_CONSOLE_TIMEOUT_MS_MIN = 1000
DOCKER_CONSOLE_TIMEOUT_MS_MAX = 120000
DOCKER_SERVICE_DEFAULT_HOST = "192.168.1.61"
DOCKER_CONFIG_CACHE_TTL_S = 8.0
VIDEO_STREAM_RETENTION_SEC = 15.0
VIDEO_STREAM_LIMIT = 128
ANSI_COLOR_TABLE = {
    30: "#1d2433",
    31: "#ff6f7d",
    32: "#61f2a3",
    33: "#ffd56d",
    34: "#68a3ff",
    35: "#ff7bf1",
    36: "#56f0ff",
    37: "#f1f7ff",
    90: "#6f7c91",
    91: "#ff98a4",
    92: "#8cffbe",
    93: "#ffe38f",
    94: "#8ab8ff",
    95: "#ff9cf6",
    96: "#86f7ff",
    97: "#ffffff",
}


def _clamp_int(value: Any, *, default: int, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return max(minimum, min(parsed, maximum))


def _default_zmq_test_request_payload() -> dict[str, Any]:
    return {
        "request_id": str(uuid4()),
        "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "rgb_image": "<base64_image_string>",
        "depth_image": "<base64_depth_string>",
    }


def _is_json_schema_document(raw: Any) -> bool:
    if not isinstance(raw, dict):
        return False
    if "$schema" in raw or "oneOf" in raw or "anyOf" in raw or "allOf" in raw:
        return True
    if isinstance(raw.get("properties"), dict):
        return True
    raw_type = str(raw.get("type", "")).strip().lower()
    if raw_type in {"object", "array", "string", "number", "integer", "boolean"}:
        for key in (
            "items",
            "properties",
            "enum",
            "const",
            "format",
            "contentEncoding",
            "default",
            "example",
        ):
            if key in raw:
                return True
    return False


def _random_base64_string(byte_count: int = 48) -> str:
    return base64.b64encode(os.urandom(max(4, int(byte_count)))).decode("ascii")


def _schema_int_bounds(schema_node: dict[str, Any]) -> tuple[int, int]:
    minimum_raw = schema_node.get("minimum")
    maximum_raw = schema_node.get("maximum")
    try:
        minimum = int(minimum_raw)
    except (TypeError, ValueError):
        minimum = 0
    try:
        maximum = int(maximum_raw)
    except (TypeError, ValueError):
        maximum = minimum + 10
    if maximum < minimum:
        maximum = minimum
    if maximum - minimum > 1000:
        maximum = minimum + 1000
    return minimum, maximum


def _schema_float_bounds(schema_node: dict[str, Any]) -> tuple[float, float]:
    minimum_raw = schema_node.get("minimum")
    maximum_raw = schema_node.get("maximum")
    try:
        minimum = float(minimum_raw)
    except (TypeError, ValueError):
        minimum = 0.0
    try:
        maximum = float(maximum_raw)
    except (TypeError, ValueError):
        maximum = minimum + 10.0
    if maximum < minimum:
        maximum = minimum
    if maximum - minimum > 1000:
        maximum = minimum + 1000.0
    return minimum, maximum


def _schema_field_looks_like_base64(field_name: str, schema_node: dict[str, Any]) -> bool:
    encoding = str(schema_node.get("contentEncoding", "")).strip().lower()
    if encoding == "base64":
        return True
    token = normalize_docker_name(field_name)
    return any(
        hint in token
        for hint in ("base64", "b64", "image", "depth", "mask", "png", "jpg", "jpeg")
    )


def _generate_value_from_schema(
    schema_node: Any,
    *,
    rng: random.Random,
    field_name: str = "",
    depth: int = 0,
) -> Any:
    if depth > 8:
        return None

    if not isinstance(schema_node, dict):
        return schema_node

    if "const" in schema_node:
        return schema_node["const"]
    enum_raw = schema_node.get("enum")
    if isinstance(enum_raw, list) and enum_raw:
        return rng.choice(enum_raw)
    if "example" in schema_node:
        return schema_node["example"]
    if "default" in schema_node:
        return schema_node["default"]

    any_of = schema_node.get("oneOf") or schema_node.get("anyOf")
    if isinstance(any_of, list) and any_of:
        selected = rng.choice([item for item in any_of if isinstance(item, dict)] or any_of)
        return _generate_value_from_schema(
            selected,
            rng=rng,
            field_name=field_name,
            depth=depth + 1,
        )

    raw_type = str(schema_node.get("type", "")).strip().lower()
    if not raw_type and isinstance(schema_node.get("properties"), dict):
        raw_type = "object"
    if not raw_type and "items" in schema_node:
        raw_type = "array"

    if raw_type == "object":
        properties = schema_node.get("properties")
        if isinstance(properties, dict) and properties:
            required = {
                str(item)
                for item in schema_node.get("required", [])
                if isinstance(item, str)
            }
            generated: dict[str, Any] = {}
            for key, child_schema in properties.items():
                include_field = key in required or rng.random() > 0.35
                if not include_field:
                    continue
                generated[str(key)] = _generate_value_from_schema(
                    child_schema,
                    rng=rng,
                    field_name=str(key),
                    depth=depth + 1,
                )
            for key in required:
                if key not in generated and key in properties:
                    generated[key] = _generate_value_from_schema(
                        properties[key],
                        rng=rng,
                        field_name=key,
                        depth=depth + 1,
                    )
            return generated
        return {}

    if raw_type == "array":
        items_schema = schema_node.get("items", {})
        min_items = _clamp_int(schema_node.get("minItems"), default=1, minimum=0, maximum=4)
        max_items = _clamp_int(schema_node.get("maxItems"), default=max(min_items, 2), minimum=min_items, maximum=6)
        count = rng.randint(min_items, max_items) if max_items >= min_items else min_items
        return [
            _generate_value_from_schema(
                items_schema,
                rng=rng,
                field_name=field_name,
                depth=depth + 1,
            )
            for _ in range(count)
        ]

    if raw_type == "boolean":
        return bool(rng.randint(0, 1))

    if raw_type == "integer":
        minimum, maximum = _schema_int_bounds(schema_node)
        return rng.randint(minimum, maximum)

    if raw_type == "number":
        minimum, maximum = _schema_float_bounds(schema_node)
        return round(rng.uniform(minimum, maximum), 4)

    if raw_type == "string":
        fmt = str(schema_node.get("format", "")).strip().lower()
        if fmt == "uuid":
            return str(uuid4())
        if fmt in {"date-time", "datetime"}:
            return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        if _schema_field_looks_like_base64(field_name, schema_node):
            return _random_base64_string()

        min_len = _clamp_int(schema_node.get("minLength"), default=4, minimum=0, maximum=48)
        max_len = _clamp_int(schema_node.get("maxLength"), default=max(min_len, 18), minimum=min_len, maximum=64)
        target_len = rng.randint(min_len, max_len) if max_len >= min_len else min_len
        base = normalize_docker_name(field_name) or "text"
        return (base + "_" + str(uuid4()).replace("-", ""))[: max(target_len, 1)]

    return None


def _generate_random_payload_from_schema(schema_doc: Any) -> dict[str, Any] | None:
    if not _is_json_schema_document(schema_doc):
        return None
    generated = _generate_value_from_schema(schema_doc, rng=random.Random())
    if isinstance(generated, dict):
        return generated
    return None


def _refresh_zmq_request_defaults(payload: dict[str, Any]) -> None:
    request_id = str(payload.get("request_id", "")).strip()
    if not request_id:
        payload["request_id"] = str(uuid4())
    timestamp = str(payload.get("timestamp", "")).strip()
    if not timestamp:
        payload["timestamp"] = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _execute_zmq_json_request(
    *,
    endpoint: str,
    request_obj: dict[str, Any],
    timeout_ms: int,
) -> tuple[Any | None, str, float]:
    request_text = json.dumps(request_obj, ensure_ascii=False)
    context = zmq.Context.instance()
    socket = context.socket(zmq.REQ)
    socket.setsockopt(zmq.RCVTIMEO, timeout_ms)
    socket.setsockopt(zmq.SNDTIMEO, timeout_ms)
    socket.setsockopt(zmq.LINGER, 0)
    socket.connect(endpoint)

    start_at = time.perf_counter()
    try:
        socket.send_string(request_text)
        response_text = socket.recv_string()
        elapsed_ms = (time.perf_counter() - start_at) * 1000.0
    finally:
        socket.close(0)

    try:
        response_obj = json.loads(response_text)
    except json.JSONDecodeError:
        response_obj = None
    return response_obj, response_text, elapsed_ms


class DashboardController:
    def __init__(
        self,
        *,
        matches: list[DockerMatch] | None = None,
        results: list[DockerLaunchResult] | None = None,
        log_lines: int = 300,
        project_root: Path | None = None,
        launch_config_path: str | Path | None = None,
        docker_model_root_hint: str | Path | None = None,
        docker_model_root_override: str | Path | None = None,
        docker_names_override: list[str] | None = None,
        bridge_manager: BridgeManager | None = None,
        bridge_managers: list[BridgeManager] | None = None,
    ) -> None:
        if log_lines <= 0:
            raise ValueError("log_lines must be greater than 0.")
        if results is None and matches is None:
            raise ValueError("Either matches or results must be provided.")

        self._project_root = (
            project_root.resolve()
            if project_root is not None
            else Path(__file__).resolve().parents[2]
        )
        self._results = list(results) if results is not None else build_runtime_results(matches or [])
        self._log_lines = log_lines
        self._lock = RLock()
        self._result_lookup: dict[str, DockerLaunchResult] = {}
        self._match_lookup: dict[str, DockerMatch] = {}
        self._bridge_lookup: dict[str, BridgeManager] = {}
        self._bridge_display_names: dict[str, str] = {}
        self._bridge_order: list[str] = []
        self._docker_model_root_hint = (
            Path(docker_model_root_hint).expanduser().resolve()
            if docker_model_root_hint is not None
            else self._infer_docker_model_root(self._results)
        )
        self._docker_model_root_override = (
            Path(docker_model_root_override).expanduser().resolve()
            if docker_model_root_override is not None
            else None
        )
        self._docker_names_override = list(docker_names_override or [])
        self._launch_config_manager = LaunchConfigManager(
            project_root=self._project_root,
            config_path=launch_config_path,
        )
        self._docker_config_cache: dict[str, tuple[float, dict[str, Any]]] = {}
        self._zmq_test_history: deque[dict[str, Any]] = deque(
            maxlen=ZMQ_TEST_HISTORY_LIMIT_DEFAULT
        )
        self._video_streams: dict[str, dict[str, Any]] = {}
        # Runtime status (docker/tmux/SSH probes) is collected on a background
        # thread and cached here so request handlers never block on subprocesses.
        # ``None`` means "not yet computed" (cold start).
        self._runtime_status_cache: list[Any] | None = None
        for result in self._results:
            self._index_match(result.match)
        for result in self._results:
            self._index_result(result)
        managers = list(bridge_managers or [])
        if bridge_manager is not None:
            managers.insert(0, bridge_manager)
        self._index_bridges(managers)

    @property
    def results(self) -> list[DockerLaunchResult]:
        with self._lock:
            return list(self._results)

    def refresh_runtime_cache(self) -> None:
        """Recompute the runtime-status snapshot off the request path.

        Invoked periodically by :class:`RuntimeStatusRefresher`. The expensive
        ``collect_runtime_statuses`` call runs outside the lock; only the cache
        swap and config-cache warming happen while holding it.
        """

        with self._lock:
            results = list(self._results)
        statuses = collect_runtime_statuses(results)
        with self._lock:
            self._runtime_status_cache = statuses
            for status in statuses:
                try:
                    self._read_docker_config_fields_locked(status.result.match.target)
                except Exception:
                    # Config warming is best-effort; status_payload tolerates misses.
                    pass

    def _runtime_statuses_locked(self) -> list[Any]:
        """Return cached runtime statuses, computing once on cold start."""

        if self._runtime_status_cache is not None:
            return self._runtime_status_cache
        statuses = collect_runtime_statuses(self._results)
        self._runtime_status_cache = statuses
        return statuses

    def _invalidate_runtime_cache_locked(self) -> None:
        self._runtime_status_cache = None

    def status_payload(self) -> dict[str, object]:
        with self._lock:
            self._prune_video_streams_locked()
            statuses = self._runtime_statuses_locked()
            bridge_payloads = self._bridge_payloads_locked()
            dockers: list[dict[str, object]] = []
            running_count = 0
            ended_count = 0
            error_count = 0

            for status in statuses:
                try:
                    folder_name = status.result.match.target.folder_name
                    connection = self._docker_connection_from_target(status.result.match.target)
                    if status.overall_status == "running":
                        running_count += 1
                    elif status.overall_status == "error":
                        error_count += 1
                    elif status.overall_status == "ended":
                        ended_count += 1

                    config_fields = self._read_docker_config_fields_locked(status.result.match.target)
                    config_image = str(config_fields.get("image", "") or "").strip()
                    config_container = str(config_fields.get("container_name", "") or "").strip()
                    config_host = str(config_fields.get("host", "") or "").strip()
                    config_port_raw = config_fields.get("port")
                    config_port_text = (
                        ""
                        if (config_port_raw is None or config_port_raw == "")
                        else str(config_port_raw).strip()
                    )

                    # Pure config-driven display (no runtime container checks).
                    image_summary = config_image or str(getattr(status, "image_summary", "untracked") or "untracked")
                    container_summary = config_container or str(status.container_summary or "untracked")
                    if config_host and config_port_text:
                        ports_summary = f"{config_host}:{config_port_text}"
                    elif config_port_text:
                        ports_summary = config_port_text
                    else:
                        ports_summary = str(status.ports_summary or "untracked")

                    dockers.append(
                        {
                            "name": folder_name,
                            "requested_name": status.result.match.requested_name,
                            "group": status.result.match.group_name or "ungrouped",
                            "status": status.overall_status,
                            "session_state": status.session_state,
                            "session_name": status.result.tmux_session or "",
                            "image": image_summary,
                            "container_summary": container_summary,
                            "ports": ports_summary,
                            "status_message": self._status_message(status),
                            "location": connection["location"],
                            "docker_model_root": connection["docker_model_root"],
                            "remote_host": connection["remote_host"],
                            "remote_user": connection["remote_user"],
                            "remote_ssh_port": connection["remote_ssh_port"],
                            "remote_docker_model_root": connection["remote_docker_model_root"],
                            "remote_password_set": connection["remote_password_set"],
                            "config_host": config_host,
                            "config_port": config_port_text,
                            "log_available": bool(
                                status.result.tmux_session
                                or status.result.log_path
                                or status.result.container_ids
                                or status.result.startup_output
                            ),
                            "can_view_logs": bool(
                                status.result.tmux_session
                                or status.result.log_path
                                or status.result.container_ids
                                or status.result.startup_output
                            ),
                        }
                    )
                except Exception as exc:
                    fallback_name = status.result.match.target.folder_name
                    fallback_connection = self._docker_connection_from_target(status.result.match.target)
                    dockers.append(
                        {
                            "name": fallback_name,
                            "requested_name": status.result.match.requested_name,
                            "group": status.result.match.group_name or "ungrouped",
                            "status": status.overall_status,
                            "session_state": status.session_state,
                            "session_name": status.result.tmux_session or "",
                            "image": str(getattr(status, "image_summary", "untracked") or "untracked"),
                            "container_summary": str(status.container_summary or "untracked"),
                            "ports": str(status.ports_summary or "untracked"),
                            "status_message": f"{self._status_message(status)} config-read-error: {exc}",
                            "location": fallback_connection["location"],
                            "docker_model_root": fallback_connection["docker_model_root"],
                            "remote_host": fallback_connection["remote_host"],
                            "remote_user": fallback_connection["remote_user"],
                            "remote_ssh_port": fallback_connection["remote_ssh_port"],
                            "remote_docker_model_root": fallback_connection["remote_docker_model_root"],
                            "remote_password_set": fallback_connection["remote_password_set"],
                            "config_host": "",
                            "config_port": "",
                            "log_available": bool(
                                status.result.tmux_session
                                or status.result.log_path
                                or status.result.container_ids
                                or status.result.startup_output
                            ),
                            "can_view_logs": bool(
                                status.result.tmux_session
                                or status.result.log_path
                                or status.result.container_ids
                                or status.result.startup_output
                            ),
                        }
                    )

            dockers.sort(key=self._docker_sort_key)
            return {
                "title": "Marvin Robot System",
                "updated_at": datetime.now(timezone.utc).isoformat(),
                "summary": {
                    "total": len(dockers),
                    "running": running_count,
                    "error": error_count,
                    "ended": ended_count,
                    "other": max(len(dockers) - running_count - error_count - ended_count, 0),
                },
                "bridge": bridge_payloads[0] if bridge_payloads else self._default_bridge_payload(),
                "bridges": bridge_payloads,
                "dockers": dockers,
                "video_streams": self.video_streams_payload_locked(),
            }

    def publish_video_stream(
        self,
        *,
        title: str,
        frame_base64: str,
        mime_type: str = "image/jpeg",
        source: str = "",
    ) -> dict[str, object]:
        normalized_title = str(title or "").strip()
        if not normalized_title:
            raise ValueError("title is required.")
        normalized_frame = str(frame_base64 or "").strip()
        if not normalized_frame:
            raise ValueError("frame_base64 is required.")
        normalized_mime = str(mime_type or "image/jpeg").strip() or "image/jpeg"
        if not normalized_mime.startswith("image/"):
            raise ValueError("mime_type must start with 'image/'.")

        with self._lock:
            self._prune_video_streams_locked()
            self._video_streams[normalized_title] = {
                "title": normalized_title,
                "frame_base64": normalized_frame,
                "mime_type": normalized_mime,
                "source": str(source or "").strip(),
                "updated_at": datetime.now(timezone.utc).isoformat(),
                "received_ts": time.monotonic(),
            }
            while len(self._video_streams) > VIDEO_STREAM_LIMIT:
                oldest_title = min(
                    self._video_streams.items(),
                    key=lambda item: float(item[1].get("received_ts", 0.0)),
                )[0]
                self._video_streams.pop(oldest_title, None)

            stream = self._video_streams[normalized_title]
            return {
                "ok": True,
                "title": normalized_title,
                "updated_at": stream["updated_at"],
            }

    def video_streams_payload(self) -> dict[str, object]:
        with self._lock:
            return {
                "updated_at": datetime.now(timezone.utc).isoformat(),
                "streams": self.video_streams_payload_locked(),
                "format_hint": (
                    "POST /api/video-stream with JSON "
                    "{title, frame_base64, mime_type?, source?}. "
                    "Supported mime_type values should be image/*, for example image/jpeg or image/png."
                ),
            }

    def video_streams_payload_locked(self) -> list[dict[str, object]]:
        self._prune_video_streams_locked()
        items = sorted(
            self._video_streams.values(),
            key=lambda item: str(item.get("title", "")).lower(),
        )
        payloads: list[dict[str, object]] = []
        now = time.monotonic()
        for item in items:
            payloads.append(
                {
                    "title": item["title"],
                    "frame_base64": item["frame_base64"],
                    "mime_type": item["mime_type"],
                    "source": item.get("source", ""),
                    "updated_at": item["updated_at"],
                    "age_ms": round(max(now - float(item.get("received_ts", now)), 0.0) * 1000.0, 1),
                }
            )
        return payloads

    def _prune_video_streams_locked(self) -> None:
        now = time.monotonic()
        stale_titles = [
            title
            for title, item in self._video_streams.items()
            if now - float(item.get("received_ts", now)) > VIDEO_STREAM_RETENTION_SEC
        ]
        for title in stale_titles:
            self._video_streams.pop(title, None)

    def _resolve_container_by_config_locked(
        self,
        target,
        *,
        local_containers: list[DockerContainerInfo],
        remote_container_cache: dict[str, list[DockerContainerInfo]],
    ) -> DockerContainerInfo | None:
        configured_candidates = self._configured_container_candidates_for_target_locked(target)
        if not configured_candidates:
            return None

        if target.is_remote:
            cache_key = self._remote_target_label(target)
            remote_containers = remote_container_cache.get(cache_key)
            if remote_containers is None:
                remote_containers = self._list_remote_containers_locked(target)
                remote_container_cache[cache_key] = remote_containers
            for configured_name in configured_candidates:
                matched = self._find_container_by_name(
                    remote_containers,
                    configured_name,
                    allow_fuzzy=False,
                )
                if matched is None:
                    matched = self._find_container_by_name(
                        remote_containers,
                        configured_name,
                        allow_fuzzy=True,
                    )
                if matched is not None:
                    return matched
            return None

        for configured_name in configured_candidates:
            matched = self._find_container_by_name(
                local_containers,
                configured_name,
                allow_fuzzy=False,
            )
            if matched is None:
                matched = self._find_container_by_name(
                    local_containers,
                    configured_name,
                    allow_fuzzy=True,
                )
            if matched is not None:
                return matched
        return None

    def _read_docker_config_fields_locked(self, target) -> dict[str, Any]:
        cache_key = self._target_cache_key(target)
        now = time.monotonic()
        cached_entry = self._docker_config_cache.get(cache_key)
        if cached_entry is not None:
            expires_at, cached_payload = cached_entry
            if now < expires_at:
                return dict(cached_payload)

        try:
            _, config_data = self._load_service_config_document_locked(target)
        except Exception:
            self._docker_config_cache[cache_key] = (now + 2.0, {})
            return {}
        docker_block = config_data.get("docker")
        server_block = config_data.get("server")
        if not isinstance(docker_block, dict):
            docker_block = {}
        if not isinstance(server_block, dict):
            server_block = {}

        container_name = str(docker_block.get("container_name", "")).strip()
        resolved_container_name = self._resolve_docker_template_value(
            container_name,
            config_data=config_data,
            docker_block=docker_block,
        )

        payload = {
            "image": str(docker_block.get("image", "")).strip(),
            "container_name": resolved_container_name or container_name,
            "host": str(server_block.get("host", "")).strip(),
            "port": server_block.get("port"),
        }
        self._docker_config_cache[cache_key] = (now + DOCKER_CONFIG_CACHE_TTL_S, payload)
        return dict(payload)

    @staticmethod
    def _target_cache_key(target) -> str:
        if getattr(target, "is_remote", False):
            return (
                f"remote:{target.remote_user or ''}@{target.remote_host or ''}:"
                f"{int(target.remote_ssh_port or 22)}:{target.folder_path}"
            )
        return f"local:{target.folder_path}"

    def _resolve_status_container_fallback_locked(self, status) -> DockerContainerInfo | None:
        try:
            return self._resolve_console_container_locked(status.result, strict_config=False)
        except Exception:
            return None

    @staticmethod
    def _normalize_runtime_container_status(raw_status: str) -> str:
        status_text = str(raw_status or "").strip()
        lowered = status_text.lower()
        if lowered.startswith("up"):
            return "running"
        if lowered.startswith("exited"):
            return "ended"
        if lowered.startswith("created"):
            return "created"
        if lowered.startswith("restarting"):
            return "restarting"
        return status_text or "unknown"

    def log_payload(self, name: str, *, lines: int | None = None) -> dict[str, object]:
        with self._lock:
            result = self._resolve_result(name)
        if result is None:
            raise KeyError(f"Cannot find docker '{name}'.")

        tail_lines = lines if lines is not None else self._log_lines
        source, content = read_result_logs(
            result,
            tail_lines=tail_lines,
            preserve_ansi=True,
        )
        is_error = (source == "status") and bool(content.strip().lower().startswith("startup status: error"))
        return {
            "name": result.match.target.folder_name,
            "group": result.match.group_name or "ungrouped",
            "source": source,
            "lines": tail_lines,
            "session_name": result.tmux_session or "",
            "content": content,
            "html": ansi_to_html(content),
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "is_error": is_error,
        }

    def bridge_log_payload(
        self,
        name: str | None = None,
        *,
        lines: int | None = None,
    ) -> dict[str, object]:
        tail_lines = lines if lines is not None else self._log_lines
        with self._lock:
            bridge_name, bridge_manager = self._resolve_bridge_manager(name)
            bridge = self._bridge_payload_for_locked(bridge_name, bridge_manager)
            content = bridge_manager.read_logs(tail_lines)

        source = "file" if content else "status"
        if not content:
            content = str(bridge.get("message", "")).strip() or "No bridge logs available yet."

        return {
            "name": bridge_name,
            "source": source,
            "lines": tail_lines,
            "content": content,
            "html": ansi_to_html(content),
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "is_error": bridge.get("status") == "error",
            "status": bridge.get("status", "unknown"),
            "endpoint": bridge.get("endpoint", "unconfigured"),
            "config_path": bridge.get("config_path", ""),
            "log_path": bridge.get("log_path", ""),
        }

    def bridge_config_payload(self, name: str | None = None) -> dict[str, object]:
        with self._lock:
            bridge_name, bridge_manager = self._resolve_bridge_manager(name)
            bridge = self._bridge_payload_for_locked(bridge_name, bridge_manager)
            content = bridge_manager.read_config_text()

        return {
            "name": bridge_name,
            "config_path": bridge.get("config_path", ""),
            "content": content,
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "status": bridge.get("status", "unknown"),
            "message": bridge.get("message", ""),
        }

    def launcher_config_payload(self) -> dict[str, object]:
        with self._lock:
            payload = self._launch_config_manager.payload()
            content = self._launch_config_manager.read_config_text()
            structured = self._launch_config_manager.structured_payload()

        return {
            "config_path": payload.get("config_path", ""),
            "content": content,
            "structured": structured,
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "status": payload.get("status", "unknown"),
            "message": payload.get("message", ""),
            "docker_model_root": payload.get("docker_model_root", ""),
            "docker_count": payload.get("docker_count", 0),
            "bridge_count": payload.get("bridge_count", 0),
        }

    def zmq_test_schema_payload(self) -> dict[str, object]:
        with self._lock:
            settings = self._launch_config_manager.zmq_test_settings()
            endpoint_map = self._normalize_zmq_endpoint_map(settings.get("endpoints"))
            timeout_ms = _clamp_int(
                settings.get("timeout_ms"),
                default=ZMQ_TEST_TIMEOUT_MS_DEFAULT,
                minimum=ZMQ_TEST_TIMEOUT_MS_MIN,
                maximum=ZMQ_TEST_TIMEOUT_MS_MAX,
            )
            history_limit = _clamp_int(
                settings.get("history_limit"),
                default=ZMQ_TEST_HISTORY_LIMIT_DEFAULT,
                minimum=ZMQ_TEST_HISTORY_LIMIT_MIN,
                maximum=ZMQ_TEST_HISTORY_LIMIT_MAX,
            )
            self._apply_zmq_test_history_limit_locked(history_limit)

            dockers: list[dict[str, object]] = []
            for result in self._results:
                docker_name = result.match.target.folder_name
                request_format = self._load_request_format_for_target_locked(result.match.target)
                dockers.append(
                    {
                        "name": docker_name,
                        "group": result.match.group_name or "ungrouped",
                        "endpoint": self._resolve_zmq_endpoint_for_target_locked(
                            result.match.target,
                            endpoint_map,
                        )
                        or "",
                        "request_template": request_format.get("input_template"),
                        "expected_output_template": request_format.get("output_template"),
                        "input_schema": request_format.get("input_schema"),
                        "output_schema": request_format.get("output_schema"),
                        "request_input_path": request_format.get("input_path", ""),
                        "request_output_path": request_format.get("output_path", ""),
                        "request_format_note": request_format.get("note", ""),
                    }
                )
            dockers.sort(key=self._docker_sort_key)
            history = list(self._zmq_test_history)

        return {
            "dockers": dockers,
            "endpoints": endpoint_map,
            "timeout_ms": timeout_ms,
            "history_limit": history_limit,
            "history": history,
            "format_hint": (
                "Request body should be a JSON object. For bridge external_json mode, "
                "send {'request_id': '...', 'rgb_image': '<base64>', 'depth_image': '<base64>'}."
            ),
            "request_template": _default_zmq_test_request_payload(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }

    def zmq_test_history_payload(self, name: str | None = None) -> dict[str, object]:
        normalized_name = normalize_docker_name(name or "")
        with self._lock:
            if normalized_name:
                history = [
                    record
                    for record in self._zmq_test_history
                    if normalize_docker_name(str(record.get("docker_name", ""))) == normalized_name
                ]
            else:
                history = list(self._zmq_test_history)
        return {
            "history": history,
            "count": len(history),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }

    def generate_zmq_request_template(self, *, name: str) -> dict[str, object]:
        requested_name = str(name).strip()
        if not requested_name:
            raise ValueError("Docker name is required.")

        with self._lock:
            resolved_result = self._resolve_result(requested_name)
            resolved_match = self._resolve_match(requested_name)
            if resolved_result is None and resolved_match is None:
                raise KeyError(f"Cannot find docker '{requested_name}'.")

            docker_name = (
                resolved_result.match.target.folder_name
                if resolved_result is not None
                else resolved_match.target.folder_name
            )
            resolved_target = (
                resolved_result.match.target
                if resolved_result is not None
                else resolved_match.target
            )
            request_format = self._load_request_format_for_target_locked(resolved_target)

        template: dict[str, Any] | None = None
        schema_doc = request_format.get("input_schema")
        if isinstance(schema_doc, dict):
            template = _generate_random_payload_from_schema(schema_doc)

        if template is None:
            raw_template = request_format.get("input_template")
            if isinstance(raw_template, dict):
                template = json.loads(json.dumps(raw_template, ensure_ascii=False))

        if template is None:
            template = _default_zmq_test_request_payload()

        _refresh_zmq_request_defaults(template)
        message = (
            f"Generated random request for '{docker_name}' from JSON Schema."
            if isinstance(schema_doc, dict)
            else f"Loaded request template for '{docker_name}'."
        )
        return {
            "ok": True,
            "name": docker_name,
            "request_template": template,
            "message": message,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }

    def run_zmq_test(
        self,
        *,
        name: str,
        endpoint: str | None = None,
        timeout_ms: int | None = None,
        request_payload: Any = None,
    ) -> dict[str, object]:
        requested_name = str(name).strip()
        if not requested_name:
            raise ValueError("Docker name is required.")

        with self._lock:
            resolved_result = self._resolve_result(requested_name)
            resolved_match = self._resolve_match(requested_name)
            if resolved_result is None and resolved_match is None:
                raise KeyError(f"Cannot find docker '{requested_name}'.")

            docker_name = (
                resolved_result.match.target.folder_name
                if resolved_result is not None
                else resolved_match.target.folder_name
            )
            resolved_target = (
                resolved_result.match.target
                if resolved_result is not None
                else resolved_match.target
            )

            settings = self._launch_config_manager.zmq_test_settings()
            endpoint_map = self._normalize_zmq_endpoint_map(settings.get("endpoints"))
            default_endpoint = self._resolve_zmq_endpoint_for_target_locked(
                resolved_target,
                endpoint_map,
            )
            request_format = self._load_request_format_for_target_locked(resolved_target)
            default_timeout_ms = _clamp_int(
                settings.get("timeout_ms"),
                default=ZMQ_TEST_TIMEOUT_MS_DEFAULT,
                minimum=ZMQ_TEST_TIMEOUT_MS_MIN,
                maximum=ZMQ_TEST_TIMEOUT_MS_MAX,
            )
            history_limit = _clamp_int(
                settings.get("history_limit"),
                default=ZMQ_TEST_HISTORY_LIMIT_DEFAULT,
                minimum=ZMQ_TEST_HISTORY_LIMIT_MIN,
                maximum=ZMQ_TEST_HISTORY_LIMIT_MAX,
            )
            self._apply_zmq_test_history_limit_locked(history_limit)

        resolved_endpoint = str(endpoint or default_endpoint or "").strip()
        if not resolved_endpoint:
            raise ValueError(
                f"No ZMQ endpoint configured for '{docker_name}'. "
                "Set server.host/server.port in that docker's config.yaml or input endpoint manually."
            )

        resolved_timeout_ms = _clamp_int(
            timeout_ms,
            default=default_timeout_ms,
            minimum=ZMQ_TEST_TIMEOUT_MS_MIN,
            maximum=ZMQ_TEST_TIMEOUT_MS_MAX,
        )

        if request_payload is None:
            template_payload = request_format.get("input_template")
            if isinstance(template_payload, dict):
                request_obj = dict(template_payload)
            else:
                request_obj = _default_zmq_test_request_payload()
        elif isinstance(request_payload, str):
            raw_text = request_payload.strip()
            if not raw_text:
                template_payload = request_format.get("input_template")
                if isinstance(template_payload, dict):
                    request_obj = dict(template_payload)
                else:
                    request_obj = _default_zmq_test_request_payload()
            else:
                try:
                    parsed = json.loads(raw_text)
                except json.JSONDecodeError as exc:
                    raise ValueError("Request payload text must be valid JSON.") from exc
                if not isinstance(parsed, dict):
                    raise ValueError("Request payload JSON must be an object.")
                request_obj = dict(parsed)
        elif isinstance(request_payload, dict):
            request_obj = dict(request_payload)
        else:
            raise ValueError("Request payload must be a JSON object, JSON string, or null.")

        request_id = str(request_obj.get("request_id", "")).strip()
        if not request_id:
            request_id = str(uuid4())
            request_obj["request_id"] = request_id

        started_at = datetime.now(timezone.utc).isoformat()
        request_pretty = json.dumps(request_obj, ensure_ascii=False, indent=2)
        run_start = time.perf_counter()
        ok = False
        error_text: str | None = None
        response_obj: Any | None = None
        response_text = ""
        elapsed_ms = 0.0

        try:
            response_obj, response_text, elapsed_ms = _execute_zmq_json_request(
                endpoint=resolved_endpoint,
                request_obj=request_obj,
                timeout_ms=resolved_timeout_ms,
            )
            ok = True
        except Exception as exc:
            elapsed_ms = (time.perf_counter() - run_start) * 1000.0
            error_text = str(exc)

        if response_obj is not None:
            response_pretty = json.dumps(response_obj, ensure_ascii=False, indent=2)
        else:
            response_pretty = response_text

        record = {
            "id": str(uuid4()),
            "docker_name": docker_name,
            "endpoint": resolved_endpoint,
            "request_id": request_id,
            "timeout_ms": resolved_timeout_ms,
            "started_at": started_at,
            "elapsed_ms": round(elapsed_ms, 2),
            "status": "ok" if ok else "error",
            "request_json": request_obj,
            "request_text": request_pretty,
            "response_json": response_obj,
            "response_text": response_pretty,
            "error": error_text or "",
        }

        with self._lock:
            self._zmq_test_history.appendleft(record)
            history = list(self._zmq_test_history)

        if ok:
            message = (
                f"ZMQ test succeeded for '{docker_name}' "
                f"(request_id={request_id}, elapsed={record['elapsed_ms']} ms)."
            )
        else:
            message = f"ZMQ test failed for '{docker_name}': {error_text}"

        return {
            "ok": ok,
            "message": message,
            "record": record,
            "history": history,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }

    def save_launcher_config(
        self,
        content: str,
        *,
        restart: bool = False,
    ) -> dict[str, object]:
        with self._lock:
            self._launch_config_manager.save_config_text(content)
            message = "Saved docker launcher config."
            if restart:
                reload_message = self._reload_launcher_state_locked()
                message = f"{message} {reload_message}".strip()

            return {
                "ok": True,
                "message": message,
                "config": self.launcher_config_payload(),
                "status": self.status_payload(),
            }

    def save_launcher_structured(
        self,
        structured: dict[str, object],
        *,
        restart: bool = False,
    ) -> dict[str, object]:
        with self._lock:
            self._launch_config_manager.save_structured(structured)
            message = "Saved launcher configuration."
            if restart:
                reload_message = self._reload_launcher_state_locked()
                message = f"{message} {reload_message}".strip()

            return {
                "ok": True,
                "message": message,
                "config": self.launcher_config_payload(),
                "status": self.status_payload(),
            }

    def reload_launcher_config(self) -> dict[str, object]:
        with self._lock:
            message = self._reload_launcher_state_locked()
            return {
                "ok": True,
                "message": message,
                "config": self.launcher_config_payload(),
                "status": self.status_payload(),
            }

    def update_docker_connection(
        self,
        *,
        name: str,
        location: str,
        docker_model_root: str | None,
        remote_host: str | None,
        remote_user: str | None,
        remote_docker_model_root: str | None,
        remote_ssh_port: int | None,
        remote_password: str | None,
    ) -> dict[str, object]:
        with self._lock:
            if self._resolve_match(name) is None and self._resolve_result(name) is None:
                raise KeyError(f"Cannot find docker '{name}'.")
            self._launch_config_manager.update_docker_connection(
                name=name,
                location=location,
                docker_model_root=docker_model_root,
                remote_host=remote_host,
                remote_user=remote_user,
                remote_docker_model_root=remote_docker_model_root,
                remote_ssh_port=remote_ssh_port,
                remote_password=remote_password,
                matches=self._results,
            )
            reload_message = self._reload_launcher_state_locked()
            return {
                "ok": True,
                "message": f"Saved connection for '{name}'. {reload_message}".strip(),
                "config": self.launcher_config_payload(),
                "status": self.status_payload(),
            }

    def save_bridge_config(
        self,
        name: str | None,
        content: str,
        *,
        restart: bool = False,
    ) -> dict[str, object]:
        with self._lock:
            bridge_name, bridge_manager = self._resolve_bridge_manager(name)
            bridge_manager.save_config_text(content)
            message = f"Saved config for '{bridge_name}'."
            bridge_response: dict[str, object] | None = None
            if restart:
                bridge_response = bridge_manager.restart()
                message = f"{message} {bridge_response['message']}".strip()

            response = {
                "ok": True,
                "message": message,
                "bridge_name": bridge_name,
                "config": self.bridge_config_payload(bridge_name),
                "status": self.status_payload(),
            }
            if bridge_response is not None:
                response["bridge"] = bridge_response.get("bridge")
            return response

    def start_docker(self, name: str) -> dict[str, object]:
        with self._lock:
            match = self._resolve_match(name)
            if match is None:
                raise KeyError(f"Cannot find docker '{name}'.")

            current_result = self._resolve_result(name)
            current_status = (
                self._current_status_for_result(current_result)
                if current_result is not None
                else None
            )
            if current_status is not None and current_status.overall_status == "running":
                return {
                    "ok": True,
                    "message": f"Docker '{match.target.folder_name}' is already running.",
                    "status": self.status_payload(),
                }

            new_result = launch_single_match(match, use_tmux=True, replace_session=True)
            self._upsert_result(new_result)
            if not new_result.succeeded:
                detail = (new_result.startup_output or "").strip()
                message = f"Failed to start '{match.target.folder_name}'."
                if detail:
                    message = f"{message} {detail}"
                return {
                    "ok": False,
                    "message": message,
                    "status": self.status_payload(),
                }
            return {
                "ok": True,
                "message": f"Start command sent for '{match.target.folder_name}'.",
                "status": self.status_payload(),
            }

    def stop_docker(self, name: str) -> dict[str, object]:
        with self._lock:
            result = self._resolve_result(name)
            if result is None:
                match = self._resolve_match(name)
                if match is None:
                    raise KeyError(f"Cannot find docker '{name}'.")
                result = DockerLaunchResult(
                    match=match,
                    return_code=0,
                    tmux_session=match.target.folder_name,
                    reused_existing=True,
                )
                self._upsert_result(result)

            ok, message = stop_launch_result(result)
            self._replace_result(
                DockerLaunchResult(
                    match=result.match,
                    return_code=0,
                    tmux_session=result.tmux_session,
                    reused_existing=True,
                    dry_run=result.dry_run,
                )
            )
            return {
                "ok": ok,
                "message": message,
                "status": self.status_payload(),
            }

    def restart_docker(self, name: str) -> dict[str, object]:
        with self._lock:
            match = self._resolve_match(name)
            if match is None:
                raise KeyError(f"Cannot find docker '{name}'.")

            existing_result = self._resolve_result(name)
            stop_message = ""
            if existing_result is not None:
                _, stop_message = stop_launch_result(existing_result)
                self._replace_result(
                    DockerLaunchResult(
                        match=existing_result.match,
                        return_code=0,
                        tmux_session=existing_result.tmux_session,
                        reused_existing=True,
                        dry_run=existing_result.dry_run,
                    )
                )

            new_result = launch_single_match(match, use_tmux=True, replace_session=True)
            self._upsert_result(new_result)
            if not new_result.succeeded:
                detail = (new_result.startup_output or "").strip()
                combined = f"Failed to restart '{match.target.folder_name}'."
                if stop_message:
                    combined += f" {stop_message}"
                if detail:
                    combined += f" {detail}"
                return {
                    "ok": False,
                    "message": combined.strip(),
                    "status": self.status_payload(),
                }
            combined = f"Restarted '{match.target.folder_name}'."
            if stop_message:
                combined += f" {stop_message}"
            return {
                "ok": True,
                "message": combined,
                "status": self.status_payload(),
            }

    def docker_service_config_payload(self, name: str) -> dict[str, object]:
        with self._lock:
            target = self._resolve_target_for_name_locked(name)
            config_path, config_data = self._load_service_config_document_locked(target)
            docker_block = config_data.get("docker", {})
            server_block = config_data.get("server", {})
            container_name = str(
                docker_block.get("container_name")
                or docker_block.get("name")
                or ""
            ).strip()
            host = str(server_block.get("host", "")).strip() or DOCKER_SERVICE_DEFAULT_HOST
            raw_port = server_block.get("port")
            port: int | None = None
            if raw_port not in {None, ""}:
                try:
                    port = int(raw_port)
                except (TypeError, ValueError):
                    port = None

        return {
            "ok": True,
            "name": target.folder_name,
            "location": "remote" if target.is_remote else "local",
            "config_path": str(config_path),
            "container_name": container_name,
            "host": host,
            "port": port,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }

    def save_docker_service_config(
        self,
        name: str,
        *,
        host: str,
        port: int,
        container_name: str | None = None,
        restart: bool = False,
    ) -> dict[str, object]:
        host_value = str(host).strip()
        if not host_value:
            raise ValueError("Host cannot be empty.")
        if port <= 0 or port > 65535:
            raise ValueError("Port must be between 1 and 65535.")

        container_value = str(container_name or "").strip()
        with self._lock:
            target = self._resolve_target_for_name_locked(name)
            config_path, config_data = self._load_service_config_document_locked(target)
            docker_block = config_data.get("docker")
            if not isinstance(docker_block, dict):
                docker_block = {}
                config_data["docker"] = docker_block
            server_block = config_data.get("server")
            if not isinstance(server_block, dict):
                server_block = {}
                config_data["server"] = server_block

            if container_value:
                docker_block["container_name"] = container_value
                if "name" in docker_block:
                    docker_block["name"] = container_value
            elif "container_name" not in docker_block:
                docker_block["container_name"] = target.folder_name

            server_block["host"] = host_value
            server_block["port"] = int(port)

            serialized = yaml.safe_dump(
                config_data,
                allow_unicode=True,
                sort_keys=False,
            )
            self._write_service_config_text_locked(target, config_path, serialized)
            self._docker_config_cache.pop(self._target_cache_key(target), None)

            updated_payload = {
                "ok": True,
                "name": target.folder_name,
                "location": "remote" if target.is_remote else "local",
                "config_path": str(config_path),
                "container_name": str(docker_block.get("container_name", "")).strip(),
                "host": str(server_block.get("host", "")).strip(),
                "port": int(server_block.get("port", 0)),
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }

        message = f"Saved service config for '{name}'."
        status_payload = self.status_payload()
        restart_response: dict[str, object] | None = None
        if restart:
            restart_response = self.restart_docker(name)
            status_payload = restart_response.get("status", status_payload)
            restart_message = str(restart_response.get("message", "")).strip()
            if restart_message:
                message = f"{message} {restart_message}".strip()

        response = {
            "ok": True,
            "message": message,
            "config": updated_payload,
            "status": status_payload,
        }
        if restart_response is not None:
            response["restart"] = restart_response
        return response

    def open_docker_terminal(self, name: str) -> dict[str, object]:
        with self._lock:
            result = self._resolve_result(name)
            if result is None:
                raise KeyError(f"Cannot find docker '{name}'.")
            container_info = self._resolve_console_container_locked(result)
            target = result.match.target
            shell_hint = self._build_shell_hint_locked(target, container_info)

        launch_message = self._spawn_terminal_process(shell_hint)
        return {
            "ok": True,
            "name": result.match.target.folder_name,
            "container_name": container_info.name,
            "container_id": container_info.container_id,
            "location": "remote" if target.is_remote else "local",
            "shell_hint": shell_hint,
            "message": launch_message,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }

    def docker_console_meta(self, name: str) -> dict[str, object]:
        with self._lock:
            result = self._resolve_result(name)
            if result is None:
                raise KeyError(f"Cannot find docker '{name}'.")
            container_info = self._resolve_console_container_locked(result)
            target = result.match.target
            shell_hint = self._build_shell_hint_locked(target, container_info)

        location = "remote" if target.is_remote else "local"
        return {
            "ok": True,
            "name": result.match.target.folder_name,
            "location": location,
            "container_name": container_info.name,
            "container_id": container_info.container_id,
            "shell_hint": shell_hint,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }

    def docker_console_exec(
        self,
        name: str,
        command: str,
        *,
        timeout_ms: int | None = None,
    ) -> dict[str, object]:
        normalized_command = command.strip()
        if not normalized_command:
            raise ValueError("Console command cannot be empty.")

        timeout_value = _clamp_int(
            timeout_ms,
            default=DOCKER_CONSOLE_TIMEOUT_MS_DEFAULT,
            minimum=DOCKER_CONSOLE_TIMEOUT_MS_MIN,
            maximum=DOCKER_CONSOLE_TIMEOUT_MS_MAX,
        )

        with self._lock:
            result = self._resolve_result(name)
            if result is None:
                raise KeyError(f"Cannot find docker '{name}'.")
            container_info = self._resolve_console_container_locked(result)
            target = result.match.target

        started_at = time.perf_counter()
        try:
            if target.is_remote:
                remote_inner = (
                    f"docker exec -i {shlex.quote(container_info.container_id)} "
                    f"sh -lc {shlex.quote(normalized_command)}"
                )
                completed = subprocess.run(
                    self._build_remote_ssh_command(target, remote_inner),
                    check=False,
                    capture_output=True,
                    text=True,
                    timeout=timeout_value / 1000.0,
                )
            else:
                docker_path = shutil.which("docker")
                if not docker_path:
                    raise RuntimeError("docker is not installed or not available in PATH.")
                completed = subprocess.run(
                    [
                        docker_path,
                        "exec",
                        "-i",
                        container_info.container_id,
                        "sh",
                        "-lc",
                        normalized_command,
                    ],
                    check=False,
                    capture_output=True,
                    text=True,
                    timeout=timeout_value / 1000.0,
                )
        except subprocess.TimeoutExpired as exc:
            elapsed_ms = (time.perf_counter() - started_at) * 1000.0
            partial_stdout = (exc.stdout or "").strip() if isinstance(exc.stdout, str) else ""
            partial_stderr = (exc.stderr or "").strip() if isinstance(exc.stderr, str) else ""
            partial_output = "\n".join(part for part in [partial_stdout, partial_stderr] if part).strip()
            timeout_message = (
                f"Console command timed out after {timeout_value} ms."
                + (f"\n{partial_output}" if partial_output else "")
            )
            return {
                "ok": False,
                "name": result.match.target.folder_name,
                "location": "remote" if target.is_remote else "local",
                "container_name": container_info.name,
                "container_id": container_info.container_id,
                "command": normalized_command,
                "exit_code": None,
                "timed_out": True,
                "elapsed_ms": elapsed_ms,
                "output": timeout_message,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }

        elapsed_ms = (time.perf_counter() - started_at) * 1000.0
        stdout = (completed.stdout or "").rstrip()
        stderr = (completed.stderr or "").rstrip()
        output_text = "\n".join(part for part in [stdout, stderr] if part).strip()
        if not output_text:
            output_text = (
                f"Command finished with exit code {completed.returncode} "
                f"(no stdout/stderr output)."
            )

        return {
            "ok": completed.returncode == 0,
            "name": result.match.target.folder_name,
            "location": "remote" if target.is_remote else "local",
            "container_name": container_info.name,
            "container_id": container_info.container_id,
            "command": normalized_command,
            "exit_code": completed.returncode,
            "timed_out": False,
            "elapsed_ms": elapsed_ms,
            "output": output_text,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }

    def start_bridge(self, name: str | None = None) -> dict[str, object]:
        with self._lock:
            bridge_name, bridge_manager = self._resolve_bridge_manager(name)
            response = bridge_manager.start()
            response["bridge_name"] = bridge_name
            response["status"] = self.status_payload()
            return response

    def stop_bridge(self, name: str | None = None) -> dict[str, object]:
        with self._lock:
            bridge_name, bridge_manager = self._resolve_bridge_manager(name)
            response = bridge_manager.stop()
            response["bridge_name"] = bridge_name
            response["status"] = self.status_payload()
            return response

    def restart_bridge(self, name: str | None = None) -> dict[str, object]:
        with self._lock:
            bridge_name, bridge_manager = self._resolve_bridge_manager(name)
            response = bridge_manager.restart()
            response["bridge_name"] = bridge_name
            response["status"] = self.status_payload()
            return response

    def shutdown(self) -> None:
        with self._lock:
            for key in self._bridge_order:
                self._bridge_lookup[key].shutdown()

    def _reload_launcher_state_locked(self) -> str:
        launch_config = self._launch_config_manager.load_config()
        if launch_config is None:
            raise RuntimeError("Docker launcher config is missing, cannot reload dashboard state.")

        # Keep the injected $TJFUSION_MODE in sync with the (possibly edited)
        # camera_mode so dockers started after a reload come up in the new mode.
        set_launch_env(launch_config.camera_mode)
        matches = self._resolve_matches_from_launch_config(launch_config)
        self._replace_matches_locked(matches)
        self._reconfigure_bridge_managers_locked(launch_config.bridge_entries)
        self._docker_config_cache.clear()
        self._launch_config_manager.set_message(
            f"Launcher config reloaded for {len(matches)} docker(s) and {len(launch_config.bridge_entries)} bridge(s)."
        )
        return "Launcher config reloaded into the dashboard."

    def _index_result(self, result: DockerLaunchResult) -> None:
        for raw_name in (
            result.match.target.folder_name,
            result.match.target.relative_folder,
            result.match.requested_name,
            result.tmux_session or "",
        ):
            normalized = normalize_docker_name(raw_name)
            if normalized and normalized not in self._result_lookup:
                self._result_lookup[normalized] = result

    def _index_match(self, match: DockerMatch) -> None:
        for raw_name in (
            match.target.folder_name,
            match.target.relative_folder,
            match.requested_name,
        ):
            normalized = normalize_docker_name(raw_name)
            if normalized and normalized not in self._match_lookup:
                self._match_lookup[normalized] = match

    def _resolve_result(self, name: str) -> DockerLaunchResult | None:
        return self._result_lookup.get(normalize_docker_name(name))

    def _resolve_match(self, name: str) -> DockerMatch | None:
        return self._match_lookup.get(normalize_docker_name(name))

    def _resolve_target_for_name_locked(self, name: str):
        result = self._resolve_result(name)
        if result is not None:
            return result.match.target
        match = self._resolve_match(name)
        if match is not None:
            return match.target
        raise KeyError(f"Cannot find docker '{name}'.")

    def _load_service_config_document_locked(
        self,
        target,
    ) -> tuple[Path | str, dict[str, Any]]:
        if target.is_remote:
            config_path = self._discover_service_config_path_remote_locked(target)
            if config_path is None:
                raise RuntimeError(
                    f"No YAML file with docker.container_name and server.host/port was found under remote folder '{target.folder_path}'."
                )
            raw_text = self._read_remote_text_locked(target, config_path)
            try:
                parsed = yaml.safe_load(raw_text) if raw_text.strip() else {}
            except Exception as exc:
                raise RuntimeError(f"Failed to parse remote YAML file '{config_path}': {exc}") from exc
            if not isinstance(parsed, dict):
                raise RuntimeError(f"Remote YAML file '{config_path}' must be a mapping object.")
            return config_path, parsed

        config_path = self._discover_service_config_path_local_locked(target)
        if config_path is None:
            raise RuntimeError(
                f"No YAML file with docker.container_name and server.host/port was found under '{target.folder_path}'."
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

    def _discover_service_config_path_local_locked(self, target) -> Path | None:
        folder = Path(target.folder_path)
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
        selected = self._select_best_service_config_candidate(candidates)
        return selected[0] if selected is not None else None

    def _discover_service_config_path_remote_locked(self, target) -> str | None:
        folder_text = str(target.folder_path)
        preferred_remote = str(PurePosixPath(folder_text) / "config.yaml")
        try:
            self._read_remote_text_locked(target, preferred_remote)
            return preferred_remote
        except Exception:
            pass
        list_command = (
            f"find {shlex.quote(folder_text)} -maxdepth 4 -type f "
            "\\( -name '*.yaml' -o -name '*.yml' \\) | sort"
        )
        listed = subprocess.run(
            self._build_remote_ssh_command(target, list_command),
            check=False,
            capture_output=True,
            text=True,
        )
        if listed.returncode != 0:
            detail = listed.stderr.strip() or listed.stdout.strip() or f"exit code {listed.returncode}"
            raise RuntimeError(
                f"Failed to scan remote YAML files under '{folder_text}': {detail}"
            )
        candidates: list[tuple[str, dict[str, Any]]] = []
        for raw_line in listed.stdout.splitlines():
            candidate_path = raw_line.strip()
            if not candidate_path:
                continue
            try:
                text = self._read_remote_text_locked(target, candidate_path)
                data = yaml.safe_load(text) if text.strip() else {}
            except Exception:
                continue
            if isinstance(data, dict):
                candidates.append((candidate_path, data))
        selected = self._select_best_service_config_candidate(candidates)
        return str(selected[0]) if selected is not None else None

    @staticmethod
    def _select_best_service_config_candidate(
        candidates: list[tuple[Any, dict[str, Any]]],
    ) -> tuple[Any, dict[str, Any]] | None:
        if not candidates:
            return None

        def score(item: tuple[Any, dict[str, Any]]) -> tuple[int, int, str]:
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

            depth = path_text.count("/")
            return total + name_bonus, -depth, path_text

        ranked = sorted(candidates, key=score, reverse=True)
        best_path, best_data = ranked[0]
        best_score = score((best_path, best_data))[0]
        if best_score <= 0:
            return None
        return best_path, best_data

    def _read_remote_text_locked(self, target, remote_path: str) -> str:
        read_command = f"cat {shlex.quote(remote_path)}"
        try:
            read_result = subprocess.run(
                self._build_remote_ssh_command(target, read_command),
                check=False,
                capture_output=True,
                text=True,
                timeout=STATUS_SUBPROCESS_TIMEOUT_S,
            )
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError(
                f"Timed out reading remote file '{remote_path}' on {self._remote_target_label(target)}."
            ) from exc
        if read_result.returncode != 0:
            detail = read_result.stderr.strip() or read_result.stdout.strip() or f"exit code {read_result.returncode}"
            raise RuntimeError(
                f"Failed to read remote file '{remote_path}' on {self._remote_target_label(target)}: {detail}"
            )
        return read_result.stdout

    def _write_service_config_text_locked(
        self,
        target,
        config_path: Path | str,
        content: str,
    ) -> None:
        if target.is_remote:
            self._write_remote_text_locked(target, str(config_path), content)
            return
        local_path = Path(config_path)
        local_path.parent.mkdir(parents=True, exist_ok=True)
        local_path.write_text(content, encoding="utf-8")

    def _write_remote_text_locked(self, target, remote_path: str, content: str) -> None:
        encoded = base64.b64encode(content.encode("utf-8")).decode("ascii")
        write_script = shlex.quote(
            "import base64, pathlib;"
            f"path = pathlib.Path({remote_path!r});"
            "path.parent.mkdir(parents=True, exist_ok=True);"
            f"path.write_text(base64.b64decode({encoded!r}).decode('utf-8'), encoding='utf-8')"
        )
        remote_command = (
            f"(python3 -c {write_script}) || (python -c {write_script})"
        )
        written = subprocess.run(
            self._build_remote_ssh_command(target, remote_command),
            check=False,
            capture_output=True,
            text=True,
        )
        if written.returncode != 0:
            detail = written.stderr.strip() or written.stdout.strip() or f"exit code {written.returncode}"
            raise RuntimeError(
                f"Failed to write remote file '{remote_path}' on {self._remote_target_label(target)}: {detail}"
            )

    def _resolve_console_container_locked(
        self,
        result: DockerLaunchResult,
        *,
        strict_config: bool = True,
    ) -> DockerContainerInfo:
        remote_containers: list[DockerContainerInfo] | None = None
        local_containers: list[DockerContainerInfo] | None = None
        configured_container_candidates = self._configured_container_candidates_for_target_locked(
            result.match.target
        )
        configured_primary = configured_container_candidates[0] if configured_container_candidates else ""
        for configured_name in configured_container_candidates:
            if result.match.target.is_remote:
                if remote_containers is None:
                    remote_containers = self._list_remote_containers_locked(result.match.target)
                matched_remote = self._find_container_by_name(
                    remote_containers,
                    configured_name,
                    allow_fuzzy=False,
                )
                if matched_remote is None:
                    matched_remote = self._find_container_by_name(
                        remote_containers,
                        configured_name,
                        allow_fuzzy=True,
                    )
                if matched_remote is not None:
                    return matched_remote
            else:
                if local_containers is None:
                    local_containers = list(_list_docker_containers().values())
                local_container = self._find_container_by_name(
                    local_containers,
                    configured_name,
                    allow_fuzzy=False,
                )
                if local_container is None:
                    local_container = self._find_container_by_name(
                        local_containers,
                        configured_name,
                        allow_fuzzy=True,
                    )
                if local_container is not None:
                    return local_container

        if configured_primary and strict_config:
            available_names: list[str] = []
            if result.match.target.is_remote:
                if remote_containers is None:
                    remote_containers = self._list_remote_containers_locked(result.match.target)
                available_names = [item.name for item in remote_containers]
            else:
                if local_containers is None:
                    local_containers = list(_list_docker_containers().values())
                available_names = [item.name for item in local_containers]

            preview = ", ".join(available_names[:8]) if available_names else "none"
            raise RuntimeError(
                "Cannot find container by configured docker.container_name "
                f"'{configured_primary}' for '{result.match.target.folder_name}'. "
                f"Currently available containers: {preview}."
            )

        if result.match.target.is_remote:
            if remote_containers is None:
                remote_containers = self._list_remote_containers_locked(result.match.target)
            container = self._select_container_from_listing(result, remote_containers)
        else:
            container = resolve_preferred_container(result)
        if container is None:
            raise RuntimeError(
                f"Cannot find a runnable container for '{result.match.target.folder_name}'. "
                "Please start docker first."
        )
        return container

    def _configured_container_candidates_for_target_locked(self, target) -> list[str]:
        try:
            _, config_data = self._load_service_config_document_locked(target)
        except Exception:
            return []
        docker_block = config_data.get("docker")
        if not isinstance(docker_block, dict):
            return []

        candidates: list[str] = []

        # First priority: docker.container_name (supports template like ${image}_tmp).
        container_name_raw = str(docker_block.get("container_name", "")).strip()
        container_name_resolved = self._resolve_docker_template_value(
            container_name_raw,
            config_data=config_data,
            docker_block=docker_block,
        )
        for value in (container_name_resolved, container_name_raw):
            if value and value not in candidates:
                candidates.append(value)

        # Fallback only when container_name is not configured.
        if not candidates:
            name_raw = str(docker_block.get("name", "")).strip()
            name_resolved = self._resolve_docker_template_value(
                name_raw,
                config_data=config_data,
                docker_block=docker_block,
            )
            for value in (name_resolved, name_raw):
                if value and value not in candidates:
                    candidates.append(value)
        return candidates

    @classmethod
    def _resolve_docker_template_value(
        cls,
        raw_value: str,
        *,
        config_data: dict[str, Any],
        docker_block: dict[str, Any],
    ) -> str:
        value = str(raw_value or "").strip()
        if not value:
            return ""
        if "${" not in value:
            return value

        def replace_var(match: re.Match[str]) -> str:
            token = match.group(1).strip()
            replacement = cls._lookup_template_token(
                token,
                config_data=config_data,
                docker_block=docker_block,
            )
            if replacement is None:
                return match.group(0)
            return replacement

        return DOCKER_TEMPLATE_VAR_RE.sub(replace_var, value).strip()

    @staticmethod
    def _lookup_template_token(
        token: str,
        *,
        config_data: dict[str, Any],
        docker_block: dict[str, Any],
    ) -> str | None:
        if not token:
            return None
        path_parts = [part.strip() for part in token.split(".") if part.strip()]
        if not path_parts:
            return None

        def walk(source: Any, parts: list[str]) -> Any:
            current = source
            for part in parts:
                if not isinstance(current, dict) or part not in current:
                    return None
                current = current[part]
            return current

        candidate_values: list[Any] = []
        if len(path_parts) == 1:
            key = path_parts[0]
            candidate_values.append(docker_block.get(key))
            candidate_values.append(config_data.get(key))
        candidate_values.append(walk(config_data, path_parts))

        for value in candidate_values:
            if value is None:
                continue
            if isinstance(value, (str, int, float, bool)):
                return str(value)
        return None

    @staticmethod
    def _find_container_by_name(
        containers: list[DockerContainerInfo],
        container_name: str,
        *,
        allow_fuzzy: bool = True,
    ) -> DockerContainerInfo | None:
        normalized_target = normalize_docker_name(container_name)
        if not normalized_target:
            return None
        exact = [
            info
            for info in containers
            if normalize_docker_name(info.name) == normalized_target
        ]
        if exact:
            return next((info for info in exact if info.status.lower().startswith("up")), exact[0])
        if not allow_fuzzy:
            return None
        fuzzy = [
            info
            for info in containers
            if normalized_target in normalize_docker_name(info.name)
        ]
        if fuzzy:
            return next((info for info in fuzzy if info.status.lower().startswith("up")), fuzzy[0])
        return None

    @staticmethod
    def _find_local_container_by_name(container_name: str) -> DockerContainerInfo | None:
        try:
            containers_by_id = _list_docker_containers()
        except Exception:
            return None
        return DashboardController._find_container_by_name(list(containers_by_id.values()), container_name)

    def _list_remote_containers_locked(self, target) -> list[DockerContainerInfo]:
        remote_command = (
            "docker ps -a --no-trunc "
            "--format '{{.ID}}\\t{{.Names}}\\t{{.Status}}\\t{{.Image}}\\t{{.Ports}}'"
        )
        try:
            listed = subprocess.run(
                self._build_remote_ssh_command(target, remote_command),
                check=False,
                capture_output=True,
                text=True,
                timeout=STATUS_SUBPROCESS_TIMEOUT_S,
            )
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError(
                f"Timed out listing remote containers on {self._remote_target_label(target)}."
            ) from exc
        if listed.returncode != 0:
            detail = (listed.stderr.strip() or listed.stdout.strip() or f"exit code {listed.returncode}")
            raise RuntimeError(
                f"Failed to list remote containers on {self._remote_target_label(target)}: {detail}"
            )
        return self._parse_container_listing(listed.stdout)

    @staticmethod
    def _parse_container_listing(raw_text: str) -> list[DockerContainerInfo]:
        containers: list[DockerContainerInfo] = []
        for raw_line in raw_text.splitlines():
            line = raw_line.strip()
            if not line:
                continue
            parts = line.split("\t")
            if len(parts) < 3:
                continue
            image = ""
            ports = ""
            if len(parts) >= 5:
                image = parts[3].strip()
                ports = parts[4].strip()
            elif len(parts) >= 4:
                ports = parts[3].strip()
            containers.append(
                DockerContainerInfo(
                    container_id=parts[0].strip(),
                    name=parts[1].strip(),
                    status=parts[2].strip(),
                    image=image,
                    ports=ports,
                )
            )
        return containers

    @staticmethod
    def _select_container_from_listing(
        result: DockerLaunchResult,
        containers: list[DockerContainerInfo],
    ) -> DockerContainerInfo | None:
        aliases = {
            normalize_docker_name(result.match.target.folder_name),
            normalize_docker_name(result.match.target.relative_folder),
            normalize_docker_name(result.match.requested_name),
            normalize_docker_name(result.tmux_session or ""),
        }
        aliases = {alias for alias in aliases if alias}
        if not aliases:
            return None

        matched: list[DockerContainerInfo] = []
        for info in containers:
            normalized_name = normalize_docker_name(info.name)
            if any(
                normalized_name == alias
                or normalized_name.startswith(alias)
                or alias.startswith(normalized_name)
                or alias in normalized_name
                for alias in aliases
            ):
                matched.append(info)
        if not matched:
            return None

        return next(
            (info for info in matched if info.status.lower().startswith("up")),
            matched[0],
        )

    @staticmethod
    def _remote_target_label(target) -> str:
        if target.remote_user:
            return f"{target.remote_user}@{target.remote_host}:{target.remote_ssh_port}"
        return f"{target.remote_host}:{target.remote_ssh_port}"

    @staticmethod
    def _build_remote_ssh_command(target, remote_command: str) -> list[str]:
        if not target.remote_host:
            raise ValueError("Remote command requested without remote host configuration.")

        remote_password = str(getattr(target, "remote_password", "") or "").strip()
        batch_mode = "no" if remote_password else "yes"
        endpoint = f"{target.remote_user}@{target.remote_host}" if target.remote_user else target.remote_host
        command = [
            "ssh",
            "-p",
            str(int(target.remote_ssh_port or 22)),
            "-o",
            "ConnectTimeout=5",
            "-o",
            f"BatchMode={batch_mode}",
            "-o",
            "ServerAliveInterval=30",
            "-o",
            "ServerAliveCountMax=3",
            endpoint,
            "bash",
            "--noprofile",
            "--norc",
            "-c",
            remote_command,
        ]
        if remote_password:
            sshpass_path = shutil.which("sshpass")
            if not sshpass_path:
                raise RuntimeError(
                    "sshpass is required when remote_password is configured. "
                    "Please install sshpass on this machine."
                )
            command = [
                sshpass_path,
                "-p",
                remote_password,
                *command,
            ]
        return command

    @staticmethod
    def _build_shell_hint_locked(target, container: DockerContainerInfo) -> str:
        shell_fallback = "if command -v bash >/dev/null 2>&1; then exec bash; else exec sh; fi"
        if target.is_remote:
            endpoint = f"{target.remote_user}@{target.remote_host}" if target.remote_user else target.remote_host
            return (
                f"ssh -p {int(target.remote_ssh_port or 22)} {endpoint} "
                f"\"docker exec -it {container.container_id} sh -lc {shlex.quote(shell_fallback)}\""
            )
        return (
            f"docker exec -it {container.container_id} "
            f"sh -lc {shlex.quote(shell_fallback)}"
        )

    @staticmethod
    def _spawn_terminal_process(command_text: str) -> str:
        if not command_text.strip():
            raise RuntimeError("Terminal command is empty.")

        if sys.platform == "darwin":
            escaped_command = command_text.replace("\\", "\\\\").replace('"', '\\"')
            started = subprocess.run(
                [
                    "osascript",
                    "-e",
                    'tell application "Terminal" to activate',
                    "-e",
                    f'tell application "Terminal" to do script "{escaped_command}"',
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            if started.returncode != 0:
                detail = started.stderr.strip() or started.stdout.strip() or f"exit code {started.returncode}"
                raise RuntimeError(f"Failed to open macOS Terminal: {detail}")
            return "Opened terminal window and attached into docker shell."

        shell_command = f"{command_text}; exec bash"
        terminal_candidates: list[tuple[str, list[str]]] = []

        # Prefer Ubuntu default terminal launcher first.
        xterm_emulator = shutil.which("x-terminal-emulator")
        if xterm_emulator:
            terminal_candidates.append(
                (
                    "x-terminal-emulator",
                    [xterm_emulator, "-e", f"bash -lc {shlex.quote(shell_command)}"],
                )
            )
        gnome_path = shutil.which("gnome-terminal")
        if gnome_path:
            terminal_candidates.append(
                ("gnome-terminal", [gnome_path, "--", "bash", "-lc", shell_command])
            )
        kgx_path = shutil.which("kgx")
        if kgx_path:
            terminal_candidates.append(
                ("kgx", [kgx_path, "--", "bash", "-lc", shell_command])
            )
        konsole_path = shutil.which("konsole")
        if konsole_path:
            terminal_candidates.append(
                ("konsole", [konsole_path, "-e", "bash", "-lc", shell_command])
            )
        xfce_path = shutil.which("xfce4-terminal")
        if xfce_path:
            terminal_candidates.append(
                ("xfce4-terminal", [xfce_path, "--command", f"bash -lc {shlex.quote(shell_command)}"])
            )
        mate_path = shutil.which("mate-terminal")
        if mate_path:
            terminal_candidates.append(
                ("mate-terminal", [mate_path, "--", "bash", "-lc", shell_command])
            )
        terminator_path = shutil.which("terminator")
        if terminator_path:
            terminal_candidates.append(
                ("terminator", [terminator_path, "-x", "bash", "-lc", shell_command])
            )
        tilix_path = shutil.which("tilix")
        if tilix_path:
            terminal_candidates.append(
                ("tilix", [tilix_path, "--", "bash", "-lc", shell_command])
            )
        kitty_path = shutil.which("kitty")
        if kitty_path:
            terminal_candidates.append(
                ("kitty", [kitty_path, "bash", "-lc", shell_command])
            )
        alacritty_path = shutil.which("alacritty")
        if alacritty_path:
            terminal_candidates.append(
                ("alacritty", [alacritty_path, "-e", "bash", "-lc", shell_command])
            )
        wezterm_path = shutil.which("wezterm")
        if wezterm_path:
            terminal_candidates.append(
                ("wezterm", [wezterm_path, "start", "--", "bash", "-lc", shell_command])
            )
        xterm_path = shutil.which("xterm")
        if xterm_path:
            terminal_candidates.append(
                ("xterm", [xterm_path, "-e", "bash", "-lc", shell_command])
            )

        launch_errors: list[str] = []
        for launcher_name, terminal_cmd in terminal_candidates:
            try:
                launched = subprocess.Popen(
                    terminal_cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    start_new_session=True,
                )
            except OSError as exc:
                launch_errors.append(f"{launcher_name}: {exc}")
                continue

            # Non-blocking: if the launcher stays alive briefly, treat as successful popup.
            time.sleep(0.15)
            return_code = launched.poll()
            if return_code is None:
                return "Opened terminal window and attached into docker shell."
            if return_code == 0:
                return "Opened terminal window and attached into docker shell."

            try:
                stdout_text, stderr_text = launched.communicate(timeout=0.2)
            except subprocess.TimeoutExpired:
                stdout_text, stderr_text = ("", "")
            detail = (stderr_text or stdout_text or f"exit code {return_code}").strip()
            launch_errors.append(f"{launcher_name}: {detail}")

        tmux_path = shutil.which("tmux")
        if tmux_path:
            session_name = f"marvin_pop_{int(time.time())}"
            started = subprocess.run(
                [
                    tmux_path,
                    "new-session",
                    "-d",
                    "-s",
                    session_name,
                    "bash",
                    "-lc",
                    shell_command,
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            if started.returncode == 0:
                return (
                    "No GUI terminal launcher detected. "
                    f"Created tmux session '{session_name}'. "
                    f"Attach with: tmux attach -t {session_name}"
                )
            detail = started.stderr.strip() or started.stdout.strip() or f"exit code {started.returncode}"
            launch_errors.append(f"tmux: {detail}")

        launcher_names = "/".join(name for name, _ in terminal_candidates) or "none"
        display_hint = ""
        if not os.environ.get("DISPLAY") and not os.environ.get("WAYLAND_DISPLAY"):
            display_hint = " DISPLAY/WAYLAND is not set."
        detail_text = "; ".join(launch_errors[-3:]) if launch_errors else "no launchers were found in PATH"
        raise RuntimeError(
            "No GUI terminal launcher was available "
            f"(tried {launcher_names}).{display_hint} Last errors: {detail_text}"
        )

    def _current_status_for_result(self, result: DockerLaunchResult):
        statuses = collect_runtime_statuses(self._results)
        for status in statuses:
            if status.result is result:
                return status
        return None

    def _replace_result(self, new_result: DockerLaunchResult) -> None:
        # Results changed (start/stop/restart) — drop the cached runtime snapshot
        # so the next status read recomputes fresh instead of showing stale state.
        self._invalidate_runtime_cache_locked()
        for index, result in enumerate(self._results):
            if self._target_identity(result.match.target) == self._target_identity(
                new_result.match.target
            ):
                self._results[index] = new_result
                self._rebuild_result_lookup()
                return
        self._results.append(new_result)
        self._rebuild_result_lookup()

    def _upsert_result(self, new_result: DockerLaunchResult) -> None:
        self._index_match(new_result.match)
        self._replace_result(new_result)

    def _rebuild_result_lookup(self) -> None:
        self._result_lookup = {}
        for result in self._results:
            self._index_result(result)

    def _rebuild_match_lookup(self) -> None:
        self._match_lookup = {}
        for result in self._results:
            self._index_match(result.match)

    def _index_bridges(self, bridge_managers: list[BridgeManager]) -> None:
        for index, manager in enumerate(bridge_managers, start=1):
            raw_name = getattr(manager, "name", None)
            display_name = raw_name if isinstance(raw_name, str) and raw_name.strip() else f"Bridge {index}"
            normalized = normalize_docker_name(display_name)
            if not normalized or normalized in self._bridge_lookup:
                continue
            self._bridge_lookup[normalized] = manager
            self._bridge_display_names[normalized] = str(display_name)
            self._bridge_order.append(normalized)

    def _bridge_payloads_locked(self) -> list[dict[str, object]]:
        if not self._bridge_order:
            return []
        payloads: list[dict[str, object]] = []
        for key in self._bridge_order:
            manager = self._bridge_lookup[key]
            payloads.append(self._bridge_payload_for_locked(self._bridge_display_names[key], manager))
        return payloads

    def _bridge_payload_for_locked(
        self,
        display_name: str,
        bridge_manager: BridgeManager,
    ) -> dict[str, object]:
        payload = dict(bridge_manager.payload())
        payload["name"] = display_name
        return payload

    def _resolve_bridge_manager(self, name: str | None) -> tuple[str, BridgeManager]:
        if not self._bridge_order:
            raise RuntimeError("Bridge control is not configured.")
        if name is None or not str(name).strip():
            first_key = self._bridge_order[0]
            return self._bridge_display_names[first_key], self._bridge_lookup[first_key]

        normalized = normalize_docker_name(str(name))
        manager = self._bridge_lookup.get(normalized)
        if manager is None:
            raise KeyError(f"Cannot find bridge '{name}'.")
        return self._bridge_display_names[normalized], manager

    @staticmethod
    def _normalize_zmq_endpoint_map(raw_map: Any) -> dict[str, str]:
        if not isinstance(raw_map, dict):
            return {}
        endpoints: dict[str, str] = {}
        for raw_name, raw_endpoint in raw_map.items():
            docker_name = str(raw_name).strip()
            endpoint = str(raw_endpoint).strip()
            if docker_name and endpoint:
                endpoints[docker_name] = endpoint
        return endpoints

    def _apply_zmq_test_history_limit_locked(self, history_limit: int) -> None:
        if self._zmq_test_history.maxlen == history_limit:
            return
        self._zmq_test_history = deque(self._zmq_test_history, maxlen=history_limit)

    @staticmethod
    def _read_json_if_exists(path: Path) -> tuple[Any | None, str | None]:
        if not path.exists() or not path.is_file():
            return None, "file not found"

        try:
            raw_text = path.read_text(encoding="utf-8")
        except Exception as exc:
            return None, f"read failed: {exc}"

        try:
            return json.loads(raw_text), None
        except Exception as json_exc:
            # Fallback to YAML parser to support light non-strict JSON variants.
            try:
                parsed_yaml = yaml.safe_load(raw_text)
            except Exception:
                return None, f"invalid JSON: {json_exc}"
            if isinstance(parsed_yaml, (dict, list)):
                return parsed_yaml, None
            return None, "invalid format: root must be object/array"

    def _load_request_format_for_target_locked(self, target) -> dict[str, object]:
        if getattr(target, "is_remote", False):
            return {
                "input_template": None,
                "output_template": None,
                "input_schema": None,
                "output_schema": None,
                "input_path": "",
                "output_path": "",
                "note": "remote docker path is not readable from local dashboard",
            }

        folder_path = Path(target.folder_path)
        request_dir_candidates = [
            folder_path / "RequestFormat",
            folder_path / "request_format",
            folder_path / "requestformat",
        ]

        selected_dir: Path | None = None
        for candidate in request_dir_candidates:
            if candidate.exists() and candidate.is_dir():
                selected_dir = candidate
                break

        if selected_dir is None:
            return {
                "input_template": None,
                "output_template": None,
                "input_schema": None,
                "output_schema": None,
                "input_path": "",
                "output_path": "",
                "note": "RequestFormat directory not found",
            }

        input_candidates = [
            selected_dir / "input.schema.json",
            selected_dir / "input.json",
        ]
        output_candidates = [
            selected_dir / "output.schema.json",
            selected_dir / "output.json",
        ]

        input_path = next((path for path in input_candidates if path.exists()), input_candidates[0])
        output_path = next((path for path in output_candidates if path.exists()), output_candidates[0])
        input_label = input_path.name
        output_label = output_path.name

        input_template_raw, input_error = self._read_json_if_exists(input_path)
        output_template_raw, output_error = self._read_json_if_exists(output_path)

        input_template = input_template_raw
        output_template = output_template_raw
        input_schema: dict[str, Any] | None = None
        output_schema: dict[str, Any] | None = None

        note_parts: list[str] = []
        if input_error:
            note_parts.append(f"{input_label} {input_error}")
        if _is_json_schema_document(input_template_raw):
            input_schema = dict(input_template_raw)
            generated_input = _generate_random_payload_from_schema(input_template_raw)
            if generated_input is not None:
                _refresh_zmq_request_defaults(generated_input)
                input_template = generated_input
                note_parts.append(
                    f"{input_label} detected as JSON Schema (auto-generated random request template)"
                )
            else:
                input_template = _default_zmq_test_request_payload()
                note_parts.append(
                    f"{input_label} detected as JSON Schema (fallback template applied)"
                )
        if output_error:
            note_parts.append(f"{output_label} {output_error}")
        if _is_json_schema_document(output_template_raw):
            output_schema = dict(output_template_raw)
            generated_output = _generate_random_payload_from_schema(output_template_raw)
            if generated_output is not None:
                output_template = generated_output
                note_parts.append(
                    f"{output_label} detected as JSON Schema (auto-generated expected output)"
                )
        note = " | ".join(note_parts)

        return {
            "input_template": input_template,
            "output_template": output_template,
            "input_schema": input_schema,
            "output_schema": output_schema,
            "input_path": str(input_path) if input_path.exists() else "",
            "output_path": str(output_path) if output_path.exists() else "",
            "note": note,
        }

    @staticmethod
    def _resolve_zmq_endpoint_locked(
        docker_name: str,
        endpoint_map: dict[str, str],
    ) -> str | None:
        direct_match = endpoint_map.get(docker_name)
        if direct_match:
            return direct_match

        normalized_target = normalize_docker_name(docker_name)
        for mapped_name, endpoint in endpoint_map.items():
            if normalize_docker_name(mapped_name) == normalized_target:
                return endpoint
        return None

    def _resolve_zmq_endpoint_for_target_locked(
        self,
        target,
        endpoint_map: dict[str, str],
    ) -> str | None:
        config_fields = self._read_docker_config_fields_locked(target)
        host = str(config_fields.get("host", "") or "").strip()
        port_raw = config_fields.get("port")
        port_text = "" if port_raw in {None, ""} else str(port_raw).strip()
        if host and port_text:
            if host.startswith("tcp://"):
                return f"{host}:{port_text}"
            return f"tcp://{host}:{port_text}"
        return self._resolve_zmq_endpoint_locked(target.folder_name, endpoint_map)

    @staticmethod
    def _status_message(status) -> str:
        if status.overall_status == "error":
            return f"Startup status: error. {status.container_summary}."
        if status.overall_status == "running":
            return f"Runtime status: running. {status.container_summary}."
        if status.overall_status == "ended":
            return f"Runtime status: ended. {status.container_summary}."
        return f"Runtime status: {status.overall_status}. {status.container_summary}."

    @staticmethod
    def _docker_sort_key(item: dict[str, object]) -> tuple[int, str]:
        group_name = str(item.get("group", "ungrouped"))
        order = GROUP_ORDER.index(group_name) if group_name in GROUP_ORDER else len(GROUP_ORDER)
        return order, str(item.get("name", "")).lower()

    @staticmethod
    def _infer_docker_model_root(results: list[DockerLaunchResult]) -> Path | None:
        if not results:
            return None
        target = results[0].match.target
        relative = Path(target.relative_folder)
        if not relative.parts:
            return target.folder_path.parent.resolve()
        parent_index = len(relative.parts) - 1
        return target.folder_path.parents[parent_index].resolve()

    def _resolve_docker_model_root(self, launch_config: DockerLaunchConfig) -> Path:
        if self._docker_model_root_override is not None:
            return self._docker_model_root_override
        if launch_config.docker_model_root:
            return Path(launch_config.docker_model_root).expanduser().resolve()
        if self._docker_model_root_hint is not None:
            return self._docker_model_root_hint
        raise RuntimeError("DockerModel root is not configured.")

    def _resolve_dashboard_docker_names(
        self,
        launch_config: DockerLaunchConfig,
        docker_model_root: Path,
    ) -> list[str]:
        if self._docker_names_override:
            return list(self._docker_names_override)
        if launch_config.docker_names:
            return list(launch_config.docker_names)
        return describe_targets(docker_model_root)

    def _resolve_matches_from_launch_config(
        self,
        launch_config: DockerLaunchConfig,
    ) -> list[DockerMatch]:
        if launch_config.docker_targets:
            return self._resolve_matches_from_target_entries(launch_config)

        docker_model_root = self._resolve_docker_model_root(launch_config)
        docker_names = self._resolve_dashboard_docker_names(launch_config, docker_model_root)
        group_lookup = _build_group_lookup_from_launch_config(launch_config)
        matches = match_requested_dockers(
            docker_model_root,
            docker_names,
            group_lookup=group_lookup,
        )
        self._docker_model_root_hint = docker_model_root
        return matches

    def _resolve_matches_from_target_entries(
        self,
        launch_config: DockerLaunchConfig,
    ) -> list[DockerMatch]:
        # Disabled targets (enabled=false) stay in the catalog but are not launched
        # or managed unless an explicit name override asks for them.
        selected_entries = [entry for entry in launch_config.docker_targets if entry.enabled]
        if self._docker_names_override:
            requested = {normalize_docker_name(name) for name in self._docker_names_override}
            selected_entries = [
                entry
                for entry in launch_config.docker_targets
                if normalize_docker_name(entry.name) in requested
            ]
            missing_requested = sorted(
                name
                for name in self._docker_names_override
                if normalize_docker_name(name)
                not in {normalize_docker_name(entry.name) for entry in selected_entries}
            )
            if missing_requested:
                raise RuntimeError(
                    "These docker names are not defined under docker_launcher.docker_targets: "
                    + ", ".join(missing_requested)
                )

        matches: list[DockerMatch] = []
        seen_target_keys: set[tuple[str, str, int, str]] = set()
        first_local_root: Path | None = None
        grouped_scan_requests: dict[
            tuple[str, str, str, int, str],
            dict[str, object],
        ] = {}
        for entry in selected_entries:
            (
                root_value,
                remote_host,
                remote_user,
                remote_ssh_port,
                remote_password,
            ) = self._resolve_target_scan_params(
                entry,
                launch_config,
            )
            if first_local_root is None and remote_host is None:
                first_local_root = Path(root_value).expanduser().resolve()
            scan_key = (
                str(root_value),
                str(remote_host or ""),
                str(remote_user or ""),
                int(remote_ssh_port or 22),
                str(remote_password or ""),
            )
            request_group = grouped_scan_requests.get(scan_key)
            if request_group is None:
                request_group = {
                    "root_value": str(root_value),
                    "remote_host": remote_host,
                    "remote_user": remote_user,
                    "remote_ssh_port": int(remote_ssh_port or 22),
                    "remote_password": remote_password,
                    "entries": [],
                }
                grouped_scan_requests[scan_key] = request_group
            entries = request_group["entries"]
            assert isinstance(entries, list)
            entries.append(entry)

        for request_group in grouped_scan_requests.values():
            entries = request_group["entries"]
            assert isinstance(entries, list)
            docker_names_for_scan = [entry.name for entry in entries]
            group_lookup_for_scan = {entry.name: entry.group for entry in entries}
            matched = match_requested_dockers(
                request_group["root_value"],
                docker_names_for_scan,
                group_lookup=group_lookup_for_scan,
                remote_host=request_group["remote_host"],
                remote_user=request_group["remote_user"],
                remote_ssh_port=request_group["remote_ssh_port"],
                remote_password=request_group["remote_password"],
            )
            for match in matched:
                requested_normalized = normalize_docker_name(match.requested_name)
                matched_entry = next(
                    (entry for entry in entries if normalize_docker_name(entry.name) == requested_normalized),
                    None,
                )
                if matched_entry is not None:
                    match.group_name = matched_entry.group
                target_key = self._target_identity(match.target)
                if target_key in seen_target_keys:
                    continue
                seen_target_keys.add(target_key)
                matches.append(match)

        if first_local_root is not None:
            self._docker_model_root_hint = first_local_root
        return matches

    def _resolve_target_scan_params(
        self,
        entry: DockerTargetEntry,
        launch_config: DockerLaunchConfig,
    ) -> tuple[str, str | None, str | None, int, str | None]:
        if entry.location == "remote":
            remote_root = (
                entry.remote_docker_model_root
                or launch_config.remote_docker_model_root
                or launch_config.docker_model_root
            )
            if not remote_root:
                raise RuntimeError(
                    f"Docker target '{entry.name}' is remote but remote_docker_model_root is missing."
                )
            if not entry.remote_host:
                raise RuntimeError(
                    f"Docker target '{entry.name}' is remote but remote_host is missing."
                )
            remote_password = entry.remote_password or launch_config.remote_password
            return (
                str(remote_root),
                entry.remote_host,
                entry.remote_user,
                int(entry.remote_ssh_port or 22),
                remote_password,
            )

        local_root = (
            entry.docker_model_root
            or launch_config.docker_model_root
            or (
                str(self._docker_model_root_override)
                if self._docker_model_root_override is not None
                else None
            )
            or (
                str(self._docker_model_root_hint)
                if self._docker_model_root_hint is not None
                else None
            )
        )
        if not local_root:
            raise RuntimeError(
                f"Docker target '{entry.name}' is local but docker_model_root is not configured."
            )
        return str(local_root), None, None, 22, None

    @staticmethod
    def _target_identity(target) -> tuple[str, str, int, str]:
        return (
            target.remote_host or "",
            target.remote_user or "",
            int(target.remote_ssh_port),
            str(target.run_script_path),
        )

    @classmethod
    def _docker_connection_from_target(cls, target) -> dict[str, object]:
        is_remote = bool(target.remote_host)
        inferred_root = cls._infer_target_root_string(target)
        return {
            "location": "remote" if is_remote else "local",
            "docker_model_root": "" if is_remote else (inferred_root or ""),
            "remote_host": target.remote_host or "",
            "remote_user": target.remote_user or "",
            "remote_ssh_port": int(target.remote_ssh_port or 22),
            "remote_docker_model_root": (inferred_root or "") if is_remote else "",
            "remote_password_set": bool(getattr(target, "remote_password", None)),
        }

    @staticmethod
    def _infer_target_root_string(target) -> str | None:
        relative = Path(target.relative_folder)
        folder = target.folder_path
        try:
            if not relative.parts:
                return str(folder.parent)
            parent_index = len(relative.parts) - 1
            return str(folder.parents[parent_index])
        except Exception:
            return None

    def _replace_matches_locked(self, matches: list[DockerMatch]) -> None:
        self._invalidate_runtime_cache_locked()
        existing_by_script = {
            self._target_identity(result.match.target): result
            for result in self._results
        }
        new_results: list[DockerLaunchResult] = []
        for match in matches:
            existing = existing_by_script.get(self._target_identity(match.target))
            if existing is None:
                new_results.append(
                    DockerLaunchResult(
                        match=match,
                        return_code=0,
                        tmux_session=None if match.target.is_remote else match.target.folder_name,
                        reused_existing=True,
                    )
                )
                continue

            new_results.append(
                DockerLaunchResult(
                    match=match,
                    return_code=existing.return_code,
                    log_path=existing.log_path,
                    pid=existing.pid,
                    detached=existing.detached,
                    tmux_session=existing.tmux_session,
                    reused_existing=existing.reused_existing,
                    container_ids=list(existing.container_ids),
                    dry_run=existing.dry_run,
                    startup_output=existing.startup_output,
                )
            )

        self._results = new_results
        self._rebuild_match_lookup()
        self._rebuild_result_lookup()

    def _reconfigure_bridge_managers_locked(
        self,
        entries: list[BridgeLaunchEntry],
    ) -> None:
        existing = dict(self._bridge_lookup)
        display_names = dict(self._bridge_display_names)
        new_lookup: dict[str, BridgeManager] = {}
        new_display_names: dict[str, str] = {}
        new_order: list[str] = []

        for index, entry in enumerate(entries, start=1):
            display_name = entry.name.strip() or f"Bridge {index}"
            normalized = normalize_docker_name(display_name)
            if not normalized:
                continue
            manager = existing.pop(normalized, None)
            if manager is None:
                manager = BridgeManager(
                    name=display_name,
                    project_root=self._project_root,
                    enabled=entry.enabled,
                    config_path=entry.config_path,
                    schema_check=entry.schema_check,
                )
            else:
                manager.reconfigure(
                    enabled=entry.enabled,
                    config_path=entry.config_path,
                    schema_check=entry.schema_check,
                )
            new_lookup[normalized] = manager
            new_display_names[normalized] = display_name
            new_order.append(normalized)

        for normalized, manager in existing.items():
            if normalized in display_names:
                manager.shutdown()

        self._bridge_lookup = new_lookup
        self._bridge_display_names = new_display_names
        self._bridge_order = new_order

    @staticmethod
    def _default_bridge_payload() -> dict[str, object]:
        return {
            "name": "Bridge Service",
            "enabled": False,
            "status": "disabled",
            "message": "Bridge control is not configured.",
            "config_path": "",
            "log_path": "",
            "endpoint": "unconfigured",
            "managed": False,
            "pid": None,
        }


def ansi_to_html(text: str) -> str:
    if not text:
        return ""

    sanitized = _strip_non_sgr_ansi(text)
    chunks: list[str] = []
    state: dict[str, object] = {
        "fg": None,
        "bg": None,
        "bold": False,
        "underline": False,
        "italic": False,
    }
    span_open = False
    cursor = 0

    for match in ANSI_CSI_RE.finditer(sanitized):
        if match.start() > cursor:
            chunks.append(escape(sanitized[cursor:match.start()]))

        codes = _parse_sgr_codes(match.group(1))
        _apply_sgr_codes(state, codes)

        if span_open:
            chunks.append("</span>")
            span_open = False

        style = _state_to_css(state)
        if style:
            chunks.append(f'<span style="{style}">')
            span_open = True

        cursor = match.end()

    if cursor < len(sanitized):
        chunks.append(escape(sanitized[cursor:]))

    if span_open:
        chunks.append("</span>")

    return "".join(chunks)


def _strip_non_sgr_ansi(text: str) -> str:
    return ANSI_ESCAPE_RE.sub(
        lambda match: match.group(0) if match.group(0).endswith("m") else "",
        text,
    )


def _parse_sgr_codes(raw_codes: str) -> list[int]:
    if not raw_codes:
        return [0]
    codes: list[int] = []
    for token in raw_codes.split(";"):
        if token == "":
            codes.append(0)
            continue
        try:
            codes.append(int(token))
        except ValueError:
            continue
    return codes or [0]


def _apply_sgr_codes(state: dict[str, object], codes: list[int]) -> None:
    index = 0
    while index < len(codes):
        code = codes[index]
        if code == 0:
            state["fg"] = None
            state["bg"] = None
            state["bold"] = False
            state["underline"] = False
            state["italic"] = False
        elif code == 1:
            state["bold"] = True
        elif code == 3:
            state["italic"] = True
        elif code == 4:
            state["underline"] = True
        elif code == 22:
            state["bold"] = False
        elif code == 23:
            state["italic"] = False
        elif code == 24:
            state["underline"] = False
        elif code == 39:
            state["fg"] = None
        elif code == 49:
            state["bg"] = None
        elif code in ANSI_COLOR_TABLE:
            state["fg"] = ANSI_COLOR_TABLE[code]
        elif 40 <= code <= 47:
            fg_code = code - 10
            state["bg"] = ANSI_COLOR_TABLE.get(fg_code)
        elif 100 <= code <= 107:
            fg_code = code - 10
            state["bg"] = ANSI_COLOR_TABLE.get(fg_code)
        elif code in {38, 48}:
            consumed, color_value = _parse_extended_color(codes[index + 1 :])
            if color_value is not None:
                if code == 38:
                    state["fg"] = color_value
                else:
                    state["bg"] = color_value
            index += consumed
        index += 1


def _parse_extended_color(codes: list[int]) -> tuple[int, str | None]:
    if not codes:
        return 0, None
    mode = codes[0]
    if mode == 5 and len(codes) >= 2:
        return 2, _xterm_256_to_hex(codes[1])
    if mode == 2 and len(codes) >= 4:
        red = max(0, min(codes[1], 255))
        green = max(0, min(codes[2], 255))
        blue = max(0, min(codes[3], 255))
        return 4, f"#{red:02x}{green:02x}{blue:02x}"
    return 0, None


def _xterm_256_to_hex(index: int) -> str:
    if index < 0:
        index = 0
    if index > 255:
        index = 255

    base_palette = {
        0: "#000000",
        1: "#800000",
        2: "#008000",
        3: "#808000",
        4: "#000080",
        5: "#800080",
        6: "#008080",
        7: "#c0c0c0",
        8: "#808080",
        9: "#ff0000",
        10: "#00ff00",
        11: "#ffff00",
        12: "#0000ff",
        13: "#ff00ff",
        14: "#00ffff",
        15: "#ffffff",
    }
    if index in base_palette:
        return base_palette[index]
    if 16 <= index <= 231:
        color_index = index - 16
        red = color_index // 36
        green = (color_index % 36) // 6
        blue = color_index % 6
        cube = [0, 95, 135, 175, 215, 255]
        return f"#{cube[red]:02x}{cube[green]:02x}{cube[blue]:02x}"
    gray = 8 + (index - 232) * 10
    return f"#{gray:02x}{gray:02x}{gray:02x}"


def _state_to_css(state: dict[str, object]) -> str:
    styles: list[str] = []
    fg = state.get("fg")
    bg = state.get("bg")
    if isinstance(fg, str) and fg:
        styles.append(f"color: {fg}")
    if isinstance(bg, str) and bg:
        styles.append(f"background-color: {bg}")
    if state.get("bold"):
        styles.append("font-weight: 700")
    if state.get("underline"):
        styles.append("text-decoration: underline")
    if state.get("italic"):
        styles.append("font-style: italic")
    return "; ".join(styles)


def _build_group_lookup_from_launch_config(
    launch_config: DockerLaunchConfig,
) -> dict[str, str]:
    group_lookup: dict[str, str] = {}
    for group_name, docker_names in launch_config.docker_groups.items():
        for docker_name in docker_names:
            group_lookup[docker_name] = group_name
    return group_lookup


class BridgeManager:
    def __init__(
        self,
        *,
        name: str,
        project_root: Path,
        config_base_dir: Path | None = None,
        enabled: bool = True,
        config_path: str | None = None,
        schema_check: BridgeSchemaCheckConfig | None = None,
    ) -> None:
        self.name = name.strip() or "Bridge Service"
        self._project_root = project_root.resolve()
        self._config_base_dir = (
            config_base_dir.resolve() if config_base_dir is not None else self._project_root
        )
        self._enabled = enabled
        self._requested_config_path = config_path
        self._schema_check_override = self._clone_schema_check(schema_check)
        self._config_path = self._resolve_config_path(config_path)
        self._config: BridgeServiceConfig | None = None
        self._config_error: str | None = None
        self._process: subprocess.Popen[str] | None = None
        log_slug = normalize_docker_name(self.name) or "bridge-service"
        self._log_path = (
            self._project_root / "logs" / "bridge" / f"{log_slug}.log"
        ).resolve()
        self._log_clear_offset = 0
        self._last_message = "Bridge is idle."
        self._reload_config()

    def reconfigure(
        self,
        *,
        enabled: bool,
        config_path: str | None,
        schema_check: BridgeSchemaCheckConfig | None,
    ) -> None:
        self._enabled = enabled
        self._requested_config_path = config_path
        self._schema_check_override = self._clone_schema_check(schema_check)
        self._config_path = self._resolve_config_path(config_path)
        self._reload_config()
        self._last_message = "Bridge config reloaded."

    def payload(self) -> dict[str, object]:
        self._refresh_process_state()
        config_exists = self._config_path is not None and self._config_path.exists()

        if not self._enabled:
            status = "disabled"
            message = "Bridge control is disabled in docker launch config."
        elif self._config_error:
            status = "error"
            message = f"Bridge config error: {self._config_error}"
        elif not config_exists or self._config is None:
            status = "unavailable"
            message = (
                f"Bridge config not found: {self._config_path}"
                if self._config_path is not None
                else "Bridge config not found."
            )
        elif self._process is not None and self._process.poll() is None:
            status = "running"
            message = self._last_message or "Bridge process is running."
        elif self._process is not None and self._process.poll() not in {None, 0}:
            status = "error"
            message = self._last_message or (
                f"Bridge exited with code {self._process.poll()}."
            )
        elif self._is_endpoint_open():
            status = "running"
            message = "Bridge endpoint is already listening."
        else:
            status = "stopped"
            message = self._last_message or "Bridge is stopped."

        return {
            "enabled": self._enabled,
            "status": status,
            "message": message,
            "config_path": str(self._config_path) if self._config_path is not None else "",
            "log_path": str(self._log_path),
            "endpoint": self._endpoint_label(),
            "log_available": self._log_path.exists(),
            "managed": self._process is not None,
            "pid": self._process.pid if self._process is not None and self._process.poll() is None else None,
        }

    def start(self) -> dict[str, object]:
        self._reload_config()
        payload = self.payload()
        if self._process is not None and self._process.poll() is None:
            return {
                "ok": True,
                "message": "Bridge is already running.",
                "bridge": payload,
            }
        if not self._enabled:
            return {
                "ok": False,
                "message": "Bridge control is disabled in docker launch config.",
                "bridge": payload,
            }
        if self._config_error:
            return {
                "ok": False,
                "message": f"Bridge config error: {self._config_error}",
                "bridge": payload,
            }
        if self._config_path is None or self._config is None:
            return {
                "ok": False,
                "message": "Bridge config is missing, cannot start bridge.",
                "bridge": payload,
            }

        released_ok, release_message = self._release_listen_port_if_busy()
        if not released_ok:
            self._last_message = release_message
            return {
                "ok": False,
                "message": self._last_message,
                "bridge": self.payload(),
            }

        self._log_path.parent.mkdir(parents=True, exist_ok=True)
        env = os.environ.copy()
        src_path = str((self._project_root / "src").resolve())
        existing_pythonpath = env.get("PYTHONPATH", "").strip()
        env["PYTHONPATH"] = src_path if not existing_pythonpath else f"{src_path}:{existing_pythonpath}"
        env["FORCE_COLOR"] = "1"
        env["PYTHONUNBUFFERED"] = "1"
        env["TERM"] = env.get("TERM", "") or "xterm-256color"

        command = [
            sys.executable,
            "-u",
            "-m",
            "fusion_docker",
            "serve-bridge",
            "--config",
            str(self._config_path),
        ]

        with self._log_path.open("a", encoding="utf-8") as log_file:
            log_file.write(
                f"\n=== Starting bridge from {self._config_path} at {datetime.now().isoformat()} ===\n"
            )
            log_file.flush()
            process = subprocess.Popen(
                command,
                cwd=str(self._project_root),
                stdout=log_file,
                stderr=subprocess.STDOUT,
                text=True,
                env=env,
                start_new_session=True,
            )

        self._process = process
        try:
            process.wait(timeout=0.25)
        except subprocess.TimeoutExpired:
            pass
        self._refresh_process_state()
        self._last_message = f"Bridge start command sent (pid={process.pid})."
        if process.poll() is not None:
            self._last_message = f"Bridge exited with code {process.poll()}."
        if release_message:
            self._last_message = f"{release_message} {self._last_message}".strip()
        return {
            "ok": process.poll() is None,
            "message": self._last_message,
            "bridge": self.payload(),
        }

    def stop(self) -> dict[str, object]:
        payload = self.payload()
        if self._process is None or self._process.poll() is not None:
            if payload["status"] == "running":
                return {
                    "ok": False,
                    "message": "Bridge is running externally and is not managed by this dashboard.",
                    "bridge": payload,
                }
            self._clear_visible_logs()
            self._last_message = "Bridge is already stopped."
            return {
                "ok": True,
                "message": self._last_message,
                "bridge": self.payload(),
            }

        self._process.terminate()
        try:
            self._process.wait(timeout=5.0)
        except subprocess.TimeoutExpired:
            self._process.kill()
            self._process.wait(timeout=5.0)

        exit_code = self._process.poll()
        self._clear_visible_logs()
        self._last_message = f"Bridge stopped (exit code {exit_code})."
        self._process = None
        return {
            "ok": True,
            "message": self._last_message,
            "bridge": self.payload(),
        }

    def restart(self) -> dict[str, object]:
        stop_response = self.stop()
        if not stop_response["ok"] and self.payload()["status"] == "running":
            return stop_response
        start_response = self.start()
        message = f"{stop_response['message']} {start_response['message']}".strip()
        return {
            "ok": bool(start_response["ok"]),
            "message": message,
            "bridge": start_response["bridge"],
        }

    def _refresh_process_state(self) -> None:
        if self._process is None:
            return
        return_code = self._process.poll()
        if return_code is None:
            return
        if return_code == 0:
            self._last_message = "Bridge exited cleanly."
        else:
            self._last_message = f"Bridge exited with code {return_code}."

    def _endpoint_label(self) -> str:
        if self._config is None:
            return "unconfigured"
        if getattr(self._config, "source_mode", "external_json") == "zmq_source":
            source_addr = getattr(self._config, "zmq_source_addr", "").strip()
            return f"zmq-source: {source_addr}" if source_addr else "zmq-source: unconfigured"
        host = self._config.listen_host or "0.0.0.0"
        return f"tcp://{host}:{self._config.listen_port}"

    def _is_endpoint_open(self) -> bool:
        if self._config is None:
            return False
        if getattr(self._config, "source_mode", "external_json") == "zmq_source":
            return False
        host = (self._config.listen_host or "127.0.0.1").strip()
        if host in {"0.0.0.0", "::"}:
            host = "127.0.0.1"

        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(0.3)
        try:
            return sock.connect_ex((host, int(self._config.listen_port))) == 0
        except OSError:
            return False
        finally:
            sock.close()

    def _release_listen_port_if_busy(self) -> tuple[bool, str]:
        if self._config is None:
            return True, ""
        if getattr(self._config, "source_mode", "external_json") == "zmq_source":
            return True, ""

        port = int(self._config.listen_port)
        owner_pids = self._find_listen_port_owner_pids(port)
        owner_pids = sorted(
            {
                pid
                for pid in owner_pids
                if pid > 0 and pid != os.getpid()
            }
        )
        if not owner_pids:
            return True, ""

        killed_pids: list[int] = []
        failed_pids: list[int] = []
        for pid in owner_pids:
            if self._terminate_pid(pid):
                killed_pids.append(pid)
            else:
                failed_pids.append(pid)

        if failed_pids:
            return (
                False,
                (
                    f"Port {port} is occupied. Tried to stop PID(s) "
                    f"{', '.join(str(pid) for pid in failed_pids)} but failed."
                ),
            )
        return (
            True,
            f"Released port {port} by stopping PID(s) {', '.join(str(pid) for pid in killed_pids)}.",
        )

    def _find_listen_port_owner_pids(self, port: int) -> list[int]:
        pids: set[int] = set()
        lsof_path = shutil.which("lsof")
        if lsof_path:
            listed = subprocess.run(
                [lsof_path, "-ti", f"tcp:{port}"],
                check=False,
                capture_output=True,
                text=True,
            )
            if listed.returncode in {0, 1}:
                for line in listed.stdout.splitlines():
                    token = line.strip()
                    if token.isdigit():
                        pids.add(int(token))

        if pids:
            return sorted(pids)

        fuser_path = shutil.which("fuser")
        if not fuser_path:
            return []
        listed = subprocess.run(
            [fuser_path, "-n", "tcp", str(port)],
            check=False,
            capture_output=True,
            text=True,
        )
        if listed.returncode not in {0, 1}:
            return []
        for token in re.findall(r"\d+", f"{listed.stdout} {listed.stderr}"):
            try:
                pids.add(int(token))
            except ValueError:
                continue
        return sorted(pids)

    def _terminate_pid(self, pid: int) -> bool:
        try:
            os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:
            return True
        except PermissionError:
            return False
        except OSError:
            return False

        for _ in range(12):
            if not self._is_process_alive(pid):
                return True
            time.sleep(0.05)

        try:
            os.kill(pid, signal.SIGKILL)
        except ProcessLookupError:
            return True
        except PermissionError:
            return False
        except OSError:
            return False

        for _ in range(8):
            if not self._is_process_alive(pid):
                return True
            time.sleep(0.05)
        return not self._is_process_alive(pid)

    @staticmethod
    def _is_process_alive(pid: int) -> bool:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return False
        except PermissionError:
            return True
        except OSError:
            return False
        return True

    def _resolve_config_path(self, config_path: str | None) -> Path | None:
        if config_path:
            if Path(config_path).is_absolute():
                return Path(config_path).resolve()
            relative = Path(config_path)
            candidates: list[Path] = []
            candidates.append((self._config_base_dir / relative).resolve())
            candidates.append((self._project_root / relative).resolve())
            if self._config_base_dir.name == "configs" and relative.parts and relative.parts[0] == "configs":
                candidates.append((self._config_base_dir.parent / relative).resolve())

            for candidate in candidates:
                if candidate.exists():
                    return candidate

            # Fall back to the most common project-root-relative interpretation.
            if self._config_base_dir.name == "configs" and relative.parts and relative.parts[0] == "configs":
                return (self._config_base_dir.parent / relative).resolve()
            return candidates[0]

        local_candidate = (self._project_root / "configs" / "bridge.sam3_flowpose.yaml").resolve()
        if local_candidate.exists():
            return local_candidate
        default_candidate = (self._project_root / "configs" / "bridge.multi_zmq_pub.yaml").resolve()
        if default_candidate.exists():
            return default_candidate
        return None

    @staticmethod
    def _clone_schema_check(
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

    @staticmethod
    def _apply_schema_override(
        base: BridgeSchemaCheckConfig,
        override: BridgeSchemaCheckConfig,
    ) -> BridgeSchemaCheckConfig:
        merged_links = override.links if override.links else base.links
        merged_root = override.docker_model_root.strip() or base.docker_model_root
        return BridgeSchemaCheckConfig(
            enabled=bool(override.enabled),
            strict=bool(override.strict),
            docker_model_root=merged_root,
            links=[
                BridgeSchemaLink(
                    from_docker=str(link.from_docker),
                    to_docker=str(link.to_docker),
                    field_map={str(key): str(value) for key, value in dict(link.field_map).items()},
                    provides=tuple(str(item) for item in tuple(link.provides)),
                )
                for link in merged_links
            ],
        )

    def _load_config(self, path: Path | None) -> BridgeServiceConfig | None:
        if path is None or not path.exists():
            return None
        config = load_bridge_config(path)
        if self._schema_check_override is not None:
            config.schema_check = self._apply_schema_override(
                config.schema_check,
                self._schema_check_override,
            )
        return config

    def _reload_config(self) -> None:
        self._config_error = None
        try:
            self._config = self._load_config(self._config_path)
        except Exception as exc:
            self._config = None
            self._config_error = str(exc)

    def shutdown(self) -> None:
        if self._process is None or self._process.poll() is not None:
            return
        self._process.terminate()
        try:
            self._process.wait(timeout=5.0)
        except subprocess.TimeoutExpired:
            self._process.kill()
            self._process.wait(timeout=5.0)
        self._process = None

    def read_logs(self, lines: int) -> str:
        if lines <= 0 or not self._log_path.exists():
            return ""
        try:
            file_size = self._log_path.stat().st_size
            read_offset = self._log_clear_offset if self._log_clear_offset <= file_size else 0
            with self._log_path.open("r", encoding="utf-8", errors="replace") as handle:
                if read_offset > 0:
                    handle.seek(read_offset)
                tail = deque(handle, maxlen=lines)
        except OSError:
            return ""
        return "".join(tail).strip()

    def _clear_visible_logs(self) -> None:
        if not self._log_path.exists():
            self._log_clear_offset = 0
            return
        try:
            self._log_clear_offset = self._log_path.stat().st_size
        except OSError:
            self._log_clear_offset = 0

    def read_config_text(self) -> str:
        if self._config_path is None or not self._config_path.exists():
            return ""
        try:
            return self._config_path.read_text(encoding="utf-8")
        except OSError:
            return ""

    def save_config_text(self, content: str) -> None:
        normalized_content = content.replace("\r\n", "\n")
        target_path = self._ensure_config_path()
        target_path.parent.mkdir(parents=True, exist_ok=True)

        temp_file_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                "w",
                encoding="utf-8",
                dir=str(target_path.parent),
                prefix=f".{target_path.stem}.",
                suffix=target_path.suffix or ".yaml",
                delete=False,
            ) as handle:
                handle.write(normalized_content)
                temp_file_path = Path(handle.name)

            load_bridge_config(temp_file_path)
            temp_file_path.replace(target_path)
            temp_file_path = None
            self._reload_config()
            self._last_message = f"Saved bridge config to {target_path}."
        except Exception as exc:
            if temp_file_path is not None and temp_file_path.exists():
                try:
                    temp_file_path.unlink()
                except OSError:
                    pass
            raise ValueError(f"Invalid bridge config: {exc}") from exc

    def _ensure_config_path(self) -> Path:
        if self._config_path is not None:
            return self._config_path
        config_dir = (self._project_root / "configs").resolve()
        config_dir.mkdir(parents=True, exist_ok=True)
        slug = normalize_docker_name(self.name) or "bridge"
        self._config_path = config_dir / f"{slug}.yaml"
        return self._config_path


class LaunchConfigManager:
    def __init__(
        self,
        *,
        project_root: Path,
        config_path: str | Path | None = None,
    ) -> None:
        self._project_root = project_root.resolve()
        self._config_path = self._resolve_config_path(config_path)
        self._config: DockerLaunchConfig | None = None
        self._config_error: str | None = None
        self._last_message = "Docker launcher config is ready."
        self._reload_config()

    def payload(self) -> dict[str, object]:
        self._reload_config()
        config_exists = self._config_path.exists()
        if self._config_error:
            status = "error"
            message = f"Launcher config error: {self._config_error}"
        elif not config_exists:
            status = "unconfigured"
            message = "Launcher config does not exist yet. Save from the dashboard to create it."
        else:
            status = "ready"
            message = self._last_message

        return {
            "status": status,
            "message": message,
            "config_path": str(self._config_path),
            "docker_model_root": self._config.docker_model_root if self._config is not None else "",
            "docker_count": len(self._config.docker_names) if self._config is not None else 0,
            "bridge_count": len(self._config.bridge_entries) if self._config is not None else 0,
        }

    def set_message(self, message: str) -> None:
        self._last_message = message.strip() or self._last_message

    def load_config(self) -> DockerLaunchConfig | None:
        self._reload_config()
        if self._config_error:
            raise ValueError(f"Invalid docker launcher config: {self._config_error}")
        return self._config

    def zmq_test_settings(self) -> dict[str, object]:
        defaults: dict[str, object] = {
            "timeout_ms": ZMQ_TEST_TIMEOUT_MS_DEFAULT,
            "history_limit": ZMQ_TEST_HISTORY_LIMIT_DEFAULT,
            "endpoints": {},
        }
        try:
            raw_data = self._read_raw_config_data()
        except Exception:
            return defaults

        launcher_raw = raw_data.get("docker_launcher")
        if not isinstance(launcher_raw, dict):
            return defaults

        zmq_test_raw = launcher_raw.get("zmq_test")
        if not isinstance(zmq_test_raw, dict):
            return defaults

        timeout_ms = _clamp_int(
            zmq_test_raw.get("timeout_ms"),
            default=ZMQ_TEST_TIMEOUT_MS_DEFAULT,
            minimum=ZMQ_TEST_TIMEOUT_MS_MIN,
            maximum=ZMQ_TEST_TIMEOUT_MS_MAX,
        )
        history_limit = _clamp_int(
            zmq_test_raw.get("history_limit"),
            default=ZMQ_TEST_HISTORY_LIMIT_DEFAULT,
            minimum=ZMQ_TEST_HISTORY_LIMIT_MIN,
            maximum=ZMQ_TEST_HISTORY_LIMIT_MAX,
        )
        endpoints_raw = zmq_test_raw.get("endpoints", {})
        endpoints: dict[str, str] = {}
        if isinstance(endpoints_raw, dict):
            for raw_name, raw_endpoint in endpoints_raw.items():
                docker_name = str(raw_name).strip()
                endpoint = str(raw_endpoint).strip()
                if docker_name and endpoint:
                    endpoints[docker_name] = endpoint

        return {
            "timeout_ms": timeout_ms,
            "history_limit": history_limit,
            "endpoints": endpoints,
        }

    def read_config_text(self) -> str:
        if not self._config_path.exists():
            return ""
        try:
            return self._config_path.read_text(encoding="utf-8")
        except OSError:
            return ""

    def save_config_text(self, content: str) -> None:
        normalized_content = content.replace("\r\n", "\n")
        target_path = self._ensure_config_path()
        target_path.parent.mkdir(parents=True, exist_ok=True)

        temp_file_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                "w",
                encoding="utf-8",
                dir=str(target_path.parent),
                prefix=f".{target_path.stem}.",
                suffix=target_path.suffix or ".yaml",
                delete=False,
            ) as handle:
                handle.write(normalized_content)
                temp_file_path = Path(handle.name)

            load_docker_launch_config(temp_file_path)
            temp_file_path.replace(target_path)
            temp_file_path = None
            self._reload_config()
            self._last_message = f"Saved launcher config to {target_path}."
        except Exception as exc:
            if temp_file_path is not None and temp_file_path.exists():
                try:
                    temp_file_path.unlink()
                except OSError:
                    pass
            raise ValueError(f"Invalid docker launcher config: {exc}") from exc

    def structured_payload(self) -> dict[str, object]:
        """Structured view of docker_launch.yaml for the form-based UI editor.

        Built from the raw YAML (not the expanded config) so values such as
        ``${DOCKER_MODEL_ROOT}`` round-trip unchanged when saved back.
        """
        try:
            raw = self._read_raw_config_data()
        except Exception:
            raw = {}
        launcher = raw.get("docker_launcher")
        if launcher is None:
            launcher = raw.get("launcher")
        if not isinstance(launcher, dict):
            launcher = {}

        selected_raw = launcher.get("selected_dockers")
        has_selected = isinstance(selected_raw, list)
        selected_set: set[str] = set()
        if has_selected:
            for item in selected_raw:
                if isinstance(item, str) and item.strip():
                    selected_set.add(normalize_docker_name(item))

        targets: list[dict[str, object]] = []
        targets_raw = launcher.get("docker_targets")
        if isinstance(targets_raw, list):
            for entry in targets_raw:
                if not isinstance(entry, dict):
                    continue
                name = str(entry.get("name", "")).strip()
                if not name:
                    continue
                if "enabled" in entry:
                    enabled = bool(entry.get("enabled"))
                elif has_selected:
                    enabled = normalize_docker_name(name) in selected_set
                else:
                    enabled = True
                location = str(entry.get("location", "local")).strip().lower() or "local"
                if location == "localhost":
                    location = "local"
                targets.append(
                    {
                        "name": name,
                        "group": str(entry.get("group", "ungrouped")).strip().lower()
                        or "ungrouped",
                        "location": location if location in {"local", "remote"} else "local",
                        "enabled": enabled,
                    }
                )

        bridges: list[dict[str, object]] = []
        bridges_raw = launcher.get("bridges")
        if isinstance(bridges_raw, list):
            for entry in bridges_raw:
                if not isinstance(entry, dict):
                    continue
                bridges.append(
                    {
                        "name": str(entry.get("name", "")).strip(),
                        "enabled": bool(entry.get("enabled", True)),
                        "config": str(entry.get("config", "")).strip(),
                    }
                )

        def _as_bool(value: object, default: bool) -> bool:
            if value is None:
                return default
            return bool(value)

        try:
            poll_interval = float(launcher.get("poll_interval", 0.5))
        except (TypeError, ValueError):
            poll_interval = 0.5

        return {
            "available": bool(launcher),
            "docker_model_root": str(launcher.get("docker_model_root", "")).strip(),
            "tmux": _as_bool(launcher.get("tmux"), True),
            "monitor": _as_bool(launcher.get("monitor"), True),
            "replace_session": _as_bool(launcher.get("replace_session"), False),
            "poll_interval": poll_interval,
            "docker_targets": targets,
            "bridges": bridges,
            "available_dockers": self._discover_available_docker_names(targets),
            "migrated_from_selected": has_selected,
        }

    def _discover_available_docker_names(
        self,
        current_targets: list[dict[str, object]],
    ) -> list[str]:
        root = None
        if self._config is not None and self._config.docker_model_root:
            root = self._config.docker_model_root
        if not root:
            return []
        try:
            discovered = discover_docker_targets(root)
        except Exception:
            return []
        existing = {
            normalize_docker_name(str(entry.get("name", ""))) for entry in current_targets
        }
        names: list[str] = []
        for target in discovered:
            folder = target.folder_name
            if normalize_docker_name(folder) in existing:
                continue
            names.append(folder)
        return sorted(dict.fromkeys(names))

    def save_structured(self, payload: dict[str, object]) -> None:
        """Apply a structured edit from the form-based UI to docker_launch.yaml.

        Only the keys the form owns are rewritten; unrelated keys (zmq_test,
        dashboard, ...) are preserved. The deprecated ``selected_dockers`` list is
        removed in favour of per-target ``enabled`` flags.
        """
        self._reload_config()
        raw = self._read_raw_config_data()
        launcher = raw.get("docker_launcher")
        if launcher is None and isinstance(raw.get("launcher"), dict):
            launcher = raw.get("launcher")
        if launcher is None:
            launcher = {}
            raw["docker_launcher"] = launcher
        if not isinstance(launcher, dict):
            raise ValueError("docker_launcher must be a mapping.")

        if "docker_model_root" in payload:
            root_value = str(payload.get("docker_model_root") or "").strip()
            if root_value:
                launcher["docker_model_root"] = root_value
            else:
                launcher.pop("docker_model_root", None)

        if "tmux" in payload:
            launcher["tmux"] = bool(payload.get("tmux"))
        if "monitor" in payload:
            launcher["monitor"] = bool(payload.get("monitor"))
        if "replace_session" in payload:
            launcher["replace_session"] = bool(payload.get("replace_session"))
        if "poll_interval" in payload:
            try:
                poll_value = float(payload.get("poll_interval"))
            except (TypeError, ValueError) as exc:
                raise ValueError("poll_interval must be a number.") from exc
            if poll_value <= 0:
                raise ValueError("poll_interval must be greater than 0.")
            launcher["poll_interval"] = poll_value

        targets_payload = payload.get("docker_targets")
        if isinstance(targets_payload, list):
            existing_by_name: dict[str, dict[str, Any]] = {}
            existing_raw = launcher.get("docker_targets")
            if isinstance(existing_raw, list):
                for entry in existing_raw:
                    if isinstance(entry, dict) and str(entry.get("name", "")).strip():
                        existing_by_name[normalize_docker_name(str(entry["name"]))] = entry

            new_targets: list[dict[str, Any]] = []
            seen: set[str] = set()
            for item in targets_payload:
                if not isinstance(item, dict):
                    continue
                name = str(item.get("name", "")).strip()
                if not name:
                    raise ValueError("Each docker target requires a name.")
                key = normalize_docker_name(name)
                if key in seen:
                    raise ValueError(f"Duplicate docker target: {name}")
                seen.add(key)
                # Reuse the existing raw entry so remote/docker_model_root details
                # (managed via the Docker Connection panel) are preserved.
                base = existing_by_name.get(key)
                entry = dict(base) if isinstance(base, dict) else {}
                entry["name"] = name
                entry["group"] = str(item.get("group", "ungrouped")).strip().lower() or "ungrouped"
                location = str(item.get("location", "local")).strip().lower() or "local"
                if location == "localhost":
                    location = "local"
                if location not in {"local", "remote"}:
                    raise ValueError(
                        f"docker target '{name}' location must be 'local' or 'remote'."
                    )
                entry["location"] = location
                entry["enabled"] = bool(item.get("enabled", True))
                new_targets.append(entry)
            launcher["docker_targets"] = new_targets

        bridges_payload = payload.get("bridges")
        if isinstance(bridges_payload, list):
            new_bridges: list[dict[str, Any]] = []
            for item in bridges_payload:
                if not isinstance(item, dict):
                    continue
                name = str(item.get("name", "")).strip()
                config = str(item.get("config", "")).strip()
                if not name and not config:
                    continue
                if not name:
                    raise ValueError("Each bridge requires a name.")
                if not config:
                    raise ValueError(f"Bridge '{name}' requires a config path.")
                new_bridges.append(
                    {
                        "name": name,
                        "enabled": bool(item.get("enabled", True)),
                        "config": config,
                    }
                )
            launcher["bridges"] = new_bridges

        # selected_dockers is deprecated; enabled flags are the source of truth.
        launcher.pop("selected_dockers", None)

        dumped = yaml.safe_dump(raw, allow_unicode=True, sort_keys=False)
        self.save_config_text(dumped)

    def update_docker_connection(
        self,
        *,
        name: str,
        location: str,
        docker_model_root: str | None,
        remote_host: str | None,
        remote_user: str | None,
        remote_docker_model_root: str | None,
        remote_ssh_port: int | None,
        remote_password: str | None,
        matches: list[DockerLaunchResult],
    ) -> None:
        normalized_name = str(name).strip()
        if not normalized_name:
            raise ValueError("Docker name is required.")

        normalized_location = str(location).strip().lower() or "local"
        if normalized_location == "localhost":
            normalized_location = "local"
        if normalized_location not in {"local", "remote"}:
            raise ValueError("location must be 'localhost', 'local', or 'remote'.")

        port_value = int(remote_ssh_port) if remote_ssh_port is not None else 22
        if port_value <= 0 or port_value > 65535:
            raise ValueError("remote_ssh_port must be between 1 and 65535.")

        self._reload_config()
        raw_data = self._read_raw_config_data()
        launcher_raw = raw_data.get("docker_launcher")
        if launcher_raw is None:
            launcher_raw = {}
            raw_data["docker_launcher"] = launcher_raw
        if not isinstance(launcher_raw, dict):
            raise ValueError("docker_launcher must be a mapping.")

        targets_raw = self._ensure_docker_targets_raw(launcher_raw, matches)
        target_raw = self._find_or_create_target_raw(targets_raw, normalized_name, matches)
        current_remote_raw = target_raw.get("remote", {})
        if not isinstance(current_remote_raw, dict):
            current_remote_raw = {}

        local_root_value = (docker_model_root or "").strip() or None
        remote_host_value = (remote_host or "").strip() or None
        remote_user_value = (remote_user or "").strip() or None
        remote_root_value = (remote_docker_model_root or "").strip() or None
        remote_password_value = (
            str(remote_password).strip() if remote_password is not None else None
        )
        if remote_password_value == "":
            remote_password_value = None
        existing_remote_host = (
            str(
                current_remote_raw.get(
                    "host",
                    target_raw.get("remote_host", target_raw.get("remote_ip", "")),
                )
            ).strip()
            or None
        )
        existing_remote_user = (
            str(
                current_remote_raw.get(
                    "user",
                    target_raw.get("remote_user", target_raw.get("remote_username", "")),
                )
            ).strip()
            or None
        )
        existing_remote_root = (
            str(
                current_remote_raw.get(
                    "docker_model_root",
                    target_raw.get(
                        "remote_docker_model_root",
                        target_raw.get("remote_model_root", ""),
                    ),
                )
            ).strip()
            or None
        )
        existing_remote_port = current_remote_raw.get(
            "ssh_port",
            target_raw.get("remote_ssh_port", 22),
        )
        existing_remote_password = (
            str(
                current_remote_raw.get(
                    "password",
                    target_raw.get("remote_password", ""),
                )
            ).strip()
            or None
        )

        resolved_remote_host = remote_host_value or existing_remote_host
        resolved_remote_user = remote_user_value or existing_remote_user
        resolved_remote_root = remote_root_value or existing_remote_root
        resolved_remote_port = port_value if remote_ssh_port is not None else int(existing_remote_port or 22)
        resolved_remote_password = (
            remote_password_value
            if remote_password is not None
            else existing_remote_password
        )

        target_raw["name"] = normalized_name
        target_raw["group"] = self._resolve_target_group(target_raw, normalized_name, matches)
        target_raw["location"] = normalized_location

        if local_root_value:
            target_raw["docker_model_root"] = local_root_value
        else:
            target_raw.pop("docker_model_root", None)

        if normalized_location == "remote":
            if not resolved_remote_host or not resolved_remote_user or not resolved_remote_root:
                raise ValueError(
                    "Remote docker requires remote_host, remote_user, and remote_docker_model_root."
                )
            target_raw["remote"] = {
                "host": resolved_remote_host,
                "user": resolved_remote_user,
                "docker_model_root": resolved_remote_root,
                "ssh_port": int(resolved_remote_port),
            }
            if resolved_remote_password is not None:
                target_raw["remote"]["password"] = resolved_remote_password
            else:
                target_raw["remote"].pop("password", None)
            target_raw.pop("remote_host", None)
            target_raw.pop("remote_user", None)
            target_raw.pop("remote_docker_model_root", None)
            target_raw.pop("remote_model_root", None)
            target_raw.pop("remote_ssh_port", None)
            target_raw.pop("remote_password", None)
            target_raw.pop("remote_ip", None)
            target_raw.pop("remote_username", None)
        else:
            if (
                not local_root_value
                and not str(launcher_raw.get("docker_model_root", "")).strip()
                and self._infer_local_root_from_matches(normalized_name, matches) is None
            ):
                raise ValueError(
                    "Local docker requires docker_model_root (entry or docker_launcher.docker_model_root)."
                )
            if not local_root_value:
                inferred_root = self._infer_local_root_from_matches(normalized_name, matches)
                if inferred_root:
                    target_raw["docker_model_root"] = inferred_root
            target_raw.pop("remote", None)
            target_raw.pop("remote_host", None)
            target_raw.pop("remote_user", None)
            target_raw.pop("remote_docker_model_root", None)
            target_raw.pop("remote_model_root", None)
            target_raw.pop("remote_ssh_port", None)
            target_raw.pop("remote_password", None)
            target_raw.pop("remote_ip", None)
            target_raw.pop("remote_username", None)

        dumped = yaml.safe_dump(
            raw_data,
            allow_unicode=True,
            sort_keys=False,
        )
        self.save_config_text(dumped)

    def _read_raw_config_data(self) -> dict[str, Any]:
        if not self._config_path.exists():
            return {}
        with self._config_path.open("r", encoding="utf-8") as handle:
            loaded = yaml.safe_load(handle) or {}
        if not isinstance(loaded, dict):
            raise ValueError("docker launch config root must be a mapping.")
        return loaded

    def _ensure_docker_targets_raw(
        self,
        launcher_raw: dict[str, Any],
        matches: list[DockerLaunchResult],
    ) -> list[dict[str, Any]]:
        raw_targets = launcher_raw.get("docker_targets")
        if raw_targets is None:
            synthesized = self._synthesize_target_entries(launcher_raw, matches)
            launcher_raw["docker_targets"] = synthesized
            return synthesized
        if not isinstance(raw_targets, list):
            raise ValueError("docker_launcher.docker_targets must be a list.")
        for index, entry in enumerate(raw_targets, start=1):
            if not isinstance(entry, dict):
                raise ValueError(f"docker_launcher.docker_targets[{index}] must be a mapping.")
        return raw_targets

    def _synthesize_target_entries(
        self,
        launcher_raw: dict[str, Any],
        matches: list[DockerLaunchResult],
    ) -> list[dict[str, Any]]:
        entries: list[dict[str, Any]] = []
        if self._config is not None and self._config.docker_targets:
            for entry in self._config.docker_targets:
                raw_entry: dict[str, Any] = {
                    "name": entry.name,
                    "group": entry.group,
                    "location": entry.location,
                }
                if entry.docker_model_root:
                    raw_entry["docker_model_root"] = entry.docker_model_root
                if entry.location == "remote":
                    raw_entry["remote"] = {
                        "host": entry.remote_host or "",
                        "user": entry.remote_user or "",
                        "docker_model_root": entry.remote_docker_model_root or "",
                        "ssh_port": int(entry.remote_ssh_port or 22),
                    }
                    if entry.remote_password:
                        raw_entry["remote"]["password"] = entry.remote_password
                entries.append(raw_entry)
            return entries

        if self._config is not None and self._config.docker_groups:
            for group_name, docker_names in self._config.docker_groups.items():
                for docker_name in docker_names:
                    raw_entry: dict[str, Any] = {
                        "name": docker_name,
                        "group": group_name,
                        "location": "local",
                    }
                    if self._config.docker_model_root:
                        raw_entry["docker_model_root"] = self._config.docker_model_root
                    entries.append(raw_entry)
            if entries:
                return entries

        for result in matches:
            target = result.match.target
            if any(
                normalize_docker_name(str(entry.get("name", "")))
                == normalize_docker_name(target.folder_name)
                for entry in entries
            ):
                continue
            raw_entry = {
                "name": target.folder_name,
                "group": result.match.group_name or "ungrouped",
                "location": "remote" if target.is_remote else "local",
            }
            root_value = self._infer_local_root_from_matches(target.folder_name, matches)
            if root_value and not target.is_remote:
                raw_entry["docker_model_root"] = root_value
            if target.is_remote:
                raw_entry["remote"] = {
                    "host": target.remote_host or "",
                    "user": target.remote_user or "",
                    "docker_model_root": self._infer_remote_root_from_target(target) or "",
                    "ssh_port": int(target.remote_ssh_port or 22),
                }
                target_password = getattr(target, "remote_password", None)
                if target_password:
                    raw_entry["remote"]["password"] = str(target_password)
            entries.append(raw_entry)
        return entries

    def _find_or_create_target_raw(
        self,
        targets_raw: list[dict[str, Any]],
        name: str,
        matches: list[DockerLaunchResult],
    ) -> dict[str, Any]:
        normalized = normalize_docker_name(name)
        for entry in targets_raw:
            if normalize_docker_name(str(entry.get("name", ""))) == normalized:
                return entry

        created = {
            "name": name,
            "group": self._infer_group_from_matches(name, matches) or "ungrouped",
            "location": "local",
        }
        inferred_root = self._infer_local_root_from_matches(name, matches)
        if inferred_root:
            created["docker_model_root"] = inferred_root
        targets_raw.append(created)
        return created

    def _resolve_target_group(
        self,
        target_raw: dict[str, Any],
        docker_name: str,
        matches: list[DockerLaunchResult],
    ) -> str:
        existing = str(target_raw.get("group", "")).strip().lower()
        if existing:
            return existing
        inferred = self._infer_group_from_matches(docker_name, matches)
        return inferred or "ungrouped"

    def _infer_group_from_matches(
        self,
        docker_name: str,
        matches: list[DockerLaunchResult],
    ) -> str | None:
        normalized_name = normalize_docker_name(docker_name)
        for result in matches:
            target = result.match.target
            if normalize_docker_name(target.folder_name) == normalized_name:
                return (result.match.group_name or "").strip().lower() or None
        return None

    def _infer_local_root_from_matches(
        self,
        docker_name: str,
        matches: list[DockerLaunchResult],
    ) -> str | None:
        normalized_name = normalize_docker_name(docker_name)
        for result in matches:
            target = result.match.target
            if target.is_remote:
                continue
            if normalize_docker_name(target.folder_name) != normalized_name:
                continue
            relative = Path(target.relative_folder)
            try:
                if not relative.parts:
                    return str(target.folder_path.parent)
                parent_index = len(relative.parts) - 1
                return str(target.folder_path.parents[parent_index])
            except Exception:
                return None
        return None

    @staticmethod
    def _infer_remote_root_from_target(target) -> str | None:
        relative = Path(target.relative_folder)
        try:
            if not relative.parts:
                return str(target.folder_path.parent)
            parent_index = len(relative.parts) - 1
            return str(target.folder_path.parents[parent_index])
        except Exception:
            return None

    def _reload_config(self) -> None:
        self._config_error = None
        try:
            self._config = (
                load_docker_launch_config(self._config_path)
                if self._config_path.exists()
                else None
            )
        except Exception as exc:
            self._config = None
            self._config_error = str(exc)

    def _resolve_config_path(self, config_path: str | Path | None) -> Path:
        if config_path is None:
            return (self._project_root / "configs" / "docker_launch.yaml").resolve()
        raw_path = Path(config_path)
        if raw_path.is_absolute():
            return raw_path.resolve()
        return (self._project_root / raw_path).resolve()

    def _ensure_config_path(self) -> Path:
        self._config_path.parent.mkdir(parents=True, exist_ok=True)
        return self._config_path


def serve_dashboard_ui(
    *,
    matches: list[DockerMatch] | None = None,
    results: list[DockerLaunchResult] | None = None,
    host: str = "127.0.0.1",
    port: int = 8765,
    log_lines: int = 300,
    project_root: Path | None = None,
    launch_config_path: str | Path | None = None,
    docker_model_root_hint: str | Path | None = None,
    docker_model_root_override: str | Path | None = None,
    docker_names_override: list[str] | None = None,
    bridge_entries: list[BridgeLaunchEntry] | None = None,
    bridge_enabled: bool = True,
    bridge_config_path: str | None = None,
    cleanup_on_exit: bool = False,
    auth_token: str | None = None,
) -> None:
    resolved_project_root = (
        project_root.resolve()
        if project_root is not None
        else Path(__file__).resolve().parents[2]
    )
    bridge_config_base_dir = resolved_project_root
    if launch_config_path:
        bridge_config_base_dir = Path(launch_config_path).expanduser().resolve().parent
    effective_bridge_entries = list(bridge_entries or [])
    if not effective_bridge_entries:
        effective_bridge_entries = [
            BridgeLaunchEntry(
                name="Main Bridge",
                enabled=bridge_enabled,
                config_path=bridge_config_path,
            )
        ]
    controller = DashboardController(
        matches=matches,
        results=results,
        log_lines=log_lines,
        project_root=resolved_project_root,
        launch_config_path=launch_config_path,
        docker_model_root_hint=docker_model_root_hint,
        docker_model_root_override=docker_model_root_override,
        docker_names_override=docker_names_override,
        bridge_managers=[
            BridgeManager(
                name=entry.name,
                project_root=resolved_project_root,
                config_base_dir=bridge_config_base_dir,
                enabled=entry.enabled,
                config_path=entry.config_path,
                schema_check=entry.schema_check,
            )
            for entry in effective_bridge_entries
        ],
    )
    auth = AuthPolicy.create(host=host, token=auth_token)
    server = ThreadingHTTPServer((host, port), _build_handler(controller, auth))
    display_host = "127.0.0.1" if host in {"0.0.0.0", "::"} else host
    url_suffix = auth.url_token_suffix()

    refresher = RuntimeStatusRefresher(controller.refresh_runtime_cache)
    refresher.start()

    print_status(
        "UI",
        f"Marvin dashboard is available at http://{display_host}:{server.server_port}/{url_suffix}",
        color="cyan",
    )
    if auth.require_token:
        print_status(
            "UI",
            "Network exposure detected: an auth token is required. Use the URL above "
            "(it embeds the token) or send the X-Auth-Token header.",
            color="yellow",
        )
    print_status(
        "UI",
        "Web UI mode is active. Press Ctrl+C in this terminal to stop the dashboard.",
        color="cyan",
    )

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print_warning("Stopping Marvin dashboard UI.")
    finally:
        refresher.stop()
        server.server_close()
        controller.shutdown()
        if cleanup_on_exit:
            cleanup_launched_dockers(controller.results)


def _build_handler(
    controller: DashboardController,
    auth: AuthPolicy,
) -> type[BaseHTTPRequestHandler]:
    class DashboardHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            try:
                parsed = urlparse(self.path)
                if not self._authorize("GET", parsed):
                    return
                if parsed.path == "/":
                    self._send_asset("index.html")
                    return
                if parsed.path.startswith("/static/"):
                    self._send_asset(parsed.path[len("/static/") :])
                    return
                if parsed.path == "/api/status":
                    self._send_json(controller.status_payload())
                    return
                if parsed.path == "/api/logs":
                    self._handle_logs(parsed.query)
                    return
                if parsed.path == "/api/docker/console":
                    self._handle_docker_console_meta(parsed.query)
                    return
                if parsed.path == "/api/docker/service-config":
                    self._handle_docker_service_config(parsed.query)
                    return
                if parsed.path == "/api/launcher/config":
                    self._send_json(controller.launcher_config_payload())
                    return
                if parsed.path == "/api/bridge/logs":
                    self._handle_bridge_logs(parsed.query)
                    return
                if parsed.path == "/api/bridge/config":
                    self._handle_bridge_config(parsed.query)
                    return
                if parsed.path == "/api/zmq/schema":
                    self._send_json(controller.zmq_test_schema_payload())
                    return
                if parsed.path == "/api/zmq/history":
                    self._handle_zmq_history(parsed.query)
                    return
                if parsed.path == "/api/zmq/template":
                    self._handle_zmq_template(parsed.query)
                    return
                if parsed.path == "/api/video-streams":
                    self._send_json(controller.video_streams_payload())
                    return
                if parsed.path == "/favicon.ico":
                    self.send_response(HTTPStatus.NO_CONTENT)
                    self.end_headers()
                    return
                self._send_json(
                    {"error": f"Unknown path: {parsed.path}"},
                    status=HTTPStatus.NOT_FOUND,
                )
            except Exception as exc:
                print_warning(f"GET {self.path} failed: {exc}")
                self._send_json(
                    {"error": "Internal server error."},
                    status=HTTPStatus.INTERNAL_SERVER_ERROR,
                )

        def do_POST(self) -> None:  # noqa: N802
            try:
                parsed = urlparse(self.path)
                if not self._authorize("POST", parsed):
                    return
                if parsed.path == "/api/start":
                    self._handle_action(controller.start_docker)
                    return
                if parsed.path == "/api/stop":
                    self._handle_action(controller.stop_docker)
                    return
                if parsed.path == "/api/restart":
                    self._handle_action(controller.restart_docker)
                    return
                if parsed.path == "/api/docker/console/exec":
                    self._handle_docker_console_exec()
                    return
                if parsed.path == "/api/docker/open-terminal":
                    self._handle_docker_open_terminal()
                    return
                if parsed.path == "/api/docker/service-config":
                    self._handle_docker_service_config_update()
                    return
                if parsed.path == "/api/docker/connection":
                    self._handle_docker_connection_update()
                    return
                if parsed.path == "/api/launcher/config":
                    self._handle_launcher_config_update()
                    return
                if parsed.path == "/api/launcher/structured":
                    self._handle_launcher_structured_update()
                    return
                if parsed.path == "/api/launcher/reload":
                    self._handle_launcher_reload()
                    return
                if parsed.path == "/api/bridge/config":
                    self._handle_bridge_config_update()
                    return
                if parsed.path == "/api/bridge/start":
                    self._handle_bridge_action(controller.start_bridge)
                    return
                if parsed.path == "/api/bridge/stop":
                    self._handle_bridge_action(controller.stop_bridge)
                    return
                if parsed.path == "/api/bridge/restart":
                    self._handle_bridge_action(controller.restart_bridge)
                    return
                if parsed.path == "/api/zmq/test":
                    self._handle_zmq_test()
                    return
                if parsed.path == "/api/video-stream":
                    self._handle_video_stream_publish()
                    return
                self._send_json(
                    {"error": f"Unknown path: {parsed.path}"},
                    status=HTTPStatus.NOT_FOUND,
                )
            except Exception as exc:
                print_warning(f"POST {self.path} failed: {exc}")
                self._send_json(
                    {"error": "Internal server error."},
                    status=HTTPStatus.INTERNAL_SERVER_ERROR,
                )

        def log_message(self, format: str, *args: object) -> None:
            return

        def _handle_logs(self, query: str) -> None:
            params = parse_qs(query)
            docker_name = params.get("name", [""])[0].strip()
            raw_lines = params.get("lines", [""])[0].strip()

            if not docker_name:
                self._send_json(
                    {"error": "Query parameter 'name' is required."},
                    status=HTTPStatus.BAD_REQUEST,
                )
                return

            tail_lines: int | None = None
            if raw_lines:
                try:
                    tail_lines = int(raw_lines)
                except ValueError:
                    self._send_json(
                        {"error": "Query parameter 'lines' must be an integer."},
                        status=HTTPStatus.BAD_REQUEST,
                    )
                    return

            try:
                payload = controller.log_payload(docker_name, lines=tail_lines)
            except KeyError as exc:
                self._send_json({"error": str(exc)}, status=HTTPStatus.NOT_FOUND)
                return
            except ValueError as exc:
                self._send_json({"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
                return

            self._send_json(payload)

        def _handle_bridge_logs(self, query: str) -> None:
            params = parse_qs(query)
            bridge_name = params.get("name", [""])[0].strip()
            raw_lines = params.get("lines", [""])[0].strip()

            tail_lines: int | None = None
            if raw_lines:
                try:
                    tail_lines = int(raw_lines)
                except ValueError:
                    self._send_json(
                        {"error": "Query parameter 'lines' must be an integer."},
                        status=HTTPStatus.BAD_REQUEST,
                    )
                    return

            try:
                payload = controller.bridge_log_payload(bridge_name or None, lines=tail_lines)
            except KeyError as exc:
                self._send_json({"error": str(exc)}, status=HTTPStatus.NOT_FOUND)
                return
            except RuntimeError as exc:
                self._send_json({"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
                return

            self._send_json(payload)

        def _handle_bridge_config(self, query: str) -> None:
            params = parse_qs(query)
            bridge_name = params.get("name", [""])[0].strip()

            try:
                payload = controller.bridge_config_payload(bridge_name or None)
            except KeyError as exc:
                self._send_json({"error": str(exc)}, status=HTTPStatus.NOT_FOUND)
                return
            except RuntimeError as exc:
                self._send_json({"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
                return

            self._send_json(payload)

        def _handle_video_stream_publish(self) -> None:
            try:
                payload = self._read_json_body()
            except ValueError as exc:
                self._send_json({"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
                return

            try:
                response = controller.publish_video_stream(
                    title=str(payload.get("title", "")).strip(),
                    frame_base64=str(
                        payload.get("frame_base64", payload.get("image_b64", ""))
                    ).strip(),
                    mime_type=str(payload.get("mime_type", "image/jpeg")).strip(),
                    source=str(payload.get("source", payload.get("docker", ""))).strip(),
                )
            except ValueError as exc:
                self._send_json({"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
                return

            self._send_json(response, status=HTTPStatus.ACCEPTED)

        def _handle_zmq_history(self, query: str) -> None:
            params = parse_qs(query)
            docker_name = params.get("name", [""])[0].strip()
            payload = controller.zmq_test_history_payload(docker_name or None)
            self._send_json(payload)

        def _handle_zmq_template(self, query: str) -> None:
            params = parse_qs(query)
            docker_name = params.get("name", [""])[0].strip()
            if not docker_name:
                self._send_json(
                    {"error": "Query parameter 'name' is required."},
                    status=HTTPStatus.BAD_REQUEST,
                )
                return

            try:
                payload = controller.generate_zmq_request_template(name=docker_name)
            except KeyError as exc:
                self._send_json({"error": str(exc)}, status=HTTPStatus.NOT_FOUND)
                return
            except ValueError as exc:
                self._send_json({"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
                return
            except Exception as exc:
                self._send_json({"error": str(exc)}, status=HTTPStatus.INTERNAL_SERVER_ERROR)
                return

            self._send_json(payload)

        def _handle_action(self, action) -> None:
            try:
                payload = self._read_json_body()
            except ValueError as exc:
                self._send_json({"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
                return

            docker_name = str(payload.get("name", "")).strip()
            if not docker_name:
                self._send_json(
                    {"error": "JSON field 'name' is required."},
                    status=HTTPStatus.BAD_REQUEST,
                )
                return

            try:
                response = action(docker_name)
            except KeyError as exc:
                self._send_json({"error": str(exc)}, status=HTTPStatus.NOT_FOUND)
                return
            except Exception as exc:
                self._send_json({"error": str(exc)}, status=HTTPStatus.INTERNAL_SERVER_ERROR)
                return

            if isinstance(response, dict) and response.get("ok") is False:
                self._send_json(response, status=HTTPStatus.BAD_REQUEST)
                return
            self._send_json(response)

        def _handle_docker_console_meta(self, query: str) -> None:
            params = parse_qs(query)
            docker_name = params.get("name", [""])[0].strip()
            if not docker_name:
                self._send_json(
                    {"error": "Query parameter 'name' is required."},
                    status=HTTPStatus.BAD_REQUEST,
                )
                return
            try:
                response = controller.docker_console_meta(docker_name)
            except KeyError as exc:
                self._send_json({"error": str(exc)}, status=HTTPStatus.NOT_FOUND)
                return
            except RuntimeError as exc:
                self._send_json({"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
                return
            except Exception as exc:
                self._send_json({"error": str(exc)}, status=HTTPStatus.INTERNAL_SERVER_ERROR)
                return

            self._send_json(response)

        def _handle_docker_console_exec(self) -> None:
            try:
                payload = self._read_json_body()
            except ValueError as exc:
                self._send_json({"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
                return

            docker_name = str(payload.get("name", "")).strip()
            command = str(payload.get("command", "")).strip()
            timeout_raw = payload.get("timeout_ms")

            if not docker_name:
                self._send_json(
                    {"error": "JSON field 'name' is required."},
                    status=HTTPStatus.BAD_REQUEST,
                )
                return
            if not command:
                self._send_json(
                    {"error": "JSON field 'command' is required."},
                    status=HTTPStatus.BAD_REQUEST,
                )
                return

            timeout_ms: int | None = None
            if timeout_raw not in {None, ""}:
                try:
                    timeout_ms = int(timeout_raw)
                except (TypeError, ValueError):
                    self._send_json(
                        {"error": "JSON field 'timeout_ms' must be an integer."},
                        status=HTTPStatus.BAD_REQUEST,
                    )
                    return

            try:
                response = controller.docker_console_exec(
                    docker_name,
                    command,
                    timeout_ms=timeout_ms,
                )
            except KeyError as exc:
                self._send_json({"error": str(exc)}, status=HTTPStatus.NOT_FOUND)
                return
            except ValueError as exc:
                self._send_json({"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
                return
            except RuntimeError as exc:
                self._send_json({"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
                return
            except Exception as exc:
                self._send_json({"error": str(exc)}, status=HTTPStatus.INTERNAL_SERVER_ERROR)
                return

            self._send_json(response)

        def _handle_docker_open_terminal(self) -> None:
            try:
                payload = self._read_json_body()
            except ValueError as exc:
                self._send_json({"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
                return

            docker_name = str(payload.get("name", "")).strip()
            if not docker_name:
                self._send_json(
                    {"error": "JSON field 'name' is required."},
                    status=HTTPStatus.BAD_REQUEST,
                )
                return

            try:
                response = controller.open_docker_terminal(docker_name)
            except KeyError as exc:
                self._send_json({"error": str(exc)}, status=HTTPStatus.NOT_FOUND)
                return
            except RuntimeError as exc:
                self._send_json({"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
                return
            except Exception as exc:
                self._send_json({"error": str(exc)}, status=HTTPStatus.INTERNAL_SERVER_ERROR)
                return

            self._send_json(response)

        def _handle_docker_service_config(self, query: str) -> None:
            params = parse_qs(query)
            docker_name = params.get("name", [""])[0].strip()
            if not docker_name:
                self._send_json(
                    {"error": "Query parameter 'name' is required."},
                    status=HTTPStatus.BAD_REQUEST,
                )
                return

            try:
                response = controller.docker_service_config_payload(docker_name)
            except KeyError as exc:
                self._send_json({"error": str(exc)}, status=HTTPStatus.NOT_FOUND)
                return
            except RuntimeError as exc:
                self._send_json({"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
                return
            except Exception as exc:
                self._send_json({"error": str(exc)}, status=HTTPStatus.INTERNAL_SERVER_ERROR)
                return

            self._send_json(response)

        def _handle_docker_service_config_update(self) -> None:
            try:
                payload = self._read_json_body()
            except ValueError as exc:
                self._send_json({"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
                return

            docker_name = str(payload.get("name", "")).strip()
            host = str(payload.get("host", "")).strip()
            port_raw = payload.get("port")
            container_name_raw = payload.get("container_name")
            restart = bool(payload.get("restart", False))
            if not docker_name:
                self._send_json(
                    {"error": "JSON field 'name' is required."},
                    status=HTTPStatus.BAD_REQUEST,
                )
                return
            if not host:
                self._send_json(
                    {"error": "JSON field 'host' is required."},
                    status=HTTPStatus.BAD_REQUEST,
                )
                return
            try:
                port = int(port_raw)
            except (TypeError, ValueError):
                self._send_json(
                    {"error": "JSON field 'port' must be an integer."},
                    status=HTTPStatus.BAD_REQUEST,
                )
                return

            container_name: str | None = None
            if container_name_raw is not None:
                if not isinstance(container_name_raw, str):
                    self._send_json(
                        {"error": "JSON field 'container_name' must be a string or null."},
                        status=HTTPStatus.BAD_REQUEST,
                    )
                    return
                container_name = container_name_raw

            try:
                response = controller.save_docker_service_config(
                    docker_name,
                    host=host,
                    port=port,
                    container_name=container_name,
                    restart=restart,
                )
            except KeyError as exc:
                self._send_json({"error": str(exc)}, status=HTTPStatus.NOT_FOUND)
                return
            except ValueError as exc:
                self._send_json({"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
                return
            except RuntimeError as exc:
                self._send_json({"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
                return
            except Exception as exc:
                self._send_json({"error": str(exc)}, status=HTTPStatus.INTERNAL_SERVER_ERROR)
                return

            self._send_json(response)

        def _handle_bridge_action(self, action) -> None:
            try:
                payload = self._read_json_body()
            except ValueError as exc:
                self._send_json({"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
                return

            bridge_name = str(payload.get("name", "")).strip()

            try:
                response = action(bridge_name or None)
            except KeyError as exc:
                self._send_json({"error": str(exc)}, status=HTTPStatus.NOT_FOUND)
                return
            except RuntimeError as exc:
                self._send_json({"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
                return
            except Exception as exc:
                self._send_json({"error": str(exc)}, status=HTTPStatus.INTERNAL_SERVER_ERROR)
                return

            self._send_json(response)

        def _handle_zmq_test(self) -> None:
            try:
                payload = self._read_json_body()
            except ValueError as exc:
                self._send_json({"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
                return

            docker_name = str(payload.get("name", "")).strip()
            if not docker_name:
                self._send_json(
                    {"error": "JSON field 'name' is required."},
                    status=HTTPStatus.BAD_REQUEST,
                )
                return

            endpoint_value = payload.get("endpoint")
            endpoint = str(endpoint_value).strip() if isinstance(endpoint_value, str) else None

            timeout_raw = payload.get("timeout_ms")
            timeout_ms: int | None = None
            if timeout_raw not in {None, ""}:
                try:
                    timeout_ms = int(timeout_raw)
                except (TypeError, ValueError):
                    self._send_json(
                        {"error": "JSON field 'timeout_ms' must be an integer."},
                        status=HTTPStatus.BAD_REQUEST,
                    )
                    return

            request_payload = payload.get("request")

            try:
                response = controller.run_zmq_test(
                    name=docker_name,
                    endpoint=endpoint,
                    timeout_ms=timeout_ms,
                    request_payload=request_payload,
                )
            except KeyError as exc:
                self._send_json({"error": str(exc)}, status=HTTPStatus.NOT_FOUND)
                return
            except ValueError as exc:
                self._send_json({"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
                return
            except Exception as exc:
                self._send_json({"error": str(exc)}, status=HTTPStatus.INTERNAL_SERVER_ERROR)
                return

            self._send_json(response)

        def _handle_docker_connection_update(self) -> None:
            try:
                payload = self._read_json_body()
            except ValueError as exc:
                self._send_json({"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
                return

            docker_name = str(payload.get("name", "")).strip()
            if not docker_name:
                self._send_json(
                    {"error": "JSON field 'name' is required."},
                    status=HTTPStatus.BAD_REQUEST,
                )
                return

            location = str(payload.get("location", "local")).strip().lower() or "local"
            docker_model_root = payload.get("docker_model_root")
            remote_host = payload.get("remote_host")
            remote_user = payload.get("remote_user")
            remote_docker_model_root = payload.get("remote_docker_model_root")
            remote_ssh_port = payload.get("remote_ssh_port")
            remote_password = payload.get("remote_password")

            if remote_password is not None and not isinstance(remote_password, str):
                self._send_json(
                    {"error": "JSON field 'remote_password' must be a string or null."},
                    status=HTTPStatus.BAD_REQUEST,
                )
                return

            try:
                response = controller.update_docker_connection(
                    name=docker_name,
                    location=location,
                    docker_model_root=(
                        str(docker_model_root) if isinstance(docker_model_root, str) else None
                    ),
                    remote_host=str(remote_host) if isinstance(remote_host, str) else None,
                    remote_user=str(remote_user) if isinstance(remote_user, str) else None,
                    remote_docker_model_root=(
                        str(remote_docker_model_root)
                        if isinstance(remote_docker_model_root, str)
                        else None
                    ),
                    remote_ssh_port=(
                        int(remote_ssh_port) if remote_ssh_port not in {None, ""} else None
                    ),
                    remote_password=remote_password,
                )
            except KeyError as exc:
                self._send_json({"error": str(exc)}, status=HTTPStatus.NOT_FOUND)
                return
            except ValueError as exc:
                self._send_json({"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
                return
            except RuntimeError as exc:
                self._send_json({"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
                return
            except Exception as exc:
                self._send_json({"error": str(exc)}, status=HTTPStatus.INTERNAL_SERVER_ERROR)
                return

            self._send_json(response)

        def _handle_launcher_config_update(self) -> None:
            try:
                payload = self._read_json_body()
            except ValueError as exc:
                self._send_json({"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
                return

            content = payload.get("content")
            if not isinstance(content, str):
                self._send_json(
                    {"error": "JSON field 'content' is required and must be a string."},
                    status=HTTPStatus.BAD_REQUEST,
                )
                return

            restart = bool(payload.get("restart", False))
            try:
                response = controller.save_launcher_config(content, restart=restart)
            except ValueError as exc:
                self._send_json({"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
                return
            except RuntimeError as exc:
                self._send_json({"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
                return
            except Exception as exc:
                self._send_json({"error": str(exc)}, status=HTTPStatus.INTERNAL_SERVER_ERROR)
                return

            self._send_json(response)

        def _handle_launcher_structured_update(self) -> None:
            try:
                payload = self._read_json_body()
            except ValueError as exc:
                self._send_json({"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
                return

            structured = payload.get("structured")
            if not isinstance(structured, dict):
                self._send_json(
                    {"error": "JSON field 'structured' is required and must be an object."},
                    status=HTTPStatus.BAD_REQUEST,
                )
                return

            restart = bool(payload.get("restart", False))
            try:
                response = controller.save_launcher_structured(structured, restart=restart)
            except ValueError as exc:
                self._send_json({"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
                return
            except RuntimeError as exc:
                self._send_json({"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
                return
            except Exception as exc:
                self._send_json({"error": str(exc)}, status=HTTPStatus.INTERNAL_SERVER_ERROR)
                return

            self._send_json(response)

        def _handle_launcher_reload(self) -> None:
            try:
                response = controller.reload_launcher_config()
            except ValueError as exc:
                self._send_json({"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
                return
            except RuntimeError as exc:
                self._send_json({"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
                return
            except Exception as exc:
                self._send_json({"error": str(exc)}, status=HTTPStatus.INTERNAL_SERVER_ERROR)
                return

            self._send_json(response)

        def _handle_bridge_config_update(self) -> None:
            try:
                payload = self._read_json_body()
            except ValueError as exc:
                self._send_json({"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
                return

            bridge_name = str(payload.get("name", "")).strip()
            content = payload.get("content")
            if not isinstance(content, str):
                self._send_json(
                    {"error": "JSON field 'content' is required and must be a string."},
                    status=HTTPStatus.BAD_REQUEST,
                )
                return

            restart = bool(payload.get("restart", False))

            try:
                response = controller.save_bridge_config(
                    bridge_name or None,
                    content,
                    restart=restart,
                )
            except KeyError as exc:
                self._send_json({"error": str(exc)}, status=HTTPStatus.NOT_FOUND)
                return
            except ValueError as exc:
                self._send_json({"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
                return
            except RuntimeError as exc:
                self._send_json({"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
                return
            except Exception as exc:
                self._send_json({"error": str(exc)}, status=HTTPStatus.INTERNAL_SERVER_ERROR)
                return

            self._send_json(response)

        def _read_json_body(self) -> dict[str, object]:
            raw_length = self.headers.get("Content-Length", "0").strip() or "0"
            try:
                length = int(raw_length)
            except ValueError as exc:
                raise ValueError("Content-Length must be an integer.") from exc

            body = self.rfile.read(length) if length > 0 else b"{}"
            try:
                payload = json.loads(body.decode("utf-8"))
            except json.JSONDecodeError as exc:
                raise ValueError("Request body must be valid JSON.") from exc
            if not isinstance(payload, dict):
                raise ValueError("Request JSON must be an object.")
            return payload

        def _authorize(self, method: str, parsed) -> bool:
            result = auth.authorize(
                method=method,
                path=parsed.path,
                query=parsed.query,
                headers=self.headers,
            )
            if result.ok:
                return True
            self._send_json({"error": result.message}, status=HTTPStatus(result.status))
            return False

        def _send_asset(self, name: str) -> None:
            asset = get_static_asset(name)
            if asset is None:
                self._send_json(
                    {"error": f"Unknown asset: {name}"},
                    status=HTTPStatus.NOT_FOUND,
                )
                return
            if self.headers.get("If-None-Match") == asset.etag:
                self.send_response(HTTPStatus.NOT_MODIFIED)
                self.send_header("ETag", asset.etag)
                self.end_headers()
                return
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", asset.content_type)
            self.send_header("Content-Length", str(len(asset.body)))
            self.send_header("ETag", asset.etag)
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            self.wfile.write(asset.body)

        def _send_json(
            self,
            payload: dict[str, object],
            *,
            status: HTTPStatus = HTTPStatus.OK,
        ) -> None:
            encoded = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

    return DashboardHandler



def _build_dashboard_html() -> str:
    """Return the dashboard index document.

    The frontend now lives as plain files under ``ui/static/`` and is loaded via
    :mod:`fusion_docker.ui.assets`. This thin wrapper is kept for backwards
    compatibility with any caller that imported the old builder.
    """

    return render_index_html()
