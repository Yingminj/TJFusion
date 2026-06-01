# TJFusion 标准协议（`tjfusion_protocol`）

这是 Bridge 与所有模型 Docker **共用的唯一通信契约**。Phase 1 的目标：固化六种核心
数据类型的标准格式与接口，让新模型"按标准封装即可接入"。

依赖极轻（仅 `numpy`，ZMQ 按需懒加载），可在各模型镜像构建时直接 COPY 进去。

## 1. 六种核心数据类型

`rgb` · `depth` · `mask` · `status` · `pose` · `action`

每种类型一份声明式契约：`tjfusion_protocol/schemas/<type>.json`，分别描述
`request` 与 `response` 的 `fields`（小结构数据）和 `arrays`（NumPy 数组，按 dtype/ndim 校验）。

## 2. 标准信封（Envelope）

每条消息的**外层包头对六种类型完全一致**，通用机制（Bridge 路由、日志、错误处理）
只读信封，不关心里面是哪个模型：

| 信封字段 | 含义 |
|---|---|
| `schema_version` | 协议版本（当前 `"1.0"`） |
| `data_type` | 六类型之一 |
| `request_id` | 请求标识，响应原样回带 |
| `status` | `ok` / `error`（统一，不再有 `ok:true` vs `status:"ok"` 的分歧） |
| `error` | `null` 或错误信息 |
| `elapsed_ms` | 处理耗时 |

包头之内分两部分：
- `fields`：小的、可 JSON 序列化的结构数据（内参、位姿、标签、prompts……）
- `arrays`：命名的 NumPy 数组（color/depth/mask……），**不进 JSON**，由 codec 走独立二进制帧

## 3. 线格式：NumPy multipart（不再用 base64）

本地传输、带宽充足，故彻底放弃 base64 / PNG / JPG，直接发 NumPy 原始字节：

```
Frame 0 : 包头 JSON（信封 + arrays 描述符列表，有序）
Frame 1 : arrays[0].tobytes()   # C 连续原始字节
Frame 2 : arrays[1].tobytes()
...
```

包头里 `arrays: [{name,dtype,shape}, ...]` 按帧顺序描述 1..N 帧，接收方
`np.frombuffer(frame, dtype).reshape(shape)` 还原。**float32 深度无损**、零编码开销。

编解码只有一处实现（`codec.py` 的 `pack_message` / `unpack_message`），Bridge 与所有
server 共用，杜绝格式漂移。

## 4. 写一个新模型 server（即插即用的关键）

继承 `BaseModelServer`，只实现 `load_model()` 和 `infer()`，其余（REP socket、
收发、编解码、请求/响应校验、计时、错误信封、`--port` CLI）全部免费：

```python
from tjfusion_protocol.server import BaseModelServer
from tjfusion_protocol.envelope import Message

class MyDepthServer(BaseModelServer):
    data_type = "depth"

    def load_model(self):
        self.model = load_weights(...)

    def infer(self, request: Message) -> Message:
        left, right = request.arrays["left"], request.arrays["right"]
        depth = self.model(left, right)          # float32 [H,W]
        return self.ok(request, arrays={"depth": depth}, fields={"unit": "m"})

if __name__ == "__main__":
    MyDepthServer.main()      # python my_server.py --port 4444
```

接入流程：起一个符合契约的 server + 在 Bridge 的 `pipeline:` 加一个节点。**无需改 Bridge 代码。**

## 5. 目录

```
protocol/
  pyproject.toml
  README.md
  tjfusion_protocol/
    __init__.py        # 公开 API
    envelope.py        # 信封 + Message + 工厂函数（无第三方依赖）
    codec.py           # NumPy multipart 编解码
    validate.py        # 按类型 schema 校验
    server.py          # BaseModelServer（ZMQ REP）
    client.py          # ModelClient（ZMQ REQ，供 Bridge/demo 用）
    schemas/
      rgb.json depth.json mask.json status.json pose.json action.json
  tests/
    test_protocol.py   # 7 个用例：编解码无损、帧数校验、六类型校验……
```

## 6. 自测

```bash
cd protocol
python -m tests.test_protocol      # 或 pytest -q
```

## 7. 安装到各模型镜像

构建时把 `protocol/` 拷进镜像并安装：

```dockerfile
COPY protocol /opt/tjfusion_protocol
RUN pip install /opt/tjfusion_protocol        # 仅拉 numpy；ZMQ 用 [zmq] extra
```

或开发期直接 `PYTHONPATH=protocol`。

## 8. 字段命名统一（消除历史漂移）

旧代码里同一概念有多个别名（`rgb_image`/`rgb`/`image`/`color_image`/`image_b64`…）。
新标准统一为：

| 类型 | arrays | 关键 fields |
|---|---|---|
| rgb | `color` | `intrinsics` |
| depth | in:`left`,`right` · out:`depth` | `intrinsics`,`baseline_m`,`unit`,`z_far` |
| mask | in:`color` · out:`masks`,`combined_mask` | `prompts`,`obj_ids`,`class_names`,`scores` |
| status | in:`color`(+可选`mask`) | `best_category`,`best_similarity`,`topk` |
| pose | in:`color`,`depth`,`combined_mask` · out:无 | `intrinsics`,`objects` |
| action | 无 | in:`objects`,`best_category`,`goal` · out:`action`,`action_params`,`done` |
