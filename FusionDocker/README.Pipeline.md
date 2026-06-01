# 如何编写 Bridge Pipeline YAML（含 RealSense + 深度拆分）

本文说明怎么用 `custom_pipeline` 的 `pipeline:` 配置来**控制运行哪些模型、控制顺序、
即插即用地接新模型**，并给出 RealSense/Fast-Foundation 拆分后的示例配置。

> ⚠️ **重要边界（请先读）**
> Phase 1 已交付：标准协议 `protocol/`、RealSense 源服务、纯深度 Fast-Foundation 服务。
> 这三者之间用**新协议（NumPy multipart + 标准信封）**通信，已用 `ModelClient` 验证通过。
>
> 但**当前 bridge 仍说旧协议**（base64 JSON，store 里 seed 的是 `rgb/depth/rgb_image`，
> 且**还不解析 `data_type`**）。所以下面的 `bridge.realsense_split.yaml` 是 **Phase 2/3
> 迁移完成后**的目标配置；在 bridge 改造前，它还不能与新服务端直接互通。
> 本文末尾「现在能跑什么」一节给出当前可立即验证的路径。

---

## 1. 一个 pipeline 节点的字段

`pipeline:` 是一个**有序列表**，每个元素是一个模型节点（对应 `ModelNode`，见
`src/fusion_docker/models.py`）：

```yaml
- name: flowpose            # 节点唯一名（也用于 depends_on 引用）
  kind: generic             # 适配器类型；目前只有 "generic"
  data_type: pose           # ★ 六类型之一（Phase 2 起用于自动 schema 校验）
  endpoint: tcp://127.0.0.1:6667   # 该模型 server 的 ZMQ 地址
  enabled: true             # false = 跳过该模型（控制“运行哪些”）
  timeout_ms: 5000          # 该节点 REQ 超时
  depends_on:               # 依赖的节点名；都完成后才跑（控制“顺序”）
    - fast_foundation
    - sam3
  role: required            # required / optional（失败处理语义）
  inputs:                   # 该节点需要 store 里存在的键（缺则报错）
    - color
    - depth
    - combined_mask
  request_map:              # 构造发给 server 的请求：键=请求字段，值=取数来源
    color: $color           #   $xxx = 从共享 store 取 xxx
    depth: $depth
    combined_mask: $combined_mask
    return_masks:
      value: true           #   {value: ...} = 字面量
  response_map:             # 把响应字段写回 store：键=store 键，值=响应里的路径
    objects: objects
```

### 三个目标怎么落到字段上
- **控制运行哪些模型** → 节点的 `enabled: true/false`（`false` 直接跳过）。
- **控制顺序** → `depends_on`。bridge 按依赖做**拓扑分层**：无依赖关系的节点在同一层
  **并行**执行，后层等前层全部完成。例：`fast_foundation` 与 `sam3`、`siglip2` 同层
  并行；`flowpose` 依赖前两者，排到下一层。
- **即插即用** → 加一个模型 = 列表里**加一个节点**（起一个符合协议的 server + 写
  endpoint/inputs/request_map/response_map）。**无需改 bridge Python 代码。**

### `request_map` / `response_map` 的取值语法
- `request_map` 的值：
  - `$key` → 从共享 store 取 `key`
  - `{value: X}` → 字面量 `X`
- `response_map` 的值：响应里的字段路径（字符串或点分路径 `a.b.c`，或列表 `[a,b]`）。
- 不写 `request_map` 时，退化为「把 `inputs` 里每个键原样发出」。
- 不写 `response_map` 时，退化为「把响应里与 `outputs` 同名的键写回 store」。

### 共享 store（节点间的数据总线）
源数据先 seed 进 store，每个节点的 `response_map` 再把输出写回 store，供后续节点 `$引用`。
**新标准下源会 seed 的键**（来自 RealSense 标准消息）：
`color`、`ir_left`、`ir_right`、`hw_depth`（可选）、`intrinsics`、`color_intrinsics`、
`baseline_m`、`ir_to_color_rotation`、`ir_to_color_translation`、`prompts`、`request_id`。

