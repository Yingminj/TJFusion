# FusionDocker

这个项目现在主要围绕两件事：

- 管理 `DockerModel` 里的 docker
- 管理和运行多个 bridge

下面只保留最常用的操作。

## 准备

安装依赖：

```bash
pip install -r requirements.txt
```

统一命令入口：

```bash
PYTHONPATH=src python3 -m fusion_docker --help
```

## 1. 一键启动所有 Docker

推荐直接使用 launch config：

```bash
PYTHONPATH=src python3 -m fusion_docker launch-dockers \
  --launch-config configs/docker_launch.yaml
```

如果你希望同时打开 Web UI：

```bash
PYTHONPATH=src python3 -m fusion_docker serve-ui \
  --launch-config configs/docker_launch.yaml
```

默认配置文件：

- [docker_launch.yaml](/home/yang/Desktop/DockerModel/FusionDocker/configs/docker_launch.yaml)

## 2. 关闭某个 Docker

目前最直接的方式是通过 UI：

```bash
PYTHONPATH=src python3 -m fusion_docker serve-ui \
  --launch-config configs/docker_launch.yaml
```

然后在页面里选择对应 docker，点击 `Stop Docker`。

说明：

- 当前 CLI 里有“一键启动 docker”
- “关闭单个 docker” 现在主要通过 UI 完成

## 3. 开启某个 Bridge

如果你已经有 bridge 配置文件，可以直接启动：

```bash
PYTHONPATH=src python3 -m fusion_docker serve-bridge \
  --config configs/bridge.local.yaml
```

如果你想在 UI 里管理 bridge，先启动 UI：

```bash
PYTHONPATH=src python3 -m fusion_docker serve-ui \
  --launch-config configs/docker_launch.yaml
```

然后在 `Bridge Window` 里选择 bridge，点击 `Start Bridge`。

## 4. 创建 Bridge

自动生成 bridge 模块和配置文件：

```bash
PYTHONPATH=src python3 -m fusion_docker create-bridge my_bridge
```

生成后你会得到：

- `src/fusion_docker/bridges/my_bridge.py`
- `configs/bridge.my_bridge.yaml`
- 自动注册到 `src/fusion_docker/bridges/__init__.py`

查看当前有哪些 bridge：

```bash
PYTHONPATH=src python3 -m fusion_docker list-bridges
```

## 5. 导入 Bridge 到 UI

把某个 bridge 自动加入 `docker_launch.yaml`：

```bash
PYTHONPATH=src python3 -m fusion_docker add-bridge-to-ui MyBridge \
  --bridge-config configs/bridge.my_bridge.yaml \
  --launch-config configs/docker_launch.yaml
```

如果同名 bridge 已存在，想覆盖：

```bash
PYTHONPATH=src python3 -m fusion_docker add-bridge-to-ui MyBridge \
  --bridge-config configs/bridge.my_bridge.yaml \
  --launch-config configs/docker_launch.yaml \
  --force
```

导入完成后，重新启动 UI：

```bash
PYTHONPATH=src python3 -m fusion_docker serve-ui \
  --launch-config configs/docker_launch.yaml
```

然后就可以在 `Bridge Window` 里看到它。

## 6. 创建某个 Docker 骨架

如果你想在 `DockerModel` 下面新建一个标准 docker 目录骨架：

```bash
PYTHONPATH=src python3 -m fusion_docker create-system MySystem \
  --docker-model-root /home/yang/Desktop/DockerModel
```

这个命令会自动创建一套基础文件，包括：

- `Dockerfile`
- `build.sh`
- `run.sh`
- `config.yaml`
- `Server/server.py`
- `RequestFormat/input.schema.json`
- `RequestFormat/output.schema.json`

如果目标目录已经存在，想覆盖：

```bash
PYTHONPATH=src python3 -m fusion_docker create-system MySystem \
  --docker-model-root /home/yang/Desktop/DockerModel \
  --force
```

## 7. 接入实时视频流到网页

现在 Web UI 已经支持单独的 `Video Window`。

你的任意 docker 只要向 dashboard 发送一份 JSON：

```json
{
  "title": "Siglip Preview",
  "frame_base64": "<base64_jpg_or_png>",
  "mime_type": "image/jpeg",
  "source": "SiglipDocker"
}
```

网页就会自动创建一个对应标题的视频窗口，并持续显示这个标题的最新一帧。

### 7.1 接口说明

上传接口：

```text
POST /api/video-stream
```

字段说明：

- `title`: 视频窗口标题，同一个 `title` 会覆盖为最新帧
- `frame_base64`: 图像内容的 base64，推荐传 JPG 或 PNG 编码后的字节
- `mime_type`: 可选，默认 `image/jpeg`
- `source`: 可选，用于在网页里显示来源 docker 名称

