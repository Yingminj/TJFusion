// NOLINT: This file starts with a BOM since it contain non-ASCII characters
// generated from rosidl_generator_c/resource/idl__struct.h.em
// with input from fake_interface_pkg:msg/ActionPlan.idl
// generated code does not contain a copyright notice

#ifndef FAKE_INTERFACE_PKG__MSG__DETAIL__ACTION_PLAN__STRUCT_H_
#define FAKE_INTERFACE_PKG__MSG__DETAIL__ACTION_PLAN__STRUCT_H_

#ifdef __cplusplus
extern "C"
{
#endif

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>


// Constants defined in the message

// Include directives for member types
// Member 'header'
#include "std_msgs/msg/detail/header__struct.h"
// Member 'action_plan'
#include "fake_interface_pkg/msg/detail/action__struct.h"

/// Struct defined in msg/ActionPlan in the package fake_interface_pkg.
/**
  * ActionPlan.msg
 */
typedef struct fake_interface_pkg__msg__ActionPlan
{
  std_msgs__msg__Header header;
  /// 动作列表
  fake_interface_pkg__msg__Action__Sequence action_plan;
} fake_interface_pkg__msg__ActionPlan;

// Struct for a sequence of fake_interface_pkg__msg__ActionPlan.
typedef struct fake_interface_pkg__msg__ActionPlan__Sequence
{
  fake_interface_pkg__msg__ActionPlan * data;
  /// The number of valid items in data
  size_t size;
  /// The number of allocated items in data
  size_t capacity;
} fake_interface_pkg__msg__ActionPlan__Sequence;

#ifdef __cplusplus
}
#endif

#endif  // FAKE_INTERFACE_PKG__MSG__DETAIL__ACTION_PLAN__STRUCT_H_
