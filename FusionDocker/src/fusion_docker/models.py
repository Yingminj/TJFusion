from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

Pose = tuple[float, float, float, float, float, float, float]


def normalize_token(value: str | None) -> str:
    return (value or "").strip().lower().replace(" ", "_")


@dataclass(slots=True)
class ZmqEndpointConfig:
    name: str
    endpoint: str
    topic: str
    mode: str = "connect"


@dataclass(slots=True)
class AppConfig:
    service_name: str
    poll_timeout_ms: int
    inputs: dict[str, ZmqEndpointConfig]
    outputs: dict[str, ZmqEndpointConfig]


@dataclass(slots=True)
class BridgeInputMapping:
    rgb_keys: tuple[str, ...] = (
        "rgb_image",
        "rgb_image_base64",
        "rgb_b64",
        "color_image",
        "color_image_base64",
        "color_b64",
        "rgb",
        "image",
    )
    depth_keys: tuple[str, ...] = (
        "depth_image",
        "depth_image_base64",
        "depth_b64",
        "depth",
        "depth_png_base64",
        "depth_png_b64",
    )
    depth_raw_keys: tuple[str, ...] = (
        "depth_raw_base64",
        "depth_raw_b64",
        "depth_u16_base64",
    )
    nested_payload_keys: tuple[str, ...] = ("data", "payload", "frame", "msg")
    depth_shape_keys: tuple[str, ...] = ("depth_shape",)
    depth_height_keys: tuple[str, ...] = ("depth_height", "height")
    depth_width_keys: tuple[str, ...] = ("depth_width", "width")


@dataclass(slots=True)
class BridgeSchemaLink:
    from_docker: str
    to_docker: str
    field_map: dict[str, str] = field(default_factory=dict)
    provides: tuple[str, ...] = ()


@dataclass(slots=True)
class BridgeSchemaCheckConfig:
    enabled: bool = False
    docker_model_root: str = ""
    strict: bool = False
    links: list[BridgeSchemaLink] = field(default_factory=list)


@dataclass(slots=True)
class ModelNode:
    """A single model node in a processing pipeline.

    ``depends_on`` lists model names that must complete before this
    node starts.  Nodes whose dependencies are all satisfied run in
    parallel within the same topological layer.
    """
    name: str
    kind: str = "generic"
    endpoint: str = ""
    enabled: bool = True
    timeout_ms: int | None = None
    depends_on: list[str] = field(default_factory=list)
    role: str = "optional"
    inputs: list[str] = field(default_factory=list)
    outputs: list[str] = field(default_factory=list)
    request_map: dict[str, Any] = field(default_factory=dict)
    response_map: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class BridgeServiceConfig:
    sam3_server_addr: str
    flowpose_server_addr: str
    sam3_timeout_ms: int | None = None
    source_mode: str = "external_json"
    zmq_source_addr: str = ""
    zmq_timeout_sec: float = 3.0
    siglip2_server_addr: str = ""
    flowpose_sidecar_server_addr: str = ""
    run_sam3_flowpose: bool = True
    input_mapping: BridgeInputMapping = field(default_factory=BridgeInputMapping)
    schema_check: BridgeSchemaCheckConfig = field(default_factory=BridgeSchemaCheckConfig)
    prompts: list[str] = field(default_factory=list)
    obj_ids: list[Any] = field(default_factory=list)
    obj_id_map: dict[str, int | str] = field(default_factory=dict)
    return_masks: bool = True
    clear_previous: bool = True
    output_json: str = "response_sam3.json"
    req_timeout_ms: int = 1000
    rgb_jpg_quality: int = 85
    listen_host: str = "0.0.0.0"
    listen_port: int = 5556
    result_pub_addr: str = ""
    result_pub_frame_id: str = "camera_rgb_link"
    result_siglip_topic: str = "/siglip2/result"
    result_tf_topic: str = "/tf"
    pipeline: list[ModelNode] = field(default_factory=list)
    pipeline_outputs: list[str] = field(default_factory=list)

    @property
    def downstream_server_addr(self) -> str:
        return self.flowpose_server_addr

    @property
    def yomni_server_addr(self) -> str:
        # Backward-compat alias: old config/runtime used "yomni" naming.
        return self.flowpose_sidecar_server_addr

    @property
    def siglip_server_addr(self) -> str:
        # Backward-compat alias: old config/runtime used "siglip" naming.
        return self.siglip2_server_addr

    @property
    def effective_pipeline(self) -> list[ModelNode]:
        """Return the explicitly configured *pipeline*, or build one from
        legacy fields when *pipeline* is empty."""
        return self.pipeline if self.pipeline else self.build_default_pipeline()

    def build_default_pipeline(self) -> list[ModelNode]:
        """Build a pipeline from legacy address fields.

        This is used for backward compatibility when no ``pipeline:`` section
        is present in the YAML config.
        """
        nodes: list[ModelNode] = []
        if self.run_sam3_flowpose and self.sam3_server_addr:
            nodes.append(
                ModelNode(
                    name="sam3",
                    endpoint=self.sam3_server_addr,
                    timeout_ms=self.sam3_timeout_ms or self.req_timeout_ms,
                    role="required",
                )
            )
            nodes.append(
                ModelNode(
                    name="flowpose",
                    endpoint=self.flowpose_server_addr,
                    timeout_ms=self.req_timeout_ms,
                    depends_on=["sam3"],
                    role="required",
                )
            )
        if self.siglip2_server_addr:
            nodes.append(
                ModelNode(
                    name="siglip2",
                    endpoint=self.siglip2_server_addr,
                    timeout_ms=self.req_timeout_ms,
                )
            )
        if self.flowpose_sidecar_server_addr:
            nodes.append(
                ModelNode(
                    name="flowpose_sidecar",
                    endpoint=self.flowpose_sidecar_server_addr,
                    timeout_ms=self.req_timeout_ms,
                )
            )
        return nodes


