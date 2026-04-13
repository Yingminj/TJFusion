// generated from rosidl_generator_cpp/resource/idl__struct.hpp.em
// with input from fake_interface_pkg:msg/ActionPlan.idl
// generated code does not contain a copyright notice

#ifndef FAKE_INTERFACE_PKG__MSG__DETAIL__ACTION_PLAN__STRUCT_HPP_
#define FAKE_INTERFACE_PKG__MSG__DETAIL__ACTION_PLAN__STRUCT_HPP_

#include <algorithm>
#include <array>
#include <memory>
#include <string>
#include <vector>

#include "rosidl_runtime_cpp/bounded_vector.hpp"
#include "rosidl_runtime_cpp/message_initialization.hpp"


// Include directives for member types
// Member 'header'
#include "std_msgs/msg/detail/header__struct.hpp"
// Member 'action_plan'
#include "fake_interface_pkg/msg/detail/action__struct.hpp"

#ifndef _WIN32
# define DEPRECATED__fake_interface_pkg__msg__ActionPlan __attribute__((deprecated))
#else
# define DEPRECATED__fake_interface_pkg__msg__ActionPlan __declspec(deprecated)
#endif

namespace fake_interface_pkg
{

namespace msg
{

// message struct
template<class ContainerAllocator>
struct ActionPlan_
{
  using Type = ActionPlan_<ContainerAllocator>;

  explicit ActionPlan_(rosidl_runtime_cpp::MessageInitialization _init = rosidl_runtime_cpp::MessageInitialization::ALL)
  : header(_init)
  {
    (void)_init;
  }

  explicit ActionPlan_(const ContainerAllocator & _alloc, rosidl_runtime_cpp::MessageInitialization _init = rosidl_runtime_cpp::MessageInitialization::ALL)
  : header(_alloc, _init)
  {
    (void)_init;
  }

  // field types and members
  using _header_type =
    std_msgs::msg::Header_<ContainerAllocator>;
  _header_type header;
  using _action_plan_type =
    std::vector<fake_interface_pkg::msg::Action_<ContainerAllocator>, typename std::allocator_traits<ContainerAllocator>::template rebind_alloc<fake_interface_pkg::msg::Action_<ContainerAllocator>>>;
  _action_plan_type action_plan;

  // setters for named parameter idiom
  Type & set__header(
    const std_msgs::msg::Header_<ContainerAllocator> & _arg)
  {
    this->header = _arg;
    return *this;
  }
  Type & set__action_plan(
    const std::vector<fake_interface_pkg::msg::Action_<ContainerAllocator>, typename std::allocator_traits<ContainerAllocator>::template rebind_alloc<fake_interface_pkg::msg::Action_<ContainerAllocator>>> & _arg)
  {
    this->action_plan = _arg;
    return *this;
  }

  // constant declarations

  // pointer types
  using RawPtr =
    fake_interface_pkg::msg::ActionPlan_<ContainerAllocator> *;
  using ConstRawPtr =
    const fake_interface_pkg::msg::ActionPlan_<ContainerAllocator> *;
  using SharedPtr =
    std::shared_ptr<fake_interface_pkg::msg::ActionPlan_<ContainerAllocator>>;
  using ConstSharedPtr =
    std::shared_ptr<fake_interface_pkg::msg::ActionPlan_<ContainerAllocator> const>;

  template<typename Deleter = std::default_delete<
      fake_interface_pkg::msg::ActionPlan_<ContainerAllocator>>>
  using UniquePtrWithDeleter =
    std::unique_ptr<fake_interface_pkg::msg::ActionPlan_<ContainerAllocator>, Deleter>;

  using UniquePtr = UniquePtrWithDeleter<>;

  template<typename Deleter = std::default_delete<
      fake_interface_pkg::msg::ActionPlan_<ContainerAllocator>>>
  using ConstUniquePtrWithDeleter =
    std::unique_ptr<fake_interface_pkg::msg::ActionPlan_<ContainerAllocator> const, Deleter>;
  using ConstUniquePtr = ConstUniquePtrWithDeleter<>;

  using WeakPtr =
    std::weak_ptr<fake_interface_pkg::msg::ActionPlan_<ContainerAllocator>>;
  using ConstWeakPtr =
    std::weak_ptr<fake_interface_pkg::msg::ActionPlan_<ContainerAllocator> const>;

  // pointer types similar to ROS 1, use SharedPtr / ConstSharedPtr instead
  // NOTE: Can't use 'using' here because GNU C++ can't parse attributes properly
  typedef DEPRECATED__fake_interface_pkg__msg__ActionPlan
    std::shared_ptr<fake_interface_pkg::msg::ActionPlan_<ContainerAllocator>>
    Ptr;
  typedef DEPRECATED__fake_interface_pkg__msg__ActionPlan
    std::shared_ptr<fake_interface_pkg::msg::ActionPlan_<ContainerAllocator> const>
    ConstPtr;

  // comparison operators
  bool operator==(const ActionPlan_ & other) const
  {
    if (this->header != other.header) {
      return false;
    }
    if (this->action_plan != other.action_plan) {
      return false;
    }
    return true;
  }
  bool operator!=(const ActionPlan_ & other) const
  {
    return !this->operator==(other);
  }
};  // struct ActionPlan_

// alias to use template instance with default allocator
using ActionPlan =
  fake_interface_pkg::msg::ActionPlan_<std::allocator<void>>;

// constant definitions

}  // namespace msg

}  // namespace fake_interface_pkg

#endif  // FAKE_INTERFACE_PKG__MSG__DETAIL__ACTION_PLAN__STRUCT_HPP_
