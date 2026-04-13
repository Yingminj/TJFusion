// NOLINT: This file starts with a BOM since it contain non-ASCII characters
// generated from rosidl_generator_c/resource/idl__struct.h.em
// with input from fake_interface_pkg:msg/KeypointPose.idl
// generated code does not contain a copyright notice

#ifndef FAKE_INTERFACE_PKG__MSG__DETAIL__KEYPOINT_POSE__STRUCT_H_
#define FAKE_INTERFACE_PKG__MSG__DETAIL__KEYPOINT_POSE__STRUCT_H_

#ifdef __cplusplus
extern "C"
{
#endif

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>


// Constants defined in the message

// Include directives for member types
// Member 'name'
// Member 'arm'
#include "rosidl_runtime_c/string.h"
// Member 'poses'
#include "geometry_msgs/msg/detail/pose__struct.h"
// Member 'gripper_value'
// Member 'time'
#include "rosidl_runtime_c/primitives_sequence.h"

/// Struct defined in msg/KeypointPose in the package fake_interface_pkg.
/**
  * 用于描述一个关键点
 */
typedef struct fake_interface_pkg__msg__KeypointPose
{
  /// 关键点名称
  rosidl_runtime_c__String name;
  /// 使用的机械臂，left/right
  rosidl_runtime_c__String arm;
  /// 位姿信息
  geometry_msgs__msg__Pose__Sequence poses;
  /// 约束和速度
  /// xyz旋转约束
  float constraints[3];
  /// 移动速度
  float speed;
  /// 手爪控制
  /// 手爪开闭程度
  rosidl_runtime_c__float__Sequence gripper_value;
  rosidl_runtime_c__float__Sequence time;
} fake_interface_pkg__msg__KeypointPose;

// Struct for a sequence of fake_interface_pkg__msg__KeypointPose.
typedef struct fake_interface_pkg__msg__KeypointPose__Sequence
{
  fake_interface_pkg__msg__KeypointPose * data;
  /// The number of valid items in data
  size_t size;
  /// The number of allocated items in data
  size_t capacity;
} fake_interface_pkg__msg__KeypointPose__Sequence;

#ifdef __cplusplus
}
#endif

#endif  // FAKE_INTERFACE_PKG__MSG__DETAIL__KEYPOINT_POSE__STRUCT_H_
