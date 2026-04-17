# Bridge Guide

这个文档专门说明：如何在 `FusionDocker` 里创建一个新的 bridge。

目标不是讲抽象概念，而是让你能按步骤做出来。

## 1. 先理解 bridge 是什么

在这个项目里，bridge 本质上就是一层“数据适配和转发逻辑”：

```text
Docker A -> Bridge -> Docker B
```

例如：

- 上游是 `ZeroMQ RGBD` 数据流
- bridge 把它改成下游需要的字段
- 下游是 `Siglip2`、`SAM3`、`FlowPose`

bridge 最常做的事情只有三类：

1. 接收上游数据
2. 转换格式或字段
3. 调用下游服务，并输出结果

## 2. 创建 bridge 的两种方式

### 方式 A：用脚手架生成

最推荐，先生成骨架再改。

```bash
PYTHONPATH=src python3 -m fusion_docker create-bridge my_bridge
```

生成后通常会得到：

- `src/fusion_docker/bridges/my_bridge.py`
- `configs/bridge.my_bridge.yaml`

然后你只需要修改生成的 Python 文件和 YAML。

### 方式 B：手动创建

如果你已经知道自己要做什么，也可以手动写。

最少需要改这三处：

1. 新建 bridge Python 文件
2. 在 `bridges/__init__.py` 里注册
3. 新建一个 YAML 配置文件

---

## 3. 一个 bridge 的最小结构

先看一个最小模板。

文件：

- [src/fusion_docker/bridges/my_bridge.py](/home/yang/Desktop/DockerModel/FusionDocker/src/fusion_docker/bridges/my_bridge.py)

示例：

```python
from __future__ import annotations

from fusion_docker.bridges.base import BridgeDefinition
from fusion_docker.bridges.profiled import BridgeProfile, load_profiled_bridge_config


def _mutate_my_bridge_config(config):
    # 在这里约束这个 bridge 的运行方式
    config.run_sam3_flowpose = False

    if not config.siglip2_server_addr:
        raise ValueError("my_bridge requires bridge.siglip2_server_addr.")

    return config


def _run_my_bridge(config, *, verbose: bool = False, save_json: bool = False) -> None:
    from fusion_docker.bridge_service import run_bridge_service

    run_bridge_service(config, verbose=verbose, save_json=save_json)


MY_BRIDGE = BridgeDefinition(
    kind="my_bridge",
    description="My custom bridge.",
    load_config=lambda config_path: load_profiled_bridge_config(
        config_path,
        BridgeProfile(
            kind="my_bridge",
            description="my_bridge",
            aliases=("my",),
            mutate_config=_mutate_my_bridge_config,
        ),
    ),
    run=_run_my_bridge,
    aliases=("my",),
)
```

## 4. 这几个部分分别是干什么的

### `_mutate_my_bridge_config`

这个函数负责“限制和修正配置”。

典型用途：

- 强制关闭不需要的分支
- 强制要求某些地址必须存在
- 统一这个 bridge 的语义

例如：

```python
config.run_sam3_flowpose = False
```

表示这个 bridge 不走 `sam3 -> flowpose` 分支。

### `_run_my_bridge`

这个函数决定 bridge 真正怎么跑。

有两种常见写法：

1. 直接复用现有 `run_bridge_service(...)`
2. 自己手写一套 `recv -> transform -> send` 循环

### `MY_BRIDGE`

这是 bridge 的注册对象。

系统靠它识别：

- bridge 名称是什么
- 配置怎么加载
- 实际运行函数是什么

---

## 5. 注册 bridge

写完 bridge 文件以后，要把它注册进去。

文件：

- [src/fusion_docker/bridges/__init__.py](/home/yang/Desktop/DockerModel/FusionDocker/src/fusion_docker/bridges/__init__.py)

加两行：

```python
from fusion_docker.bridges.my_bridge import MY_BRIDGE

register_bridge(MY_BRIDGE)
```

不注册的话，CLI 不认识这个 bridge。

## 6. 创建配置文件

文件：

- [configs/bridge.my_bridge.yaml](/home/yang/Desktop/DockerModel/FusionDocker/configs/bridge.my_bridge.yaml)

最小例子：

