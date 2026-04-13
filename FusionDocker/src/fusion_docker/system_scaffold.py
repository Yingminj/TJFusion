from __future__ import annotations

from dataclasses import dataclass, field
import os
from pathlib import Path
import re
from textwrap import dedent


@dataclass(slots=True)
class ScaffoldResult:
    requested_name: str
    folder_name: str
    image_name: str
    folder_path: Path
    created_files: list[Path] = field(default_factory=list)
    updated_files: list[Path] = field(default_factory=list)
    created_dirs: list[Path] = field(default_factory=list)


def create_system_scaffold(
    *,
    name: str,
    docker_model_root: str | Path,
    server_host: str = "0.0.0.0",
    server_port: int = 5555,
    force: bool = False,
) -> ScaffoldResult:
    requested_name = str(name).strip()
    if not requested_name:
        raise ValueError("System name cannot be empty.")
    if server_port <= 0 or server_port > 65535:
        raise ValueError("server_port must be between 1 and 65535.")
    host_value = str(server_host).strip()
    if not host_value:
        raise ValueError("server_host cannot be empty.")

    folder_name = canonical_docker_folder_name(requested_name)
    image_name = canonical_docker_image_name(requested_name)
    root_path = Path(docker_model_root).expanduser().resolve()
    root_path.mkdir(parents=True, exist_ok=True)

    folder_path = root_path / folder_name
    folder_path.mkdir(parents=True, exist_ok=True)
    result = ScaffoldResult(
        requested_name=requested_name,
        folder_name=folder_name,
        image_name=image_name,
        folder_path=folder_path,
    )

    for relative_dir in ("Server", "RequestFormat"):
        dir_path = folder_path / relative_dir
        if not dir_path.exists():
            dir_path.mkdir(parents=True, exist_ok=True)
            result.created_dirs.append(dir_path)

    files_to_write: list[tuple[Path, str, bool]] = [
        (
            folder_path / "Dockerfile",
            _dockerfile_template(server_port=server_port),
            False,
        ),
        (
            folder_path / "build.sh",
            _build_sh_template(),
            True,
        ),
        (
            folder_path / "run.sh",
            _run_sh_template(),
            True,
        ),
        (
            folder_path / "config.yaml",
            _config_yaml_template(
                image_name=image_name,
                server_host=host_value,
                server_port=server_port,
            ),
            False,
        ),
        (
            folder_path / "Server" / "server.py",
            _server_py_template(),
            False,
        ),
        (
            folder_path / "RequestFormat" / "input.schema.json",
            _request_schema_template(),
            False,
        ),
        (
            folder_path / "RequestFormat" / "output.schema.json",
            _response_schema_template(),
            False,
        ),
        (
            folder_path / "README.md",
            _readme_template(folder_name=folder_name),
            False,
        ),
    ]

    for target_path, content, executable in files_to_write:
        existed = target_path.exists()
        if existed and not force:
            raise FileExistsError(
                f"Scaffold target already exists: {target_path}. "
                "Use --force to overwrite."
            )

        target_path.write_text(content.rstrip() + "\n", encoding="utf-8")
        if executable:
            os.chmod(target_path, 0o755)

        if existed:
            result.updated_files.append(target_path)
        else:
            result.created_files.append(target_path)

    return result


def canonical_docker_folder_name(raw_name: str) -> str:
    words = _split_words(raw_name)
    if not words:
        raise ValueError("System name must contain letters or numbers.")

    if words and words[-1].lower() == "docker":
        words = words[:-1]
    base = "".join(_pascal_case_word(word) for word in words)
    if not base:
        base = "System"
    return f"{base}Docker"


def canonical_docker_image_name(raw_name: str) -> str:
    token = re.sub(r"[^a-z0-9]+", "_", raw_name.strip().lower()).strip("_")
    if not token:
        token = "system"
    if token.endswith("_docker"):
        token = token[: -len("_docker")]
    elif token.endswith("docker"):
        token = token[: -len("docker")].strip("_")
    return token or "system"


def _split_words(raw_name: str) -> list[str]:
    normalized = re.sub(r"[^A-Za-z0-9]+", " ", raw_name).strip()
    if not normalized:
        return []

    words: list[str] = []
    for chunk in normalized.split():
        split_chunk = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", chunk).split()
        words.extend(split_chunk)
    return words


