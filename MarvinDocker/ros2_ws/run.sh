#!/bin/bash

WORKDIR=~/work/distri_0112/ros2_ws
ENV_CMD="source install/setup.sh"

gnome-terminal --title="Terminal 1" -- bash -c "
cd $WORKDIR
$ENV_CMD
conda deactivate || true
ros2 launch marvin_fabric planner_m6.launch.py
exec bash
"

sleep 5

gnome-terminal --title="Terminal 2" -- bash -c "
cd $WORKDIR
$ENV_CMD
ros2 launch dm_gripper_py dm_gripper.launch.py
exec bash
"

gnome-terminal --title="Terminal 3" -- bash -c "
cd $WORKDIR
$ENV_CMD
conda deactivate || true
/usr/bin/python3 src/marvin_fabric/scripts/world/test_task_manager_dynamic0323.py
exec bash
"

gnome-terminal --title="Terminal 4" -- bash -c "
cd $WORKDIR
$ENV_CMD
rqt
exec bash
"   