```yaml
bridge:
  type: my_bridge
  source_mode: zmq_source
  zmq_source_addr: tcp://127.0.0.1:4444
  siglip2_server_addr: tcp://127.0.0.1:7777
```

几个关键字段：

- `type`
  必须和 `BridgeDefinition.kind` 一致
- `source_mode`
  常见是 `zmq_source` 或 `external_json`
- `zmq_source_addr`
  上游输入地址
- 其他 `*_server_addr`
  下游服务地址

## 7. 如何运行

直接启动：

```bash
PYTHONPATH=src python3 -m fusion_docker serve-bridge \
  --config configs/bridge.my_bridge.yaml
```

查看当前系统识别了哪些 bridge：

```bash
PYTHONPATH=src python3 -m fusion_docker list-bridges
```

## 8. 如何把 bridge 加进网页 UI

如果你想让 UI 的 `Bridge Window` 管理它，可以加到：

- [configs/docker_launch.yaml](/home/yang/Desktop/DockerModel/FusionDocker/configs/docker_launch.yaml)

例如：

```yaml
docker_launcher:
  bridges:
    - name: My Bridge
      enabled: true
      config: configs/bridge.my_bridge.yaml
```

或者用命令添加：

```bash
PYTHONPATH=src python3 -m fusion_docker add-bridge-to-ui MyBridge \
  --bridge-config configs/bridge.my_bridge.yaml \
  --launch-config configs/docker_launch.yaml
```

## 9. 最常见的三种 bridge 写法

### 写法 1：只转发到一个下游

例如：

- `RGB -> Siglip2`

这种通常只需要：

- 接输入
- 改字段
- 发一个下游地址

### 写法 2：双分支

例如：

- 一路去 `siglip2`
- 一路去 `sam3 -> flowpose`

这种 bridge 会把同一帧同时送到多个模型，再聚合结果。

### 写法 3：结果发布型

例如：

- bridge 内部完成推理
- 最后把关键结果通过 `ZMQ PUB` 发出去

你现在项目里的：

- [src/fusion_docker/bridges/multi_zmq_pub_bridge.py](/home/yang/Desktop/DockerModel/FusionDocker/src/fusion_docker/bridges/multi_zmq_pub_bridge.py)

就是这种写法。

## 10. 如果要自己手写收发循环

下面是最小思路：

```python
while True:
    upstream = recv_from_source()
    payload = transform(upstream)
    reply = send_to_downstream(payload)
    publish_or_return(reply)
```

也就是：

1. `recv`
2. `transform`
3. `send`
4. `output`

bridge 的本质就是这个，不要把它想得太复杂。

## 11. 创建 bridge 前先回答这三个问题

每次写新 bridge，先把这三个问题写清楚：

1. 上游发什么格式？
2. 下游需要什么格式？
3. 中间差了什么字段/编码/协议？

只要这三个问题清楚，bridge 就能写出来。

## 12. 推荐开发顺序

建议按这个顺序来：

1. 先跑通最小版本
2. 再补配置校验
3. 再补日志和错误恢复
4. 最后再补 UI 接入和测试

不要一开始就把 bridge 写成全功能版本。

## 13. 推荐参考文件

你现在项目里最值得参考的 bridge 有这几个：

- [src/fusion_docker/bridges/siglip2_bridge.py](/home/yang/Desktop/DockerModel/FusionDocker/src/fusion_docker/bridges/siglip2_bridge.py)
- [src/fusion_docker/bridges/sam3_flowpose.py](/home/yang/Desktop/DockerModel/FusionDocker/src/fusion_docker/bridges/sam3_flowpose.py)
- [src/fusion_docker/bridges/multi_zmq_pub_bridge.py](/home/yang/Desktop/DockerModel/FusionDocker/src/fusion_docker/bridges/multi_zmq_pub_bridge.py)

以及运行主逻辑：

- [src/fusion_docker/bridge_service.py](/home/yang/Desktop/DockerModel/FusionDocker/src/fusion_docker/bridge_service.py)

## 14. 什么时候应该新建 bridge，而不是改旧 bridge

建议新建 bridge 的情况：

- 你的输入协议变了
- 你的输出协议变了
- 你的分支组合变了
- 你不想让旧 bridge 的行为被污染

如果只是改几个地址，用 YAML 就够了。

如果行为逻辑变了，就应该新建一个 bridge。
