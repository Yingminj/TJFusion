#!/bin/bash
set -euo pipefail

WS="/ros2_ws"
SESSION="marvin"

# ---------- 通用：每个 pane 先 source ----------
PRELUDE="cd ${WS} && source /opt/ros/humble/setup.bash && source /ros2_ws/install/setup.bash && source /robotaction/install/setup.bash"
SET_ROS_DOMAIN_ID="export ROS_DOMAIN_ID=13"

# ---------- 修改 robot_ip（在 launch 前生效） ----------
YAML="${WS}/install/marvin_ros_control/share/marvin_ros_control/config/robot_param_m6.yaml"
NEW_IP="${1:-${ROBOT_IP:-}}"

if [[ -n "${NEW_IP}" ]]; then
  cp -a "${YAML}" "${YAML}.bak.$(date +%Y%m%d_%H%M%S)" 2>/dev/null || true
  sed -i -E "s/^([[:space:]]*robot_ip:[[:space:]]*).*/\1${NEW_IP}/" "${YAML}"
  echo "[OK] robot_ip updated -> ${NEW_IP}"
else
  echo "[INFO] robot_ip not changed (pass IP as arg1 or set ROBOT_IP)"
fi

# 关闭旧 session
tmux kill-session -t "${SESSION}" 2>/dev/null || true

# ========== 单 Session，所有 Pane 集中管理 ==========
tmux new-session -d -s "${SESSION}" -x 200 -y 50 bash

tmux set-option -t "${SESSION}" -g pane-border-status top
tmux set-option -t "${SESSION}" -g pane-border-format " #{pane_index}: #{pane_title} "

# --- 创建 7 个 pane ---
# 初始 pane 0，然后逐个 split
tmux split-window -v -t "${SESSION}:0" bash          # pane 1
tmux split-window -v -t "${SESSION}:0" bash          # pane 2
tmux split-window -v -t "${SESSION}:0" bash          # pane 3
tmux split-window -h -t "${SESSION}:0" bash          # pane 4
tmux split-window -h -t "${SESSION}:0" bash          # pane 5
tmux split-window -h -t "${SESSION}:0" bash          # pane 6

# 使用 tiled 布局自动排列（左 4 右 3）
tmux select-layout -t "${SESSION}:0" tiled

# --- 设置标题 & 发送命令 ---
tmux select-pane -t "${SESSION}:0.0" -T "PLANNER"
tmux send-keys -t "${SESSION}:0.0" "bash -lc '${SET_ROS_DOMAIN_ID}; ${PRELUDE}; ros2 launch marvin_fabric planner_m6.launch.py'" C-m

tmux select-pane -t "${SESSION}:0.1" -T "GRIPPER"
tmux send-keys -t "${SESSION}:0.1" "bash -lc '${SET_ROS_DOMAIN_ID}; ${PRELUDE}; sleep 5; ros2 launch dm_gripper_py dm_gripper.launch.py'" C-m

tmux select-pane -t "${SESSION}:0.2" -T "CONTROL"
tmux send-keys -t "${SESSION}:0.2" "${SET_ROS_DOMAIN_ID}; bash -lc 'bash /scripts/ServiceCall.sh'" C-m

tmux select-pane -t "${SESSION}:0.3" -T "TASK_MANAGER"
tmux send-keys -t "${SESSION}:0.3" "bash -lc '${SET_ROS_DOMAIN_ID}; ${PRELUDE}; sleep 8 && python3 ${WS}/src/marvin_fabric/scripts/world/test_task_manager_dynamic0323.py'" C-m

tmux select-pane -t "${SESSION}:0.4" -T "TF_BRIDGE"
tmux send-keys -t "${SESSION}:0.4" "bash -lc '${SET_ROS_DOMAIN_ID}; ${PRELUDE}; cd /robotaction && python3 zmq2ros.py --zmq_topic /tf'" C-m

tmux select-pane -t "${SESSION}:0.5" -T "SIGLIP_BRIDGE"
tmux send-keys -t "${SESSION}:0.5" "bash -lc '${SET_ROS_DOMAIN_ID}; ${PRELUDE}; cd /robotaction && python3 zmq2ros.py --zmq_topic /siglip2/result'" C-m

tmux select-pane -t "${SESSION}:0.6" -T "ROBOT_ACTION"
tmux send-keys -t "${SESSION}:0.6" "bash -lc '${SET_ROS_DOMAIN_ID}; ${PRELUDE}; sleep 3 && python3 /robotaction/robot_action.py --object_yaml_path /robotaction/data/lab/test_tube.yaml --status_json_path /robotaction/data/lab/graph_info_lab.json --status_topic /siglip2/result --progress_topic /control/task_percentage --object_tf_topic /tf'" C-m

# 默认聚焦 PLANNER
tmux select-pane -t "${SESSION}:0.0"

# 进入 session
tmux attach -t "${SESSION}"
