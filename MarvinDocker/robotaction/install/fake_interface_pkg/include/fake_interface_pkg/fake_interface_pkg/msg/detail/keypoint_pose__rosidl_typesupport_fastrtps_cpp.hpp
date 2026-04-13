// generated from rosidl_typesupport_fastrtps_cpp/resource/idl__rosidl_typesupport_fastrtps_cpp.hpp.em
// with input from fake_interface_pkg:msg/KeypointPose.idl
// generated code does not contain a copyright notice

#ifndef FAKE_INTERFACE_PKG__MSG__DETAIL__KEYPOINT_POSE__ROSIDL_TYPESUPPORT_FASTRTPS_CPP_HPP_
#define FAKE_INTERFACE_PKG__MSG__DETAIL__KEYPOINT_POSE__ROSIDL_TYPESUPPORT_FASTRTPS_CPP_HPP_

#include "rosidl_runtime_c/message_type_support_struct.h"
#include "rosidl_typesupport_interface/macros.h"
#include "fake_interface_pkg/msg/rosidl_typesupport_fastrtps_cpp__visibility_control.h"
#include "fake_interface_pkg/msg/detail/keypoint_pose__struct.hpp"

#ifndef _WIN32
# pragma GCC diagnostic push
# pragma GCC diagnostic ignored "-Wunused-parameter"
# ifdef __clang__
#  pragma clang diagnostic ignored "-Wdeprecated-register"
#  pragma clang diagnostic ignored "-Wreturn-type-c-linkage"
# endif
#endif
#ifndef _WIN32
# pragma GCC diagnostic pop
#endif

#include "fastcdr/Cdr.h"

namespace fake_interface_pkg
{

namespace msg
{

namespace typesupport_fastrtps_cpp
{

bool
ROSIDL_TYPESUPPORT_FASTRTPS_CPP_PUBLIC_fake_interface_pkg
cdr_serialize(
  const fake_interface_pkg::msg::KeypointPose & ros_message,
  eprosima::fastcdr::Cdr & cdr);

bool
ROSIDL_TYPESUPPORT_FASTRTPS_CPP_PUBLIC_fake_interface_pkg
cdr_deserialize(
  eprosima::fastcdr::Cdr & cdr,
  fake_interface_pkg::msg::KeypointPose & ros_message);

size_t
ROSIDL_TYPESUPPORT_FASTRTPS_CPP_PUBLIC_fake_interface_pkg
get_serialized_size(
  const fake_interface_pkg::msg::KeypointPose & ros_message,
  size_t current_alignment);

size_t
ROSIDL_TYPESUPPORT_FASTRTPS_CPP_PUBLIC_fake_interface_pkg
max_serialized_size_KeypointPose(
  bool & full_bounded,
  bool & is_plain,
  size_t current_alignment);

}  // namespace typesupport_fastrtps_cpp

}  // namespace msg

}  // namespace fake_interface_pkg

#ifdef __cplusplus
extern "C"
{
#endif

ROSIDL_TYPESUPPORT_FASTRTPS_CPP_PUBLIC_fake_interface_pkg
const rosidl_message_type_support_t *
  ROSIDL_TYPESUPPORT_INTERFACE__MESSAGE_SYMBOL_NAME(rosidl_typesupport_fastrtps_cpp, fake_interface_pkg, msg, KeypointPose)();

#ifdef __cplusplus
}
#endif

#endif  // FAKE_INTERFACE_PKG__MSG__DETAIL__KEYPOINT_POSE__ROSIDL_TYPESUPPORT_FASTRTPS_CPP_HPP_