def _pascal_case_word(word: str) -> str:
    return word[:1].upper() + word[1:].lower()


def _dockerfile_template(*, server_port: int) -> str:
    return dedent(
        f"""\
        FROM python:3.11-slim

        WORKDIR /workspace

        ENV PYTHONDONTWRITEBYTECODE=1 \\
            PYTHONUNBUFFERED=1

        COPY . /workspace

        RUN pip install --no-cache-dir pyzmq pyyaml

        EXPOSE {server_port}

        CMD ["python3", "/workspace/Server/server.py", "--config", "/workspace/config.yaml"]
        """
    )


def _build_sh_template() -> str:
    return dedent(
        """\
        #!/usr/bin/env bash
        set -euo pipefail

        SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
        CONFIG_PATH="${SCRIPT_DIR}/config.yaml"

        IMAGE_NAME="$(python3 - "$CONFIG_PATH" <<'PY'
        import os
        import re
        import sys
        from pathlib import Path

        import yaml

        config_path = Path(sys.argv[1])
        raw = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
        docker_cfg = raw.get("docker", {}) if isinstance(raw, dict) else {}
        image = str(docker_cfg.get("image", "system")).strip() or "system"
        image = re.sub(r"[^a-zA-Z0-9_.-]+", "_", image)
        print(image)
        PY
        )"

        echo "[BUILD] Building image ${IMAGE_NAME} from ${SCRIPT_DIR}"
        docker build -t "${IMAGE_NAME}" "${SCRIPT_DIR}"
        echo "[BUILD] Done."
        """
    )


def _run_sh_template() -> str:
    return dedent(
        """\
        #!/usr/bin/env bash
        set -euo pipefail

        SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
        CONFIG_PATH="${SCRIPT_DIR}/config.yaml"

        readarray -t CONFIG_VALUES < <(python3 - "$CONFIG_PATH" <<'PY'
        import re
        import sys
        from pathlib import Path

        import yaml

        config_path = Path(sys.argv[1])
        raw = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
        if not isinstance(raw, dict):
            raw = {}

        docker_cfg = raw.get("docker", {})
        server_cfg = raw.get("server", {})
        image = str(docker_cfg.get("image", "system")).strip() or "system"
        container = str(docker_cfg.get("container_name", "${image}_tmp")).strip() or "${image}_tmp"
        host = str(server_cfg.get("host", "0.0.0.0")).strip() or "0.0.0.0"
        port = int(server_cfg.get("port", 5555))
        container = container.replace("${image}", image)
        image = re.sub(r"[^a-zA-Z0-9_.-]+", "_", image)
        container = re.sub(r"[^a-zA-Z0-9_.-]+", "_", container)
        print(image)
        print(container)
        print(host)
        print(port)
        PY
        )

        IMAGE_NAME="${CONFIG_VALUES[0]}"
        CONTAINER_NAME="${CONFIG_VALUES[1]}"
        SERVER_HOST="${CONFIG_VALUES[2]}"
        SERVER_PORT="${CONFIG_VALUES[3]}"
        HOST_PORT="${HOST_PORT:-${SERVER_PORT}}"

        echo "[RUN] image=${IMAGE_NAME} container=${CONTAINER_NAME} host=${SERVER_HOST} port=${SERVER_PORT}"
        docker rm -f "${CONTAINER_NAME}" >/dev/null 2>&1 || true

        docker run --name "${CONTAINER_NAME}" --rm -i \
          -p "${HOST_PORT}:${SERVER_PORT}" \
          -v "${SCRIPT_DIR}:/workspace" \
          "${IMAGE_NAME}" \
          bash -lc "cd /workspace && python3 Server/server.py --config /workspace/config.yaml"
        """
    )


def _config_yaml_template(
    *,
    image_name: str,
    server_host: str,
    server_port: int,
) -> str:
    return dedent(
        f"""\
        docker:
          image: "{image_name}"
          container_name: "${{image}}_tmp"

        server:
          host: "{server_host}"
          port: {server_port}
        """
    )


