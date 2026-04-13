// generated from rosidl_generator_cpp/resource/idl__traits.hpp.em
// with input from fake_interface_pkg:msg/Action.idl
// generated code does not contain a copyright notice

#ifndef FAKE_INTERFACE_PKG__MSG__DETAIL__ACTION__TRAITS_HPP_
#define FAKE_INTERFACE_PKG__MSG__DETAIL__ACTION__TRAITS_HPP_

#include <stdint.h>

#include <sstream>
#include <string>
#include <type_traits>

#include "fake_interface_pkg/msg/detail/action__struct.hpp"
#include "rosidl_runtime_cpp/traits.hpp"

namespace fake_interface_pkg
{

namespace msg
{

inline void to_flow_style_yaml(
  const Action & msg,
  std::ostream & out)
{
  out << "{";
  // member: description
  {
    out << "description: ";
    rosidl_generator_traits::value_to_yaml(msg.description, out);
    out << ", ";
  }

  // member: goal
  {
    out << "goal: ";
    rosidl_generator_traits::value_to_yaml(msg.goal, out);
    out << ", ";
  }

  // member: action
  {
    out << "action: ";
    rosidl_generator_traits::value_to_yaml(msg.action, out);
  }
  out << "}";
}  // NOLINT(readability/fn_size)

inline void to_block_style_yaml(
  const Action & msg,
  std::ostream & out, size_t indentation = 0)
{
  // member: description
  {
    if (indentation > 0) {
      out << std::string(indentation, ' ');
    }
    out << "description: ";
    rosidl_generator_traits::value_to_yaml(msg.description, out);
    out << "\n";
  }

  // member: goal
  {
    if (indentation > 0) {
      out << std::string(indentation, ' ');
    }
    out << "goal: ";
    rosidl_generator_traits::value_to_yaml(msg.goal, out);
    out << "\n";
  }

  // member: action
  {
    if (indentation > 0) {
      out << std::string(indentation, ' ');
    }
    out << "action: ";
    rosidl_generator_traits::value_to_yaml(msg.action, out);
    out << "\n";
  }
}  // NOLINT(readability/fn_size)

inline std::string to_yaml(const Action & msg, bool use_flow_style = false)
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
  const fake_interface_pkg::msg::Action & msg,
  std::ostream & out, size_t indentation = 0)
{
  fake_interface_pkg::msg::to_block_style_yaml(msg, out, indentation);
}

[[deprecated("use fake_interface_pkg::msg::to_yaml() instead")]]
inline std::string to_yaml(const fake_interface_pkg::msg::Action & msg)
{
  return fake_interface_pkg::msg::to_yaml(msg);
}

template<>
inline const char * data_type<fake_interface_pkg::msg::Action>()
{
  return "fake_interface_pkg::msg::Action";
}

template<>
inline const char * name<fake_interface_pkg::msg::Action>()
{
  return "fake_interface_pkg/msg/Action";
}

template<>
struct has_fixed_size<fake_interface_pkg::msg::Action>
  : std::integral_constant<bool, false> {};

template<>
struct has_bounded_size<fake_interface_pkg::msg::Action>
  : std::integral_constant<bool, false> {};

template<>
struct is_message<fake_interface_pkg::msg::Action>
  : std::true_type {};

}  // namespace rosidl_generator_traits

#endif  // FAKE_INTERFACE_PKG__MSG__DETAIL__ACTION__TRAITS_HPP_
