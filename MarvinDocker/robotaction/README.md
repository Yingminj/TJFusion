# robot_action_parts

这个目录保存了拆分后的 `robot_action` 相关代码。当前的运行入口已经在本目录中，不再是外层 `translator/robot_action.py`。

## 运行入口

- `robot_action.py`
  - 当前节点的启动入口。
  - 负责解析命令行参数、创建 `FusionNode`、初始化 ROS2 executor。
  - 也负责把各个拆分后的 mixin 和 watcher 组装成一个完整节点。
  - 你实际运行时，应该运行这个文件。

## 文件功能说明

- `common.py`
  - 放通用基础能力。
  - 包含 `ActionHandler` 的动态加载逻辑。
  - 包含状态常量 `TaskStatus`。
  - 包含动作步骤数据结构 `Step`。
  - 包含 `ArmResolver`，用于根据配置或目标位置决定使用左臂/右臂。
  - 包含 `FixedEndpointManager`，用于固定末端点模式下的轨迹续接。
  - 包含对象名、状态文本、frame id 的规范化函数。
  - 包含 TF 和矩阵之间的转换函数。

- `watchers.py`
  - 放 ROS 订阅型监听器。
  - `StatusWatcher`
    - 监听状态识别结果，例如 `siglip` 输出。
    - 负责提取稳定状态，避免单帧抖动直接触发动作。
  - `TaskProgressWatcher`
    - 监听动作执行进度，例如 `/control/task_percentage`。
    - 用于判断一个机械臂动作是否已经执行完成。
  - `ObjectTfWatcher`
    - 监听目标物体 TF。
    - 缓存最新的目标物体位姿，供后续目标选择和动作生成使用。

- `tf_helpers.py`
  - 放和 TF、目标物体选择有关的逻辑。
  - `FusionTfMixin`
    - 获取当前可用的目标物体 frame。
    - 从相机坐标系或缓存 TF 中筛选目标实例。
    - 把物体位姿转换到 `base_frame`。
    - 在多个同类目标中选择一个实例。
    - 等待目标 TF 稳定，避免目标列表变化过快时直接执行。

- `execution.py`
  - 放动作发布与执行逻辑。
  - `FusionExecutionMixin`
    - 发布当前动作信息到 `/fusion/current_action`。
    - 发布关键点轨迹到 `/fusion_pose`。
    - 执行普通动作步骤。
    - 执行 `home` 动作并等待动作完成。
    - 处理 approach/post 两阶段动作拆分。

- `state_machine.py`
  - 放状态机主流程。
  - `FusionStateMixin`
    - 读取 `status_json`，把状态映射成动作列表。
    - 根据当前稳定状态激活动作组。
    - 维护 `active_state`、`active_steps`、`active_step_idx`。
    - 处理 preempt 逻辑，也就是状态变化时是否要中断当前动作并切换。
    - 在 `on_timer()` 中驱动整套执行流程，是当前业务主控逻辑所在位置。

- `__init__.py`
  - 包初始化文件。
  - 当前没有业务逻辑，主要用于让目录作为一个 Python 包被导入。

## 模块关系

大致依赖关系如下：

`robot_action.py`
-> 组合 `FusionStateMixin`
-> 组合 `FusionExecutionMixin`
-> 组合 `FusionTfMixin`
-> 使用 `StatusWatcher` / `TaskProgressWatcher` / `ObjectTfWatcher`
-> 使用 `common.py` 中的公共数据结构和工具函数

职责划分可以理解为：

- `robot_action.py`：入口和装配
- `common.py`：基础类型和公共函数
- `watchers.py`：输入监听
- `tf_helpers.py`：目标感知与 TF 处理
- `execution.py`：动作下发
- `state_machine.py`：流程控制

## 当前应该运行哪个文件

当前应该运行：

```bash
python3 /home/yang/Desktop/DockerModel/MarvinDocker/robot_action/robot_action.py \
  --object_yaml_path <path> \
  --status_json_path <path>
```

如果你是通过 ROS2 launch 或其他脚本启动，也应该把入口指向这个文件：

- `/home/yang/Desktop/DockerModel/MarvinDocker/robot_action/robot_action.py`

## 后续维护建议

- 想改状态切换、动作组推进、preempt 行为：优先看 `state_machine.py`
- 想改目标选择、TF 来源、实例筛选：优先看 `tf_helpers.py`
- 想改轨迹发布、home 行为、动作下发格式：优先看 `execution.py`
- 想改基础工具、名字规范化、矩阵变换、动作步骤结构：优先看 `common.py`
- 想改订阅输入来源或稳定判定：优先看 `watchers.py`
