from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from fusion_docker.bridge_scaffold import (
    canonical_bridge_kind,
    canonical_bridge_module_name,
    create_bridge_scaffold,
)
from fusion_docker.cli import _build_parser


class BridgeScaffoldTest(unittest.TestCase):
    def test_canonical_bridge_name_helpers(self) -> None:
        self.assertEqual(canonical_bridge_module_name("My Bridge"), "my_bridge")
        self.assertEqual(canonical_bridge_kind("My Bridge"), "my_bridge")

    def test_create_bridge_scaffold_generates_module_config_and_registry(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            bridges_dir = root / "src" / "fusion_docker" / "bridges"
            configs_dir = root / "configs"
            bridges_dir.mkdir(parents=True, exist_ok=True)
            configs_dir.mkdir(parents=True, exist_ok=True)
            registry_path = bridges_dir / "__init__.py"
            registry_path.write_text(
                "\n".join(
                    [
                        "from __future__ import annotations",
                        "",
                        "from fusion_docker.bridges.registry import register_bridge",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            result = create_bridge_scaffold(
                name="demo bridge",
                project_root=root,
            )

            self.assertTrue(result.module_path.exists())
            self.assertTrue(result.config_path.exists())
            registry_text = registry_path.read_text(encoding="utf-8")
            self.assertIn(
                "from fusion_docker.bridges.demo_bridge import DEMO_BRIDGE",
                registry_text,
            )
            self.assertIn("register_bridge(DEMO_BRIDGE)", registry_text)
            self.assertIn('kind="demo_bridge"', result.module_path.read_text(encoding="utf-8"))
            self.assertIn("type: demo_bridge", result.config_path.read_text(encoding="utf-8"))

    def test_create_bridge_scaffold_requires_force_to_overwrite(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            bridges_dir = root / "src" / "fusion_docker" / "bridges"
            configs_dir = root / "configs"
            bridges_dir.mkdir(parents=True, exist_ok=True)
            configs_dir.mkdir(parents=True, exist_ok=True)
            (bridges_dir / "__init__.py").write_text(
                "\n".join(
                    [
                        "from __future__ import annotations",
                        "",
                        "from fusion_docker.bridges.registry import register_bridge",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            create_bridge_scaffold(name="demo", project_root=root)

            with self.assertRaises(FileExistsError):
                create_bridge_scaffold(name="demo", project_root=root)

            result = create_bridge_scaffold(name="demo", project_root=root, force=True)
            self.assertTrue(result.updated_files)

    def test_cli_parser_supports_create_bridge_command(self) -> None:
        parser = _build_parser()
        args = parser.parse_args(
            [
                "create-bridge",
                "demo",
                "--project-root",
                "/tmp/project",
                "--force",
            ]
        )
        self.assertEqual(args.command, "create-bridge")
        self.assertEqual(args.name, "demo")
        self.assertEqual(args.project_root, "/tmp/project")
        self.assertTrue(args.force)


if __name__ == "__main__":
    unittest.main()
