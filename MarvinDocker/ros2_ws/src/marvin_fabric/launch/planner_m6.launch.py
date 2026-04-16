from launch import LaunchDescription
from launch_ros.actions import Node
from launch.actions import IncludeLaunchDescription, DeclareLaunchArgument
from launch.launch_description_sources import PythonLaunchDescriptionSource
from ament_index_python.packages import get_package_share_directory
import os

def generate_launch_description():
    config = os.path.join(
        get_package_share_directory('marvin_fabric'),
        'config',
        'robot_param_m6.yaml'
    )

        

    return LaunchDescription([
        Node(
            package='marvin_fabric',
            executable='planner_node',
            name='planner_node',
            parameters=[config],
            output='screen',
            arguments=['--ros-args', '--log-level', 'INFO']
        ),
        # Node(
        #     package='marvin_fabric',
        #     executable='test_task_manager_dynamic.py',
        #     name='task_manager_dynamic',
        #     output='screen',
        #     arguments=['--ros-args', '--log-level', 'INFO']
        # ),
        IncludeLaunchDescription(
            PythonLaunchDescriptionSource(
                os.path.join(
                    get_package_share_directory('marvin_ros_control'),
                    'launch',
                    'bringup_control_m6.launch.py'
                )
            ),
        ),
    ])