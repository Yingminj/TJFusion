// generated from rosidl_generator_cpp/resource/idl__builder.hpp.em
// with input from fake_interface_pkg:msg/KeypointPoseArray.idl
// generated code does not contain a copyright notice

#ifndef FAKE_INTERFACE_PKG__MSG__DETAIL__KEYPOINT_POSE_ARRAY__BUILDER_HPP_
#define FAKE_INTERFACE_PKG__MSG__DETAIL__KEYPOINT_POSE_ARRAY__BUILDER_HPP_

#include <algorithm>
#include <utility>

#include "fake_interface_pkg/msg/detail/keypoint_pose_array__struct.hpp"
#include "rosidl_runtime_cpp/message_initialization.hpp"


namespace fake_interface_pkg
{

namespace msg
{

namespace builder
{

class Init_KeypointPoseArray_poses
{
public:
  explicit Init_KeypointPoseArray_poses(::fake_interface_pkg::msg::KeypointPoseArray & msg)
  : msg_(msg)
  {}
  ::fake_interface_pkg::msg::KeypointPoseArray poses(::fake_interface_pkg::msg::KeypointPoseArray::_poses_type arg)
  {
    msg_.poses = std::move(arg);
    return std::move(msg_);
  }

private:
  ::fake_interface_pkg::msg::KeypointPoseArray msg_;
};

class Init_KeypointPoseArray_header
{
public:
  Init_KeypointPoseArray_header()
  : msg_(::rosidl_runtime_cpp::MessageInitialization::SKIP)
  {}
  Init_KeypointPoseArray_poses header(::fake_interface_pkg::msg::KeypointPoseArray::_header_type arg)
  {
    msg_.header = std::move(arg);
    return Init_KeypointPoseArray_poses(msg_);
  }

private:
  ::fake_interface_pkg::msg::KeypointPoseArray msg_;
};

}  // namespace builder

}  // namespace msg

template<typename MessageType>
auto build();

template<>
inline
auto build<::fake_interface_pkg::msg::KeypointPoseArray>()
{
  return fake_interface_pkg::msg::builder::Init_KeypointPoseArray_header();
}

}  // namespace fake_interface_pkg

#endif  // FAKE_INTERFACE_PKG__MSG__DETAIL__KEYPOINT_POSE_ARRAY__BUILDER_HPP_
