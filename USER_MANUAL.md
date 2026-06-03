# TJFusion 用户手册（新版 · 标准协议架构）

> 适用分支：`feature/status_modification`
> 本手册覆盖 Phase 1–3 改造后的新架构：**统一标准协议**、**相机/深度拆分**、
> **config 驱动的可插拔流水线**。

---

## 目录

1. [它解决了什么问题](#1-它解决了什么问题)
2. [整体架构与数据流](#2-整体架构与数据流)
3. [六种核心数据类型与标准信封](#3-六种核心数据类型与标准信封)
4. [快速开始](#4-快速开始)
5. [构建与运行各服务](#5-构建与运行各服务)
6. [编写 Bridge 流水线 YAML](#6-编写-bridge-流水线-yaml)
7. [接入一个新模型（即插即用）](#7-接入一个新模型即插即用)
8. [常见操作速查](#8-常见操作速查)
9. [测试与排错](#9-测试与排错)
10. [迁移说明与兼容性](#10-迁移说明与兼容性)
11. [术语表](#11-术语表)

---

## 1. 它解决了什么问题

改造前：各模型 Docker 各说各的报文格式（`status:"ok"` vs `ok:true`、字段名
`rgb_image`/`rgb`/`image_b64` 混用），编排与顺序硬编码，加一个模型要改代码，
RealSense 还被焊死在 Fast-Foundation 里。

改造后，你得到三件事：

- **控制运行哪些模型** —— 流水线节点的 `enabled`
- **控制运行顺序** —— 节点的 `depends_on`（支持并行）
- **即插即用** —— 新模型按标准协议封装 + 在 YAML 加一个节点，**不改 bridge 代码**

加上一个统一的线协议：**标准信封 + NumPy multipart（不再 base64）+ 六类型 schema 校验**。

---

## 2. 整体架构与数据流

```
RealSenseDocker (相机源, 唯一 pyrealsense2)
  ├─ REP :5550   按需取 color / ir_left / ir_right / hw_depth + 相机参数
  └─ PUB :5551   持续推标准消息 ───────────────┐
                                                ▼
                                  FusionDocker / bridge (SUB)
                                  source_mode: protocol
                                  把 message.arrays/fields 直接 seed 进共享 store
                                                │
        ┌──────────── pipeline DAG（顺序=depends_on，同层并行）─────────────┐
        ▼                         ▼                       ▼
  fast_foundation(depth)     sam3(mask)            siglip2(status)
  ir_left+ir_right→depth     color→combined_mask    color→best_category
        └──────────────┬───────────┘
                       ▼
               flowpose(pose)  depends_on:[fast_foundation, sam3]
               color+depth+mask→objects
                       │
                       ▼  result_pub :8899
               MarvinDocker (action)
```

每个模型 = 一个 ZMQ REP server；bridge = 一个 SUB 源 + DAG 调度器（ZMQ REQ 调各 server）。

---

## 3. 六种核心数据类型与标准信封

六类型：`rgb` · `depth` · `mask` · `status` · `pose` · `action`。
每种一份契约：`protocol/tjfusion_protocol/schemas/<type>.json`，分别描述
`request` / `response` 的 `fields`（小结构数据）与 `arrays`（NumPy 数组）。

### 标准信封（每条消息外层都一样）

| 字段 | 含义 |
|---|---|
| `schema_version` | 协议版本（`"1.0"`） |
| `data_type` | 六类型之一 |
| `request_id` | 请求标识，响应原样回带 |
| `status` | `ok` / `error`（统一） |
| `error` | `null` 或错误信息 |
| `elapsed_ms` | 处理耗时 |

包头之内：
- `fields`：可 JSON 序列化的小数据（内参、位姿、标签、prompts……）
- `arrays`：命名 NumPy 数组（color/depth/mask……），**走独立二进制帧，不进 JSON**

> **为什么有"信封"？** 通用机制（bridge 路由、日志、错误处理）只读信封就能工作，
> 永远不需要理解里面是哪个模型。新增模型不会破坏路由，因为信封是封闭固定的。

### 线格式：NumPy multipart（本地传输，放弃 base64）

```
Frame 0 : 包头 JSON（信封 + arrays 描述符列表，有序）
Frame 1 : arrays[0].tobytes()    # C 连续原始字节
Frame 2 : arrays[1].tobytes()
...
```
包头里 `arrays:[{name,dtype,shape},...]` 按帧顺序描述，接收方
`np.frombuffer(frame,dtype).reshape(shape)` 还原。float32 深度无损、零编码开销。

### 字段命名标准（消除历史别名）

| 类型 | arrays | 关键 fields |
|---|---|---|
| rgb | `color` | `intrinsics` |
| depth | in:`left`,`right` · out:`depth` | `intrinsics`,`baseline_m`,`unit`,`z_far` |
| mask | in:`color` · out:`masks`,`combined_mask` | `prompts`,`obj_ids`,`class_names`,`scores` |
| status | in:`color`(+可选`mask`) | `best_category`,`best_similarity`,`topk` |
| pose | in:`color`,`depth`,`combined_mask` · out:无 | `intrinsics`,`objects` |
| action | 无 | in:`objects`,`best_category`,`goal` · out:`action`,`action_params`,`done` |

---

## 4. 快速开始

### 4.1 无需相机/GPU 的本地验证

```bash
# 协议自测
cd protocol && python -m tests.test_protocol

# bridge 协议路径 ↔ 真实 server（multipart 端到端）
PYTHONPATH="protocol;FusionDocker/src" python FusionDocker/tests/test_phase2_protocol_node.py

# 完整源→DAG→结果（伪 RealSense PUB）
PYTHONPATH="protocol;FusionDocker/src" python FusionDocker/tests/test_phase3_protocol_source.py
```

> Windows PowerShell 下 `PYTHONPATH` 用分号 `;` 分隔（如上）；Linux/macOS 用冒号 `:`。

### 4.2 上硬件的最小链路

1. 起 RealSense 源：`RealSenseDocker/build.sh && RealSenseDocker/run.sh`
2. 起纯深度 Fast-Foundation：`Fast-FoundationSteroDocker/build.depth.sh && run.depth.sh`
3. 起其余模型 server（sam3 / siglip2 / flowpose），各自监听端口
4. 起 bridge：
   ```bash
   cd FusionDocker
   PYTHONPATH=src python3 -m fusion_docker serve-bridge \
     --config configs/bridge.realsense_split.yaml
   ```

---

## 5. 构建与运行各服务

> **构建上下文 = 仓库根**。RealSense 与 ffs-depth 镜像需要把共享的 `protocol/`
> 包 COPY 进镜像，所以务必用提供的 `build*.sh`（它们 `cd` 到仓库根再 `docker build -f ...`）。
> 仓库根的 `.dockerignore` 已排除无关的同级 Docker 项目，构建上下文很小。

### 5.1 RealSenseDocker（相机源）

| 文件 | 说明 |
|---|---|
| `RealSenseDocker/Dockerfile` | `ubuntu:22.04` + pyrealsense2（无 CUDA） |
| `RealSenseDocker/build.sh` | `docker build -f RealSenseDocker/Dockerfile -t realsense:latest .`（在仓库根） |
| `RealSenseDocker/run.sh` | `--privileged -v /dev:/dev --net=host`（USB 直通） |

运行参数（透传给 `realsense_server.py`）：
```bash
RealSenseDocker/run.sh \
  --rep-bind tcp://0.0.0.0:5550 \
  --pub-bind tcp://0.0.0.0:5551 \
  --pub-streams color,ir_left,ir_right
# 仅 REP：--no-pub   仅 PUB：--no-rep   关硬件深度：--no-hw-depth
```

两种接口：
- **REP（按需）**：请求 `fields.streams=["color","ir_left",...]`，返回最新帧 + 相机参数
- **PUB（推流）**：每帧作为标准 `rgb` 消息发布，供 bridge / Fast-Foundation 高频消费

暴露的流：`color`、`ir_left`、`ir_right`、`hw_depth`（硬件深度，米制 float32）。

### 5.2 Fast-Foundation（纯深度估计器）

不再开相机。输入立体 `left`/`right` + `intrinsics`/`baseline_m`，输出 `depth`。

| 文件 | 说明 |
|---|---|
| `Fast-FoundationSteroDocker/Dockerfile.depth` | CUDA 12.8 + torch 2.8，**无 pyrealsense2** |
| `build.depth.sh` | 构建 `ffs-depth:latest`（仓库根上下文） |
| `run.depth.sh` | 需要 nvidia runtime；运行时挂载 `model/` 权重，监听 `:4444` |

> 注意：`depth_server.py` 的 `model.forward` 在骨架里是 TODO（无权重/CUDA 时返回零深度）。
> 上真实硬件时按文件内注释接回原 `InputPadder + model.forward` 即可。

### 5.3 其余模型 server

sam3 / siglip2 / flowpose 等照常运行。要让它们走**新协议**，把各自 server 迁到
`BaseModelServer`（见第 7 节）；未迁移前，对应节点**不写 `data_type`**即可继续走旧 JSON 路径。

---

## 6. 编写 Bridge 流水线 YAML

完整示例：`FusionDocker/configs/bridge.realsense_split.yaml`。

### 6.1 顶层结构

```yaml
bridge:
  type: custom_pipeline          # 用通用 DAG bridge
  source_mode: protocol          # 新：标准协议源（NumPy multipart）
  zmq_source_addr: tcp://127.0.0.1:5551   # RealSenseDocker 的 --pub-bind

  result_pub_addr: tcp://0.0.0.0:8899     # 结果 PUB 给 MarvinDocker（可选）
  result_tf_topic: /fusion/pose
  result_siglip_topic: /fusion/status

  prompts: [cup, red box]        # 默认 prompts（源消息里没带时用它）

  pipeline_outputs:              # 想从 bridge 最终拿到哪些字段
    - depth
    - combined_mask
    - obj_ids
    - objects

  pipeline:                      # 有序节点列表（见下）
    - ...
```

`source_mode` 三选一：

| 值 | 含义 |
|---|---|
| `protocol` | **新**：SUB 标准协议消息，arrays/fields 直接 seed 进 store |
| `zmq_source` | 旧：base64 RGB-D 流（向后兼容，原配置不受影响） |
| `external_json` | 旧：外部 JSON 请求 |

### 6.2 一个节点的字段

```yaml
- name: flowpose            # 节点唯一名（depends_on 用它引用）
  kind: generic             # 适配器，目前只有 generic
  data_type: pose           # ★ 六类型之一。写了它 → 走新协议；不写 → 走旧 JSON
  endpoint: tcp://127.0.0.1:6667
  enabled: true             # false = 跳过此模型
  timeout_ms: 5000
  depends_on: [fast_foundation, sam3]   # 都完成后才跑
  role: required            # required / optional
  inputs: [color, depth, combined_mask] # 需要 store 里存在的键（缺则报错）
  request_map:              # 构造请求：键=请求字段，值=取数来源
    color: $color           #   $xxx = 从 store 取 xxx
    depth: $depth
    combined_mask: $combined_mask
    return_masks: { value: true }   # {value:X} = 字面量
  response_map:             # 写回 store：键=store 键，值=响应里的路径
    objects: objects
```

**取值语法**
- `request_map` 值：`$key`（取 store）或 `{value: X}`（字面量）
- `response_map` 值：响应里的字段名 / 点分路径 `a.b.c` / 列表路径 `[a,b]`
- 省略 `request_map` → 把 `inputs` 每个键原样发出
- 省略 `response_map` → 把响应里与 `outputs` 同名的键写回 store

### 6.3 三个目标怎么落到字段

| 目标 | 字段 |
|---|---|
| 运行哪些模型 | `enabled: true/false` |
| 运行顺序 | `depends_on`（无依赖关系的节点同层**并行**） |
| 即插即用 | `pipeline:` 加一个节点（起 server + 写 endpoint/映射），不改代码 |

### 6.4 store（节点间数据总线）

`source_mode: protocol` 下，源消息的 arrays + fields 直接成为 store 键。RealSense 会
seed：`color`、`ir_left`、`ir_right`、`hw_depth`(可选)、`intrinsics`、`color_intrinsics`、
`baseline_m`、`ir_to_color_rotation`、`ir_to_color_translation`、`prompts`、`request_id`。
之后每个节点的 `response_map` 把输出写回 store，供后续节点 `$引用`。

> **想用硬件深度而非立体估计？** 删掉 `fast_foundation` 节点，把 flowpose 的
> `depth: $depth` 改成 `depth: $hw_depth` 即可——这就是"自由调用 rgb 或 depth"。

---

## 7. 接入一个新模型（即插即用）

### 7.1 服务端：继承 `BaseModelServer`

只需实现 `load_model()` 和 `infer()`，其余（REP socket、multipart 收发、编解码、
请求/响应 schema 校验、计时、错误信封、`--port` CLI）全部免费：

```python
from tjfusion_protocol.server import BaseModelServer
from tjfusion_protocol.envelope import Message

class MyMaskServer(BaseModelServer):
    data_type = "mask"

    def load_model(self):
        self.model = load_weights(...)

    def infer(self, request: Message) -> Message:
        color = request.arrays["color"]            # numpy, 已解码
        prompts = request.fields.get("prompts", [])
        combined, ids, names = self.model(color, prompts)
        return self.ok(
            request,
            arrays={"combined_mask": combined},     # float/uint8 数组
            fields={"obj_ids": ids, "class_names": names},
        )

if __name__ == "__main__":
    MyMaskServer.main()    # python my_server.py --port 5562
```

### 7.2 客户端 / bridge 节点

起好 server 后，在 `pipeline:` 加一个节点：

```yaml
- name: my_mask
  data_type: mask
  endpoint: tcp://127.0.0.1:5562
  inputs: [color, prompts]
  request_map: { color: $color, prompts: $prompts }
  response_map: { combined_mask: combined_mask, obj_ids: obj_ids }
```

**完成。不需要改 bridge 任何 Python 代码。**

### 7.3 镜像里装协议包

```dockerfile
COPY protocol /opt/tjfusion_protocol
RUN pip install /opt/tjfusion_protocol      # 仅依赖 numpy；ZMQ 用 [zmq] extra
```
开发期也可直接 `PYTHONPATH=protocol`。

---

## 8. 常见操作速查

| 我想… | 怎么做 |
|---|---|
| 临时停用某模型 | 该节点 `enabled: false` |
| 调整顺序 | 改 `depends_on`；想并行就去掉彼此依赖 |
| 让 A 在 B 之后跑 | 给 A 加 `depends_on: [B]` |
| 换深度来源为硬件深度 | 删 `fast_foundation` 节点，flowpose `depth: $hw_depth` |
| 改某模型地址 | 改该节点 `endpoint`（不必新建 bridge） |
| 让 bridge 输出更多字段 | 往 `pipeline_outputs` 加键名 |
| 把结果发给动作模块 | 设 `result_pub_addr` |
| 新模型暂不迁协议 | 该节点**不写** `data_type`，走旧 JSON 路径 |

---

## 9. 测试与排错

### 自测命令
```bash
cd protocol && python -m tests.test_protocol
PYTHONPATH="protocol;FusionDocker/src" python FusionDocker/tests/test_phase2_protocol_node.py
PYTHONPATH="protocol;FusionDocker/src" python FusionDocker/tests/test_phase3_protocol_source.py
```

### 常见报错

| 现象 | 原因 / 处理 |
|---|---|
| `requires the tjfusion_protocol package` | 节点写了 `data_type` 但镜像没装 `protocol`。`pip install ./protocol` 或加 `PYTHONPATH` |
| `Missing inputs for <node>: [...]` | `inputs` 里的键 store 里没有。检查源是否 seed、上游 `response_map` 是否写回 |
| `<node> request timeout` | 对应 server 没起 / 端口不对 / `timeout_ms` 太小 |
| `... response schema warnings: ...` | 响应字段不符 schema（迁移期仅告警，不中断）。对齐字段名或补 schema |
| `<node> returned error: ...` | server 端 `infer` 抛异常，错误信息已回带。看 server 日志 |
| `Array '<name>' size mismatch` | 数组 dtype/shape 与描述符不符，通常是手工拼包出错。用 `pack_message`/`ModelClient` |
| `Timeout waiting for protocol source` | bridge 没收到源消息。确认 RealSense PUB 地址 = bridge `zmq_source_addr` |

### verbose
```bash
PYTHONPATH=src python3 -m fusion_docker serve-bridge --config <yaml> --verbose
```

---

## 10. 迁移说明与兼容性

本次改造**向后兼容**，全部为新增 + 极小改动：

- 节点**不写 `data_type`** → 走原 `send_json` 旧路径，行为与改造前一致。
- `source_mode: zmq_source` / `external_json` → 原逻辑完全保留。
- 原 `Fast-FoundationSteroDocker/Dockerfile`、`bridge.custom.yaml` 等**未改动**。

**可以逐模型迁移**：先把已上协议的 server（RealSense、ffs-depth）对应节点加上
`data_type` 与 `source_mode: protocol`，其余保持旧路径，互不影响。

各阶段产物：
- **Phase 1**：`protocol/`（信封 + codec + 六类型 schema + `BaseModelServer`/`ModelClient`）、
  RealSense 源服务、纯深度 Fast-Foundation 骨架、Dockerfile/脚本
- **Phase 2**：`ModelNode.data_type` 解析；bridge 对 `data_type` 节点走新协议（multipart + 校验）
- **Phase 3**：`source_mode: protocol` 源接收 + store seed（`color`/`ir_left`/`intrinsics`/…）

---

## 11. 术语表

| 术语 | 含义 |
|---|---|
| 信封 Envelope | 每条消息固定的外层包头，六类型一致 |
| 数据类型 data_type | `rgb/depth/mask/status/pose/action` 之一 |
| 节点 ModelNode | 流水线里一个模型调用单元 |
| store | 流水线内的共享数据总线，节点间靠它传值 |
| DAG / 分层 | 按 `depends_on` 拓扑排序，同层并行、层间串行 |
| 适配器 adapter | 构造请求/处理响应的策略，目前为 `generic` |
| codec | `pack_message`/`unpack_message`，NumPy↔multipart |
| BaseModelServer | 服务端 SDK 基类，新模型只实现 `load_model`/`infer` |
| ModelClient | 客户端帮助类，按标准协议调用任意 server |

---

## 相关文档

- 协议细节：`protocol/README.md`
- 流水线编写（含新旧协议切换）：`FusionDocker/README.Pipeline.md`
- 新增 bridge 种类（少见，需改 Python）：`FusionDocker/README.Bridge.md`
- RealSense 拆分：`RealSenseDocker/README.md`
