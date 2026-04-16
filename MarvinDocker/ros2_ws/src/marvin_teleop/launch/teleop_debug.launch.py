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
        'robot_param.yaml'
    )

        

    return LaunchDescription([
        Node(
            package='marvin_teleop',
            executable='marvin_robot_node',
            name='marvin_robot_node',
            parameters=[config],
            output='screen',
            arguments=['--ros-args', '--log-level', 'INFO']
        ),
        Node(
            package='marvin_teleop',
            executable='IK_v2',
            name='motion_node',
            parameters=[config, {"config_file": '/home/marvin/ros2_ws/src/marvin_teleop/config/ccs.MvKDCfg'}],
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
            executable='controller_udp.py',
            name='VR_reader',
            output='screen',
        ),

        # Node(
        #     package='hitbot_gripper',
        #     executable='gripper_control_dual',
        #     name='gripper_485_control',
        #     output='screen',
        #     parameters=[{'serial_port': '/dev/serial/by-id/usb-1a86_USB_Single_Serial_588B038387-if00'}]
        # ),

        IncludeLaunchDescription(
            PythonLaunchDescriptionSource(
                os.path.join(
                    get_package_share_directory('marvin_description'),
                    'launch',
                    'description_only.launch.py'
                )
            ),
        ),
        # IncludeLaunchDescription(
        #     PythonLaunchDescriptionSource(
        #         os.path.join(
        #             get_package_share_directory('marvin_teleop'),
        #             'launch',
        #             'video_stream.launch.py'
        #         )
        #     )
        # ),
    ])
