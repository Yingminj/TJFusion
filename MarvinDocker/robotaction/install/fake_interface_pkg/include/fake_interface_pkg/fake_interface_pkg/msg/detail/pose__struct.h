// generated from rosidl_generator_c/resource/idl__struct.h.em
// with input from fake_interface_pkg:msg/Pose.idl
// generated code does not contain a copyright notice

#ifndef FAKE_INTERFACE_PKG__MSG__DETAIL__POSE__STRUCT_H_
#define FAKE_INTERFACE_PKG__MSG__DETAIL__POSE__STRUCT_H_

#ifdef __cplusplus
extern "C"
{
#endif

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>


// Constants defined in the message

// Include directives for member types
// Member 'position'
#include "geometry_msgs/msg/detail/point__struct.h"
// Member 'orientation'
#include "geometry_msgs/msg/detail/quaternion__struct.h"
// Member 'obj_name'
#include "rosidl_runtime_c/string.h"

/// Struct defined in msg/Pose in the package fake_interface_pkg.
/**
  * Pose.msg
 */
typedef struct fake_interface_pkg__msg__Pose
{
  geometry_msgs__msg__Point position;
  geometry_msgs__msg__Quaternion orientation;
  int32_t obj_id;
  rosidl_runtime_c__String obj_name;
} fake_interface_pkg__msg__Pose;

// Struct for a sequence of fake_interface_pkg__msg__Pose.
typedef struct fake_interface_pkg__msg__Pose__Sequence
{
  fake_interface_pkg__msg__Pose * data;
  /// The number of valid items in data
  size_t size;
  /// The number of allocated items in data
  size_t capacity;
} fake_interface_pkg__msg__Pose__Sequence;

#ifdef __cplusplus
}
#endif

#endif  // FAKE_INTERFACE_PKG__MSG__DETAIL__POSE__STRUCT_H_
