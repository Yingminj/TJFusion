#!/bin/bash
# generate_urdf.sh
# This script generates URDF files from xacro files.

# Exit immediately if a command fails
set -e

echo "Generating marvin_CCS_m6.urdf..."
ros2 run xacro xacro urdf/marvin_CCS_m6.urdf.xacro > urdf/marvin_CCS_m6.urdf
echo "✅ marvin_CCS_m6.urdf generated."

echo "Generating marvin_CCS_m3.urdf..."
ros2 run xacro xacro urdf/marvin_CCS_m3.urdf.xacro > urdf/marvin_CCS_m3.urdf
echo "✅ marvin_CCS_m3.urdf generated."

echo "All URDF files generated successfully!"

