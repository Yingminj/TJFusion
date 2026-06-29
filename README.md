# TJFusion

**TJFusion is a robotics perception → action pipeline**, built as a monorepo of
independently containerized model services. A RealSense camera publishes
RGB/stereo frames; a set of model servers turn those frames into depth,
segmentation masks, semantic status, and 6-DoF object poses; a fusion engine
matches the perceived object state against goals and emits robot commands that
the **Marvin** ROS 2 robot executes.

Every service and every router speaks one shared wire contract
(`tjfusion_protocol`), so adding a model is mostly a config change — no plumbing
rewrites.

```
RealSenseDocker (camera source, ZMQ PUB :5551)
   └─► FusionDocker bridge (SUB → shared store)
         ├─ layer 1 (parallel):
         │     Fast-FoundationSteroDocker  → depth   (stereo depth, :4444)
         │     Sam3Docker                  → mask    (SAM3 promptable seg, :5562)
         │     SiglipDocker / VlmDocker     → status  (state classification, :7777 / :7788)
         ├─ layer 2:
         │     FlowPoseDocker              → pose    (6-DoF; depends on depth + mask, :6667)
         └─► result PUB :8899 → FusionDocker fusion engine → action → MarvinDocker (ROS 2 robot)
```

---

## Table of contents

1. [Architecture](#1-architecture)
2. [Repository layout](#2-repository-layout)
3. [Installation](#3-installation)
   - [One-click install](#31-one-click-install)
   - [Shared Docker base images](#32-shared-docker-base-images)
   - [Local fusion env (no clone / no reinstall)](#33-local-fusion-env-no-clone--no-reinstall)
   - [Install into an existing env](#34-install-into-an-existing-env)
   - [Distributed / multi-machine install](#35-distributed--multi-machine-install)
   - [Model weights](#36-model-weights)
4. [Usage](#4-usage)
5. [Service reference](#5-service-reference)
6. [Testing](#6-testing)
7. [Documentation index](#7-documentation-index)

---

## 1. Architecture

There are three layers to understand:

1. **`protocol/` (`tjfusion_protocol`)** — the single source of truth for
   inter-service messaging. Six data types: `rgb` · `depth` · `mask` ·
   `status` · `pose` · `action`. Every message uses a common JSON **envelope**
   (`schema_version`, `data_type`, `request_id`, `status`, `error`,
   `elapsed_ms`) plus `fields` (small JSON data) and `arrays` (named NumPy
   arrays). The wire format is a **ZMQ multipart of raw NumPy bytes** (frame 0 =
   JSON header with array descriptors, frames 1..N = `arr.tobytes()`) — no
   base64/PNG. A new model server subclasses `BaseModelServer` and implements
   only `load_model()` + `infer()`; the ZMQ REP socket, schema validation,
   timing, error envelope, and `--port` CLI are inherited.

2. **Model Dockers** (`RealSenseDocker`, `Fast-FoundationSteroDocker`,
   `Sam3Docker`, `SiglipDocker`, `FlowPoseDocker`, `VlmDocker`, `YOLODocker`,
   `SenyunDocker`, `MarvinDocker`) — each is a self-contained service with the
   same skeleton: `Dockerfile`, `build.sh` (builds with **repo root as Docker
   context** so the shared `protocol/` package is bundled in), `run.sh` (usually
   `--net=host`), `config.yaml`, `Server/`. See each directory's `README.md`.

3. **`FusionDocker/` orchestrator (`fusion_docker`)** — the CLI, the
   config-driven **bridge** framework, the web UI/dashboard, and the **fusion
   engine** (`core/`: `object_registry.py`, `state_matcher.py`,
   `action_library.py`, `command_builder.py`, `fusion_engine.py`).

**Data routing** is done by *bridges*. The most flexible is `custom_pipeline`:
the entire model DAG is declared in a YAML `pipeline:` list — each node has
`data_type`, `endpoint`, `enabled`, `depends_on` (topological layering →
independent nodes run in parallel), `request_map` (`$key` = read from shared
store, `{value: X}` = literal), and `response_map` (write results back to the
store for later nodes). **Adding a model = adding a node + starting a conforming
server; no bridge Python code changes needed.**

## 2. Repository layout

| Path | Role |
|---|---|
| `protocol/` | Shared wire contract `tjfusion_protocol` (envelope, codec, schemas, `BaseModelServer`, `ModelClient`) + the repo's test suite |
| `docker/` | Shared Docker base images (`Dockerfile.base`, `Dockerfile.gpu-base`, `build-base.sh`) — built once, reused by all model dockers |
| `RealSenseDocker/` | Intel RealSense camera source → `rgb` (+ hardware `depth`). REP `:5550`, PUB `:5551` |
| `Fast-FoundationSteroDocker/` | FoundationStereo stereo → `depth` (`:4444`) |
| `Sam3Docker/` | SAM3 promptable segmentation → `mask` (`:5562`) |
| `SiglipDocker/` | SigLIP2 open-vocabulary state classification → `status` (`:7777`) |
| `VlmDocker/` | Fine-tuned Qwen3.5-VL + LoRA → `status` (drop-in alt for SigLIP, `:7788`) |
| `FlowPoseDocker/` | Flow-matching 6-DoF pose → `pose` (`:6667`) |
| `YOLODocker/` | YOLO detector (auxiliary; legacy base64-JSON server) |
| `SenyunDocker/` | WebRTC multi-view camera → ZMQ image feeder (legacy) |
| `MarvinDocker/` | Marvin robot: ROS 2 Humble workspace + task data; consumes `action` |
| `FusionDocker/` | Orchestrator: CLI, bridges, web UI, fusion engine, configs |
| `install.sh` | One-click installer for the `tjfusion` launcher |
| `setup_fusion_env.sh` | Local `.venv-tjfusion` + `./tjfusion-local` launcher (no clone) |
| `USER_MANUAL.md` | Full pipeline-authoring guide (中文) |
| `model_struction.md` | Repository structure & functionality companion notes |

## 3. Installation

**Prerequisites**
- Linux with Docker (NVIDIA Container Toolkit for the GPU model servers).
- Python 3.10+ for the orchestrator (`FusionDocker`) and the protocol package.
- RealSense USB camera for live capture; an NVIDIA GPU for the vision/VLM models.

### 3.1 One-click install

Installs base tooling, (optionally) clones the repo, creates a venv, installs
`FusionDocker` dependencies, installs a global `tjfusion` launcher with
bash/zsh completion, **and builds the shared Docker base images**
(`tjfusion-base` + `tjfusion-gpu-base`) so subsequent `build.sh` runs are fast:

```bash
curl -fsSL https://raw.githubusercontent.com/yangzhaofeng496/TJFusion/main/install.sh | bash
```

Or run a checked-out copy with options:

```bash
./install.sh                          # local mode in the current checkout
./install.sh --repo-url <git-url> --clone-dir "$HOME/TJFusion"   # clone first
./install.sh --local --skip-clone     # set up env in cwd, do not clone/pull
./install.sh --system                 # system-wide launcher install
```

Then point the launcher at your checkout:

```bash
export DOCKER_MODEL_ROOT=/path/to/TJFusion
```

### 3.2 Shared Docker base images

The 6 GPU model dockers (Fast-FoundationStero, FlowPose, Sam3, Siglip, Vlm,
YOLO) share a single base image — `tjfusion-gpu-base` — that bundles the
common system libraries, **torch 2.9.0 (cu128)**, numpy/opencv-python/pyzmq,
and the `tjfusion_protocol` package. RealSenseDocker uses the lighter
`tjfusion-base` (same deps minus torch/CUDA). This means the ~2.5 GB torch
download happens **once** instead of six times.

`install.sh` builds both bases automatically. To build them manually (or
rebuild after changing `protocol/`):

```bash
./docker/build-base.sh                  # build both if missing
./docker/build-base.sh --rebuild        # force rebuild (no cache)
./docker/build-base.sh --gpu-only       # only the GPU base
```

Each model docker's `Dockerfile` starts with `FROM tjfusion-gpu-base:latest`
and only adds its own unique dependencies, so `cd <SomeDocker> && ./build.sh`
is fast after the bases exist.

> If you skip the base build during `install.sh` (`--skip-docker-base`), the
> individual `build.sh` scripts will fail until you run `./docker/build-base.sh`.

### 3.3 Local fusion env (no clone / no reinstall)

If the code and Docker images are already prepared locally, build just the
Fusion runtime env in this repo:

```bash
./setup_fusion_env.sh                  # create/reuse .venv-tjfusion + ./tjfusion-local
./setup_fusion_env.sh --sync           # force-reinstall deps when requirements changed
./setup_fusion_env.sh --venv-path=/p/.venv-tjfusion --launcher-path=/p/tjfusion
```

This script creates/reuses `.venv-tjfusion`, editable-installs the shared
`protocol/` package, creates the `./tjfusion-local` launcher, and does **not**
git clone/pull or install system packages.

### 3.4 Install into an existing env

If you already have a venv/conda env and only need the Python packages, install
both editable (so repo edits take effect without reinstalling):

```bash
pip install -e protocol        # tjfusion_protocol (bridge + model servers)
pip install -e FusionDocker    # fusion_docker orchestrator / CLI
```

> The bridge fails with `Pipeline nodes with a 'data_type' require the
> tjfusion_protocol package` if `tjfusion_protocol` is missing.
> `setup_fusion_env.sh`, `FusionDocker/run.sh` (which adds `protocol/` to
> `PYTHONPATH`), and the editable install above each resolve it.

### 3.5 Distributed / multi-machine install

The orchestrator can manage Docker services that live on **other hosts** over
SSH — e.g. run the camera + vision models on a GPU box and the robot
(`MarvinDocker`) on the robot's onboard computer.

1. On **each** machine: clone the repo (or copy the relevant `*Docker/`
   directories) and set `DOCKER_MODEL_ROOT`. Run `./docker/build-base.sh` first
   (one-time shared layer), then build the images that machine will run
   (`./build.sh` per docker). The host running the orchestrator needs SSH
   access (key or password) to every remote host.
2. In `FusionDocker/configs/docker_launch.yaml`, mark a target `location: remote`
   and give it a `remote:` block. The orchestrator then builds/starts/stops that
   container over SSH and the dashboard manages it like a local one:

```yaml
docker_targets:
  - name: RealSenseDocker          # local (the host running the orchestrator)
    group: camera
    location: local
    docker_model_root: ${DOCKER_MODEL_ROOT}

  - name: MarvinDocker             # runs on the robot's onboard computer
    group: action
    location: remote
    remote:
      host: 192.168.1.50           # required for remote
      user: robot                  # required for remote
      docker_model_root: /home/robot/TJFusion   # required for remote (path on that host)
      ssh_port: 22                 # optional, default 22
      password: ""                 # optional; prefer SSH keys
```

Because all services talk over ZMQ on `--net=host`, make sure the configured
host/IP and ports are reachable across machines (a flat robot LAN is assumed —
there is no auth on the ZMQ sockets).

### 3.6 Model weights

Weights are **not committed**. Each model docker fetches them with a
`model/download.sh` / `download_models.py`, or mounts them at runtime:

```bash
Fast-FoundationSteroDocker/model/download.sh
Sam3Docker/model/download.sh
SiglipDocker/model/download.sh
cd FlowPoseDocker && python3 download_models.py     # see FlowPoseDocker/README.md
# VlmDocker: base + LoRA mounted at runtime via run.sh (WEIGHTS_DIR=...)
```

## 4. Usage

All `fusion_docker` commands run from `FusionDocker/` (the `tjfusion` /
`./tjfusion-local` launchers wrap `python -m fusion_docker`). First:

```bash
export DOCKER_MODEL_ROOT=/path/to/TJFusion
```

### Pick which dockers to run

```bash
tjfusion docker-select        # interactive: ↑/↓ move · Space toggle · Enter save · q cancel
```

This edits `selected_dockers` in `FusionDocker/configs/docker_launch.yaml`.

### One-click start (recommended)

`FusionDocker/run.sh` is the single entry point for the whole stack. It reads
`configs/docker_launch.yaml`, frees stale managed ports, builds + launches every
docker in `selected_dockers` (each in its own tmux window, auto-building via the
folder's `build.sh` if the image is missing), and serves the web dashboard at
`http://localhost:8765`:

```bash
cd FusionDocker
./run.sh
```

`run.sh` starts the **model containers + dashboard**; bring the **bridge** up
from the dashboard (entries under `bridges:` become start/stop buttons), or run
it directly (see below). The web UI also lets you start/stop individual dockers
and bridges and view live video windows.

Equivalent CLI:

```bash
cd FusionDocker
tjfusion launch-dockers --launch-config configs/docker_launch.yaml   # build + launch
tjfusion serve-ui       --launch-config configs/docker_launch.yaml   # dashboard :8765
```

### Run / author the bridge (the pipeline)

```bash
cd FusionDocker
tjfusion serve-bridge --config configs/bridge.realsense_split.yaml --verbose
```

Which models run, in what order, and on which endpoints is **config-only** in
`configs/bridge.realsense_split.yaml` (`enabled`, `depends_on`, `endpoint`,
`request_map`, `response_map`). To add a model: start a `BaseModelServer` and add
a `pipeline:` node — no Python changes. The full authoring guide is
`USER_MANUAL.md`.

### Scaffolding & debugging

```bash
tjfusion create-bridge my_bridge      # bridges/my_bridge.py + configs/bridge.my_bridge.yaml (auto-registered)
tjfusion list-bridges
tjfusion create-system MySystem --docker-model-root "$DOCKER_MODEL_ROOT"   # new docker skeleton

tjfusion inspect-ports --port 1883 --watch-seconds 10   # listening ports / live connections (tcpdump needs sudo)
tjfusion listen-zmq --port 8899 --topic /siglip2/result --limit 3   # tap ZMQ traffic
```

## 5. Service reference

| Docker | Data type | Default port | Protocol | Needs |
|---|---|---|---|---|
| RealSenseDocker | `rgb` (+ hw `depth`) | REP 5550 / PUB 5551 | standard | RealSense USB (`--privileged`) |
| Fast-FoundationSteroDocker | `depth` | 4444 | standard | NVIDIA GPU |
| Sam3Docker | `mask` | 5562 | standard | NVIDIA GPU |
| SiglipDocker | `status` | 7777 | standard | NVIDIA GPU |
| VlmDocker | `status` | 7788 | standard | NVIDIA GPU (~19 GB) |
| FlowPoseDocker | `pose` | 6667 | standard | NVIDIA GPU |
| YOLODocker | detection | 5562 | legacy base64-JSON | NVIDIA GPU |
| SenyunDocker | image feed | 5559 | legacy ZMQ PUB | network to device |
| MarvinDocker | consumes `action` | — | ROS 2 Humble | robot / CAN |
| FusionDocker bridge | result PUB | 8899 | standard | — |
| FusionDocker dashboard | web UI | 8765 | HTTP | — |

> Build any single docker standalone with `cd <SomeDocker> && ./build.sh && ./run.sh`.
> `build.sh` always uses the repo root as the Docker context so `protocol/` is bundled in.
> The shared base images (`tjfusion-base` / `tjfusion-gpu-base`) must exist first —
> run `./docker/build-base.sh` once if you skipped it during `install.sh`.

## 6. Testing

The protocol package carries the test suite:

```bash
cd protocol
python -m tests.test_protocol      # or: pytest -q
```

No-hardware end-to-end checks (a fake RealSense PUB driving the DAG) live under
`FusionDocker/tests/` — see `USER_MANUAL.md` §4.1.

## 7. Documentation index

- **`USER_MANUAL.md`** — full pipeline-authoring guide: data types, envelope,
  writing a bridge YAML, plugging in a new model (中文).
- **`protocol/README.md`** — the standard protocol in detail.
- **`FusionDocker/README.md`** + `README.Pipeline.md` / `README.Bridge.md` /
  `README.Cli.md` — orchestrator, pipeline, and CLI references.
- **`<SomeDocker>/README.md`** — each model service.
- **`CLAUDE.md`** / **`model_struction.md`** — repository orientation.
