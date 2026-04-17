from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from fusion_docker.config import load_docker_launch_config


class DockerLaunchConfigTest(unittest.TestCase):
    def test_load_docker_launch_config_supports_grouped_entries(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            config_path = Path(tmp_dir) / "docker_launch.yaml"
            config_path.write_text(
                "\n".join(
                    [
                        "docker_launcher:",
                        "  docker_model_root: /tmp/DockerModel",
                        "  tmux: true",
                        "  monitor: false",
                        "  poll_interval: 0.8",
                        "  dashboard:",
                        "    mode: web",
                        "    host: 0.0.0.0",
                        "    port: 8899",
                        "    log_lines: 420",
                        "  bridges:",
                        "    - name: VisionBridge",
                        "      enabled: true",
                        "      config: configs/bridge.sam3_flowpose.yaml",
                        "    - name: ActionBridge",
                        "      enabled: false",
                        "      config: configs/bridge.action.yaml",
                        "  groups:",
                        "    vision:",
                        "      - Sam3Docker",
                        "      - RealSenseDocker",
                        "    inference:",
                        "      - name: FlowPoseDocker",
                        "        enabled: true",
                        "      - name: DebugDocker",
                        "        enabled: false",
                        "    action:",
                        "      - MarvinDocker",
                    ]
                ),
                encoding="utf-8",
            )

            config = load_docker_launch_config(config_path)

        self.assertEqual(config.docker_model_root, "/tmp/DockerModel")
        self.assertEqual(
            config.docker_names,
            ["Sam3Docker", "RealSenseDocker", "FlowPoseDocker", "MarvinDocker"],
        )
        self.assertEqual(
            config.docker_groups,
            {
                "vision": ["Sam3Docker", "RealSenseDocker"],
                "inference": ["FlowPoseDocker"],
                "action": ["MarvinDocker"],
            },
        )
        self.assertTrue(config.use_tmux)
        self.assertFalse(config.monitor)
        self.assertEqual(config.poll_interval, 0.8)
        self.assertEqual(config.dashboard_mode, "web")
        self.assertEqual(config.ui_host, "0.0.0.0")
        self.assertEqual(config.ui_port, 8899)
        self.assertEqual(config.ui_log_lines, 420)
        self.assertTrue(config.bridge_enabled)
        self.assertEqual(config.bridge_config_path, "configs/bridge.sam3_flowpose.yaml")
        self.assertEqual(
            [(entry.name, entry.enabled, entry.config_path) for entry in config.bridge_entries],
            [
                ("VisionBridge", True, "configs/bridge.sam3_flowpose.yaml"),
                ("ActionBridge", False, "configs/bridge.action.yaml"),
            ],
        )

    def test_load_docker_launch_config_rejects_invalid_dashboard_mode(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            config_path = Path(tmp_dir) / "docker_launch.yaml"
            config_path.write_text(
                "\n".join(
                    [
                        "docker_launcher:",
                        "  dashboard:",
                        "    mode: hologram",
                    ]
                ),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ValueError, "dashboard.mode"):
                load_docker_launch_config(config_path)

    def test_load_docker_launch_config_supports_remote_settings(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            config_path = Path(tmp_dir) / "docker_launch.yaml"
            config_path.write_text(
                "\n".join(
                    [
                        "docker_launcher:",
                        "  remote:",
                        "    enabled: true",
                        "    host: 192.168.1.88",
                        "    user: robot",
                        "    docker_model_root: /home/robot/DockerModel",
                        "    ssh_port: 2222",
                        "    password: robotpass",
                    ]
                ),
                encoding="utf-8",
            )

            config = load_docker_launch_config(config_path)

        self.assertTrue(config.remote_enabled)
        self.assertEqual(config.remote_host, "192.168.1.88")
        self.assertEqual(config.remote_user, "robot")
        self.assertEqual(config.remote_docker_model_root, "/home/robot/DockerModel")
        self.assertEqual(config.remote_ssh_port, 2222)
        self.assertEqual(config.remote_password, "robotpass")

    def test_load_docker_launch_config_supports_per_docker_targets(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            config_path = Path(tmp_dir) / "docker_launch.yaml"
            config_path.write_text(
                "\n".join(
                    [
                        "docker_launcher:",
                        "  docker_model_root: /home/yang/Desktop/DockerModel",
                        "  docker_targets:",
                        "    - name: Sam3Docker",
                        "      group: vision",
                        "      location: local",
                        "    - name: FlowPoseDocker",
                        "      group: vision",
                        "      location: remote",
                        "      remote:",
                        "        host: 192.168.1.88",
                        "        user: robot",
                        "        docker_model_root: /home/robot/DockerModel",
                        "        ssh_port: 2222",
                        "        password: robotpass",
                    ]
                ),
                encoding="utf-8",
            )

            config = load_docker_launch_config(config_path)

        self.assertEqual(config.docker_names, ["Sam3Docker", "FlowPoseDocker"])
        self.assertEqual(config.docker_groups["vision"], ["Sam3Docker", "FlowPoseDocker"])
        self.assertEqual(len(config.docker_targets), 2)
        self.assertEqual(config.docker_targets[0].location, "local")
        self.assertEqual(config.docker_targets[0].docker_model_root, "/home/yang/Desktop/DockerModel")
        self.assertEqual(config.docker_targets[1].location, "remote")
        self.assertEqual(config.docker_targets[1].remote_host, "192.168.1.88")
        self.assertEqual(config.docker_targets[1].remote_user, "robot")
        self.assertEqual(
            config.docker_targets[1].remote_docker_model_root,
            "/home/robot/DockerModel",
        )
        self.assertEqual(config.docker_targets[1].remote_ssh_port, 2222)
        self.assertEqual(config.docker_targets[1].remote_password, "robotpass")

    def test_load_docker_launch_config_selected_dockers_override_default_order(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            config_path = Path(tmp_dir) / "docker_launch.yaml"
            config_path.write_text(
                "\n".join(
                    [
                        "docker_launcher:",
                        "  groups:",
                        "    vision:",
                        "      - Sam3Docker",
                        "      - FlowPoseDocker",
                        "    action:",
                        "      - MarvinDocker",
                        "  selected_dockers:",
                        "    - MarvinDocker",
                        "    - Sam3Docker",
                    ]
                ),
                encoding="utf-8",
            )

            config = load_docker_launch_config(config_path)

        self.assertEqual(config.docker_names, ["MarvinDocker", "Sam3Docker"])
        self.assertEqual(
            config.docker_groups,
            {
                "vision": ["Sam3Docker", "FlowPoseDocker"],
                "action": ["MarvinDocker"],
            },
        )

    def test_load_docker_launch_config_rejects_remote_target_without_required_fields(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            config_path = Path(tmp_dir) / "docker_launch.yaml"
            config_path.write_text(
                "\n".join(
                    [
                        "docker_launcher:",
                        "  docker_targets:",
                        "    - name: FlowPoseDocker",
                        "      location: remote",
                    ]
                ),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ValueError, "location=remote requires remote host/user/docker_model_root"):
                load_docker_launch_config(config_path)

    def test_load_docker_launch_config_accepts_localhost_alias_for_location(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            config_path = Path(tmp_dir) / "docker_launch.yaml"
            config_path.write_text(
                "\n".join(
                    [
                        "docker_launcher:",
                        "  docker_model_root: /home/yang/Desktop/DockerModel",
                        "  docker_targets:",
                        "    - name: Sam3Docker",
                        "      group: vision",
                        "      location: localhost",
                    ]
                ),
                encoding="utf-8",
            )

            config = load_docker_launch_config(config_path)

        self.assertEqual(len(config.docker_targets), 1)
        self.assertEqual(config.docker_targets[0].location, "local")

    def test_load_docker_launch_config_parses_bridge_schema_check_overrides(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            config_path = Path(tmp_dir) / "docker_launch.yaml"
            config_path.write_text(
                "\n".join(
                    [
                        "docker_launcher:",
                        "  bridge_schema_check:",
                        "    enabled: true",
                        "    strict: false",
                        "    docker_model_root: ./DockerModel",
                        "    links:",
                        "      - from: __source__",
                        "        to: Sam3Docker",
                        "        provides: [prompts]",
                        "  bridges:",
                        "    - name: MainBridge",
                        "      enabled: true",
                        "      config: configs/bridge.local.yaml",
                        "    - name: ActionBridge",
                        "      enabled: true",
                        "      config: configs/bridge.action.yaml",
                        "      schema_check:",
                        "        enabled: true",
                        "        strict: true",
                        "        docker_model_root: /abs/DockerModel",
                        "        links:",
                        "          - from: Sam3Docker",
                        "            to: FlowPoseDocker",
                    ]
                ),
                encoding="utf-8",
            )

            config = load_docker_launch_config(config_path)

        self.assertEqual(len(config.bridge_entries), 2)
        main_schema = config.bridge_entries[0].schema_check
        self.assertIsNotNone(main_schema)
        assert main_schema is not None
        self.assertTrue(main_schema.enabled)
        self.assertFalse(main_schema.strict)
        self.assertTrue(main_schema.docker_model_root.endswith("DockerModel"))
        self.assertEqual(len(main_schema.links), 1)
        self.assertEqual(main_schema.links[0].to_docker, "Sam3Docker")

        action_schema = config.bridge_entries[1].schema_check
        self.assertIsNotNone(action_schema)
        assert action_schema is not None
        self.assertTrue(action_schema.enabled)
        self.assertTrue(action_schema.strict)
        self.assertEqual(action_schema.docker_model_root, "/abs/DockerModel")
        self.assertEqual(len(action_schema.links), 1)
        self.assertEqual(action_schema.links[0].from_docker, "Sam3Docker")
        self.assertEqual(action_schema.links[0].to_docker, "FlowPoseDocker")


if __name__ == "__main__":
    unittest.main()