def _server_py_template() -> str:
    return dedent(
        """\
        from __future__ import annotations

        import argparse
        import json
        import time
        from pathlib import Path
        from uuid import uuid4

        import yaml
        import zmq


        def load_config(path: str | Path) -> dict:
            config_path = Path(path)
            if not config_path.exists():
                raise FileNotFoundError(f"Config file not found: {config_path}")
            raw = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
            if not isinstance(raw, dict):
                raise ValueError("config.yaml root must be a mapping")
            return raw


        def main() -> None:
            parser = argparse.ArgumentParser(description="Docker service skeleton ZMQ REP server.")
            parser.add_argument("--config", default="/workspace/config.yaml", help="Path to config.yaml")
            args = parser.parse_args()

            config = load_config(args.config)
            server_cfg = config.get("server", {}) if isinstance(config, dict) else {}
            host = str(server_cfg.get("host", "0.0.0.0")).strip() or "0.0.0.0"
            port = int(server_cfg.get("port", 5555))
            endpoint = f"tcp://{host}:{port}"

            context = zmq.Context.instance()
            socket = context.socket(zmq.REP)
            socket.bind(endpoint)
            print(f"[READY] skeleton server listening at {endpoint}", flush=True)

            try:
                while True:
                    request_text = socket.recv_string()
                    started_at = time.perf_counter()
                    try:
                        request_obj = json.loads(request_text)
                    except json.JSONDecodeError as exc:
                        socket.send_json(
                            {
                                "status": "error",
                                "request_id": "",
                                "message": f"invalid JSON: {exc}",
                                "elapsed_sec": 0.0,
                            }
                        )
                        continue

                    request_id = str(request_obj.get("request_id", "")).strip() or str(uuid4())
                    response_obj = {
                        "status": "ok",
                        "request_id": request_id,
                        "objects": [],
                        "elapsed_sec": round(time.perf_counter() - started_at, 6),
                        "echo": {
                            "keys": sorted(request_obj.keys()),
                        },
                    }
                    socket.send_json(response_obj)
            except KeyboardInterrupt:
                print("[STOP] server interrupted by user", flush=True)
            finally:
                socket.close(0)
                context.term()


        if __name__ == "__main__":
            main()
        """
    )


def _request_schema_template() -> str:
    return dedent(
        """\
        {
          "$schema": "https://json-schema.org/draft/2020-12/schema",
          "title": "SkeletonRequest",
          "type": "object",
          "additionalProperties": true,
          "required": [
            "request_id",
            "rgb_image",
            "depth_image"
          ],
          "properties": {
            "request_id": {
              "type": "string",
              "format": "uuid"
            },
            "rgb_image": {
              "type": "string",
              "contentEncoding": "base64"
            },
            "depth_image": {
              "type": "string",
              "contentEncoding": "base64"
            },
            "combined_mask": {
              "type": "string",
              "contentEncoding": "base64"
            },
            "obj_ids": {
              "type": "array",
              "items": {
                "type": "array",
                "items": {
                  "type": "integer"
                },
                "minItems": 2,
                "maxItems": 2
              }
            }
          }
        }
        """
    )


def _response_schema_template() -> str:
    return dedent(
        """\
        {
          "$schema": "https://json-schema.org/draft/2020-12/schema",
          "title": "SkeletonResponse",
          "type": "object",
          "additionalProperties": true,
          "required": [
            "status",
            "request_id",
            "objects",
            "elapsed_sec"
          ],
          "properties": {
            "status": {
              "type": "string",
              "enum": ["ok", "error"]
            },
            "request_id": {
              "type": "string"
            },
            "objects": {
              "type": "array",
              "items": {
                "type": "object"
              }
            },
            "elapsed_sec": {
              "type": "number",
              "minimum": 0
            }
          }
        }
        """
    )


def _readme_template(*, folder_name: str) -> str:
    return dedent(
        f"""\
        # {folder_name}

        Auto-generated by FusionDocker `create-system`.

        ## Quick Start

        ```bash
        ./build.sh
        ./run.sh
        ```

        ## Files

        - `config.yaml`: docker image/container and server host/port.
        - `Dockerfile`: service image definition.
        - `build.sh`: build image from `config.yaml`.
        - `run.sh`: run container and map host port.
        - `Server/server.py`: ZMQ REP service skeleton.
        - `RequestFormat/input.schema.json`: request schema.
        - `RequestFormat/output.schema.json`: response schema.
        """
    )
