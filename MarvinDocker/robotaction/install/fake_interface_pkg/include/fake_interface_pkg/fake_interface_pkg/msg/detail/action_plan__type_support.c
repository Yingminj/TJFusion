// generated from rosidl_typesupport_introspection_c/resource/idl__type_support.c.em
// with input from fake_interface_pkg:msg/ActionPlan.idl
// generated code does not contain a copyright notice

#include <stddef.h>
#include "fake_interface_pkg/msg/detail/action_plan__rosidl_typesupport_introspection_c.h"
#include "fake_interface_pkg/msg/rosidl_typesupport_introspection_c__visibility_control.h"
#include "rosidl_typesupport_introspection_c/field_types.h"
#include "rosidl_typesupport_introspection_c/identifier.h"
#include "rosidl_typesupport_introspection_c/message_introspection.h"
#include "fake_interface_pkg/msg/detail/action_plan__functions.h"
#include "fake_interface_pkg/msg/detail/action_plan__struct.h"


// Include directives for member types
// Member `header`
#include "std_msgs/msg/header.h"
// Member `header`
#include "std_msgs/msg/detail/header__rosidl_typesupport_introspection_c.h"
// Member `action_plan`
#include "fake_interface_pkg/msg/action.h"
// Member `action_plan`
#include "fake_interface_pkg/msg/detail/action__rosidl_typesupport_introspection_c.h"

