#!/usr/bin/env bash
set -e

source /opt/ros/humble/setup.bash

# 如果你自己的工作空间也需要 source，就取消下面这行注释
# source /ros2_ws/install/setup.bash

echo "Waiting for /reset_left_arm ..."
ros2 service wait /reset_left_arm

echo "Calling /reset_left_arm ..."
ros2 service call /reset_left_arm std_srvs/srv/Trigger "{}"

sleep 1

echo "Waiting for /reset_right_arm ..."
ros2 service wait /reset_right_arm

echo "Calling /reset_right_arm ..."
ros2 service call /reset_right_arm std_srvs/srv/Trigger "{}"

echo "Done."