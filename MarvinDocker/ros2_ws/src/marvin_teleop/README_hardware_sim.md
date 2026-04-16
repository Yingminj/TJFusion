# Hardware Simulator

This package contains a hardware simulator node that publishes joint feedback messages with the default resting pose from the SRDF configuration file.

## Overview

The `hardware_sim.py` script publishes to the `info/joint_feedback` topic with the following message structure:

```
std_msgs/Header header
float64[14] positions   # Joint positions in radians
float64[14] velocities  # Joint velocities (all zeros)
float64[14] efforts     # Joint efforts (all zeros)
```

### Joint Order
The joints are ordered as: **L1, L2, L3, L4, L5, L6, L7, R1, R2, R3, R4, R5, R6, R7**

### Default Resting Pose Values

The default values are read from `config/marvin_robot.srdf` under the `resting` group state:

| Joint | Value (radians) |
|-------|----------------|
| Joint1_L | 1.57 |
| Joint2_L | -1.57 |
| Joint3_L | -1.57 |
| Joint4_L | -1.57 |
| Joint5_L | 0.0 |
| Joint6_L | 0.0 |
| Joint7_L | 0.0 |
| Joint1_R | -1.57 |
| Joint2_R | -1.57 |
| Joint3_R | 1.57 |
| Joint4_R | -1.57 |
| Joint5_R | 0.0 |
| Joint6_R | 0.0 |
| Joint7_R | 0.0 |

## Usage

### Build the package

```bash
cd /home/marvin/KernelMind_Apex
colcon build --packages-select marvin_teleop
source install/setup.bash
```

### Run the hardware simulator

**Option 1: Using the launch file**
```bash
ros2 launch marvin_teleop hardware_sim.launch.py
```

**Option 2: Running the node directly**
```bash
ros2 run marvin_teleop hardware_sim.py
```

### Monitor the published messages

To see the joint feedback being published:

```bash
ros2 topic echo /info/joint_feedback
```

To check the publishing rate:

```bash
ros2 topic hz /info/joint_feedback
```

The node publishes at **100 Hz** (every 10ms).

## Files

- `marvin_teleop/hardware_sim.py` - Main simulator node
- `launch/hardware_sim.launch.py` - Launch file for the simulator
- `config/marvin_robot.srdf` - SRDF file containing the default resting pose

## Notes

- All velocities are set to 0.0
- All efforts are set to 0.0
- Only positions are populated with the default resting pose values
- The simulator runs at 100 Hz to match typical robot control frequencies
