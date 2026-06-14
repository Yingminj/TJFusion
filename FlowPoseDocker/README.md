# FlowPoseDocker — 6-DoF pose estimation (`pose`)

FlowPose served as a standard-protocol **`pose`** model server. It estimates
6-DoF object poses from color + metric depth + a combined mask, and is the
second pipeline layer (`depends_on: [fast_foundation, sam3]`).

> Vendored upstream: `FlowPose/`.

## Protocol contract (`protocol/schemas/pose.json`)

| | content |
|---|---|
| `request.arrays`  | `color` `[H,W,3]` uint8, `depth` `[H,W]` float32, `combined_mask` `[H,W]` uint8 |
| `request.fields`  | `color_intrinsics?`, `obj_ids?`, `class_names?`, `instance_names?` |
| `response.fields` | `objects` (list of `{name, pose, length, obj_id, box_id}`) |

The depth is aligned to the color camera upstream, so pose uses the **color**
intrinsics. Poses and lengths are returned in **meters**. The server
(`Server/StandardProtocol/flowpose_server.py`) subclasses `BaseModelServer`; the
pose inference is lifted verbatim from the old base64-JSON server, only the I/O
layer changed (NumPy multipart, no cv2 visualization). Default port: **6667**
(`config.yaml → server.port`).

## Build & run

```bash
cd FlowPoseDocker
python3 download_models.py     # fetch weights into model/ (see guide below)
./build.sh                     # -> flowpose:latest  (repo root as build context)
./run.sh                       # pose server on tcp://0.0.0.0:6667 (needs GPU)
```

`config.yaml → paths` points the server at the weights below; `visualization`
holds the default camera intrinsics used for debug overlays.

---

# FlowPose 模型权重下载指南

## 📍 文件位置

- **Python 下载脚本**: `./download_models.py` （推荐）
- **模型保存目录**: `./` （当前目录，也就是 `FlowPoseDocker/model/`）

## 🎯 需要的权重文件

代码中配置的路径（`config.yaml` 中）：
```yaml
paths:
  pretrained_flow_model_path: /workspace/model/flowpose.pth
  pretrained_scale_model_path: /workspace/model/scalenet.pth
```

本地对应目录：`/home/kewei/TJFusion/FlowPoseDocker/model/`

需要下载的文件：
- `flowpose.pth` - FlowPose 主模型
- `scalenet.pth` - 尺度预测网络模型
- `dinov2_vits14_pretrain.pth` - DINOv2 预训练权重
- `facebookresearch_dinov2_main/` - DINOv2 本地仓库目录

## 📥 下载方式

### 方式 1: 使用 Python 脚本（推荐）

**安装依赖**（如果未安装）：
```bash
pip install modelscope
```

**运行下载脚本**：
```bash
cd /home/kewei/TJFusion/FlowPoseDocker/model
python3 download_models.py
```

或指定保存目录：
```bash
python3 download_models.py --save-dir /home/kewei/TJFusion/FlowPoseDocker/model
```

### 方式 2: 手动下载

1. 访问 ModelScope 模型页面：
   https://www.modelscope.cn/models/kernelmind/FlowPose/files

2. 下载以下文件：
   - `flowpose.pth`
   - `scalenet.pth`
   - `dinov2_vits14_pretrain.pth`
   - `facebookresearch_dinov2_main/`

3. 将文件放在：
   `/home/kewei/TJFusion/FlowPoseDocker/model/`

## ✅ 验证

下载完成后，检查文件是否存在：
```bash
ls -lh /home/kewei/TJFusion/FlowPoseDocker/model/
```

应该看到：
```
-rw-r--r-- ... flowpose.pth
-rw-r--r-- ... scalenet.pth
-rw-r--r-- ... dinov2_vits14_pretrain.pth
drwxr-xr-x ... facebookresearch_dinov2_main
```

## 🐳 Docker 中的使用

当你运行 Docker 容器时，这些文件会自动通过 volume mount 映射到容器内：
```
本地: /home/kewei/TJFusion/FlowPoseDocker/model/
容器: /workspace/model/
```

`run.sh` 里的 DINO checkpoint 挂载路径也已经改成：
```bash
./model/dinov2_vits14_pretrain.pth
```

代码会自动从配置中读取路径：
```python
pretrained_flow_model_path: /workspace/model/flowpose.pth
pretrained_scale_model_path: /workspace/model/scalenet.pth
```

## 🔗 ModelScope 仓库

官方仓库地址：
https://www.modelscope.cn/models/kernelmind/FlowPose

## 💡 故障排除

| 问题 | 解决方案 |
|------|--------|
| `modelscope` 库未安装 | 运行 `pip install modelscope` |
| 网络连接失败 | 检查网络连接，尝试 VPN 或代理 |
| 权限拒绝 | 确保有写入权限: `chmod 755 download_models.py` |
| 文件已存在 | 脚本会自动覆盖旧文件 |
| 下载不完整 | 删除不完整的文件后重试 |

## 📝 配置文件参考

`config.yaml` 中的相关配置：
```yaml
paths:
  py_runner_path: /workspace/FlowPose/py_runners
  pretrained_flow_model_path: /workspace/model/flowpose.pth
  pretrained_scale_model_path: /workspace/model/scalenet.pth
```

如需修改权重路径，编辑 `config.yaml` 中的 `paths` 部分。
