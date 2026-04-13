// generated from rosidl_generator_cpp/resource/idl__builder.hpp.em
// with input from fake_interface_pkg:msg/ActionPlan.idl
// generated code does not contain a copyright notice

#ifndef FAKE_INTERFACE_PKG__MSG__DETAIL__ACTION_PLAN__BUILDER_HPP_
#define FAKE_INTERFACE_PKG__MSG__DETAIL__ACTION_PLAN__BUILDER_HPP_

#include <algorithm>
#include <utility>

#include "fake_interface_pkg/msg/detail/action_plan__struct.hpp"
#include "rosidl_runtime_cpp/message_initialization.hpp"


namespace fake_interface_pkg
{

namespace msg
{

namespace builder
{

class Init_ActionPlan_action_plan
{
public:
  explicit Init_ActionPlan_action_plan(::fake_interface_pkg::msg::ActionPlan & msg)
  : msg_(msg)
  {}
  ::fake_interface_pkg::msg::ActionPlan action_plan(::fake_interface_pkg::msg::ActionPlan::_action_plan_type arg)
  {
    msg_.action_plan = std::move(arg);
    return std::move(msg_);
  }

private:
  ::fake_interface_pkg::msg::ActionPlan msg_;
};

class Init_ActionPlan_header
{
public:
  Init_ActionPlan_header()
  : msg_(::rosidl_runtime_cpp::MessageInitialization::SKIP)
  {}
  Init_ActionPlan_action_plan header(::fake_interface_pkg::msg::ActionPlan::_header_type arg)
  {
    msg_.header = std::move(arg);
    return Init_ActionPlan_action_plan(msg_);
  }

private:
  ::fake_interface_pkg::msg::ActionPlan msg_;
};

}  // namespace builder

}  // namespace msg

template<typename MessageType>
auto build();

template<>
inline
auto build<::fake_interface_pkg::msg::ActionPlan>()
{
  return fake_interface_pkg::msg::builder::Init_ActionPlan_header();
}

}  // namespace fake_interface_pkg

#endif  // FAKE_INTERFACE_PKG__MSG__DETAIL__ACTION_PLAN__BUILDER_HPP_
