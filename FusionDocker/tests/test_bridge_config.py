from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from fusion_docker.config import load_bridge_config


class BridgeConfigTest(unittest.TestCase):
    def test_load_bridge_config_supports_client_key(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            config_path = Path(tmp_dir) / "ClientConfig.yaml"
            config_path.write_text(
                "\n".join(
                    [
                        "client:",
                        "  sam3_server_addr: tcp://127.0.0.1:5554",
                        "  flowpose_server_addr: tcp://127.0.0.1:5555",
                        "  listen_port: 5566",
                        "  prompts:",
                        "    - drawer",
                        "    - cup",
                    ]
                ),
                encoding="utf-8",
            )

            config = load_bridge_config(config_path)

        self.assertEqual(config.sam3_server_addr, "tcp://127.0.0.1:5554")
        self.assertEqual(config.flowpose_server_addr, "tcp://127.0.0.1:5555")
        self.assertEqual(config.listen_port, 5566)
        self.assertEqual(config.prompts, ["drawer", "cup"])

    def test_load_bridge_config_keeps_legacy_downstream_key_compatible(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            config_path = Path(tmp_dir) / "bridge.yaml"
            config_path.write_text(
                "\n".join(
                    [
                        "bridge:",
                        "  sam3_server_addr: tcp://127.0.0.1:5554",
                        "  downstream_server_addr: tcp://127.0.0.1:5555",
                    ]
                ),
                encoding="utf-8",
            )

            config = load_bridge_config(config_path)

        self.assertEqual(config.flowpose_server_addr, "tcp://127.0.0.1:5555")
        self.assertEqual(config.downstream_server_addr, "tcp://127.0.0.1:5555")

    def test_load_bridge_config_supports_zmq_source_mode(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            config_path = Path(tmp_dir) / "bridge_zmq.yaml"
            config_path.write_text(
                "\n".join(
                    [
                        "bridge:",
                        "  source_mode: zmq_source",
                        "  sam3_server_addr: tcp://127.0.0.1:5555",
                        "  flowpose_server_addr: tcp://127.0.0.1:6666",
                        "  zmq_source_addr: tcp://127.0.0.1:6000",
                        "  zmq_timeout_sec: 2.5",
                    ]
                ),
                encoding="utf-8",
            )

            config = load_bridge_config(config_path)

        self.assertEqual(config.source_mode, "zmq_source")
        self.assertEqual(config.sam3_server_addr, "tcp://127.0.0.1:5555")
        self.assertEqual(config.flowpose_server_addr, "tcp://127.0.0.1:6666")
        self.assertEqual(config.zmq_source_addr, "tcp://127.0.0.1:6000")
        self.assertEqual(config.zmq_timeout_sec, 2.5)

    def test_load_bridge_config_supports_siglip_flowpose_sidecar_and_legacy_yomni_alias(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            config_path = Path(tmp_dir) / "bridge_multi.yaml"
            config_path.write_text(
                "\n".join(
                    [
                        "bridge:",
                        "  source_mode: zmq_source",
                        "  rgbd_endpoint: tcp://127.0.0.1:4444",
                        "  run_sam3_flowpose: false",
                        "  siglip2_ip: 127.0.0.1",
                        "  siglip2_port: 7777",
                        "  flowpose_sidecar_server_addr: tcp://127.0.0.1:5556",
                    ]
                ),
                encoding="utf-8",
            )

            config = load_bridge_config(config_path)

        self.assertEqual(config.source_mode, "zmq_source")
        self.assertEqual(config.zmq_source_addr, "tcp://127.0.0.1:4444")
        self.assertFalse(config.run_sam3_flowpose)
        self.assertEqual(config.siglip2_server_addr, "tcp://127.0.0.1:7777")
        self.assertEqual(config.siglip_server_addr, "tcp://127.0.0.1:7777")
        self.assertEqual(config.flowpose_sidecar_server_addr, "tcp://127.0.0.1:5556")
        self.assertEqual(config.yomni_server_addr, "tcp://127.0.0.1:5556")

    def test_load_bridge_config_parses_input_mapping(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            config_path = Path(tmp_dir) / "bridge_mapping.yaml"
            config_path.write_text(
                "\n".join(
                    [
                        "bridge:",
                        "  source_mode: zmq_source",
                        "  zmq_source_addr: tcp://127.0.0.1:4444",
                        "  run_sam3_flowpose: false",
                        "  siglip2_server_addr: tcp://127.0.0.1:7777",
                        "  input_mapping:",
                        "    rgb_keys: [color_image, image]",
                        "    depth_keys: [depth]",
                        "    nested_payload_keys: [payload, frame]",
                    ]
                ),
                encoding="utf-8",
            )

            config = load_bridge_config(config_path)

        self.assertEqual(config.input_mapping.rgb_keys, ("color_image", "image"))
        self.assertEqual(config.input_mapping.depth_keys, ("depth",))
        self.assertEqual(config.input_mapping.nested_payload_keys, ("payload", "frame"))

    def test_load_bridge_config_parses_result_pub_fields(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            config_path = Path(tmp_dir) / "bridge_pub.yaml"
            config_path.write_text(
                "\n".join(
                    [
                        "bridge:",
                        "  run_sam3_flowpose: false",
                        "  siglip2_server_addr: tcp://127.0.0.1:7777",
                        "  result_pub_addr: tcp://0.0.0.0:8899",
                        "  result_pub_frame_id: camera_rgb_link",
                        "  result_siglip_topic: /siglip2/result",
                        "  result_siglip_vote_window: 7",
                        "  result_siglip_sync_with_pose: true",
                        "  result_siglip_pose_wait_timeout_sec: 1.25",
                        "  result_tf_topic: /tf",
                    ]
                ),
                encoding="utf-8",
            )

            config = load_bridge_config(config_path)

        self.assertEqual(config.result_pub_addr, "tcp://0.0.0.0:8899")
        self.assertEqual(config.result_pub_frame_id, "camera_rgb_link")
        self.assertEqual(config.result_siglip_topic, "/siglip2/result")
        self.assertEqual(config.result_siglip_vote_window, 7)
        self.assertTrue(config.result_siglip_sync_with_pose)
        self.assertAlmostEqual(config.result_siglip_pose_wait_timeout_sec, 1.25)
        self.assertEqual(config.result_tf_topic, "/tf")

    def test_load_bridge_config_supports_split_yaml_sections(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            config_path = Path(tmp_dir) / "bridge_split.yaml"
            config_path.write_text(
                "\n".join(
                    [
                        "bridge:",
                        "  type: multi_zmq_pub_bridge",
                        "  source_mode: zmq_source",
                        "  zmq_source_addr: tcp://127.0.0.1:4444",
                        "  prompts: [toy car, cup]",
                        "sam3:",
                        "  server_addr: tcp://127.0.0.1:5562",
                        "  timeout_ms: 5000",
                        "flowpose:",
                        "  server_addr: tcp://127.0.0.1:6667",
                        "siglip2:",
                        "  server_addr: tcp://127.0.0.1:7777",
                        "publisher:",
                        "  result_pub_addr: tcp://0.0.0.0:8899",
                        "  result_siglip_topic: /siglip2/result",
                        "  result_tf_topic: /tf",
                    ]
                ),
                encoding="utf-8",
            )

            config = load_bridge_config(config_path)

        self.assertEqual(config.sam3_server_addr, "tcp://127.0.0.1:5562")
        self.assertEqual(config.sam3_timeout_ms, 5000)
        self.assertEqual(config.flowpose_server_addr, "tcp://127.0.0.1:6667")
        self.assertEqual(config.siglip2_server_addr, "tcp://127.0.0.1:7777")
        self.assertEqual(config.result_pub_addr, "tcp://0.0.0.0:8899")
        self.assertEqual(config.result_siglip_topic, "/siglip2/result")
        self.assertEqual(config.result_tf_topic, "/tf")
        self.assertEqual(config.prompts, ["toy car", "cup"])

    def test_load_bridge_config_parses_schema_check(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            docker_root = tmp_path / "DockerModel"
            docker_root.mkdir(parents=True, exist_ok=True)
            config_path = tmp_path / "bridge_schema_check.yaml"
            config_path.write_text(
                "\n".join(
                    [
                        "bridge:",
                        "  source_mode: zmq_source",
                        "  zmq_source_addr: tcp://127.0.0.1:4444",
                        "  run_sam3_flowpose: false",
                        "  siglip2_server_addr: tcp://127.0.0.1:7777",
                        "  schema_check:",
                        "    enabled: true",
                        "    strict: true",
                        "    docker_model_root: ./DockerModel",
                        "    links:",
                        "      - from: Sam3Docker",
                        "        to: FlowPoseDocker",
                        "        provides: [rgb_image, depth_image]",
                        "        field_map:",
                        "          combined_mask: combined_mask",
                    ]
                ),
                encoding="utf-8",
            )

            config = load_bridge_config(config_path)

        self.assertTrue(config.schema_check.enabled)
        self.assertTrue(config.schema_check.strict)
        self.assertTrue(config.schema_check.docker_model_root.endswith("DockerModel"))
        self.assertEqual(len(config.schema_check.links), 1)
        self.assertEqual(config.schema_check.links[0].from_docker, "Sam3Docker")
        self.assertEqual(config.schema_check.links[0].to_docker, "FlowPoseDocker")
        self.assertEqual(config.schema_check.links[0].provides, ("rgb_image", "depth_image"))
        self.assertEqual(
            config.schema_check.links[0].field_map,
            {"combined_mask": "combined_mask"},
        )


if __name__ == "__main__":
    unittest.main()
