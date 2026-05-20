#!/bin/bash
# generate_urdf.sh
# Regenerate flat URDFs from xacro sources for each robot.

set -e

echo "Generating Gento_Sky.urdf..."
ros2 run xacro xacro urdf/Gento_Sky/Gento_Sky.urdf.xacro > urdf/Gento_Sky/Gento_Sky.urdf
echo "Gento_Sky.urdf generated."

echo "Generating Marvin_Ultra.urdf..."
ros2 run xacro xacro urdf/Marvin_Ultra/Marvin_Ultra.urdf.xacro > urdf/Marvin_Ultra/Marvin_Ultra.urdf
echo "Marvin_Ultra.urdf generated."

echo "All URDF files generated successfully!"
