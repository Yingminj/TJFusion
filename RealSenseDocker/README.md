# RealSenseDocker（相机源服务）

把 RealSense 从 Fast-Foundation 里**拆出来**的独立源服务。它是**唯一**导入
`pyrealsense2` 的组件，让调用方可以自由获取 RGB、立体 IR 对、或硬件深度，而不必
牵扯立体深度模型。

> Phase 1 状态：**骨架**。相机采集与参数读取已按原 Fast-Foundation 代码实现并做了
> 可选导入保护（无 SDK/无相机的机器也能 import 和单测）；尚未在真实相机上联调。

## 提供两种接口

### REP（按需请求）
调用方指定要哪些流，返回最新一帧：

```jsonc
// 请求（标准信封，data_type="rgb" 或 "depth"）
{ "fields": { "streams": ["color", "ir_left", "ir_right", "hw_depth"] } }
```

响应 `arrays` 含请求到的 `color`/`ir_left`/`ir_right`/`hw_depth`，`fields` 含相机参数：
`intrinsics`(左目K)、`color_intrinsics`、`baseline_m`、`ir_to_color_rotation`、
`ir_to_color_translation`。

最贴合"自由调用 rgb 或 depth"，且与 Bridge 的 REQ/REP 模型节点一致。

### PUB（持续推流）
每帧作为标准 `rgb` 消息发布（color + ir_left + ir_right + 可选 hw_depth），供
Fast-Foundation 高频 SUB 消费、连续跑深度。

## 暴露的流

- `color`   —— 彩色 [H,W,3] uint8
- `ir_left` / `ir_right` —— 立体 IR 对（转成 3 通道，喂给 Fast-Foundation）
- `hw_depth` —— RealSense **硬件深度**，米制 float32 [H,W]（按设计要求暴露）

所以下游"depth"有两条来源：RealSense 硬件深度，或 Fast-Foundation 立体估计。消费者自选。

## 运行

```bash
python Server/realsense_server.py \
  --rep-bind tcp://0.0.0.0:5550 \
  --pub-bind tcp://0.0.0.0:5551 \
  --pub-streams color,ir_left,ir_right
# 仅 REP：--no-pub   仅 PUB：--no-rep   关硬件深度：--no-hw-depth
```

## 与 Fast-Foundation 的新数据流

```
RealSenseDocker
  ├─REP→ 任意调用方按需取 color / ir_left / ir_right / hw_depth + 相机参数
  └─PUB→ Fast-FoundationDepthServer ──(left,right,intrinsics,baseline)──▶ depth(float32)
```

Fast-Foundation 不再开相机，只做立体深度估计（见
`Fast-FoundationSteroDocker/Server/StandardProtocol/depth_server.py`）。

## TODO（进入真实联调时）
- Dockerfile：`COPY protocol` 并 `pip install`，安装 `pyrealsense2`/`pyzmq`/`opencv`
- 在真实相机上验证 REP/PUB 两路
- 决定 PUB 默认是否带 `hw_depth`（带宽 vs 便利）
