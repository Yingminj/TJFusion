// generated from rosidl_generator_cpp/resource/idl__builder.hpp.em
// with input from fake_interface_pkg:msg/Action.idl
// generated code does not contain a copyright notice

#ifndef FAKE_INTERFACE_PKG__MSG__DETAIL__ACTION__BUILDER_HPP_
#define FAKE_INTERFACE_PKG__MSG__DETAIL__ACTION__BUILDER_HPP_

#include <algorithm>
#include <utility>

#include "fake_interface_pkg/msg/detail/action__struct.hpp"
#include "rosidl_runtime_cpp/message_initialization.hpp"


namespace fake_interface_pkg
{

namespace msg
{

namespace builder
{

class Init_Action_action
{
public:
  explicit Init_Action_action(::fake_interface_pkg::msg::Action & msg)
  : msg_(msg)
  {}
  ::fake_interface_pkg::msg::Action action(::fake_interface_pkg::msg::Action::_action_type arg)
  {
    msg_.action = std::move(arg);
    return std::move(msg_);
  }

private:
  ::fake_interface_pkg::msg::Action msg_;
};

class Init_Action_goal
{
public:
  explicit Init_Action_goal(::fake_interface_pkg::msg::Action & msg)
  : msg_(msg)
  {}
  Init_Action_action goal(::fake_interface_pkg::msg::Action::_goal_type arg)
  {
    msg_.goal = std::move(arg);
    return Init_Action_action(msg_);
  }

private:
  ::fake_interface_pkg::msg::Action msg_;
};

class Init_Action_description
{
public:
  Init_Action_description()
  : msg_(::rosidl_runtime_cpp::MessageInitialization::SKIP)
  {}
  Init_Action_goal description(::fake_interface_pkg::msg::Action::_description_type arg)
  {
    msg_.description = std::move(arg);
    return Init_Action_goal(msg_);
  }

private:
  ::fake_interface_pkg::msg::Action msg_;
};

}  // namespace builder

}  // namespace msg

template<typename MessageType>
auto build();

template<>
inline
auto build<::fake_interface_pkg::msg::Action>()
{
  return fake_interface_pkg::msg::builder::Init_Action_description();
}

}  // namespace fake_interface_pkg

#endif  // FAKE_INTERFACE_PKG__MSG__DETAIL__ACTION__BUILDER_HPP_
