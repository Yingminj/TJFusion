// generated from rosidl_generator_cpp/resource/idl__builder.hpp.em
// with input from fake_interface_pkg:msg/KeypointPose.idl
// generated code does not contain a copyright notice

#ifndef FAKE_INTERFACE_PKG__MSG__DETAIL__KEYPOINT_POSE__BUILDER_HPP_
#define FAKE_INTERFACE_PKG__MSG__DETAIL__KEYPOINT_POSE__BUILDER_HPP_

#include <algorithm>
#include <utility>

#include "fake_interface_pkg/msg/detail/keypoint_pose__struct.hpp"
#include "rosidl_runtime_cpp/message_initialization.hpp"


namespace fake_interface_pkg
{

namespace msg
{

namespace builder
{

class Init_KeypointPose_time
{
public:
  explicit Init_KeypointPose_time(::fake_interface_pkg::msg::KeypointPose & msg)
  : msg_(msg)
  {}
  ::fake_interface_pkg::msg::KeypointPose time(::fake_interface_pkg::msg::KeypointPose::_time_type arg)
  {
    msg_.time = std::move(arg);
    return std::move(msg_);
  }

private:
  ::fake_interface_pkg::msg::KeypointPose msg_;
};

class Init_KeypointPose_gripper_value
{
public:
  explicit Init_KeypointPose_gripper_value(::fake_interface_pkg::msg::KeypointPose & msg)
  : msg_(msg)
  {}
  Init_KeypointPose_time gripper_value(::fake_interface_pkg::msg::KeypointPose::_gripper_value_type arg)
  {
    msg_.gripper_value = std::move(arg);
    return Init_KeypointPose_time(msg_);
  }

private:
  ::fake_interface_pkg::msg::KeypointPose msg_;
};

class Init_KeypointPose_speed
{
public:
  explicit Init_KeypointPose_speed(::fake_interface_pkg::msg::KeypointPose & msg)
  : msg_(msg)
  {}
  Init_KeypointPose_gripper_value speed(::fake_interface_pkg::msg::KeypointPose::_speed_type arg)
  {
    msg_.speed = std::move(arg);
    return Init_KeypointPose_gripper_value(msg_);
  }

private:
  ::fake_interface_pkg::msg::KeypointPose msg_;
};

class Init_KeypointPose_constraints
{
public:
  explicit Init_KeypointPose_constraints(::fake_interface_pkg::msg::KeypointPose & msg)
  : msg_(msg)
  {}
  Init_KeypointPose_speed constraints(::fake_interface_pkg::msg::KeypointPose::_constraints_type arg)
  {
    msg_.constraints = std::move(arg);
    return Init_KeypointPose_speed(msg_);
  }

private:
  ::fake_interface_pkg::msg::KeypointPose msg_;
};

class Init_KeypointPose_poses
{
public:
  explicit Init_KeypointPose_poses(::fake_interface_pkg::msg::KeypointPose & msg)
  : msg_(msg)
  {}
  Init_KeypointPose_constraints poses(::fake_interface_pkg::msg::KeypointPose::_poses_type arg)
  {
    msg_.poses = std::move(arg);
    return Init_KeypointPose_constraints(msg_);
  }

private:
  ::fake_interface_pkg::msg::KeypointPose msg_;
};

class Init_KeypointPose_arm
{
public:
  explicit Init_KeypointPose_arm(::fake_interface_pkg::msg::KeypointPose & msg)
  : msg_(msg)
  {}
  Init_KeypointPose_poses arm(::fake_interface_pkg::msg::KeypointPose::_arm_type arg)
  {
    msg_.arm = std::move(arg);
    return Init_KeypointPose_poses(msg_);
  }

private:
  ::fake_interface_pkg::msg::KeypointPose msg_;
};

class Init_KeypointPose_name
{
public:
  Init_KeypointPose_name()
  : msg_(::rosidl_runtime_cpp::MessageInitialization::SKIP)
  {}
  Init_KeypointPose_arm name(::fake_interface_pkg::msg::KeypointPose::_name_type arg)
  {
    msg_.name = std::move(arg);
    return Init_KeypointPose_arm(msg_);
  }

private:
  ::fake_interface_pkg::msg::KeypointPose msg_;
};

}  // namespace builder

}  // namespace msg

template<typename MessageType>
auto build();

template<>
inline
auto build<::fake_interface_pkg::msg::KeypointPose>()
{
  return fake_interface_pkg::msg::builder::Init_KeypointPose_name();
}

}  // namespace fake_interface_pkg

#endif  // FAKE_INTERFACE_PKG__MSG__DETAIL__KEYPOINT_POSE__BUILDER_HPP_
