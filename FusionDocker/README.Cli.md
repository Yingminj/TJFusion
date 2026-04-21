# FusionDocker CLI

工作目录：

```bash
cd /home/yang/Desktop/DockerModel/FusionDocker
```

统一入口：

```bash
PYTHONPATH=src python3 -m fusion_docker --help
```

## RELEASE 命令（推荐日常使用）

```bash
tjfusion -v
```

配置 `DOCKER_MODEL_ROOT`（必须）：

```bash
export DOCKER_MODEL_ROOT=/path/to/DockerModel
```

交互式选择要启动的 docker（写入 docker_launch.yaml）：

```bash
tjfusion docker-config
```

启动已选择的 docker：

```bash
tjfusion start
```

重启（先清理再启动）：

```bash
tjfusion restart
```

更新代码并刷新 Python 包：

```bash
tjfusion update
```

## DEBUG 命令（开发调试）

启动 Docker：

```bash
PYTHONPATH=src python3 -m fusion_docker launch-dockers --launch-config configs/docker_launch.yaml
```

启动 UI：

```bash
PYTHONPATH=src python3 -m fusion_docker serve-ui --launch-config configs/docker_launch.yaml
```

查看 8899 上的所有 ZMQ 消息：

```bash
PYTHONPATH=src python3 -m fusion_docker listen-zmq --port 8899
```

查看 `指定端口下的topic`：

```bash
PYTHONPATH=src python3 -m fusion_docker listen-zmq --port 8899 --topic topic
```

只看 3 条后退出：

```bash
PYTHONPATH=src python3 -m fusion_docker listen-zmq --port 8899 --topic /siglip2/result --limit 3
```
