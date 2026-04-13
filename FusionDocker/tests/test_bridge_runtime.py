from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import fusion_docker.bridges  # noqa: F401
from fusion_docker.bridge_runtime import apply_bridge_cli_overrides
from fusion_docker.bridges.profiled import BridgeProfile, create_profiled_bridge_definition, load_profiled_bridge_config
from fusion_docker.bridges.registry import (
    detect_bridge_type,
    get_bridge_definition,
    list_bridges,
    load_bridge_runtime,
)
from fusion_docker.models import BridgeServiceConfig


class BridgeRuntimeTest(unittest.TestCase):
    def test_detect_bridge_type_defaults_to_sam3_flowpose(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            config_path = Path(tmp_dir) / "bridge.yaml"
            config_path.write_text(
                "\n".join(
                    [
                        "bridge:",
                        "  sam3_server_addr: tcp://127.0.0.1:5554",
                        "  flowpose_server_addr: tcp://127.0.0.1:5555",
                    ]
                ),
                encoding="utf-8",
            )

            bridge_type = detect_bridge_type(config_path)

        self.assertEqual(bridge_type, "sam3_flowpose")

    def test_load_bridge_runtime_uses_registered_definition(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            config_path = Path(tmp_dir) / "bridge.yaml"
            config_path.write_text(
                "\n".join(
                    [
                        "bridge:",
                        "  type: sam3_flowpose",
                        "  sam3_server_addr: tcp://127.0.0.1:5554",
                        "  flowpose_server_addr: tcp://127.0.0.1:5555",
                    ]
                ),
                encoding="utf-8",
            )

            definition, config = load_bridge_runtime(config_path)

        self.assertEqual(definition.kind, "sam3_flowpose")
        self.assertIsInstance(config, BridgeServiceConfig)

    def test_apply_bridge_cli_overrides_updates_supported_fields(self) -> None:
        config = BridgeServiceConfig(
            sam3_server_addr="tcp://127.0.0.1:5554",
            flowpose_server_addr="tcp://127.0.0.1:5555",
        )

        apply_bridge_cli_overrides(
            config,
            req_timeout_ms=3000,
            rgb_jpg_quality=92,
            listen_host="127.0.0.1",
            listen_port=6600,
        )

        self.assertEqual(config.req_timeout_ms, 3000)
        self.assertEqual(config.rgb_jpg_quality, 92)
        self.assertEqual(config.listen_host, "127.0.0.1")
        self.assertEqual(config.listen_port, 6600)

    def test_load_bridge_runtime_supports_sam3_flowpose_type(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            config_path = Path(tmp_dir) / "bridge.yaml"
            config_path.write_text(
                "\n".join(
                    [
                        "bridge:",
                        "  type: sam3_flowpose",
                        "  source_mode: zmq_source",
                        "  zmq_source_addr: tcp://127.0.0.1:4444",
                        "  sam3_server_addr: tcp://127.0.0.1:5554",
                        "  flowpose_server_addr: tcp://127.0.0.1:5555",
                        "  siglip2_server_addr: tcp://127.0.0.1:7777",
                    ]
                ),
                encoding="utf-8",
            )

            definition, config = load_bridge_runtime(config_path)

        self.assertEqual(definition.kind, "sam3_flowpose")
        self.assertTrue(config.run_sam3_flowpose)
        self.assertEqual(config.siglip2_server_addr, "")

    def test_load_bridge_runtime_supports_siglip2_type(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            config_path = Path(tmp_dir) / "bridge.yaml"
            config_path.write_text(
                "\n".join(
                    [
                        "bridge:",
                        "  type: siglip2_bridge",
                        "  source_mode: zmq_source",
                        "  zmq_source_addr: tcp://127.0.0.1:4444",
                        "  siglip2_server_addr: tcp://127.0.0.1:7777",
                        "  flowpose_sidecar_server_addr: tcp://127.0.0.1:5556",
                        "  prompts: [toy car]",
                        "  output_json: response_siglip2.json",
                    ]
                ),
                encoding="utf-8",
            )

            definition, config = load_bridge_runtime(config_path)

        self.assertEqual(definition.kind, "siglip2_bridge")
        self.assertFalse(config.run_sam3_flowpose)
        self.assertEqual(config.sam3_server_addr, "")
        self.assertEqual(config.flowpose_sidecar_server_addr, "")
        self.assertEqual(config.prompts, [])
        self.assertEqual(config.output_json, "")

    def test_load_bridge_runtime_supports_multi_zmq_pub_type(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            config_path = Path(tmp_dir) / "bridge.yaml"
            config_path.write_text(
                "\n".join(
                    [
                        "bridge:",
                        "  type: multi_zmq_pub_bridge",
                        "  source_mode: zmq_source",
                        "  zmq_source_addr: tcp://127.0.0.1:4444",
                        "  sam3_server_addr: tcp://127.0.0.1:5554",
                        "  flowpose_server_addr: tcp://127.0.0.1:5555",
                        "  siglip2_server_addr: tcp://127.0.0.1:7777",
                        "  result_pub_addr: tcp://0.0.0.0:8899",
                        "  result_siglip_topic: /siglip2/result",
                        "  result_tf_topic: /tf",
                        "  prompts: [toy car]",
                    ]
                ),
                encoding="utf-8",
            )

            definition, config = load_bridge_runtime(config_path)

        self.assertEqual(definition.kind, "multi_zmq_pub_bridge")
        self.assertTrue(config.run_sam3_flowpose)
        self.assertEqual(config.result_pub_addr, "tcp://0.0.0.0:8899")
        self.assertEqual(config.result_siglip_topic, "/siglip2/result")
        self.assertEqual(config.result_tf_topic, "/tf")

    def test_profiled_bridge_definition_reuses_shared_runner_contract(self) -> None:
        bridge_definition = create_profiled_bridge_definition(
            BridgeProfile(
                kind="custom_bridge",
                description="custom",
                aliases=("custom",),
            )
        )

        self.assertEqual(bridge_definition.kind, "custom_bridge")
        self.assertTrue(bridge_definition.supports("custom"))

    def test_load_profiled_bridge_config_applies_profile_mutation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            config_path = Path(tmp_dir) / "bridge.yaml"
            config_path.write_text(
                "\n".join(
                    [
                        "bridge:",
                        "  sam3_server_addr: tcp://127.0.0.1:5554",
                        "  flowpose_server_addr: tcp://127.0.0.1:5555",
                        "  siglip2_server_addr: tcp://127.0.0.1:7777",
                    ]
                ),
                encoding="utf-8",
            )
            profile = BridgeProfile(
                kind="custom_bridge",
                description="custom",
                mutate_config=lambda config: _disable_side_branches(config),
            )

            config = load_profiled_bridge_config(config_path, profile)

        self.assertEqual(config.siglip2_server_addr, "")

    def test_list_bridges_includes_builtin_bridge_types(self) -> None:
        bridge_kinds = {definition.kind for definition in list_bridges()}

        self.assertTrue(
            {
                "sam3_flowpose",
                "siglip2_bridge",
                "multi_zmq_pub_bridge",
            }.issubset(bridge_kinds)
        )


def _disable_side_branches(config: BridgeServiceConfig) -> BridgeServiceConfig:
    config.siglip2_server_addr = ""
    return config


if __name__ == "__main__":
    unittest.main()
