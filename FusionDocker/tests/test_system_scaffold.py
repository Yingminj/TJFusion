from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from fusion_docker.system_scaffold import (
    canonical_docker_folder_name,
    canonical_docker_image_name,
    create_system_scaffold,
)
from fusion_docker.cli import _build_parser


class SystemScaffoldTest(unittest.TestCase):
    def test_canonical_name_helpers(self) -> None:
        self.assertEqual(canonical_docker_folder_name("ros"), "RosDocker")
        self.assertEqual(canonical_docker_folder_name("Flow Pose Docker"), "FlowPoseDocker")
        self.assertEqual(canonical_docker_image_name("Flow Pose Docker"), "flow_pose")

    def test_create_system_scaffold_generates_expected_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            result = create_system_scaffold(
                name="ros",
                docker_model_root=root,
                server_host="0.0.0.0",
                server_port=5599,
            )

            target = (root / "RosDocker").resolve()
            self.assertEqual(result.folder_path.resolve(), target)
            self.assertTrue((target / "Dockerfile").exists())
            self.assertTrue((target / "run.sh").exists())
            self.assertTrue((target / "build.sh").exists())
            self.assertTrue((target / "Server").is_dir())
            self.assertTrue((target / "Server" / "server.py").exists())
            self.assertTrue((target / "RequestFormat" / "input.schema.json").exists())
            self.assertTrue((target / "RequestFormat" / "output.schema.json").exists())

            config_text = (target / "config.yaml").read_text(encoding="utf-8")
            self.assertIn('image: "ros"', config_text)
            self.assertIn('container_name: "${image}_tmp"', config_text)
            self.assertIn("port: 5599", config_text)

            self.assertTrue(os.access(target / "run.sh", os.X_OK))
            self.assertTrue(os.access(target / "build.sh", os.X_OK))

    def test_create_system_scaffold_requires_force_to_overwrite(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            create_system_scaffold(
                name="ros",
                docker_model_root=root,
            )

            with self.assertRaises(FileExistsError):
                create_system_scaffold(
                    name="ros",
                    docker_model_root=root,
                )

            result = create_system_scaffold(
                name="ros",
                docker_model_root=root,
                force=True,
            )
            self.assertTrue(result.updated_files)

    def test_cli_parser_supports_create_system_command(self) -> None:
        parser = _build_parser()
        args = parser.parse_args(
            [
                "create-system",
                "ros",
                "--docker-model-root",
                "/tmp/DockerModel",
                "--server-port",
                "5560",
                "--force",
            ]
        )
        self.assertEqual(args.command, "create-system")
        self.assertEqual(args.name, "ros")
        self.assertEqual(args.server_port, 5560)
        self.assertTrue(args.force)

    def test_cli_parser_supports_list_bridges_command(self) -> None:
        parser = _build_parser()
        args = parser.parse_args(["list-bridges"])

        self.assertEqual(args.command, "list-bridges")


if __name__ == "__main__":
    unittest.main()
