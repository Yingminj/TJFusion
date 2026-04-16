from launch import LaunchDescription
from launch_ros.actions import Node
from launch.actions import IncludeLaunchDescription, DeclareLaunchArgument
from launch.launch_description_sources import PythonLaunchDescriptionSource
from ament_index_python.packages import get_package_share_directory
import os

def generate_launch_description():
    config = os.path.join(
        get_package_share_directory('marvin_ros_control'),
        'config',
        'robot_param_m6.yaml'
    )

        

    return LaunchDescription([
        Node(
            package='marvin_ros_control',
            executable='marvin_robot_node',
            name='marvin_robot_node',
            parameters=[config],
            output='screen',
            arguments=['--ros-args', '--log-level', 'INFO']
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
