from launch import LaunchDescription
from launch_ros.actions import Node
from launch.actions import IncludeLaunchDescription, DeclareLaunchArgument
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration
from ament_index_python.packages import get_package_share_directory
import os

def generate_launch_description():
    config = os.path.join(
        get_package_share_directory('marvin_fabric'),
        'config',
        'robot_param_m6.yaml'
    )

    default_mjcf_path = (
        '/ros2_ws/src/marvin_description_new/mjcf/marvin_pro/'
        'marvin_pro_mink_with_gripper.xml'
    )
    default_description_launch = (
        '/ros2_ws/src/marvin_description_new/launch/'
        'description_only_MarvinPro.launch.py'
    )

    return LaunchDescription([
        DeclareLaunchArgument(
            'mjcf_path',
            default_value=default_mjcf_path,
            description='Path to MuJoCo MJCF file'
        ),
        DeclareLaunchArgument(
            'mujoco_rate_hz',
            default_value='200.0',
            description='MuJoCo simulation rate (Hz)'
        ),
        DeclareLaunchArgument(
            'description_launch_path',
            default_value=default_description_launch,
            description='Absolute path to description launch file'
        ),
        #  Node(
        #     package='marvin_ros_control',
        #     executable='marvin_robot_node',
        #     name='marvin_robot_node',
        #     parameters=[config,
        #     {"pub_joint_states": False}],
        #     output='screen',
        #     arguments=['--ros-args', '--log-level', 'INFO']
        # ),
        Node(
            package='marvin_fabric',
            executable='planner_node',
            name='planner_node',
            parameters=[config],
            output='screen',
            arguments=['--ros-args', '--log-level', 'INFO']
        ),
        Node(
            package='marvin_fabric',
            executable='mujoco_node.py',
            name='mujoco_node',
            parameters=[{
                'xml_path': LaunchConfiguration('mjcf_path'),
                'rate_hz': LaunchConfiguration('mujoco_rate_hz'),
            }],
            output='screen',
            arguments=['--ros-args', '--log-level', 'INFO']
        ),
        IncludeLaunchDescription(
            PythonLaunchDescriptionSource(
                LaunchConfiguration('description_launch_path')
            ),
        ),
    ])