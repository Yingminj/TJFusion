#!/usr/bin/env python3

from launch import LaunchDescription
from launch_ros.actions import Node
from ament_index_python.packages import get_package_share_directory
import os
from launch.actions import IncludeLaunchDescription, DeclareLaunchArgument
from launch.launch_description_sources import PythonLaunchDescriptionSource

def generate_launch_description():
    """
    Launch file for the hardware simulator that publishes joint feedback
    with default resting pose from the SRDF file.
    """

    config = os.path.join(
        get_package_share_directory('marvin_teleop'),
        'config',
        'robot_param_m6.yaml'
    )


    return LaunchDescription([
        Node(
            package='marvin_teleop',
            executable='hardware_sim.py',
            name='hardware_simulator',
            output='screen',
            parameters=[],
            arguments=['--ros-args', '--log-level', 'INFO']
        ),
        Node(
            package='marvin_teleop',
            executable='IK_v2',
            name='motion_node',
            parameters=[config, {"config_file": 'ccs_m6.MvKDCfg'}
                        ,{"urdf_file": 'marvin_CCS_m6.urdf'},
                        {"srdf_file": 'marvin_robot.srdf'}
                        ],
            output='screen',
        ),
        Node(
            package='marvin_teleop',
            executable='IK_viewer.py',
            name='ik_viewer_node',
            output='screen',
        ),
        Node(
            package='marvin_teleop',
            executable='6dof_maker.py',
            name='dual_6dof_marker_publisher',
            output='screen',
        ),
        IncludeLaunchDescription(
            PythonLaunchDescriptionSource(
                os.path.join(
                    get_package_share_directory('marvin_description'),
                    'launch',
                    'description_only_m6.launch.py'
                )
            ),
        ),
    ])
