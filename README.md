# TJFUSION

## Version

Current version: `0.0.1`

Check version:

```bash
tjfusion -v
```

## Install `tjfusion`

```bash
curl -fsSL https://raw.githubusercontent.com/yangzhaofeng496/TJFusion/main/install.sh | bash
```

## Configure

```bash
export DOCKER_MODEL_ROOT=/path/to/DockerModel
```

## `tjfusion root`

Show current `DOCKER_MODEL_ROOT` path.

```bash
tjfusion root
```

## `tjfusion docker-config`

Use interactive selection for which dockers should be started.

- Up/Down: move
- Space: select/unselect
- Enter: save
- q: cancel

```bash
tjfusion docker-config
```

## `tjfusion start`

Start all dockers selected in `docker_launch.yaml`.

```bash
tjfusion start
```
