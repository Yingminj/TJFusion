# TJFUSION

## Install `tjfusion`

```bash
curl -fsSL https://raw.githubusercontent.com/yangzhaofeng496/TJFusion/main/install.sh | bash
```

## Configure

```bash
export DOCKER_MODEL_ROOT=/path/to/DockerModel
```

## Local Fusion Env (No Clone/No Reinstall)

If your code and Docker are already prepared locally, use:

```bash
./setup_fusion_env.sh
```

This script only prepares local Fusion runtime env in this repo:

- Creates or reuses `.venv-tjfusion`
- Installs/updates Fusion Python dependencies only when venv is new (or `--sync` is provided)
- Editable-installs the shared `protocol/` package (`tjfusion_protocol`), which the
  bridge requires for any pipeline node that declares a `data_type`
- Creates local launcher `./tjfusion-local`
- Does not run git clone/pull
- Does not install system packages

Common usage:

```bash
# first setup
./setup_fusion_env.sh

# reuse existing venv without reinstalling deps
./setup_fusion_env.sh

# force sync deps when requirements changed
./setup_fusion_env.sh --sync

# custom venv/launcher paths
./setup_fusion_env.sh --venv-path=/path/to/.venv-tjfusion --launcher-path=/path/to/tjfusion
```

### Installing into an existing env

If you already have a venv/conda env and only need the Python packages, install
both the orchestrator and the shared protocol package (editable, so repo edits
take effect without reinstalling):

```bash
pip install -e protocol        # tjfusion_protocol (bridge + model servers)
pip install -e FusionDocker    # fusion_docker orchestrator/CLI
```

> The bridge fails with `Pipeline nodes with a 'data_type' require the
> tjfusion_protocol package` if `tjfusion_protocol` is missing. `setup_fusion_env.sh`,
> `FusionDocker/run.sh` (which adds `protocol/` to `PYTHONPATH`), and the editable
> install above each resolve it.

## `tjfusion docker-select`

Use interactive selection for which dockers should be started.

- Up/Down: move
- Space: select/unselect
- Enter: save
- q: cancel

```bash
tjfusion docker-select
```

## `tjfusion start`

Start all dockers selected in `docker_launch.yaml`.

```bash
tjfusion start
```

## One-Click Start (`FusionDocker/run.sh`)

`FusionDocker/run.sh` is the single entry point for bringing up the whole
stack. It reads `FusionDocker/configs/docker_launch.yaml`, frees any stale
managed ports, builds + launches every docker in `selected_dockers` (each in
its own tmux window, auto-building via the folder's `build.sh` if the image is
missing), and serves the web dashboard at `http://localhost:8765`.

```bash
cd FusionDocker
./run.sh
```

`run.sh` starts the **model containers + dashboard**; bring the **bridge** up
from the dashboard (the entries under `bridges:` become start/stop buttons), or
run it directly:

```bash
PYTHONPATH=src python3 -m fusion_docker serve-bridge \
  --config configs/bridge.realsense_split.yaml --verbose
```

### Pipeline architecture

```
RealSenseDocker (camera source, PUB :5551)
  → bridge (SUB, seeds shared store)
      → fast_foundation (depth :4444) · sam3 (mask :5562) · siglip2 (status :7777)   [parallel]
      → flowpose (pose :6667)   [depends_on fast_foundation, sam3]
  → result_pub :8899 → MarvinDocker (action)
```

- **Camera and depth are split**: `RealSenseDocker` is the only camera source;
  `Fast-FoundationSteroDocker` is now a pure stereo→depth estimator. Its
  `run.sh`/`build.sh` are the depth-only variant; the retired combined
  camera+depth scripts are preserved as `run.combined.sh`/`build.combined.sh`.
- **All model servers speak the standard protocol** (`tjfusion_protocol`,
  NumPy multipart, no base64). Each subclasses `BaseModelServer` and lives in
  `<Docker>/Server/StandardProtocol/`.
- **Which models run / in what order** is config-only in
  `configs/bridge.realsense_split.yaml` (`enabled`, `depends_on`, `endpoint`).
  See `USER_MANUAL.md` for the full pipeline-authoring guide.
