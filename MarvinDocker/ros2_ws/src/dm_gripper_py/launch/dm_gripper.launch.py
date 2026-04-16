#!/usr/bin/env python3
"""Launch file for dm_gripper_py gripper motor node with configurable parameters."""

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    # Declare arguments (can be overridden via command line)
    vel_cmd_arg = DeclareLaunchArgument(
        'vel_cmd', default_value='0.0', description='Velocity command (scaled)')
    current_limit_arg = DeclareLaunchArgument(
        'current_limit', default_value='0.0', description='Current limit (scaled *10000)')
    joint_name_m1_arg = DeclareLaunchArgument(
        'joint_name_motor1', default_value='gripperL', description='Joint name mapped to motor1')
    joint_name_m2_arg = DeclareLaunchArgument(
        'joint_name_motor2', default_value='gripperR', description='Joint name mapped to motor2')
    use_joint_names_arg = DeclareLaunchArgument(
        'use_joint_names', default_value='true', description='Whether to match joint names from JointState')
    auto_calibrate_arg = DeclareLaunchArgument(
        'auto_calibrate', default_value='false', description='Whether to auto calibrate min/max')
    m1_min_arg = DeclareLaunchArgument(
        'Motor1_min_pos', default_value='0.0', description='Manual min pos for Motor1 (if not auto)')
    m1_max_arg = DeclareLaunchArgument(
        'Motor1_max_pos', default_value='1.6', description='Manual max pos for Motor1 (if not auto)')
    m2_min_arg = DeclareLaunchArgument(
        'Motor2_min_pos', default_value='0.0', description='Manual min pos for Motor2 (if not auto)')
    m2_max_arg = DeclareLaunchArgument(
        'Motor2_max_pos', default_value='1.6', description='Manual max pos for Motor2 (if not auto)')

    left_motor_id_arg = DeclareLaunchArgument(
        'left_motor_id', default_value='1', description='CAN ID for left motor (default 17)')
    right_motor_id_arg = DeclareLaunchArgument(
        'right_motor_id', default_value='2', description='CAN ID for right motor (default 18)')

    node = Node(
        package='dm_gripper_py',
        executable='dm_motor_test',
        name='dm_gripper_motor_node',
        output='screen',
        parameters=[{
            'vel_cmd': LaunchConfiguration('vel_cmd'),
            'current_limit': LaunchConfiguration('current_limit'),
            'joint_name_motor1': LaunchConfiguration('joint_name_motor1'),
            'joint_name_motor2': LaunchConfiguration('joint_name_motor2'),
            'use_joint_names': LaunchConfiguration('use_joint_names'),
            'auto_calibrate': LaunchConfiguration('auto_calibrate'),
            'Motor1_min_pos': LaunchConfiguration('Motor1_min_pos'),
            'Motor1_max_pos': LaunchConfiguration('Motor1_max_pos'),
            'Motor2_min_pos': LaunchConfiguration('Motor2_min_pos'),
            'Motor2_max_pos': LaunchConfiguration('Motor2_max_pos'),
            'left_motor_id': LaunchConfiguration('left_motor_id'),
            'right_motor_id': LaunchConfiguration('right_motor_id'),
        }]
    )

    return LaunchDescription([
        vel_cmd_arg,
        current_limit_arg,
        joint_name_m1_arg,
        joint_name_m2_arg,
        use_joint_names_arg,
        auto_calibrate_arg,
        m1_min_arg,
        m1_max_arg,
        m2_min_arg,
        m2_max_arg,
        left_motor_id_arg,
        right_motor_id_arg,
        node
    ])
