// generated from rosidl_generator_cpp/resource/idl__builder.hpp.em
// with input from fake_interface_pkg:msg/Pose.idl
// generated code does not contain a copyright notice

#ifndef FAKE_INTERFACE_PKG__MSG__DETAIL__POSE__BUILDER_HPP_
#define FAKE_INTERFACE_PKG__MSG__DETAIL__POSE__BUILDER_HPP_

#include <algorithm>
#include <utility>

#include "fake_interface_pkg/msg/detail/pose__struct.hpp"
#include "rosidl_runtime_cpp/message_initialization.hpp"


namespace fake_interface_pkg
{

namespace msg
{

namespace builder
{

class Init_Pose_obj_name
{
public:
  explicit Init_Pose_obj_name(::fake_interface_pkg::msg::Pose & msg)
  : msg_(msg)
  {}
  ::fake_interface_pkg::msg::Pose obj_name(::fake_interface_pkg::msg::Pose::_obj_name_type arg)
  {
    msg_.obj_name = std::move(arg);
    return std::move(msg_);
  }

private:
  ::fake_interface_pkg::msg::Pose msg_;
};

class Init_Pose_obj_id
{
public:
  explicit Init_Pose_obj_id(::fake_interface_pkg::msg::Pose & msg)
  : msg_(msg)
  {}
  Init_Pose_obj_name obj_id(::fake_interface_pkg::msg::Pose::_obj_id_type arg)
  {
    msg_.obj_id = std::move(arg);
    return Init_Pose_obj_name(msg_);
  }

private:
  ::fake_interface_pkg::msg::Pose msg_;
};

class Init_Pose_orientation
{
public:
  explicit Init_Pose_orientation(::fake_interface_pkg::msg::Pose & msg)
  : msg_(msg)
  {}
  Init_Pose_obj_id orientation(::fake_interface_pkg::msg::Pose::_orientation_type arg)
  {
    msg_.orientation = std::move(arg);
    return Init_Pose_obj_id(msg_);
  }

private:
  ::fake_interface_pkg::msg::Pose msg_;
};

class Init_Pose_position
{
public:
  Init_Pose_position()
  : msg_(::rosidl_runtime_cpp::MessageInitialization::SKIP)
  {}
  Init_Pose_orientation position(::fake_interface_pkg::msg::Pose::_position_type arg)
  {
    msg_.position = std::move(arg);
    return Init_Pose_orientation(msg_);
  }

private:
  ::fake_interface_pkg::msg::Pose msg_;
};

}  // namespace builder

}  // namespace msg

template<typename MessageType>
auto build();

template<>
inline
auto build<::fake_interface_pkg::msg::Pose>()
{
  return fake_interface_pkg::msg::builder::Init_Pose_position();
}

}  // namespace fake_interface_pkg

#endif  // FAKE_INTERFACE_PKG__MSG__DETAIL__POSE__BUILDER_HPP_
