#!/bin/bash
# generate_urdf.sh
# This script generates URDF files from xacro files.

# Exit immediately if a command fails
set -e

echo "Generating marvin_CCS_m6.urdf..."
ros2 run xacro xacro urdf/marvin_CCS_m6_mobile.urdf.xacro > urdf/marvin_CCS_m6_mobile.urdf
echo "✅ marvin_CCS_m6.urdf generated."


echo "All URDF files generated successfully!"

