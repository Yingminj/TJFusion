# marvin_ros_control

This package provides ROS 2 control functionalities for Marvin robots.

## Installation

1. **Clone the repository:**
    ```bash
    cd ~/ros2_ws/src
    extract the package here
    ```

2. **Install dependencies:**
    ```bash
    cd ~/ros2_ws
    rosdep install --from-paths src --ignore-src -r -y
    ```

3. **Build the workspace:**
    for x64
    ```bash
    colcon build --packages-select marvin_ros_control --cmake-args -DCPU_ARCH=x86
    ```
    for arm64
    ```bash
    colcon build --packages-select marvin_ros_control --cmake-args -DCPU_ARCH=arm64
    ```

4. **Source the workspace:**
    ```bash
    source ~/ros2_ws/install/setup.bash
    ```
5. **Install the vcan auto start service:**
    ```bash
    cd ~/ros2_ws/src/marvin_ros_control
    sudo bash install_van.sh
    ```

## Usage

Refer to the package documentation and launch files for usage instructions.

## License

See [LICENSE](LICENSE) for details.


2025.10.18
