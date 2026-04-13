// generated from rosidl_generator_cpp/resource/idl__traits.hpp.em
// with input from fake_interface_pkg:msg/KeypointPose.idl
// generated code does not contain a copyright notice

#ifndef FAKE_INTERFACE_PKG__MSG__DETAIL__KEYPOINT_POSE__TRAITS_HPP_
#define FAKE_INTERFACE_PKG__MSG__DETAIL__KEYPOINT_POSE__TRAITS_HPP_

#include <stdint.h>

#include <sstream>
#include <string>
#include <type_traits>

#include "fake_interface_pkg/msg/detail/keypoint_pose__struct.hpp"
#include "rosidl_runtime_cpp/traits.hpp"

// Include directives for member types
// Member 'poses'
#include "geometry_msgs/msg/detail/pose__traits.hpp"

namespace fake_interface_pkg
{

namespace msg
{

inline void to_flow_style_yaml(
  const KeypointPose & msg,
  std::ostream & out)
{
  out << "{";
  // member: name
  {
    out << "name: ";
    rosidl_generator_traits::value_to_yaml(msg.name, out);
    out << ", ";
  }

  // member: arm
  {
    out << "arm: ";
    rosidl_generator_traits::value_to_yaml(msg.arm, out);
    out << ", ";
  }

  // member: poses
  {
    if (msg.poses.size() == 0) {
      out << "poses: []";
    } else {
      out << "poses: [";
      size_t pending_items = msg.poses.size();
      for (auto item : msg.poses) {
        to_flow_style_yaml(item, out);
        if (--pending_items > 0) {
          out << ", ";
        }
      }
      out << "]";
    }
    out << ", ";
  }

  // member: constraints
  {
    if (msg.constraints.size() == 0) {
      out << "constraints: []";
    } else {
      out << "constraints: [";
      size_t pending_items = msg.constraints.size();
      for (auto item : msg.constraints) {
        rosidl_generator_traits::value_to_yaml(item, out);
        if (--pending_items > 0) {
          out << ", ";
        }
      }
      out << "]";
    }
    out << ", ";
  }

  // member: speed
  {
    out << "speed: ";
    rosidl_generator_traits::value_to_yaml(msg.speed, out);
    out << ", ";
  }

  // member: gripper_value
  {
    if (msg.gripper_value.size() == 0) {
      out << "gripper_value: []";
    } else {
      out << "gripper_value: [";
      size_t pending_items = msg.gripper_value.size();
      for (auto item : msg.gripper_value) {
        rosidl_generator_traits::value_to_yaml(item, out);
        if (--pending_items > 0) {
          out << ", ";
        }
      }
      out << "]";
    }
    out << ", ";
  }

  // member: time
  {
    if (msg.time.size() == 0) {
      out << "time: []";
    } else {
      out << "time: [";
      size_t pending_items = msg.time.size();
      for (auto item : msg.time) {
        rosidl_generator_traits::value_to_yaml(item, out);
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
  const KeypointPose & msg,
  std::ostream & out, size_t indentation = 0)
{
  // member: name
  {
    if (indentation > 0) {
      out << std::string(indentation, ' ');
    }
    out << "name: ";
    rosidl_generator_traits::value_to_yaml(msg.name, out);
    out << "\n";
  }

  // member: arm
  {
    if (indentation > 0) {
      out << std::string(indentation, ' ');
    }
    out << "arm: ";
    rosidl_generator_traits::value_to_yaml(msg.arm, out);
    out << "\n";
  }

  // member: poses
  {
    if (indentation > 0) {
      out << std::string(indentation, ' ');
    }
    if (msg.poses.size() == 0) {
      out << "poses: []\n";
    } else {
      out << "poses:\n";
      for (auto item : msg.poses) {
        if (indentation > 0) {
          out << std::string(indentation, ' ');
        }
        out << "-\n";
        to_block_style_yaml(item, out, indentation + 2);
      }
    }
  }

  // member: constraints
  {
    if (indentation > 0) {
      out << std::string(indentation, ' ');
    }
    if (msg.constraints.size() == 0) {
      out << "constraints: []\n";
    } else {
      out << "constraints:\n";
      for (auto item : msg.constraints) {
        if (indentation > 0) {
          out << std::string(indentation, ' ');
        }
        out << "- ";
        rosidl_generator_traits::value_to_yaml(item, out);
        out << "\n";
      }
    }
  }

  // member: speed
  {
    if (indentation > 0) {
      out << std::string(indentation, ' ');
    }
    out << "speed: ";
    rosidl_generator_traits::value_to_yaml(msg.speed, out);
    out << "\n";
  }

  // member: gripper_value
  {
    if (indentation > 0) {
      out << std::string(indentation, ' ');
    }
    if (msg.gripper_value.size() == 0) {
      out << "gripper_value: []\n";
    } else {
      out << "gripper_value:\n";
      for (auto item : msg.gripper_value) {
        if (indentation > 0) {
          out << std::string(indentation, ' ');
        }
        out << "- ";
        rosidl_generator_traits::value_to_yaml(item, out);
        out << "\n";
      }
    }
  }

  // member: time
  {
    if (indentation > 0) {
      out << std::string(indentation, ' ');
    }
    if (msg.time.size() == 0) {
      out << "time: []\n";
    } else {
      out << "time:\n";
      for (auto item : msg.time) {
        if (indentation > 0) {
          out << std::string(indentation, ' ');
        }
        out << "- ";
        rosidl_generator_traits::value_to_yaml(item, out);
        out << "\n";
      }
    }
  }
}  // NOLINT(readability/fn_size)

inline std::string to_yaml(const KeypointPose & msg, bool use_flow_style = false)
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
  const fake_interface_pkg::msg::KeypointPose & msg,
  std::ostream & out, size_t indentation = 0)
{
  fake_interface_pkg::msg::to_block_style_yaml(msg, out, indentation);
}

[[deprecated("use fake_interface_pkg::msg::to_yaml() instead")]]
inline std::string to_yaml(const fake_interface_pkg::msg::KeypointPose & msg)
{
  return fake_interface_pkg::msg::to_yaml(msg);
}

template<>
inline const char * data_type<fake_interface_pkg::msg::KeypointPose>()
{
  return "fake_interface_pkg::msg::KeypointPose";
}

template<>
inline const char * name<fake_interface_pkg::msg::KeypointPose>()
{
  return "fake_interface_pkg/msg/KeypointPose";
}

template<>
struct has_fixed_size<fake_interface_pkg::msg::KeypointPose>
  : std::integral_constant<bool, false> {};

template<>
struct has_bounded_size<fake_interface_pkg::msg::KeypointPose>
  : std::integral_constant<bool, false> {};

template<>
struct is_message<fake_interface_pkg::msg::KeypointPose>
  : std::true_type {};

}  // namespace rosidl_generator_traits

#endif  // FAKE_INTERFACE_PKG__MSG__DETAIL__KEYPOINT_POSE__TRAITS_HPP_
