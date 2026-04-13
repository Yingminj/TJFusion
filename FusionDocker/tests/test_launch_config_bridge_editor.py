from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from fusion_docker.cli import _build_parser
from fusion_docker.launch_config_bridge_editor import add_bridge_to_launch_config


class LaunchConfigBridgeEditorTest(unittest.TestCase):
    def test_add_bridge_to_launch_config_appends_new_bridge_entry(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            config_path = Path(tmp_dir) / "docker_launch.yaml"
            config_path.write_text(
                "\n".join(
                    [
                        "docker_launcher:",
                        "  docker_model_root: /tmp/DockerModel",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            result = add_bridge_to_launch_config(
                launch_config_path=config_path,
                bridge_name="MyBridge",
                bridge_config_path="configs/bridge.my_bridge.yaml",
            )

            text = config_path.read_text(encoding="utf-8")

        self.assertTrue(result.created)
        self.assertFalse(result.updated)
        self.assertEqual(result.bridge_count, 1)
        self.assertIn("bridges:", text)
        self.assertIn("name: MyBridge", text)
        self.assertIn("config: configs/bridge.my_bridge.yaml", text)

    def test_add_bridge_to_launch_config_updates_existing_entry_with_force(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            config_path = Path(tmp_dir) / "docker_launch.yaml"
            config_path.write_text(
                "\n".join(
                    [
                        "docker_launcher:",
                        "  bridges:",
                        "    - name: MyBridge",
                        "      enabled: true",
                        "      config: configs/bridge.old.yaml",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            result = add_bridge_to_launch_config(
                launch_config_path=config_path,
                bridge_name="MyBridge",
                bridge_config_path="configs/bridge.new.yaml",
                enabled=False,
                force=True,
            )

            text = config_path.read_text(encoding="utf-8")

        self.assertFalse(result.created)
        self.assertTrue(result.updated)
        self.assertIn("config: configs/bridge.new.yaml", text)
        self.assertIn("enabled: false", text)

    def test_add_bridge_to_launch_config_rejects_conflicting_existing_entry_without_force(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            config_path = Path(tmp_dir) / "docker_launch.yaml"
            config_path.write_text(
                "\n".join(
                    [
                        "docker_launcher:",
                        "  bridges:",
                        "    - name: MyBridge",
                        "      enabled: true",
                        "      config: configs/bridge.old.yaml",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ValueError, "Use --force"):
                add_bridge_to_launch_config(
                    launch_config_path=config_path,
                    bridge_name="MyBridge",
                    bridge_config_path="configs/bridge.new.yaml",
                )

    def test_cli_parser_supports_add_bridge_to_ui_command(self) -> None:
        parser = _build_parser()
        args = parser.parse_args(
            [
                "add-bridge-to-ui",
                "MyBridge",
                "--bridge-config",
                "configs/bridge.my_bridge.yaml",
                "--launch-config",
                "configs/docker_launch.yaml",
                "--force",
            ]
        )

        self.assertEqual(args.command, "add-bridge-to-ui")
        self.assertEqual(args.name, "MyBridge")
        self.assertEqual(args.bridge_config, "configs/bridge.my_bridge.yaml")
        self.assertEqual(args.launch_config, "configs/docker_launch.yaml")
        self.assertTrue(args.force)


if __name__ == "__main__":
    unittest.main()