@dataclass(slots=True)
class BridgeLaunchEntry:
    name: str
    enabled: bool = True
    config_path: str | None = None
    schema_check: BridgeSchemaCheckConfig | None = None


@dataclass(slots=True)
class DockerTargetEntry:
    name: str
    group: str = "ungrouped"
    location: str = "local"
    docker_model_root: str | None = None
    remote_host: str | None = None
    remote_user: str | None = None
    remote_docker_model_root: str | None = None
    remote_ssh_port: int = 22
    remote_password: str | None = None


@dataclass(slots=True)
class DockerLaunchConfig:
    docker_model_root: str | None = None
    docker_names: list[str] = field(default_factory=list)
    docker_groups: dict[str, list[str]] = field(default_factory=dict)
    docker_targets: list[DockerTargetEntry] = field(default_factory=list)
    remote_enabled: bool = False
    remote_host: str | None = None
    remote_user: str | None = None
    remote_docker_model_root: str | None = None
    remote_ssh_port: int = 22
    remote_password: str | None = None
    use_tmux: bool = True
    monitor: bool = True
    replace_session: bool = False
    poll_interval: float = 0.5
    dashboard_mode: str = "terminal"
    ui_host: str = "127.0.0.1"
    ui_port: int = 8765
    ui_log_lines: int = 300
    bridge_entries: list[BridgeLaunchEntry] = field(default_factory=list)
    bridge_enabled: bool = True
    bridge_config_path: str | None = None


@dataclass(slots=True)
class ActionTemplate:
    template_name: str
    action_name: str
    rotation_constraint: tuple[float, float, float]
    pose_relative: list[Pose]
    gripper_state: list[float]
    time: list[float]

    @property
    def step_count(self) -> int:
        return len(self.pose_relative)


@dataclass(slots=True)
class ActionRule:
    current_state: set[str] = field(default_factory=set)
    goal: set[str] = field(default_factory=set)
    requested_action: set[str] = field(default_factory=set)
    action: str = ""

    def matches(
        self,
        current_state: str | None,
        goal: str | None,
        requested_action: str | None,
    ) -> bool:
        return (
            self._match_value(self.current_state, current_state)
            and self._match_value(self.goal, goal)
            and self._match_value(self.requested_action, requested_action)
        )

    @staticmethod
    def _match_value(expected: set[str], actual: str | None) -> bool:
        if not expected or "*" in expected:
            return True
        if not actual:
            return False
        return normalize_token(actual) in expected


@dataclass(slots=True)
class ObjectProfile:
    object_type: str
    display_name: str
    template_key: str
    aliases: set[str] = field(default_factory=set)
    attributes: dict[str, Any] = field(default_factory=dict)
    affordances: set[str] = field(default_factory=set)
    default_state: str = "unknown"
    state_aliases: dict[str, set[str]] = field(default_factory=dict)
    action_rules: list[ActionRule] = field(default_factory=list)

    def normalize_state(self, raw_state: str | None) -> str:
        token = normalize_token(raw_state)
        if not token:
            return self.default_state

        for canonical_state, aliases in self.state_aliases.items():
            if token == canonical_state or token in aliases:
                return canonical_state
        return token

    def matches_name(self, name: str | None) -> bool:
        token = normalize_token(name)
        if not token:
            return False
        return token == self.object_type or token in self.aliases

    def supports_action(self, action_name: str | None) -> bool:
        token = normalize_token(action_name)
        if not token:
            return False
        if not self.affordances:
            return True
        return token in self.affordances
