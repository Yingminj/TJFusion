# TJFusion — Repository Structure & Functionality

> Generated 2026-06-11 as part of a repository cleanup. Companion to `CLAUDE.md` and the
> per-directory `README.md` files (many of which are in Chinese and contain illustrative,
> machine-specific paths).

## 1. What TJFusion does

TJFusion is a **robotics perception → action pipeline** built as a monorepo of independently
containerized model services. A RealSense camera publishes RGB/stereo frames; a set of model
servers turn those frames into depth, segmentation masks, semantic status, and 6-DoF object
poses; a fusion engine matches the perceived object state against goals and emits robot
commands that the Marvin ROS 2 robot executes.

```
RealSenseDocker (camera, ZMQ PUB)
   └─► FusionDocker bridge (SUB → shared store)
         ├─ layer 1 (parallel):
         │     Fast-FoundationSteroDocker  → depth      (stereo depth estimation)
         │     Sam3Docker                  → mask       (SAM3 promptable segmentation)
         │     SiglipDocker                → status     (SigLIP2 open-vocabulary state classification)
         ├─ layer 2:
         │     FlowPoseDocker              → pose       (6-DoF pose; depends on depth + mask)
         └─► result PUB → FusionDocker core (fusion engine) → action → MarvinDocker (ROS 2 robot)
```

## 2. The three layers

### 2.1 `protocol/` — shared wire contract (`tjfusion_protocol`)

The single source of truth for inter-service messaging. Everything else depends on it.

| File | Role |
|---|---|
| `envelope.py` | Common JSON envelope: `schema_version`, `data_type` (`rgb`/`depth`/`mask`/`status`/`pose`/`action`), `request_id`, `status`, `error`, `elapsed_ms` |
| `codec.py` | `pack_message` / `unpack_message` — ZMQ multipart of **raw NumPy bytes** (frame 0 = JSON header with array descriptors, frames 1..N = `arr.tobytes()`). No base64/PNG |
| `server.py` | `BaseModelServer` — subclass it and implement only `load_model()` + `infer()`; ZMQ REP socket, validation, timing, error envelope, `--port` CLI are inherited |
| `client.py` | `ModelClient` — what bridges use to call services |
| `validate.py`, `schemas/*.json` | Per-data-type JSON Schema validation |
| `tests/test_protocol.py` | The repo's only test suite (7 tests, all passing) |

### 2.2 `*Docker/` — model services

