# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repo is

TJFusion is a monorepo for a robotics perception→action pipeline built from many independently-containerized model servers. Each `*Docker/` directory is a self-contained model service (camera source, depth, segmentation, classification, pose, or action). `FusionDocker/` is the **orchestrator**: it builds/launches the containers, runs the data-routing "bridges" between them, serves a web UI, and contains the fusion engine that turns perception results into robot commands. `protocol/` is the shared wire contract that every service and bridge speaks.

Most docs in the subdirectory `README.md` files are in Chinese and contain hardcoded paths from another machine (e.g. `/home/yang/Desktop/DockerModel/`) — treat those paths as illustrative, not real.

## Three layers to understand

1. **`protocol/` (`tjfusion_protocol` package)** — the single source of truth for inter-service messages. Six data types: `rgb`, `depth`, `mask`, `status`, `pose`, `action`. Every message uses a common JSON envelope (`schema_version`, `data_type`, `request_id`, `status`, `error`, `elapsed_ms`) plus `fields` (small JSON data) and `arrays` (named NumPy arrays). The wire format is **ZMQ multipart of raw NumPy bytes** (frame 0 = JSON header with array descriptors, frames 1..N = `arr.tobytes()`) — no base64/PNG/JPG. Codec lives only in `codec.py` (`pack_message`/`unpack_message`). A new model server subclasses `BaseModelServer` (in `server.py`) and implements just `load_model()` and `infer()`; everything else (ZMQ REP socket, schema validation, timing, error envelope, `--port` CLI) is inherited. Bridges call services via `ModelClient` (`client.py`).

2. **Model Dockers (`Sam3Docker`, `FlowPoseDocker`, `SiglipDocker`, `Fast-FoundationSteroDocker`, `RealSenseDocker`, `MarvinDocker`, `YOLODocker`, `SenyunDocker`)** — each has the same skeleton: `Dockerfile`, `build.sh`, `run.sh`, `config.yaml`, `Server/server.py`, and `RequestFormat/*.schema.json`. `build.sh` builds with the **repo root as the Docker context** so the shared `protocol/` package can be `COPY`d into the image. `run.sh` typically uses `--net=host` so ZMQ ports are reachable across containers (RealSense additionally needs `--privileged -v /dev:/dev` for USB). `config.yaml` declares the container image/name, the server host/port, and model weight paths (weights are downloaded via a `model/download.sh` or mounted at runtime, not committed).

3. **`FusionDocker/` orchestrator (`fusion_docker` package, in `src/`)** — the CLI, the bridge framework, the web UI/dashboard, and the fusion engine (`core/`: `fusion_engine.py`, `object_registry.py`, `action_library.py`, `state_matcher.py`, `command_builder.py`).

## Data flow

```
RealSenseDocker (camera source, PUB) → bridge (SUB, seeds shared store)
   → pipeline layer 1 (parallel): fast_foundation(depth) · sam3(mask) · siglip2(status)
   → pipeline layer 2: flowpose(pose)  [depends_on fast_foundation, sam3]
   → result_pub → MarvinDocker (action / robot command)
```

Bridges route data between the model dockers. A bridge receives upstream data, remaps fields/formats, calls one or more downstream services, and publishes/aggregates results. The most flexible bridge type is **`custom_pipeline`**: the entire model DAG is declared in a YAML `pipeline:` list — each node has `data_type`, `endpoint`, `enabled`, `depends_on` (topological layering → independent nodes run in parallel), `inputs`, `request_map` (`$key` = read from shared store, `{value: X}` = literal), and `response_map` (writes results back to the store for later nodes). Adding a model = adding a node + starting a conforming server; **no bridge Python code changes needed**.

> Migration note: parts of the bridge layer historically spoke an older base64-JSON protocol. `configs/bridge.realsense_split.yaml` and `README.Pipeline.md` describe the target state after that migration. Verify which protocol a given bridge actually uses before assuming the new NumPy-multipart path is wired end-to-end.

## Commands

### FusionDocker CLI (the main entrypoint)
Run from `FusionDocker/`. All commands use the module form:
```bash
cd FusionDocker
pip install -r requirements.txt          # PyYAML, numpy, opencv-python-headless, pyzmq
PYTHONPATH=src python3 -m fusion_docker --help
```
Common subcommands:
```bash
# Build + launch all dockers selected in the launch config
PYTHONPATH=src python3 -m fusion_docker launch-dockers --launch-config configs/docker_launch.yaml

# Web UI / dashboard (default http://0.0.0.0:8765) — start/stop dockers and bridges from the browser
PYTHONPATH=src python3 -m fusion_docker serve-ui --launch-config configs/docker_launch.yaml

# Run a single bridge directly
PYTHONPATH=src python3 -m fusion_docker serve-bridge --config configs/bridge.custom.yaml

# Scaffold a new bridge (creates bridges/<name>.py, configs/bridge.<name>.yaml, auto-registers)
PYTHONPATH=src python3 -m fusion_docker create-bridge my_bridge
PYTHONPATH=src python3 -m fusion_docker list-bridges

# Scaffold a new model docker skeleton under DOCKER_MODEL_ROOT
PYTHONPATH=src python3 -m fusion_docker create-system MySystem --docker-model-root /path/to/repo

# Debugging: inspect listening ports / live connections (tcpdump needs sudo)
PYTHONPATH=src python3 -m fusion_docker inspect-ports --port 1883 --watch-seconds 10
# Tap ZMQ traffic on a port/topic
PYTHONPATH=src python3 -m fusion_docker listen-zmq --port 8899 --topic /siglip2/result --limit 3
```

### Top-level `tjfusion` launcher
`install.sh` installs a `tjfusion` command (wrapping `python -m fusion_docker`) with bash/zsh completion. `./setup_fusion_env.sh` builds a local `.venv-tjfusion` and a `./tjfusion-local` launcher **without** git clone or system package installs (`--sync` to force dependency reinstall). Both rely on `export DOCKER_MODEL_ROOT=/path/to/repo`. Top-level convenience subcommands include `start`, `restart`, `update`, `docker-select` / `docker-config`.

### Building / running an individual model docker
```bash
cd <SomeDocker>
./build.sh    # builds with repo root as context (so protocol/ is included)
./run.sh
```

### Tests
The protocol package has the test suite:
```bash
cd protocol
python -m tests.test_protocol      # or: pytest -q
```

## Key files when extending the system

- New shared message type / wire change → `protocol/tjfusion_protocol/` (`envelope.py`, `codec.py`, `validate.py`, `schemas/*.json`) and `protocol/tests/test_protocol.py`.
- New model server → subclass `BaseModelServer` in `protocol/tjfusion_protocol/server.py`; mirror an existing `<Docker>/Server/server.py`.
- New bridge → `FusionDocker/src/fusion_docker/bridges/` (register in `bridges/__init__.py`); reference `siglip2_bridge.py`, `sam3_flowpose.py`, `multi_zmq_pub_bridge.py`, and the engine `bridge_service.py`. Most routing changes are config-only (`FusionDocker/configs/bridge.*.yaml`).
- Fusion/action logic → `FusionDocker/src/fusion_docker/core/`.
- Which dockers/bridges the UI manages → `FusionDocker/configs/docker_launch.yaml`.