#ifdef __cplusplus
extern "C"
{
#endif

void fake_interface_pkg__msg__ActionPlan__rosidl_typesupport_introspection_c__ActionPlan_init_function(
  void * message_memory, enum rosidl_runtime_c__message_initialization _init)
{
  // TODO(karsten1987): initializers are not yet implemented for typesupport c
  // see https://github.com/ros2/ros2/issues/397
  (void) _init;
  fake_interface_pkg__msg__ActionPlan__init(message_memory);
}

void fake_interface_pkg__msg__ActionPlan__rosidl_typesupport_introspection_c__ActionPlan_fini_function(void * message_memory)
{
  fake_interface_pkg__msg__ActionPlan__fini(message_memory);
}

size_t fake_interface_pkg__msg__ActionPlan__rosidl_typesupport_introspection_c__size_function__ActionPlan__action_plan(
  const void * untyped_member)
{
  const fake_interface_pkg__msg__Action__Sequence * member =
    (const fake_interface_pkg__msg__Action__Sequence *)(untyped_member);
  return member->size;
}

const void * fake_interface_pkg__msg__ActionPlan__rosidl_typesupport_introspection_c__get_const_function__ActionPlan__action_plan(
  const void * untyped_member, size_t index)
{
  const fake_interface_pkg__msg__Action__Sequence * member =
    (const fake_interface_pkg__msg__Action__Sequence *)(untyped_member);
  return &member->data[index];
}

void * fake_interface_pkg__msg__ActionPlan__rosidl_typesupport_introspection_c__get_function__ActionPlan__action_plan(
  void * untyped_member, size_t index)
{
  fake_interface_pkg__msg__Action__Sequence * member =
    (fake_interface_pkg__msg__Action__Sequence *)(untyped_member);
  return &member->data[index];
}

void fake_interface_pkg__msg__ActionPlan__rosidl_typesupport_introspection_c__fetch_function__ActionPlan__action_plan(
  const void * untyped_member, size_t index, void * untyped_value)
{
  const fake_interface_pkg__msg__Action * item =
    ((const fake_interface_pkg__msg__Action *)
    fake_interface_pkg__msg__ActionPlan__rosidl_typesupport_introspection_c__get_const_function__ActionPlan__action_plan(untyped_member, index));
  fake_interface_pkg__msg__Action * value =
    (fake_interface_pkg__msg__Action *)(untyped_value);
  *value = *item;
}

void fake_interface_pkg__msg__ActionPlan__rosidl_typesupport_introspection_c__assign_function__ActionPlan__action_plan(
  void * untyped_member, size_t index, const void * untyped_value)
{
  fake_interface_pkg__msg__Action * item =
    ((fake_interface_pkg__msg__Action *)
    fake_interface_pkg__msg__ActionPlan__rosidl_typesupport_introspection_c__get_function__ActionPlan__action_plan(untyped_member, index));
  const fake_interface_pkg__msg__Action * value =
    (const fake_interface_pkg__msg__Action *)(untyped_value);
  *item = *value;
}

bool fake_interface_pkg__msg__ActionPlan__rosidl_typesupport_introspection_c__resize_function__ActionPlan__action_plan(
  void * untyped_member, size_t size)
{
  fake_interface_pkg__msg__Action__Sequence * member =
    (fake_interface_pkg__msg__Action__Sequence *)(untyped_member);
  fake_interface_pkg__msg__Action__Sequence__fini(member);
  return fake_interface_pkg__msg__Action__Sequence__init(member, size);
}

static rosidl_typesupport_introspection_c__MessageMember fake_interface_pkg__msg__ActionPlan__rosidl_typesupport_introspection_c__ActionPlan_message_member_array[2] = {
  {
    "header",  // name
    rosidl_typesupport_introspection_c__ROS_TYPE_MESSAGE,  // type
    0,  // upper bound of string
    NULL,  // members of sub message (initialized later)
    false,  // is array
    0,  // array size
    false,  // is upper bound
    offsetof(fake_interface_pkg__msg__ActionPlan, header),  // bytes offset in struct
    NULL,  // default value
    NULL,  // size() function pointer
    NULL,  // get_const(index) function pointer
    NULL,  // get(index) function pointer
    NULL,  // fetch(index, &value) function pointer
    NULL,  // assign(index, value) function pointer
    NULL  // resize(index) function pointer
  },
  {
    "action_plan",  // name
    rosidl_typesupport_introspection_c__ROS_TYPE_MESSAGE,  // type
    0,  // upper bound of string
    NULL,  // members of sub message (initialized later)
    true,  // is array
    0,  // array size
    false,  // is upper bound
    offsetof(fake_interface_pkg__msg__ActionPlan, action_plan),  // bytes offset in struct
    NULL,  // default value
    fake_interface_pkg__msg__ActionPlan__rosidl_typesupport_introspection_c__size_function__ActionPlan__action_plan,  // size() function pointer
    fake_interface_pkg__msg__ActionPlan__rosidl_typesupport_introspection_c__get_const_function__ActionPlan__action_plan,  // get_const(index) function pointer
    fake_interface_pkg__msg__ActionPlan__rosidl_typesupport_introspection_c__get_function__ActionPlan__action_plan,  // get(index) function pointer
    fake_interface_pkg__msg__ActionPlan__rosidl_typesupport_introspection_c__fetch_function__ActionPlan__action_plan,  // fetch(index, &value) function pointer
    fake_interface_pkg__msg__ActionPlan__rosidl_typesupport_introspection_c__assign_function__ActionPlan__action_plan,  // assign(index, value) function pointer
    fake_interface_pkg__msg__ActionPlan__rosidl_typesupport_introspection_c__resize_function__ActionPlan__action_plan  // resize(index) function pointer
  }
};

static const rosidl_typesupport_introspection_c__MessageMembers fake_interface_pkg__msg__ActionPlan__rosidl_typesupport_introspection_c__ActionPlan_message_members = {
  "fake_interface_pkg__msg",  // message namespace
  "ActionPlan",  // message name
  2,  // number of fields
  sizeof(fake_interface_pkg__msg__ActionPlan),
  fake_interface_pkg__msg__ActionPlan__rosidl_typesupport_introspection_c__ActionPlan_message_member_array,  // message members
  fake_interface_pkg__msg__ActionPlan__rosidl_typesupport_introspection_c__ActionPlan_init_function,  // function to initialize message memory (memory has to be allocated)
  fake_interface_pkg__msg__ActionPlan__rosidl_typesupport_introspection_c__ActionPlan_fini_function  // function to terminate message instance (will not free memory)
};

// this is not const since it must be initialized on first access
// since C does not allow non-integral compile-time constants
static rosidl_message_type_support_t fake_interface_pkg__msg__ActionPlan__rosidl_typesupport_introspection_c__ActionPlan_message_type_support_handle = {
  0,
  &fake_interface_pkg__msg__ActionPlan__rosidl_typesupport_introspection_c__ActionPlan_message_members,
  get_message_typesupport_handle_function,
};

ROSIDL_TYPESUPPORT_INTROSPECTION_C_EXPORT_fake_interface_pkg
const rosidl_message_type_support_t *
ROSIDL_TYPESUPPORT_INTERFACE__MESSAGE_SYMBOL_NAME(rosidl_typesupport_introspection_c, fake_interface_pkg, msg, ActionPlan)() {
  fake_interface_pkg__msg__ActionPlan__rosidl_typesupport_introspection_c__ActionPlan_message_member_array[0].members_ =
    ROSIDL_TYPESUPPORT_INTERFACE__MESSAGE_SYMBOL_NAME(rosidl_typesupport_introspection_c, std_msgs, msg, Header)();
  fake_interface_pkg__msg__ActionPlan__rosidl_typesupport_introspection_c__ActionPlan_message_member_array[1].members_ =
    ROSIDL_TYPESUPPORT_INTERFACE__MESSAGE_SYMBOL_NAME(rosidl_typesupport_introspection_c, fake_interface_pkg, msg, Action)();
  if (!fake_interface_pkg__msg__ActionPlan__rosidl_typesupport_introspection_c__ActionPlan_message_type_support_handle.typesupport_identifier) {
    fake_interface_pkg__msg__ActionPlan__rosidl_typesupport_introspection_c__ActionPlan_message_type_support_handle.typesupport_identifier =
      rosidl_typesupport_introspection_c__identifier;
  }
  return &fake_interface_pkg__msg__ActionPlan__rosidl_typesupport_introspection_c__ActionPlan_message_type_support_handle;
}
#ifdef __cplusplus
}
#endif
