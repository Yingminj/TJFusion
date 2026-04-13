cmake_minimum_required(VERSION 3.5)
project(fake_interface_pkg)

find_package(ament_cmake REQUIRED)
find_package(rosidl_default_generators REQUIRED)
find_package(geometry_msgs REQUIRED)
find_package(std_msgs REQUIRED)

rosidl_generate_interfaces(${PROJECT_NAME}
  "msg/ObjectPose.msg"
  "msg/Action.msg"
  "msg/Pose.msg"
  "msg/ActionPlan.msg"
  "msg/KeypointPose.msg"
  "msg/KeypointPoseArray.msg"
  DEPENDENCIES geometry_msgs std_msgs
)

ament_package()
