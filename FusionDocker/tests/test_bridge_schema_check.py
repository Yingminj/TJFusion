from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from fusion_docker.bridge_service import run_schema_connectivity_check
from fusion_docker.models import (
    BridgeSchemaCheckConfig,
    BridgeSchemaLink,
    BridgeServiceConfig,
)


def _write_schema(path: Path, required: list[str], properties: list[str]) -> None:
    payload = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "type": "object",
        "required": required,
        "properties": {field: {"type": "string"} for field in properties},
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


class BridgeSchemaCheckTest(unittest.TestCase):
    def test_schema_check_passes_with_field_map_and_provides(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            sam3_rf = root / "Sam3Docker" / "RequestFormat"
            flow_rf = root / "FlowPoseDocker" / "RequestFormat"
            sam3_rf.mkdir(parents=True, exist_ok=True)
            flow_rf.mkdir(parents=True, exist_ok=True)

            _write_schema(
                sam3_rf / "input.schema.json",
                required=["rgb_image", "prompts"],
                properties=["rgb_image", "prompts"],
            )
            _write_schema(
                sam3_rf / "output.schema.json",
                required=["mask_png_b64", "obj_ids", "class_names"],
                properties=["mask_png_b64", "obj_ids", "class_names"],
            )
            _write_schema(
                flow_rf / "input.schema.json",
                required=["rgb_image", "depth_image", "combined_mask", "obj_ids", "class_names"],
                properties=["rgb_image", "depth_image", "combined_mask", "obj_ids", "class_names"],
            )
            _write_schema(
                flow_rf / "output.schema.json",
                required=["status"],
                properties=["status", "objects"],
            )

            config = BridgeServiceConfig(
                sam3_server_addr="tcp://127.0.0.1:5555",
                flowpose_server_addr="tcp://127.0.0.1:6666",
                schema_check=BridgeSchemaCheckConfig(
                    enabled=True,
                    strict=True,
                    docker_model_root=str(root),
                    links=[
                        BridgeSchemaLink(
                            from_docker="Sam3Docker",
                            to_docker="FlowPoseDocker",
                            field_map={"combined_mask": "mask_png_b64"},
                            provides=("rgb_image", "depth_image"),
                        )
                    ],
                ),
            )

            run_schema_connectivity_check(config)

    def test_schema_check_strict_fails_on_missing_fields(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            sam3_rf = root / "Sam3Docker" / "RequestFormat"
            flow_rf = root / "FlowPoseDocker" / "RequestFormat"
            sam3_rf.mkdir(parents=True, exist_ok=True)
            flow_rf.mkdir(parents=True, exist_ok=True)

            _write_schema(
                sam3_rf / "input.schema.json",
                required=["rgb_image"],
                properties=["rgb_image"],
            )
            _write_schema(
                sam3_rf / "output.schema.json",
                required=["obj_ids"],
                properties=["obj_ids"],
            )
            _write_schema(
                flow_rf / "input.schema.json",
                required=["combined_mask"],
                properties=["combined_mask"],
            )
            _write_schema(
                flow_rf / "output.schema.json",
                required=["status"],
                properties=["status"],
            )

            config = BridgeServiceConfig(
                sam3_server_addr="tcp://127.0.0.1:5555",
                flowpose_server_addr="tcp://127.0.0.1:6666",
                schema_check=BridgeSchemaCheckConfig(
                    enabled=True,
                    strict=True,
                    docker_model_root=str(root),
                    links=[BridgeSchemaLink(from_docker="Sam3Docker", to_docker="FlowPoseDocker")],
                ),
            )

            with self.assertRaises(RuntimeError):
                run_schema_connectivity_check(config)


if __name__ == "__main__":
    unittest.main()