---

## 2. RealSense + 深度拆分后的数据流

```
RealSenseDocker (相机源, 唯一有 pyrealsense2)
  PUB tcp://*:5551  ──标准消息(color, ir_left, ir_right [,hw_depth] + 相机参数)──┐
                                                                                  │
                                                            bridge (SUB 5551) ────┤ seed 进 store
                                                                                  │
   ┌──────────────────────────── pipeline 分层执行 ──────────────────────────────┘
   │  第1层(并行):  fast_foundation(depth)   sam3(mask)   siglip2(status)
   │                  ir_left+ir_right→depth   color→mask    color→status
   │  第2层:        flowpose(pose)  ← depends_on: [fast_foundation, sam3]
   │                  color+depth+combined_mask → objects
   └──────────────────────────────────────────────────────────────────────────────
                                          └─ result_pub → MarvinDocker(action)
```

Fast-Foundation 不再开相机：它现在是 `data_type: depth` 的纯估计器，吃
`ir_left`/`ir_right`/`intrinsics`/`baseline_m`，吐 `depth`(float32)。
深度也可改用 RealSense 的 `hw_depth`（把 flowpose 的 `depth: $depth` 改成 `depth: $hw_depth`，
并删掉 fast_foundation 节点即可——这就是“自由调用 rgb 或 depth”）。

完整示例见：[`configs/bridge.realsense_split.yaml`](configs/bridge.realsense_split.yaml)

---

## 3. 启动顺序

```bash
# 1) 相机源（REP+PUB）。需要 USB 直通。
RealSenseDocker/build.sh && RealSenseDocker/run.sh

# 2) 纯深度 Fast-Foundation（需要 GPU；权重运行时挂载）
Fast-FoundationSteroDocker/build.depth.sh
Fast-FoundationSteroDocker/run.depth.sh          # 默认监听 tcp://0.0.0.0:4444

# 3) 其余模型 server（sam3/siglip2/flowpose）照常起，监听各自端口

# 4) bridge（Phase 2/3 迁移后）
cd FusionDocker
PYTHONPATH=src python3 -m fusion_docker serve-bridge \
  --config configs/bridge.realsense_split.yaml
```

---

## 4. 怎么增删 / 改顺序（常见操作）

- **临时停用某模型**：该节点 `enabled: false`。
- **改顺序/串并行**：调整 `depends_on`。想让 A 在 B 后跑就给 A 加 `depends_on: [B]`；
  想并行就去掉彼此依赖。
- **接一个全新模型**（如新加一个 `data_type: mask` 的分割器）：
  1. 用 `BaseModelServer` 写好 server（实现 `load_model`/`infer`），起在某端口；
  2. 在 `pipeline:` 加一个节点，填 `data_type`/`endpoint`/`inputs`/`request_map`/`response_map`；
  3. 不用动 bridge 代码。

---

## 5. 现在（Phase 1）能立即验证什么

新协议三件套可**脱离 bridge** 直接联调：

```bash
# 协议自测（无需相机/GPU）
cd protocol && python -m tests.test_protocol

# 直接用 ModelClient 调新服务端（伪数据示例见各 server 顶部 docstring）
#   from tjfusion_protocol.client import ModelClient
#   from tjfusion_protocol.envelope import make_request
#   resp = ModelClient("tcp://127.0.0.1:4444", data_type="depth").call(req)
```

bridge 端到端要等 **Phase 2**（给 `ModelNode` 加 `data_type` 解析 + 让 generic 适配器
改用 `ModelClient`/multipart + schema 校验）和 **Phase 3**（源接收改成标准消息、store seed
键切到 `color/ir_left/...`）完成后才能跑通。
```
