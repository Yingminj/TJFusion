// generated from rosidl_typesupport_introspection_cpp/resource/idl__type_support.cpp.em
// with input from fake_interface_pkg:msg/KeypointPoseArray.idl
// generated code does not contain a copyright notice

#include "array"
#include "cstddef"
#include "string"
#include "vector"
#include "rosidl_runtime_c/message_type_support_struct.h"
#include "rosidl_typesupport_cpp/message_type_support.hpp"
#include "rosidl_typesupport_interface/macros.h"
#include "fake_interface_pkg/msg/detail/keypoint_pose_array__struct.hpp"
#include "rosidl_typesupport_introspection_cpp/field_types.hpp"
#include "rosidl_typesupport_introspection_cpp/identifier.hpp"
#include "rosidl_typesupport_introspection_cpp/message_introspection.hpp"
#include "rosidl_typesupport_introspection_cpp/message_type_support_decl.hpp"
#include "rosidl_typesupport_introspection_cpp/visibility_control.h"

namespace fake_interface_pkg
{

namespace msg
{

namespace rosidl_typesupport_introspection_cpp
{

void KeypointPoseArray_init_function(
  void * message_memory, rosidl_runtime_cpp::MessageInitialization _init)
{
  new (message_memory) fake_interface_pkg::msg::KeypointPoseArray(_init);
}

void KeypointPoseArray_fini_function(void * message_memory)
{
  auto typed_message = static_cast<fake_interface_pkg::msg::KeypointPoseArray *>(message_memory);
  typed_message->~KeypointPoseArray();
}

size_t size_function__KeypointPoseArray__poses(const void * untyped_member)
{
  const auto * member = reinterpret_cast<const std::vector<fake_interface_pkg::msg::KeypointPose> *>(untyped_member);
  return member->size();
}

const void * get_const_function__KeypointPoseArray__poses(const void * untyped_member, size_t index)
{
  const auto & member =
    *reinterpret_cast<const std::vector<fake_interface_pkg::msg::KeypointPose> *>(untyped_member);
  return &member[index];
}

void * get_function__KeypointPoseArray__poses(void * untyped_member, size_t index)
{
  auto & member =
    *reinterpret_cast<std::vector<fake_interface_pkg::msg::KeypointPose> *>(untyped_member);
  return &member[index];
}

void fetch_function__KeypointPoseArray__poses(
  const void * untyped_member, size_t index, void * untyped_value)
{
  const auto & item = *reinterpret_cast<const fake_interface_pkg::msg::KeypointPose *>(
    get_const_function__KeypointPoseArray__poses(untyped_member, index));
  auto & value = *reinterpret_cast<fake_interface_pkg::msg::KeypointPose *>(untyped_value);
  value = item;
}

void assign_function__KeypointPoseArray__poses(
  void * untyped_member, size_t index, const void * untyped_value)
{
  auto & item = *reinterpret_cast<fake_interface_pkg::msg::KeypointPose *>(
    get_function__KeypointPoseArray__poses(untyped_member, index));
  const auto & value = *reinterpret_cast<const fake_interface_pkg::msg::KeypointPose *>(untyped_value);
  item = value;
}

void resize_function__KeypointPoseArray__poses(void * untyped_member, size_t size)
{
  auto * member =
    reinterpret_cast<std::vector<fake_interface_pkg::msg::KeypointPose> *>(untyped_member);
  member->resize(size);
}

static const ::rosidl_typesupport_introspection_cpp::MessageMember KeypointPoseArray_message_member_array[2] = {
  {
    "header",  // name
    ::rosidl_typesupport_introspection_cpp::ROS_TYPE_MESSAGE,  // type
    0,  // upper bound of string
    ::rosidl_typesupport_introspection_cpp::get_message_type_support_handle<std_msgs::msg::Header>(),  // members of sub message
    false,  // is array
    0,  // array size
    false,  // is upper bound
    offsetof(fake_interface_pkg::msg::KeypointPoseArray, header),  // bytes offset in struct
    nullptr,  // default value
    nullptr,  // size() function pointer
    nullptr,  // get_const(index) function pointer
    nullptr,  // get(index) function pointer
    nullptr,  // fetch(index, &value) function pointer
    nullptr,  // assign(index, value) function pointer
    nullptr  // resize(index) function pointer
  },
  {
    "poses",  // name
    ::rosidl_typesupport_introspection_cpp::ROS_TYPE_MESSAGE,  // type
    0,  // upper bound of string
    ::rosidl_typesupport_introspection_cpp::get_message_type_support_handle<fake_interface_pkg::msg::KeypointPose>(),  // members of sub message
    true,  // is array
    0,  // array size
    false,  // is upper bound
    offsetof(fake_interface_pkg::msg::KeypointPoseArray, poses),  // bytes offset in struct
    nullptr,  // default value
    size_function__KeypointPoseArray__poses,  // size() function pointer
    get_const_function__KeypointPoseArray__poses,  // get_const(index) function pointer
    get_function__KeypointPoseArray__poses,  // get(index) function pointer
    fetch_function__KeypointPoseArray__poses,  // fetch(index, &value) function pointer
    assign_function__KeypointPoseArray__poses,  // assign(index, value) function pointer
    resize_function__KeypointPoseArray__poses  // resize(index) function pointer
  }
};

static const ::rosidl_typesupport_introspection_cpp::MessageMembers KeypointPoseArray_message_members = {
  "fake_interface_pkg::msg",  // message namespace
  "KeypointPoseArray",  // message name
  2,  // number of fields
  sizeof(fake_interface_pkg::msg::KeypointPoseArray),
  KeypointPoseArray_message_member_array,  // message members
  KeypointPoseArray_init_function,  // function to initialize message memory (memory has to be allocated)
  KeypointPoseArray_fini_function  // function to terminate message instance (will not free memory)
};

static const rosidl_message_type_support_t KeypointPoseArray_message_type_support_handle = {
  ::rosidl_typesupport_introspection_cpp::typesupport_identifier,
  &KeypointPoseArray_message_members,
  get_message_typesupport_handle_function,
};

}  // namespace rosidl_typesupport_introspection_cpp

}  // namespace msg

}  // namespace fake_interface_pkg


namespace rosidl_typesupport_introspection_cpp
{

template<>
ROSIDL_TYPESUPPORT_INTROSPECTION_CPP_PUBLIC
const rosidl_message_type_support_t *
get_message_type_support_handle<fake_interface_pkg::msg::KeypointPoseArray>()
{
  return &::fake_interface_pkg::msg::rosidl_typesupport_introspection_cpp::KeypointPoseArray_message_type_support_handle;
}

}  // namespace rosidl_typesupport_introspection_cpp

#ifdef __cplusplus
extern "C"
{
#endif

ROSIDL_TYPESUPPORT_INTROSPECTION_CPP_PUBLIC
const rosidl_message_type_support_t *
ROSIDL_TYPESUPPORT_INTERFACE__MESSAGE_SYMBOL_NAME(rosidl_typesupport_introspection_cpp, fake_interface_pkg, msg, KeypointPoseArray)() {
  return &::fake_interface_pkg::msg::rosidl_typesupport_introspection_cpp::KeypointPoseArray_message_type_support_handle;
}

#ifdef __cplusplus
}
#endif
