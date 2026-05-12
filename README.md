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
