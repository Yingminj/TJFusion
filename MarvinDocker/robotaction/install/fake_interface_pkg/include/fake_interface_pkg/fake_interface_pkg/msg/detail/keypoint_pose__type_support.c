// generated from rosidl_typesupport_introspection_c/resource/idl__type_support.c.em
// with input from fake_interface_pkg:msg/KeypointPose.idl
// generated code does not contain a copyright notice

#include <stddef.h>
#include "fake_interface_pkg/msg/detail/keypoint_pose__rosidl_typesupport_introspection_c.h"
#include "fake_interface_pkg/msg/rosidl_typesupport_introspection_c__visibility_control.h"
#include "rosidl_typesupport_introspection_c/field_types.h"
#include "rosidl_typesupport_introspection_c/identifier.h"
#include "rosidl_typesupport_introspection_c/message_introspection.h"
#include "fake_interface_pkg/msg/detail/keypoint_pose__functions.h"
#include "fake_interface_pkg/msg/detail/keypoint_pose__struct.h"


// Include directives for member types
// Member `name`
// Member `arm`
#include "rosidl_runtime_c/string_functions.h"
// Member `poses`
#include "geometry_msgs/msg/pose.h"
// Member `poses`
#include "geometry_msgs/msg/detail/pose__rosidl_typesupport_introspection_c.h"
// Member `gripper_value`
// Member `time`
#include "rosidl_runtime_c/primitives_sequence_functions.h"

