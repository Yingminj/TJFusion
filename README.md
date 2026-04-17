# TJFUSION

## Install `tjfusion`

```bash
curl -fsSL https://raw.githubusercontent.com/yangzhaofeng496/TJFusion/main/install.sh | bash
```

## Configure

```bash
export DOCKER_MODEL_ROOT=/path/to/DockerModel
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
