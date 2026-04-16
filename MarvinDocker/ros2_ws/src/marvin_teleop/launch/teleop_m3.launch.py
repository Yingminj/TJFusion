from launch import LaunchDescription
from launch_ros.actions import Node
from launch.actions import IncludeLaunchDescription, DeclareLaunchArgument
from launch.launch_description_sources import PythonLaunchDescriptionSource
from ament_index_python.packages import get_package_share_directory
import os

def generate_launch_description():
    config = os.path.join(
        get_package_share_directory('marvin_teleop'),
        'config',
        'robot_param_m3.yaml'
    )

    return LaunchDescription([
        
        Node(
            package='marvin_teleop',
            executable='IK_v2',
            name='motion_node',
            parameters=[config, {"config_file": 'ccs_m3.MvKDCfg'}
                        ,{"urdf_file": 'marvin_CCS_m3.urdf'},
                        {"srdf_file": 'marvin_robot.srdf'}
                        ],
            output='screen',
        ),
        Node(
            package='marvin_teleop',
            executable='controller_udp.py',
            name='VR_reader',
            output='screen',
        ),

        IncludeLaunchDescription(
            PythonLaunchDescriptionSource(
                os.path.join(
                    get_package_share_directory('marvin_ros_control'),
                    'launch',
                    'bringup_control_m3.launch.py'
                )
            ),
        ),
    ])
