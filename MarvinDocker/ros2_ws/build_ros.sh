#!/usr/bin/env bash
set -e

WORKSPACE_DIR="/ros2_ws"

echo "==> Enter workspace: ${WORKSPACE_DIR}"
cd "${WORKSPACE_DIR}"
rm -rf /ros2_ws/build /ros2_ws/log /ros2_ws/install

echo "==> Source ROS Humble"
source /opt/ros/humble/setup.bash

if [ -f "${WORKSPACE_DIR}/install/setup.bash" ]; then
    echo "==> Source existing workspace install/setup.bash"
    source "${WORKSPACE_DIR}/install/setup.bash"
fi

echo "==> Step 1: build marvin_msgs"
colcon build  --packages-select marvin_msgs fake_interface_pkg
colcon build  --packages-select marvin_description dm_gripper_py
echo "==> Step 2: install dependencies with rosdep"
rosdep install --from-paths src --ignore-src -r -y

echo "==> Step 3: build marvin_ros_control with CPU_ARCH=x86"
colcon build  --packages-select marvin_ros_control --cmake-args -DCPU_ARCH=x86

echo "==> Step 4: build marvin_fabric with CPU_ARCH=x86"
colcon build  --packages-select marvin_fabric --cmake-args -DCPU_ARCH=x86

echo "==> All steps completed successfully."