查询接口：

```text
GET /api/video-streams
```

这个接口主要给网页自己轮询使用，一般 docker 侧不需要手动调用。

### 7.2 最小接入方式

如果你的 docker 能拿到一张已经编码好的 JPG/PNG 字节流，最简单的方式是直接复用：

- [video_stream_client.py](/home/yang/Desktop/DockerModel/FusionDocker/src/fusion_docker/video_stream_client.py)

示例：

```python
from fusion_docker.video_stream_client import (
    encode_image_bytes_to_base64,
    post_video_stream_frame,
)

jpg_bytes = ...  # 你的实时图像，已经编码成 jpg/png 的 bytes

post_video_stream_frame(
    "http://127.0.0.1:8765",
    title="Siglip Preview",
    frame_base64=encode_image_bytes_to_base64(jpg_bytes),
    mime_type="image/jpeg",
    source="SiglipDocker",
)
```

### 7.3 OpenCV 示例

如果你手里是 `numpy` 图像，可以先编码再上传：

```python
import cv2
from fusion_docker.video_stream_client import (
    encode_image_bytes_to_base64,
    post_video_stream_frame,
)

frame = ...  # BGR numpy image

ok, buf = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 85])
if not ok:
    raise RuntimeError("Failed to encode frame")

post_video_stream_frame(
    "http://127.0.0.1:8765",
    title="Camera Debug",
    frame_base64=encode_image_bytes_to_base64(buf.tobytes()),
    mime_type="image/jpeg",
    source="MyDocker",
)
```

### 7.4 不想依赖项目 helper 时

你也可以直接自己发 HTTP 请求：

```bash
curl -X POST http://127.0.0.1:8765/api/video-stream \
  -H 'Content-Type: application/json' \
  -d '{
    "title": "Siglip Preview",
    "frame_base64": "<base64_jpg_or_png>",
    "mime_type": "image/jpeg",
    "source": "SiglipDocker"
  }'
```

### 7.5 接入约定

## 8. 查询服务端口和端口流量

列出当前机器上所有监听中的服务端口：

```bash
PYTHONPATH=src python3 -m fusion_docker inspect-ports
```

检查某个端口是否正在监听，并输出当前连接快照，例如 `1883`：

```bash
PYTHONPATH=src python3 -m fusion_docker inspect-ports --port 1883
```

如果你要判断某个端口最近几秒是否真的有消息/报文经过，可以加短时抓包：

```bash
sudo PYTHONPATH=src python3 -m fusion_docker inspect-ports --port 1883 --watch-seconds 10
```

说明：

- 不加 `--port` 时，只列监听端口
- 加 `--port` 时，会额外输出该端口的连接信息
- 加 `--watch-seconds` 时，会调用 `tcpdump` 检查这段时间内是否有报文
- 抓包通常需要 `sudo`

- 建议把每一路视频流固定一个 `title`
- 同一个 `title` 连续上传时，网页只保留最新帧
- 推荐传 JPG，体积更小，刷新更快
- 如果是深度图、mask、调试图，也可以传 PNG
- 这个接口当前接收的是“单帧图片流”，标准是 `title + base64 图像帧`，网页端会把它当作实时视频显示

### 7.6 在网页哪里看

启动 UI：

```bash
PYTHONPATH=src python3 -m fusion_docker serve-ui \
  --launch-config configs/docker_launch.yaml
```

打开网页后，进入：

- `Video Window`

就能看到所有已上传的实时图像窗口。

### 7.7 本地测试 Demo

项目里已经带了一个可直接运行的测试脚本：

- [push_video_demo.py](/home/yang/Desktop/DockerModel/FusionDocker/scripts/push_video_demo.py)

先启动 UI：

```bash
PYTHONPATH=src python3 -m fusion_docker serve-ui \
  --launch-config configs/docker_launch.yaml
```

再运行 demo：

```bash
python3 scripts/push_video_demo.py --dashboard http://127.0.0.1:8765
```

如果你想一次模拟多路视频：

```bash
python3 scripts/push_video_demo.py \
  --dashboard http://127.0.0.1:8765 \
  --streams 4 \
  --fps 8
```

## 常用文件

- [docker_launch.yaml](/home/yang/Desktop/DockerModel/FusionDocker/configs/docker_launch.yaml)
- [bridge.local.yaml](/home/yang/Desktop/DockerModel/FusionDocker/configs/bridge.local.yaml)
- [cli.py](/home/yang/Desktop/DockerModel/FusionDocker/src/fusion_docker/cli.py)
- [video_stream_client.py](/home/yang/Desktop/DockerModel/FusionDocker/src/fusion_docker/video_stream_client.py)
- [push_video_demo.py](/home/yang/Desktop/DockerModel/FusionDocker/scripts/push_video_demo.py)
