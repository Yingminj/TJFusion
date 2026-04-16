#!/bin/bash
set -euo pipefail

WS="/ros2_ws"
SESSION_MAIN="marvin"
SESSION_BRIDGE="marvin_bridge"
SESSION_ACTION="marvin_action"

# ---------- 通用：每个 pane 先 source ----------
PRELUDE="cd ${WS} && source /opt/ros/humble/setup.bash && source /ros2_ws/install/setup.bash && source /robotaction/install/setup.bash"
SET_ROS_DOMAIN_ID="export ROS_DOMAIN_ID=10"

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
tmux kill-session -t "${SESSION_MAIN}" 2>/dev/null || true
tmux kill-session -t "${SESSION_ACTION}" 2>/dev/null || true
tmux kill-session -t "${SESSION_BRIDGE}" 2>/dev/null || true

# ========== Session 1: marvin ==========
tmux new-session -d -s "${SESSION_MAIN}" -n "MAIN" bash

tmux set-option -t "${SESSION_MAIN}" -g pane-border-status top
tmux set-option -t "${SESSION_MAIN}" -g pane-border-format "#{pane_title}"

# 布局：左侧上下；左上分左右；右侧分上下
tmux split-window -v -t "${SESSION_MAIN}:0" bash
tmux select-pane -t "${SESSION_MAIN}:0.0"
tmux split-window -h -t "${SESSION_MAIN}:0.0" bash
tmux split-window -v -t "${SESSION_MAIN}:0.1" bash

tmux select-pane -t "${SESSION_MAIN}:0.0" -T "PLANNER"
tmux select-pane -t "${SESSION_MAIN}:0.1" -T "GRIPPER"
tmux select-pane -t "${SESSION_MAIN}:0.2" -T "CONTROL"
tmux select-pane -t "${SESSION_MAIN}:0.3" -T "TASK_MANAGER"

tmux send-keys -t "${SESSION_MAIN}:0.0" "bash -lc '${SET_ROS_DOMAIN_ID}; ${PRELUDE}; ros2 launch marvin_fabric planner_m6.launch.py'" C-m
tmux send-keys -t "${SESSION_MAIN}:0.1" "bash -lc '${SET_ROS_DOMAIN_ID}; ${PRELUDE}; sleep 5; ros2 launch dm_gripper_py dm_gripper.launch.py'" C-m
tmux send-keys -t "${SESSION_MAIN}:0.3" "bash -lc '${SET_ROS_DOMAIN_ID}; ${PRELUDE}; sleep 8 && python3 ${WS}/src/marvin_fabric/scripts/world/test_task_manager_dynamic0323.py'" C-m
tmux send-keys -t "${SESSION_MAIN}:0.2" "${SET_ROS_DOMAIN_ID}; bash -lc 'bash /scripts/ServiceCall.sh'" C-m

tmux select-layout -t "${SESSION_MAIN}:0" tiled

# ========== Session 2: marvin_bridge ==========
tmux new-session -d -s "${SESSION_BRIDGE}" -n "BRIDGE" bash

tmux set-option -t "${SESSION_BRIDGE}" -g pane-border-status top
tmux set-option -t "${SESSION_BRIDGE}" -g pane-border-format "#{pane_title}"

tmux split-window -h -t "${SESSION_BRIDGE}:0" bash
tmux select-layout -t "${SESSION_BRIDGE}:0" even-horizontal


tmux select-pane -t "${SESSION_BRIDGE}:0.0" -T "RUN_DRAWER"
tmux send-keys   -t "${SESSION_BRIDGE}:0.0" "bash -lc '${SET_ROS_DOMAIN_ID}; ${PRELUDE}; cd /robotaction && python3 zmq2ros.py --zmq_topic /tf'" C-m

tmux select-pane -t "${SESSION_BRIDGE}:0.1" -T "REALSENSE_BRIDGE"
tmux send-keys   -t "${SESSION_BRIDGE}:0.1" "bash -lc '${SET_ROS_DOMAIN_ID}; ${PRELUDE}; cd /robotaction && python3 zmq2ros.py --zmq_topic /siglip2/result'" C-m

# ========== Session 3: marvin_action ==========
tmux new-session -d -s "${SESSION_ACTION}" -n "ACTION" bash

tmux set-option -t "${SESSION_ACTION}" -g pane-border-status top
tmux set-option -t "${SESSION_ACTION}" -g pane-border-format "#{pane_title}"

tmux select-pane -t "${SESSION_ACTION}:0" -T "SESSION_ACTION"
tmux send-keys -t "${SESSION_ACTION}:0.0" "bash -lc '${SET_ROS_DOMAIN_ID}; ${PRELUDE}; sleep 3 && python3 /robotaction/robot_action.py --object_yaml_path /robotaction/data/test_box.yaml --status_json_path /robotaction/data/graph_info.json --status_topic /siglip2/result --progress_topic /control/task_percentage --object_tf_topic /tf'" C-m

# 进入主 session
tmux attach -t "${SESSION_MAIN}"
