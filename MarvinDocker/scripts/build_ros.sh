#!/usr/bin/env bash
set -e

WORKSPACE_DIR="/ros2_ws"

echo "==> Enter workspace: ${WORKSPACE_DIR}"
cd "${WORKSPACE_DIR}"
rm -rf /ros2_ws/build /ros2_ws/log /ros2_ws/install

# Avoid duplicate package name conflicts (marvin_description)
if [ -d "/ros2_ws/src/Marvin-description" ]; then
    touch "/ros2_ws/src/Marvin-description/COLCON_IGNORE"
    echo "==> COLCON_IGNORE set for /ros2_ws/src/Marvin-description"
fi

echo "==> Source ROS Humble"
set +u
source /opt/ros/humble/setup.bash
set -u

if [ -f "${WORKSPACE_DIR}/install/setup.bash" ]; then
    echo "==> Source existing workspace install/setup.bash"
    set +u
    source "${WORKSPACE_DIR}/install/setup.bash"
    set -u
fi

echo "==> Ensure missing mesh placeholders exist"
OMNI_DIR="${WORKSPACE_DIR}/src/marvin_description_new/meshes/marvin_pro/omnigripper"
WUJI_DIR="${WORKSPACE_DIR}/src/marvin_description_new/wuji-hand-description/meshes/left"

if [ -d "${OMNI_DIR}" ]; then
    if [ ! -f "${OMNI_DIR}/Underpan_Base_link.STL" ] && [ -f "${OMNI_DIR}/base_link.STL" ]; then
        cp -f "${OMNI_DIR}/base_link.STL" "${OMNI_DIR}/Underpan_Base_link.STL"
        echo "==> Created ${OMNI_DIR}/Underpan_Base_link.STL"
    fi
fi

if [ -d "${OMNI_DIR}" ] && [ -f "${OMNI_DIR}/Left_Finger_Link.STL" ]; then
    mkdir -p "${WUJI_DIR}"
    if [ ! -f "${WUJI_DIR}/left_palm_link.STL" ] && [ -f "${OMNI_DIR}/base_link.STL" ]; then
        cp -f "${OMNI_DIR}/base_link.STL" "${WUJI_DIR}/left_palm_link.STL"
    fi
    for name in \
        left_finger1_link1 left_finger1_link2 left_finger1_link3 left_finger1_link4 left_finger1_tip_link \
        left_finger2_link1 left_finger2_link2 left_finger2_link3 left_finger2_link4 left_finger2_tip_link \
        left_finger3_link1 left_finger3_link2 left_finger3_link3 left_finger3_link4 left_finger3_tip_link \
        left_finger4_link1 left_finger4_link2 left_finger4_link3 left_finger4_link4 left_finger4_tip_link \
        left_finger5_link1 left_finger5_link2 left_finger5_link3 left_finger5_link4 left_finger5_tip_link
    do
        if [ ! -f "${WUJI_DIR}/${name}.STL" ]; then
            cp -f "${OMNI_DIR}/Left_Finger_Link.STL" "${WUJI_DIR}/${name}.STL"
        fi
    done
    echo "==> Created placeholder Wuji hand meshes in ${WUJI_DIR}"
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