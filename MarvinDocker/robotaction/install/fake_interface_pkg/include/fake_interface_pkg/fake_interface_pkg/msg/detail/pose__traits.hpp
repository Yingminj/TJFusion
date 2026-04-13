// generated from rosidl_generator_cpp/resource/idl__traits.hpp.em
// with input from fake_interface_pkg:msg/Pose.idl
// generated code does not contain a copyright notice

#ifndef FAKE_INTERFACE_PKG__MSG__DETAIL__POSE__TRAITS_HPP_
#define FAKE_INTERFACE_PKG__MSG__DETAIL__POSE__TRAITS_HPP_

#include <stdint.h>

#include <sstream>
#include <string>
#include <type_traits>

#include "fake_interface_pkg/msg/detail/pose__struct.hpp"
#include "rosidl_runtime_cpp/traits.hpp"

// Include directives for member types
// Member 'position'
#include "geometry_msgs/msg/detail/point__traits.hpp"
// Member 'orientation'
#include "geometry_msgs/msg/detail/quaternion__traits.hpp"

namespace fake_interface_pkg
{

namespace msg
{

inline void to_flow_style_yaml(
  const Pose & msg,
  std::ostream & out)
{
  out << "{";
  // member: position
  {
    out << "position: ";
    to_flow_style_yaml(msg.position, out);
    out << ", ";
  }

  // member: orientation
  {
    out << "orientation: ";
    to_flow_style_yaml(msg.orientation, out);
    out << ", ";
  }

  // member: obj_id
  {
    out << "obj_id: ";
    rosidl_generator_traits::value_to_yaml(msg.obj_id, out);
    out << ", ";
  }

  // member: obj_name
  {
    out << "obj_name: ";
    rosidl_generator_traits::value_to_yaml(msg.obj_name, out);
  }
  out << "}";
}  // NOLINT(readability/fn_size)

inline void to_block_style_yaml(
  const Pose & msg,
  std::ostream & out, size_t indentation = 0)
{
  // member: position
  {
    if (indentation > 0) {
      out << std::string(indentation, ' ');
    }
    out << "position:\n";
    to_block_style_yaml(msg.position, out, indentation + 2);
  }

  // member: orientation
  {
    if (indentation > 0) {
      out << std::string(indentation, ' ');
    }
    out << "orientation:\n";
    to_block_style_yaml(msg.orientation, out, indentation + 2);
  }

  // member: obj_id
  {
    if (indentation > 0) {
      out << std::string(indentation, ' ');
    }
    out << "obj_id: ";
    rosidl_generator_traits::value_to_yaml(msg.obj_id, out);
    out << "\n";
  }

  // member: obj_name
  {
    if (indentation > 0) {
      out << std::string(indentation, ' ');
    }
    out << "obj_name: ";
    rosidl_generator_traits::value_to_yaml(msg.obj_name, out);
    out << "\n";
  }
}  // NOLINT(readability/fn_size)

inline std::string to_yaml(const Pose & msg, bool use_flow_style = false)
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
  const fake_interface_pkg::msg::Pose & msg,
  std::ostream & out, size_t indentation = 0)
{
  fake_interface_pkg::msg::to_block_style_yaml(msg, out, indentation);
}

[[deprecated("use fake_interface_pkg::msg::to_yaml() instead")]]
inline std::string to_yaml(const fake_interface_pkg::msg::Pose & msg)
{
  return fake_interface_pkg::msg::to_yaml(msg);
}

template<>
inline const char * data_type<fake_interface_pkg::msg::Pose>()
{
  return "fake_interface_pkg::msg::Pose";
}

template<>
inline const char * name<fake_interface_pkg::msg::Pose>()
{
  return "fake_interface_pkg/msg/Pose";
}

template<>
struct has_fixed_size<fake_interface_pkg::msg::Pose>
  : std::integral_constant<bool, false> {};

template<>
struct has_bounded_size<fake_interface_pkg::msg::Pose>
  : std::integral_constant<bool, false> {};

template<>
struct is_message<fake_interface_pkg::msg::Pose>
  : std::true_type {};

}  // namespace rosidl_generator_traits

#endif  // FAKE_INTERFACE_PKG__MSG__DETAIL__POSE__TRAITS_HPP_
