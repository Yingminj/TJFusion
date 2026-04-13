from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution, Command
from launch_ros.actions import Node
from launch_ros.substitutions import FindPackageShare
from launch_ros.parameter_descriptions import ParameterValue
from launch.conditions import IfCondition
def generate_launch_description():
    ld = LaunchDescription()

    package_path = FindPackageShare('marvin_description')
    default_model_path = PathJoinSubstitution([package_path, 'urdf', 'marvin_CCS_m6.urdf.xacro'])
    default_rviz_config_path = PathJoinSubstitution([package_path, 'launch', 'urdf.rviz'])

    # Arguments
    ld.add_action(DeclareLaunchArgument(
        name='model',
        default_value=default_model_path,
        description='Path to the robot URDF/XACRO file'
    ))
    ld.add_action(DeclareLaunchArgument(
        name='rvizconfig',
        default_value=default_rviz_config_path,
        description='Path to RViz config'
    ))
    ld.add_action(DeclareLaunchArgument(
        name='use_rviz',
        default_value='true',
        description='Whether to start RViz'
    ))

    # Generate the robot description from XACRO
    robot_description_param = Command(['xacro ', LaunchConfiguration('model')])

    # Pass robot_description as a string parameter
    ld.add_action(Node(
        package='robot_state_publisher',
        executable='robot_state_publisher',
        name='robot_state_publisher',
       
        parameters=[{
            'robot_description': ParameterValue(value=robot_description_param, value_type=str)
        }]
    ))

    # OPTIONAL: Launch RViz if you want
    ld.add_action(Node(
        condition=IfCondition(LaunchConfiguration('use_rviz')),
        package='rviz2',
        executable='rviz2',
        name='rviz2',
        output='screen',
        arguments=['-d', LaunchConfiguration('rvizconfig')]
    ))

    return ld
