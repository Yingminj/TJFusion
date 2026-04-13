from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import re
from textwrap import dedent


@dataclass(slots=True)
class BridgeScaffoldResult:
    requested_name: str
    bridge_kind: str
    module_name: str
    module_path: Path
    config_path: Path
    registry_path: Path
    created_files: list[Path] = field(default_factory=list)
    updated_files: list[Path] = field(default_factory=list)


def create_bridge_scaffold(
    *,
    name: str,
    project_root: str | Path,
    force: bool = False,
) -> BridgeScaffoldResult:
    requested_name = str(name).strip()
    if not requested_name:
        raise ValueError("Bridge name cannot be empty.")

    module_name = canonical_bridge_module_name(requested_name)
    bridge_kind = canonical_bridge_kind(requested_name)
    project_path = Path(project_root).expanduser().resolve()
    bridges_dir = project_path / "src" / "fusion_docker" / "bridges"
    configs_dir = project_path / "configs"
    registry_path = bridges_dir / "__init__.py"

    if not bridges_dir.is_dir():
        raise FileNotFoundError(f"Bridge directory not found: {bridges_dir}")
    if not configs_dir.is_dir():
        raise FileNotFoundError(f"Config directory not found: {configs_dir}")
    if not registry_path.is_file():
        raise FileNotFoundError(f"Bridge registry file not found: {registry_path}")

    module_path = bridges_dir / f"{module_name}.py"
    config_path = configs_dir / f"bridge.{bridge_kind}.yaml"
    result = BridgeScaffoldResult(
        requested_name=requested_name,
        bridge_kind=bridge_kind,
        module_name=module_name,
        module_path=module_path,
        config_path=config_path,
        registry_path=registry_path,
    )

    _write_scaffold_file(
        module_path,
        _bridge_module_template(bridge_kind=bridge_kind),
        force=force,
        result=result,
    )
    _write_scaffold_file(
        config_path,
        _bridge_config_template(bridge_kind=bridge_kind),
        force=force,
        result=result,
    )
    _update_bridge_registry(
        registry_path=registry_path,
        module_name=module_name,
        bridge_constant_name=_bridge_constant_name(bridge_kind),
        force=force,
        result=result,
    )

    return result


def canonical_bridge_module_name(raw_name: str) -> str:
    token = re.sub(r"[^a-z0-9]+", "_", raw_name.strip().lower()).strip("_")
    if not token:
        raise ValueError("Bridge name must contain letters or numbers.")
    if token[0].isdigit():
        token = f"bridge_{token}"
    return token


def canonical_bridge_kind(raw_name: str) -> str:
    return canonical_bridge_module_name(raw_name)


def _bridge_constant_name(bridge_kind: str) -> str:
    base = bridge_kind.upper()
    if base.endswith("_BRIDGE"):
        return base
    return f"{base}_BRIDGE"


def _write_scaffold_file(
    path: Path,
    content: str,
    *,
    force: bool,
    result: BridgeScaffoldResult,
) -> None:
    existed = path.exists()
    if existed and not force:
        raise FileExistsError(f"Scaffold target already exists: {path}. Use --force to overwrite.")
    path.write_text(content.rstrip() + "\n", encoding="utf-8")
    if existed:
        result.updated_files.append(path)
    else:
        result.created_files.append(path)


def _update_bridge_registry(
    *,
    registry_path: Path,
    module_name: str,
    bridge_constant_name: str,
    force: bool,
    result: BridgeScaffoldResult,
) -> None:
    content = registry_path.read_text(encoding="utf-8")
    import_line = f"from fusion_docker.bridges.{module_name} import {bridge_constant_name}"
    register_line = f"register_bridge({bridge_constant_name})"

    if import_line in content and register_line in content:
        if force and registry_path not in result.updated_files:
            result.updated_files.append(registry_path)
        return

    if import_line in content or register_line in content:
        raise ValueError(
            f"Bridge registry is partially configured for {module_name}. "
            "Please resolve it manually."
        )

    updated = content.rstrip() + "\n"
    updated += import_line + "\n"
    updated += register_line + "\n"
    registry_path.write_text(updated, encoding="utf-8")
    result.updated_files.append(registry_path)


def _bridge_module_template(*, bridge_kind: str) -> str:
    constant_name = _bridge_constant_name(bridge_kind)
    return dedent(
        f"""\
        from __future__ import annotations

        from fusion_docker.bridges.profiled import BridgeProfile, create_profiled_bridge_definition


        def _mutate_{bridge_kind}_config(config):
            return config


        {constant_name} = create_profiled_bridge_definition(
            BridgeProfile(
                kind="{bridge_kind}",
                description="TODO: describe this bridge.",
                aliases=(),
                mutate_config=_mutate_{bridge_kind}_config,
            )
        )
        """
    )


def _bridge_config_template(*, bridge_kind: str) -> str:
    return dedent(
        f"""\
        bridge:
          type: {bridge_kind}
          source_mode: zmq_source
          zmq_source_addr: tcp://127.0.0.1:4444
          run_sam3_flowpose: false
          req_timeout_ms: 1000
          zmq_timeout_sec: 3.0
          rgb_jpg_quality: 85
          output_json: response_{bridge_kind}.json
          prompts: []
          obj_id_map: {{}}
        """
    )
