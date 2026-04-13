// NOLINT: This file starts with a BOM since it contain non-ASCII characters
// generated from rosidl_generator_c/resource/idl__struct.h.em
// with input from fake_interface_pkg:msg/KeypointPoseArray.idl
// generated code does not contain a copyright notice

#ifndef FAKE_INTERFACE_PKG__MSG__DETAIL__KEYPOINT_POSE_ARRAY__STRUCT_H_
#define FAKE_INTERFACE_PKG__MSG__DETAIL__KEYPOINT_POSE_ARRAY__STRUCT_H_

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
#include "fake_interface_pkg/msg/detail/keypoint_pose__struct.h"

/// Struct defined in msg/KeypointPoseArray in the package fake_interface_pkg.
/**
  * 用于发送一帧的所有关键点
 */
typedef struct fake_interface_pkg__msg__KeypointPoseArray
{
  std_msgs__msg__Header header;
  fake_interface_pkg__msg__KeypointPose__Sequence poses;
} fake_interface_pkg__msg__KeypointPoseArray;

// Struct for a sequence of fake_interface_pkg__msg__KeypointPoseArray.
typedef struct fake_interface_pkg__msg__KeypointPoseArray__Sequence
{
  fake_interface_pkg__msg__KeypointPoseArray * data;
  /// The number of valid items in data
  size_t size;
  /// The number of allocated items in data
  size_t capacity;
} fake_interface_pkg__msg__KeypointPoseArray__Sequence;

#ifdef __cplusplus
}
#endif

#endif  // FAKE_INTERFACE_PKG__MSG__DETAIL__KEYPOINT_POSE_ARRAY__STRUCT_H_