#ifdef __cplusplus
extern "C"
{
#endif

void fake_interface_pkg__msg__KeypointPose__rosidl_typesupport_introspection_c__KeypointPose_init_function(
  void * message_memory, enum rosidl_runtime_c__message_initialization _init)
{
  // TODO(karsten1987): initializers are not yet implemented for typesupport c
  // see https://github.com/ros2/ros2/issues/397
  (void) _init;
  fake_interface_pkg__msg__KeypointPose__init(message_memory);
}

void fake_interface_pkg__msg__KeypointPose__rosidl_typesupport_introspection_c__KeypointPose_fini_function(void * message_memory)
{
  fake_interface_pkg__msg__KeypointPose__fini(message_memory);
}

size_t fake_interface_pkg__msg__KeypointPose__rosidl_typesupport_introspection_c__size_function__KeypointPose__poses(
  const void * untyped_member)
{
  const geometry_msgs__msg__Pose__Sequence * member =
    (const geometry_msgs__msg__Pose__Sequence *)(untyped_member);
  return member->size;
}

const void * fake_interface_pkg__msg__KeypointPose__rosidl_typesupport_introspection_c__get_const_function__KeypointPose__poses(
  const void * untyped_member, size_t index)
{
  const geometry_msgs__msg__Pose__Sequence * member =
    (const geometry_msgs__msg__Pose__Sequence *)(untyped_member);
  return &member->data[index];
}

void * fake_interface_pkg__msg__KeypointPose__rosidl_typesupport_introspection_c__get_function__KeypointPose__poses(
  void * untyped_member, size_t index)
{
  geometry_msgs__msg__Pose__Sequence * member =
    (geometry_msgs__msg__Pose__Sequence *)(untyped_member);
  return &member->data[index];
}

void fake_interface_pkg__msg__KeypointPose__rosidl_typesupport_introspection_c__fetch_function__KeypointPose__poses(
  const void * untyped_member, size_t index, void * untyped_value)
{
  const geometry_msgs__msg__Pose * item =
    ((const geometry_msgs__msg__Pose *)
    fake_interface_pkg__msg__KeypointPose__rosidl_typesupport_introspection_c__get_const_function__KeypointPose__poses(untyped_member, index));
  geometry_msgs__msg__Pose * value =
    (geometry_msgs__msg__Pose *)(untyped_value);
  *value = *item;
}

void fake_interface_pkg__msg__KeypointPose__rosidl_typesupport_introspection_c__assign_function__KeypointPose__poses(
  void * untyped_member, size_t index, const void * untyped_value)
{
  geometry_msgs__msg__Pose * item =
    ((geometry_msgs__msg__Pose *)
    fake_interface_pkg__msg__KeypointPose__rosidl_typesupport_introspection_c__get_function__KeypointPose__poses(untyped_member, index));
  const geometry_msgs__msg__Pose * value =
    (const geometry_msgs__msg__Pose *)(untyped_value);
  *item = *value;
}

bool fake_interface_pkg__msg__KeypointPose__rosidl_typesupport_introspection_c__resize_function__KeypointPose__poses(
  void * untyped_member, size_t size)
{
  geometry_msgs__msg__Pose__Sequence * member =
    (geometry_msgs__msg__Pose__Sequence *)(untyped_member);
  geometry_msgs__msg__Pose__Sequence__fini(member);
  return geometry_msgs__msg__Pose__Sequence__init(member, size);
}

size_t fake_interface_pkg__msg__KeypointPose__rosidl_typesupport_introspection_c__size_function__KeypointPose__constraints(
  const void * untyped_member)
{
  (void)untyped_member;
  return 3;
}

const void * fake_interface_pkg__msg__KeypointPose__rosidl_typesupport_introspection_c__get_const_function__KeypointPose__constraints(
  const void * untyped_member, size_t index)
{
  const float * member =
    (const float *)(untyped_member);
  return &member[index];
}

void * fake_interface_pkg__msg__KeypointPose__rosidl_typesupport_introspection_c__get_function__KeypointPose__constraints(
  void * untyped_member, size_t index)
{
  float * member =
    (float *)(untyped_member);
  return &member[index];
}

void fake_interface_pkg__msg__KeypointPose__rosidl_typesupport_introspection_c__fetch_function__KeypointPose__constraints(
  const void * untyped_member, size_t index, void * untyped_value)
{
  const float * item =
    ((const float *)
    fake_interface_pkg__msg__KeypointPose__rosidl_typesupport_introspection_c__get_const_function__KeypointPose__constraints(untyped_member, index));
  float * value =
    (float *)(untyped_value);
  *value = *item;
}

void fake_interface_pkg__msg__KeypointPose__rosidl_typesupport_introspection_c__assign_function__KeypointPose__constraints(
  void * untyped_member, size_t index, const void * untyped_value)
{
  float * item =
    ((float *)
    fake_interface_pkg__msg__KeypointPose__rosidl_typesupport_introspection_c__get_function__KeypointPose__constraints(untyped_member, index));
  const float * value =
    (const float *)(untyped_value);
  *item = *value;
}

size_t fake_interface_pkg__msg__KeypointPose__rosidl_typesupport_introspection_c__size_function__KeypointPose__gripper_value(
  const void * untyped_member)
{
  const rosidl_runtime_c__float__Sequence * member =
    (const rosidl_runtime_c__float__Sequence *)(untyped_member);
  return member->size;
}

const void * fake_interface_pkg__msg__KeypointPose__rosidl_typesupport_introspection_c__get_const_function__KeypointPose__gripper_value(
  const void * untyped_member, size_t index)
{
  const rosidl_runtime_c__float__Sequence * member =
    (const rosidl_runtime_c__float__Sequence *)(untyped_member);
  return &member->data[index];
}

void * fake_interface_pkg__msg__KeypointPose__rosidl_typesupport_introspection_c__get_function__KeypointPose__gripper_value(
  void * untyped_member, size_t index)
{
  rosidl_runtime_c__float__Sequence * member =
    (rosidl_runtime_c__float__Sequence *)(untyped_member);
  return &member->data[index];
}

void fake_interface_pkg__msg__KeypointPose__rosidl_typesupport_introspection_c__fetch_function__KeypointPose__gripper_value(
  const void * untyped_member, size_t index, void * untyped_value)
{
  const float * item =
    ((const float *)
    fake_interface_pkg__msg__KeypointPose__rosidl_typesupport_introspection_c__get_const_function__KeypointPose__gripper_value(untyped_member, index));
  float * value =
    (float *)(untyped_value);
  *value = *item;
}

void fake_interface_pkg__msg__KeypointPose__rosidl_typesupport_introspection_c__assign_function__KeypointPose__gripper_value(
  void * untyped_member, size_t index, const void * untyped_value)
{
  float * item =
    ((float *)
    fake_interface_pkg__msg__KeypointPose__rosidl_typesupport_introspection_c__get_function__KeypointPose__gripper_value(untyped_member, index));
  const float * value =
    (const float *)(untyped_value);
  *item = *value;
}

bool fake_interface_pkg__msg__KeypointPose__rosidl_typesupport_introspection_c__resize_function__KeypointPose__gripper_value(
  void * untyped_member, size_t size)
{
  rosidl_runtime_c__float__Sequence * member =
    (rosidl_runtime_c__float__Sequence *)(untyped_member);
  rosidl_runtime_c__float__Sequence__fini(member);
  return rosidl_runtime_c__float__Sequence__init(member, size);
}

size_t fake_interface_pkg__msg__KeypointPose__rosidl_typesupport_introspection_c__size_function__KeypointPose__time(
  const void * untyped_member)
{
  const rosidl_runtime_c__float__Sequence * member =
    (const rosidl_runtime_c__float__Sequence *)(untyped_member);
  return member->size;
}

const void * fake_interface_pkg__msg__KeypointPose__rosidl_typesupport_introspection_c__get_const_function__KeypointPose__time(
  const void * untyped_member, size_t index)
{
  const rosidl_runtime_c__float__Sequence * member =
    (const rosidl_runtime_c__float__Sequence *)(untyped_member);
  return &member->data[index];
}

void * fake_interface_pkg__msg__KeypointPose__rosidl_typesupport_introspection_c__get_function__KeypointPose__time(
  void * untyped_member, size_t index)
{
  rosidl_runtime_c__float__Sequence * member =
    (rosidl_runtime_c__float__Sequence *)(untyped_member);
  return &member->data[index];
}

void fake_interface_pkg__msg__KeypointPose__rosidl_typesupport_introspection_c__fetch_function__KeypointPose__time(
  const void * untyped_member, size_t index, void * untyped_value)
{
  const float * item =
    ((const float *)
    fake_interface_pkg__msg__KeypointPose__rosidl_typesupport_introspection_c__get_const_function__KeypointPose__time(untyped_member, index));
  float * value =
    (float *)(untyped_value);
  *value = *item;
}

void fake_interface_pkg__msg__KeypointPose__rosidl_typesupport_introspection_c__assign_function__KeypointPose__time(
  void * untyped_member, size_t index, const void * untyped_value)
{
  float * item =
    ((float *)
    fake_interface_pkg__msg__KeypointPose__rosidl_typesupport_introspection_c__get_function__KeypointPose__time(untyped_member, index));
  const float * value =
    (const float *)(untyped_value);
  *item = *value;
}

bool fake_interface_pkg__msg__KeypointPose__rosidl_typesupport_introspection_c__resize_function__KeypointPose__time(
  void * untyped_member, size_t size)
{
  rosidl_runtime_c__float__Sequence * member =
    (rosidl_runtime_c__float__Sequence *)(untyped_member);
  rosidl_runtime_c__float__Sequence__fini(member);
  return rosidl_runtime_c__float__Sequence__init(member, size);
}

static rosidl_typesupport_introspection_c__MessageMember fake_interface_pkg__msg__KeypointPose__rosidl_typesupport_introspection_c__KeypointPose_message_member_array[7] = {
  {
    "name",  // name
    rosidl_typesupport_introspection_c__ROS_TYPE_STRING,  // type
    0,  // upper bound of string
    NULL,  // members of sub message
    false,  // is array
    0,  // array size
    false,  // is upper bound
    offsetof(fake_interface_pkg__msg__KeypointPose, name),  // bytes offset in struct
    NULL,  // default value
    NULL,  // size() function pointer
    NULL,  // get_const(index) function pointer
    NULL,  // get(index) function pointer
    NULL,  // fetch(index, &value) function pointer
    NULL,  // assign(index, value) function pointer
    NULL  // resize(index) function pointer
  },
  {
    "arm",  // name
    rosidl_typesupport_introspection_c__ROS_TYPE_STRING,  // type
    0,  // upper bound of string
    NULL,  // members of sub message
    false,  // is array
    0,  // array size
    false,  // is upper bound
    offsetof(fake_interface_pkg__msg__KeypointPose, arm),  // bytes offset in struct
    NULL,  // default value
    NULL,  // size() function pointer
    NULL,  // get_const(index) function pointer
    NULL,  // get(index) function pointer
    NULL,  // fetch(index, &value) function pointer
    NULL,  // assign(index, value) function pointer
    NULL  // resize(index) function pointer
  },
  {
    "poses",  // name
    rosidl_typesupport_introspection_c__ROS_TYPE_MESSAGE,  // type
    0,  // upper bound of string
    NULL,  // members of sub message (initialized later)
    true,  // is array
    0,  // array size
    false,  // is upper bound
    offsetof(fake_interface_pkg__msg__KeypointPose, poses),  // bytes offset in struct
    NULL,  // default value
    fake_interface_pkg__msg__KeypointPose__rosidl_typesupport_introspection_c__size_function__KeypointPose__poses,  // size() function pointer
    fake_interface_pkg__msg__KeypointPose__rosidl_typesupport_introspection_c__get_const_function__KeypointPose__poses,  // get_const(index) function pointer
    fake_interface_pkg__msg__KeypointPose__rosidl_typesupport_introspection_c__get_function__KeypointPose__poses,  // get(index) function pointer
    fake_interface_pkg__msg__KeypointPose__rosidl_typesupport_introspection_c__fetch_function__KeypointPose__poses,  // fetch(index, &value) function pointer
    fake_interface_pkg__msg__KeypointPose__rosidl_typesupport_introspection_c__assign_function__KeypointPose__poses,  // assign(index, value) function pointer
    fake_interface_pkg__msg__KeypointPose__rosidl_typesupport_introspection_c__resize_function__KeypointPose__poses  // resize(index) function pointer
  },
  {
    "constraints",  // name
    rosidl_typesupport_introspection_c__ROS_TYPE_FLOAT,  // type
    0,  // upper bound of string
    NULL,  // members of sub message
    true,  // is array
    3,  // array size
    false,  // is upper bound
    offsetof(fake_interface_pkg__msg__KeypointPose, constraints),  // bytes offset in struct
    NULL,  // default value
    fake_interface_pkg__msg__KeypointPose__rosidl_typesupport_introspection_c__size_function__KeypointPose__constraints,  // size() function pointer
    fake_interface_pkg__msg__KeypointPose__rosidl_typesupport_introspection_c__get_const_function__KeypointPose__constraints,  // get_const(index) function pointer
    fake_interface_pkg__msg__KeypointPose__rosidl_typesupport_introspection_c__get_function__KeypointPose__constraints,  // get(index) function pointer
    fake_interface_pkg__msg__KeypointPose__rosidl_typesupport_introspection_c__fetch_function__KeypointPose__constraints,  // fetch(index, &value) function pointer
    fake_interface_pkg__msg__KeypointPose__rosidl_typesupport_introspection_c__assign_function__KeypointPose__constraints,  // assign(index, value) function pointer
    NULL  // resize(index) function pointer
  },
  {
    "speed",  // name
    rosidl_typesupport_introspection_c__ROS_TYPE_FLOAT,  // type
    0,  // upper bound of string
    NULL,  // members of sub message
    false,  // is array
    0,  // array size
    false,  // is upper bound
    offsetof(fake_interface_pkg__msg__KeypointPose, speed),  // bytes offset in struct
    NULL,  // default value
    NULL,  // size() function pointer
    NULL,  // get_const(index) function pointer
    NULL,  // get(index) function pointer
    NULL,  // fetch(index, &value) function pointer
    NULL,  // assign(index, value) function pointer
    NULL  // resize(index) function pointer
  },
  {
    "gripper_value",  // name
    rosidl_typesupport_introspection_c__ROS_TYPE_FLOAT,  // type
    0,  // upper bound of string
    NULL,  // members of sub message
    true,  // is array
    0,  // array size
    false,  // is upper bound
    offsetof(fake_interface_pkg__msg__KeypointPose, gripper_value),  // bytes offset in struct
    NULL,  // default value
    fake_interface_pkg__msg__KeypointPose__rosidl_typesupport_introspection_c__size_function__KeypointPose__gripper_value,  // size() function pointer
    fake_interface_pkg__msg__KeypointPose__rosidl_typesupport_introspection_c__get_const_function__KeypointPose__gripper_value,  // get_const(index) function pointer
    fake_interface_pkg__msg__KeypointPose__rosidl_typesupport_introspection_c__get_function__KeypointPose__gripper_value,  // get(index) function pointer
    fake_interface_pkg__msg__KeypointPose__rosidl_typesupport_introspection_c__fetch_function__KeypointPose__gripper_value,  // fetch(index, &value) function pointer
    fake_interface_pkg__msg__KeypointPose__rosidl_typesupport_introspection_c__assign_function__KeypointPose__gripper_value,  // assign(index, value) function pointer
    fake_interface_pkg__msg__KeypointPose__rosidl_typesupport_introspection_c__resize_function__KeypointPose__gripper_value  // resize(index) function pointer
  },
  {
    "time",  // name
    rosidl_typesupport_introspection_c__ROS_TYPE_FLOAT,  // type
    0,  // upper bound of string
    NULL,  // members of sub message
    true,  // is array
    0,  // array size
    false,  // is upper bound
    offsetof(fake_interface_pkg__msg__KeypointPose, time),  // bytes offset in struct
    NULL,  // default value
    fake_interface_pkg__msg__KeypointPose__rosidl_typesupport_introspection_c__size_function__KeypointPose__time,  // size() function pointer
    fake_interface_pkg__msg__KeypointPose__rosidl_typesupport_introspection_c__get_const_function__KeypointPose__time,  // get_const(index) function pointer
    fake_interface_pkg__msg__KeypointPose__rosidl_typesupport_introspection_c__get_function__KeypointPose__time,  // get(index) function pointer
    fake_interface_pkg__msg__KeypointPose__rosidl_typesupport_introspection_c__fetch_function__KeypointPose__time,  // fetch(index, &value) function pointer
    fake_interface_pkg__msg__KeypointPose__rosidl_typesupport_introspection_c__assign_function__KeypointPose__time,  // assign(index, value) function pointer
    fake_interface_pkg__msg__KeypointPose__rosidl_typesupport_introspection_c__resize_function__KeypointPose__time  // resize(index) function pointer
  }
};

static const rosidl_typesupport_introspection_c__MessageMembers fake_interface_pkg__msg__KeypointPose__rosidl_typesupport_introspection_c__KeypointPose_message_members = {
  "fake_interface_pkg__msg",  // message namespace
  "KeypointPose",  // message name
  7,  // number of fields
  sizeof(fake_interface_pkg__msg__KeypointPose),
  fake_interface_pkg__msg__KeypointPose__rosidl_typesupport_introspection_c__KeypointPose_message_member_array,  // message members
  fake_interface_pkg__msg__KeypointPose__rosidl_typesupport_introspection_c__KeypointPose_init_function,  // function to initialize message memory (memory has to be allocated)
  fake_interface_pkg__msg__KeypointPose__rosidl_typesupport_introspection_c__KeypointPose_fini_function  // function to terminate message instance (will not free memory)
};

// this is not const since it must be initialized on first access
// since C does not allow non-integral compile-time constants
static rosidl_message_type_support_t fake_interface_pkg__msg__KeypointPose__rosidl_typesupport_introspection_c__KeypointPose_message_type_support_handle = {
  0,
  &fake_interface_pkg__msg__KeypointPose__rosidl_typesupport_introspection_c__KeypointPose_message_members,
  get_message_typesupport_handle_function,
};

ROSIDL_TYPESUPPORT_INTROSPECTION_C_EXPORT_fake_interface_pkg
const rosidl_message_type_support_t *
ROSIDL_TYPESUPPORT_INTERFACE__MESSAGE_SYMBOL_NAME(rosidl_typesupport_introspection_c, fake_interface_pkg, msg, KeypointPose)() {
  fake_interface_pkg__msg__KeypointPose__rosidl_typesupport_introspection_c__KeypointPose_message_member_array[2].members_ =
    ROSIDL_TYPESUPPORT_INTERFACE__MESSAGE_SYMBOL_NAME(rosidl_typesupport_introspection_c, geometry_msgs, msg, Pose)();
  if (!fake_interface_pkg__msg__KeypointPose__rosidl_typesupport_introspection_c__KeypointPose_message_type_support_handle.typesupport_identifier) {
    fake_interface_pkg__msg__KeypointPose__rosidl_typesupport_introspection_c__KeypointPose_message_type_support_handle.typesupport_identifier =
      rosidl_typesupport_introspection_c__identifier;
  }
  return &fake_interface_pkg__msg__KeypointPose__rosidl_typesupport_introspection_c__KeypointPose_message_type_support_handle;
}
#ifdef __cplusplus
}
#endif