Each follows the same skeleton: `Dockerfile`, `build.sh` (builds with **repo root as Docker
context** so `protocol/` can be COPY'd in), `run.sh` (usually `--net=host`), `config.yaml`,
`Server/server.py`, `RequestFormat/*.schema.json`. Model weights are **not** committed — they
are fetched by `model/download.sh` or mounted at runtime.

| Directory | Model / role | Data type produced |
|---|---|---|
| `RealSenseDocker` | Intel RealSense camera source (needs `--privileged -v /dev:/dev`) | `rgb` (PUB) |
| `Fast-FoundationSteroDocker` | FoundationStereo stereo-depth (vendored upstream in `Fast-FoundationStereo-master/`) | `depth` |
| `Sam3Docker` | SAM3 promptable segmentation (vendored upstream in `sam3-main/`) | `mask` |
| `SiglipDocker` | SigLIP2 open-vocabulary classification → object state | `status` |
| `FlowPoseDocker` | Flow-matching 6-DoF pose estimator (vendored `FlowPose/`) | `pose` |
| `YOLODocker` | YOLO detector (alternative/auxiliary perception) | detection |
| `MarvinDocker` | Marvin robot: ROS 2 Humble workspace (`ros2_ws/`: description, ros2_control, fabric planner, teleop, DM gripper) + `robotaction/` task data | consumes `action` |
| `SenyunDocker` | Minimal service skeleton (Senyun device) | — |

### 2.3 `FusionDocker/` — orchestrator (`fusion_docker`, in `src/`)

| Module | Role |
|---|---|
| `cli.py` (2.2k lines) | CLI entrypoint: `launch-dockers`, `serve-ui`, `serve-bridge`, `create-bridge`, `create-system`, `inspect-ports`, `listen-zmq`, … |
| `docker_launcher.py` | Builds/starts/stops the model containers per `configs/docker_launch.yaml` |
| `ui_server.py` (9.2k lines) | Web UI / dashboard (default `:8765`) — manage dockers and bridges from the browser |
| `bridge_service.py`, `bridge_runtime.py`, `bridges/` | Bridge framework. `bridges/custom_pipeline.py` is the key one: the whole model DAG is declared in YAML (`pipeline:` nodes with `depends_on`, `request_map`, `response_map`) — adding a model requires **no Python changes** |
| `core/` | The fusion engine: `object_registry.py` (known objects + goals), `state_matcher.py` (perceived state ↔ goal), `action_library.py` (state transition → action), `command_builder.py` (action → robot command), `fusion_engine.py` (tracks objects, deduplicates commands), `geometry.py` (pose math) |
| `messaging/zmq_bus.py`, `zmq_listener.py`, `port_inspector.py` | ZMQ plumbing and debug tooling |
| `configs/` | `docker_launch.yaml` (what the UI manages), `bridge.*.yaml` (routing), `objects/` (object/goal definitions) |

Top-level: `install.sh` installs a global `tjfusion` command; `setup_fusion_env.sh` builds a
local `.venv-tjfusion` + `./tjfusion-local` launcher. Both need `export DOCKER_MODEL_ROOT=<repo>`.

## 3. How to extend (quick reference)

- **New message type / wire change** → `protocol/tjfusion_protocol/` + `protocol/tests/test_protocol.py`.
- **New model server** → subclass `BaseModelServer`; copy an existing `<Docker>/` skeleton; add a node to the pipeline YAML.
- **New routing** → usually config-only: `FusionDocker/configs/bridge.*.yaml`. New bridge code goes in `FusionDocker/src/fusion_docker/bridges/` (register in `bridges/__init__.py`).
- **Fusion/action logic** → `FusionDocker/src/fusion_docker/core/`.

## 4. Cleanup performed (2026-06-11)

- Deleted duplicate vendored copies: `Sam3Docker/sam3/` (the Dockerfile only uses `sam3-main/`)
  and `MarvinDocker/ros2_ws/src/Marvin-description/` (COLCON_IGNORE'd; superseded by
  `marvin_description_new/`, both claimed the ROS package name `marvin_description`).
- Deleted dead files: `README_bak.md`, `ZeroMQServer.bak`, `bridge_service.bak.py`, `.codex_write_test`.
- Untracked from git (kept on disk): `FusionDocker/logs/` (~45 MB of bridge logs),
  `YOLODocker/model/best.pt` (20 MB weights), ROS runtime `log/` dirs,
  `Fast-FoundationStereo-master/assets/` (~35 MB demo media).
- Rewrote `.gitignore`: organized by category; now covers logs, all weight formats
  (`*.pt`, `*.pth`, `*.onnx`, …), all `model/` dirs (keeping `download.sh`), venvs,
  IDE/tooling dirs, colcon build artifacts, and backup files.

## 5. Recommended improvements (prioritized)

### High value, low risk
1. **Finish the protocol migration.** `Fast-FoundationSteroDocker/Server/` still carries three
   parallel implementations (`ZeroMQ_base64/`, `ZeroMQ_rawbytes/`, `StandardProtocol/`), and
   FlowPose/Sam3 have similar variant folders. Pick the `BaseModelServer`/NumPy-multipart path
   everywhere, delete the legacy base64 servers, and update `bridge.*.yaml` accordingly.
   `configs/bridge.realsense_split.yaml` + `README.Pipeline.md` describe the target state.
2. **Add tests for the orchestrator.** Only `protocol/` has tests today. The `core/` modules
   (state_matcher, action_library, command_builder, fusion_engine) are pure logic with no I/O —
   ideal unit-test targets. The `custom_pipeline` DAG layering (topological sort, `request_map`
   resolution) also deserves tests, since all routing now depends on it.
3. **Set up CI + lint.** A minimal GitHub Actions workflow running `pytest` on `protocol/` and
   future `FusionDocker` tests, plus `ruff` (lint + format) via pre-commit, will keep junk and
   dead code from accumulating again.
4. **Standardize the docker skeletons.** `RealSenseDocker` lacks `config.yaml`/`RequestFormat/`;
   `SenyunDocker` lacks a README; `SiglipDocker` uses `_README.md`. A `TEMPLATE.md` or the
   existing `create-system` scaffold should be the enforced reference.

### Medium effort
5. **Split `ui_server.py` (9,217 lines).** Extract the embedded HTML/JS/CSS into static asset
   files and split route handlers into modules (dockers, bridges, streams, configs). Same for
   `cli.py` (2.2k) and `docker_launcher.py` (2.3k) — one module per subcommand/concern.
6. **Slim down vendored upstream code.** `sam3-main/`, `Fast-FoundationStereo-master/`, and
   `FlowPose/` are full upstream snapshots (with notebooks, demo assets, training code).
   Options: git submodules pinned to a commit, pip-installable forks, or pruning to the
   inference-only subset each Dockerfile actually needs.
7. **Unify documentation.** The root `README.md` is thin; per-docker READMEs mix Chinese and
   English and reference paths from another machine. Pick one canonical language (or do both),
   make the root README the entry point with the architecture diagram, and replace hardcoded
   paths with `$DOCKER_MODEL_ROOT`.
8. **Pin dependencies.** The various `requirements.txt` files are mostly unpinned. Pin at least
   `pyzmq`, `numpy`, and `opencv-python-headless` versions shared between protocol and bridges,
   since the wire format depends on NumPy dtype semantics.

### Larger / coordinate with the team
9. **Shrink git history.** The pack is ~220 MB; the logs/weights/demo media removed from the
   index still live in history. When convenient (requires force-push + team coordination), run
   `git filter-repo` to drop them, and adopt **Git LFS** for what must stay binary
   (Marvin STL meshes are ~60 MB of the repo).
10. **Fix naming drift.** `Fast-FoundationSteroDocker` (typo: "Stero"), `model_struction.md`
    vs conventional naming, mixed `CamelCaseDocker` dirs vs snake_case packages. Renaming
    directories touches build scripts and configs, so batch it as a single dedicated change.
11. **Harden the runtime.** Bridges and servers run with `--net=host` and no auth on ZMQ
    sockets — fine on a closed robot LAN, but document that assumption, and consider CURVE
    auth or at least bind-to-localhost defaults for non-camera services.
