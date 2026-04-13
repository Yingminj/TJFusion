from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from fusion_docker.docker_launcher import DockerRunTarget
from fusion_docker.docker_port_config import read_docker_configured_port


class DockerPortConfigTest(unittest.TestCase):
    def test_read_docker_configured_port_from_config_yaml(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            folder = Path(tmp_dir) / "Sam3Docker"
            folder.mkdir()
            (folder / "run.sh").write_text("#!/usr/bin/env bash\n", encoding="utf-8")
            (folder / "config.yaml").write_text(
                "\n".join(
                    [
                        "docker:",
                        "  container_name: sam3_container",
                        "server:",
                        "  host: 0.0.0.0",
                        "  port: 5555",
                    ]
                ),
                encoding="utf-8",
            )

            info = read_docker_configured_port(
                DockerRunTarget(
                    folder_name="Sam3Docker",
                    folder_path=folder,
                    run_script_path=folder / "run.sh",
                    relative_folder="Sam3Docker",
                )
            )

        self.assertEqual(info.docker_name, "Sam3Docker")
        self.assertEqual(info.container_name, "sam3_container")
        self.assertEqual(info.host, "0.0.0.0")
        self.assertEqual(info.port, 5555)


if __name__ == "__main__":
    unittest.main()
