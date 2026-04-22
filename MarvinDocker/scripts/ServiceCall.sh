#!/bin/bash
source /ros2_ws/install/setup.bash
export ROS_DOMAIN_ID=13
sleep 3
# 调用两个 service
ros2 service call /control/set_ready std_srvs/srv/Trigger "{}"
ros2 service call /control/set_mode marvin_msgs/srv/Int "{data: 3}"
ros2 topic pub -1 /control/gripL std_msgs/msg/Bool "{data: True}"
ros2 topic pub -1 /control/gripR std_msgs/msg/Bool "{data: True}"
