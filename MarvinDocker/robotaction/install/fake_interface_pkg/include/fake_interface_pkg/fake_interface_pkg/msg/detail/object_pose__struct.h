// NOLINT: This file starts with a BOM since it contain non-ASCII characters
// generated from rosidl_generator_c/resource/idl__struct.h.em
// with input from fake_interface_pkg:msg/ObjectPose.idl
// generated code does not contain a copyright notice

#ifndef FAKE_INTERFACE_PKG__MSG__DETAIL__OBJECT_POSE__STRUCT_H_
#define FAKE_INTERFACE_PKG__MSG__DETAIL__OBJECT_POSE__STRUCT_H_

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
// Member 'poses'
#include "fake_interface_pkg/msg/detail/pose__struct.h"

/// Struct defined in msg/ObjectPose in the package fake_interface_pkg.
/**
  * ObjectPose.msg
 */
typedef struct fake_interface_pkg__msg__ObjectPose
{
  std_msgs__msg__Header header;
  /// 注意名字要和 Pose.msg 一致
  fake_interface_pkg__msg__Pose__Sequence poses;
} fake_interface_pkg__msg__ObjectPose;

// Struct for a sequence of fake_interface_pkg__msg__ObjectPose.
typedef struct fake_interface_pkg__msg__ObjectPose__Sequence
{
  fake_interface_pkg__msg__ObjectPose * data;
  /// The number of valid items in data
  size_t size;
  /// The number of allocated items in data
  size_t capacity;
} fake_interface_pkg__msg__ObjectPose__Sequence;

#ifdef __cplusplus
}
#endif

#endif  // FAKE_INTERFACE_PKG__MSG__DETAIL__OBJECT_POSE__STRUCT_H_
