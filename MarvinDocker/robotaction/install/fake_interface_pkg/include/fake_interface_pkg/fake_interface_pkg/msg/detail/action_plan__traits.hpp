// generated from rosidl_generator_cpp/resource/idl__traits.hpp.em
// with input from fake_interface_pkg:msg/ActionPlan.idl
// generated code does not contain a copyright notice

#ifndef FAKE_INTERFACE_PKG__MSG__DETAIL__ACTION_PLAN__TRAITS_HPP_
#define FAKE_INTERFACE_PKG__MSG__DETAIL__ACTION_PLAN__TRAITS_HPP_

#include <stdint.h>

#include <sstream>
#include <string>
#include <type_traits>

#include "fake_interface_pkg/msg/detail/action_plan__struct.hpp"
#include "rosidl_runtime_cpp/traits.hpp"

// Include directives for member types
// Member 'header'
#include "std_msgs/msg/detail/header__traits.hpp"
// Member 'action_plan'
#include "fake_interface_pkg/msg/detail/action__traits.hpp"

namespace fake_interface_pkg
{

namespace msg
{

inline void to_flow_style_yaml(
  const ActionPlan & msg,
  std::ostream & out)
{
  out << "{";
  // member: header
  {
    out << "header: ";
    to_flow_style_yaml(msg.header, out);
    out << ", ";
  }

  // member: action_plan
  {
    if (msg.action_plan.size() == 0) {
      out << "action_plan: []";
    } else {
      out << "action_plan: [";
      size_t pending_items = msg.action_plan.size();
      for (auto item : msg.action_plan) {
        to_flow_style_yaml(item, out);
        if (--pending_items > 0) {
          out << ", ";
        }
      }
      out << "]";
    }
  }
  out << "}";
}  // NOLINT(readability/fn_size)

inline void to_block_style_yaml(
  const ActionPlan & msg,
  std::ostream & out, size_t indentation = 0)
{
  // member: header
  {
    if (indentation > 0) {
      out << std::string(indentation, ' ');
    }
    out << "header:\n";
    to_block_style_yaml(msg.header, out, indentation + 2);
  }

  // member: action_plan
  {
    if (indentation > 0) {
      out << std::string(indentation, ' ');
    }
    if (msg.action_plan.size() == 0) {
      out << "action_plan: []\n";
    } else {
      out << "action_plan:\n";
      for (auto item : msg.action_plan) {
        if (indentation > 0) {
          out << std::string(indentation, ' ');
        }
        out << "-\n";
        to_block_style_yaml(item, out, indentation + 2);
      }
    }
  }
}  // NOLINT(readability/fn_size)

inline std::string to_yaml(const ActionPlan & msg, bool use_flow_style = false)
{
  std::ostringstream out;
  if (use_flow_style) {
    to_flow_style_yaml(msg, out);
  } else {
    to_block_style_yaml(msg, out);
  }
  return out.str();
}

}  // namespace msg

}  // namespace fake_interface_pkg

namespace rosidl_generator_traits
{

[[deprecated("use fake_interface_pkg::msg::to_block_style_yaml() instead")]]
inline void to_yaml(
  const fake_interface_pkg::msg::ActionPlan & msg,
  std::ostream & out, size_t indentation = 0)
{
  fake_interface_pkg::msg::to_block_style_yaml(msg, out, indentation);
}

[[deprecated("use fake_interface_pkg::msg::to_yaml() instead")]]
inline std::string to_yaml(const fake_interface_pkg::msg::ActionPlan & msg)
{
  return fake_interface_pkg::msg::to_yaml(msg);
}

template<>
inline const char * data_type<fake_interface_pkg::msg::ActionPlan>()
{
  return "fake_interface_pkg::msg::ActionPlan";
}

template<>
inline const char * name<fake_interface_pkg::msg::ActionPlan>()
{
  return "fake_interface_pkg/msg/ActionPlan";
}

template<>
struct has_fixed_size<fake_interface_pkg::msg::ActionPlan>
  : std::integral_constant<bool, false> {};

template<>
struct has_bounded_size<fake_interface_pkg::msg::ActionPlan>
  : std::integral_constant<bool, false> {};

template<>
struct is_message<fake_interface_pkg::msg::ActionPlan>
  : std::true_type {};

}  // namespace rosidl_generator_traits

#endif  // FAKE_INTERFACE_PKG__MSG__DETAIL__ACTION_PLAN__TRAITS_HPP_
