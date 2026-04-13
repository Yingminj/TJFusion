// generated from rosidl_generator_cpp/resource/idl__builder.hpp.em
// with input from fake_interface_pkg:msg/ObjectPose.idl
// generated code does not contain a copyright notice

#ifndef FAKE_INTERFACE_PKG__MSG__DETAIL__OBJECT_POSE__BUILDER_HPP_
#define FAKE_INTERFACE_PKG__MSG__DETAIL__OBJECT_POSE__BUILDER_HPP_

#include <algorithm>
#include <utility>

#include "fake_interface_pkg/msg/detail/object_pose__struct.hpp"
#include "rosidl_runtime_cpp/message_initialization.hpp"


namespace fake_interface_pkg
{

namespace msg
{

namespace builder
{

class Init_ObjectPose_poses
{
public:
  explicit Init_ObjectPose_poses(::fake_interface_pkg::msg::ObjectPose & msg)
  : msg_(msg)
  {}
  ::fake_interface_pkg::msg::ObjectPose poses(::fake_interface_pkg::msg::ObjectPose::_poses_type arg)
  {
    msg_.poses = std::move(arg);
    return std::move(msg_);
  }

private:
  ::fake_interface_pkg::msg::ObjectPose msg_;
};

class Init_ObjectPose_header
{
public:
  Init_ObjectPose_header()
  : msg_(::rosidl_runtime_cpp::MessageInitialization::SKIP)
  {}
  Init_ObjectPose_poses header(::fake_interface_pkg::msg::ObjectPose::_header_type arg)
  {
    msg_.header = std::move(arg);
    return Init_ObjectPose_poses(msg_);
  }

private:
  ::fake_interface_pkg::msg::ObjectPose msg_;
};

}  // namespace builder

}  // namespace msg

template<typename MessageType>
auto build();

template<>
inline
auto build<::fake_interface_pkg::msg::ObjectPose>()
{
  return fake_interface_pkg::msg::builder::Init_ObjectPose_header();
}

}  // namespace fake_interface_pkg

#endif  // FAKE_INTERFACE_PKG__MSG__DETAIL__OBJECT_POSE__BUILDER_HPP_
