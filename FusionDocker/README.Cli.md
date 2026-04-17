# FusionDocker CLI

工作目录：

```bash
cd /home/yang/Desktop/DockerModel/FusionDocker
```

统一入口：

```bash
PYTHONPATH=src python3 -m fusion_docker --help
```

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

```

只看 3 条后退出：

```bash
PYTHONPATH=src python3 -m fusion_docker listen-zmq --port 8899 --topic /siglip2/result --limit 3
```
