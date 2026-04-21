# TJFUSION

## Install `tjfusion`

```bash
curl -fsSL https://raw.githubusercontent.com/yangzhaofeng496/TJFusion/main/install.sh | bash
```

## Configure

```bash
export DOCKER_MODEL_ROOT=/path/to/DockerModel
```

## Commands

### `tjfusion -v`

用途：查看当前 `tjfusion` 版本，确认安装/更新是否生效。  

```bash
tjfusion -v
```

### `tjfusion root`

用途：显示当前 `DOCKER_MODEL_ROOT` 的实际路径（绝对路径）。  
场景：排查路径配置错误、确认当前使用的是哪个 DockerModel 目录。  

```bash
tjfusion root
```

### `tjfusion docker-config`

用途：交互式选择要启动的 docker，并写入 `docker_launch.yaml`。  
场景：切换一组需要启动的模块。  

操作键：
- Up/Down: move
- Space: select/unselect
- Enter: save
- q: cancel

```bash
tjfusion docker-config
```

### `tjfusion start`

用途：按 `docker_launch.yaml` 中已选内容启动 docker。  
场景：日常一键启动当前配置。  

```bash
tjfusion start
```

### `tjfusion restart`

用途：先清理再重启已选 docker。  
场景：服务异常、端口冲突、需要完整重启流程。  

```bash
tjfusion restart
```

### `tjfusion update`

用途：拉取最新代码并刷新 Python 包。  
场景：升级到最新版本后继续使用同一套命令。  

```bash
tjfusion update
```
