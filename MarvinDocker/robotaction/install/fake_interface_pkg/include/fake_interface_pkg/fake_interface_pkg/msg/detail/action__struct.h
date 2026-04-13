// NOLINT: This file starts with a BOM since it contain non-ASCII characters
// generated from rosidl_generator_c/resource/idl__struct.h.em
// with input from fake_interface_pkg:msg/Action.idl
// generated code does not contain a copyright notice

#ifndef FAKE_INTERFACE_PKG__MSG__DETAIL__ACTION__STRUCT_H_
#define FAKE_INTERFACE_PKG__MSG__DETAIL__ACTION__STRUCT_H_

#ifdef __cplusplus
extern "C"
{
#endif

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>


// Constants defined in the message

// Include directives for member types
// Member 'description'
// Member 'goal'
// Member 'action'
#include "rosidl_runtime_c/string.h"

/// Struct defined in msg/Action in the package fake_interface_pkg.
/**
  * Action.msg
 */
typedef struct fake_interface_pkg__msg__Action
{
  /// 动作描述
  rosidl_runtime_c__String description;
  /// 对应目标物体名称
  rosidl_runtime_c__String goal;
  /// 动作类型，例如 pick/open/place
  rosidl_runtime_c__String action;
} fake_interface_pkg__msg__Action;

// Struct for a sequence of fake_interface_pkg__msg__Action.
typedef struct fake_interface_pkg__msg__Action__Sequence
{
  fake_interface_pkg__msg__Action * data;
  /// The number of valid items in data
  size_t size;
  /// The number of allocated items in data
  size_t capacity;
} fake_interface_pkg__msg__Action__Sequence;

#ifdef __cplusplus
}
#endif

#endif  // FAKE_INTERFACE_PKG__MSG__DETAIL__ACTION__STRUCT_H_
