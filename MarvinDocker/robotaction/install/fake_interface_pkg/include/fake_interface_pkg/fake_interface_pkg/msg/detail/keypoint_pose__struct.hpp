// generated from rosidl_generator_cpp/resource/idl__struct.hpp.em
// with input from fake_interface_pkg:msg/KeypointPose.idl
// generated code does not contain a copyright notice

#ifndef FAKE_INTERFACE_PKG__MSG__DETAIL__KEYPOINT_POSE__STRUCT_HPP_
#define FAKE_INTERFACE_PKG__MSG__DETAIL__KEYPOINT_POSE__STRUCT_HPP_

#include <algorithm>
#include <array>
#include <memory>
#include <string>
#include <vector>

#include "rosidl_runtime_cpp/bounded_vector.hpp"
#include "rosidl_runtime_cpp/message_initialization.hpp"


// Include directives for member types
// Member 'poses'
#include "geometry_msgs/msg/detail/pose__struct.hpp"

#ifndef _WIN32
# define DEPRECATED__fake_interface_pkg__msg__KeypointPose __attribute__((deprecated))
#else
# define DEPRECATED__fake_interface_pkg__msg__KeypointPose __declspec(deprecated)
#endif

namespace fake_interface_pkg
{

namespace msg
{

// message struct
template<class ContainerAllocator>
struct KeypointPose_
{
  using Type = KeypointPose_<ContainerAllocator>;

  explicit KeypointPose_(rosidl_runtime_cpp::MessageInitialization _init = rosidl_runtime_cpp::MessageInitialization::ALL)
  {
    if (rosidl_runtime_cpp::MessageInitialization::ALL == _init ||
      rosidl_runtime_cpp::MessageInitialization::ZERO == _init)
    {
      this->name = "";
      this->arm = "";
      std::fill<typename std::array<float, 3>::iterator, float>(this->constraints.begin(), this->constraints.end(), 0.0f);
      this->speed = 0.0f;
    }
  }

  explicit KeypointPose_(const ContainerAllocator & _alloc, rosidl_runtime_cpp::MessageInitialization _init = rosidl_runtime_cpp::MessageInitialization::ALL)
  : name(_alloc),
    arm(_alloc),
    constraints(_alloc)
  {
    if (rosidl_runtime_cpp::MessageInitialization::ALL == _init ||
      rosidl_runtime_cpp::MessageInitialization::ZERO == _init)
    {
      this->name = "";
      this->arm = "";
      std::fill<typename std::array<float, 3>::iterator, float>(this->constraints.begin(), this->constraints.end(), 0.0f);
      this->speed = 0.0f;
    }
  }

  // field types and members
  using _name_type =
    std::basic_string<char, std::char_traits<char>, typename std::allocator_traits<ContainerAllocator>::template rebind_alloc<char>>;
  _name_type name;
  using _arm_type =
    std::basic_string<char, std::char_traits<char>, typename std::allocator_traits<ContainerAllocator>::template rebind_alloc<char>>;
  _arm_type arm;
  using _poses_type =
    std::vector<geometry_msgs::msg::Pose_<ContainerAllocator>, typename std::allocator_traits<ContainerAllocator>::template rebind_alloc<geometry_msgs::msg::Pose_<ContainerAllocator>>>;
  _poses_type poses;
  using _constraints_type =
    std::array<float, 3>;
  _constraints_type constraints;
  using _speed_type =
    float;
  _speed_type speed;
  using _gripper_value_type =
    std::vector<float, typename std::allocator_traits<ContainerAllocator>::template rebind_alloc<float>>;
  _gripper_value_type gripper_value;
  using _time_type =
    std::vector<float, typename std::allocator_traits<ContainerAllocator>::template rebind_alloc<float>>;
  _time_type time;

  // setters for named parameter idiom
  Type & set__name(
    const std::basic_string<char, std::char_traits<char>, typename std::allocator_traits<ContainerAllocator>::template rebind_alloc<char>> & _arg)
  {
    this->name = _arg;
    return *this;
  }
  Type & set__arm(
    const std::basic_string<char, std::char_traits<char>, typename std::allocator_traits<ContainerAllocator>::template rebind_alloc<char>> & _arg)
  {
    this->arm = _arg;
    return *this;
  }
  Type & set__poses(
    const std::vector<geometry_msgs::msg::Pose_<ContainerAllocator>, typename std::allocator_traits<ContainerAllocator>::template rebind_alloc<geometry_msgs::msg::Pose_<ContainerAllocator>>> & _arg)
  {
    this->poses = _arg;
    return *this;
  }
  Type & set__constraints(
    const std::array<float, 3> & _arg)
  {
    this->constraints = _arg;
    return *this;
  }
  Type & set__speed(
    const float & _arg)
  {
    this->speed = _arg;
    return *this;
  }
  Type & set__gripper_value(
    const std::vector<float, typename std::allocator_traits<ContainerAllocator>::template rebind_alloc<float>> & _arg)
  {
    this->gripper_value = _arg;
    return *this;
  }
  Type & set__time(
    const std::vector<float, typename std::allocator_traits<ContainerAllocator>::template rebind_alloc<float>> & _arg)
  {
    this->time = _arg;
    return *this;
  }

  // constant declarations

  // pointer types
  using RawPtr =
    fake_interface_pkg::msg::KeypointPose_<ContainerAllocator> *;
  using ConstRawPtr =
    const fake_interface_pkg::msg::KeypointPose_<ContainerAllocator> *;
  using SharedPtr =
    std::shared_ptr<fake_interface_pkg::msg::KeypointPose_<ContainerAllocator>>;
  using ConstSharedPtr =
    std::shared_ptr<fake_interface_pkg::msg::KeypointPose_<ContainerAllocator> const>;

  template<typename Deleter = std::default_delete<
      fake_interface_pkg::msg::KeypointPose_<ContainerAllocator>>>
  using UniquePtrWithDeleter =
    std::unique_ptr<fake_interface_pkg::msg::KeypointPose_<ContainerAllocator>, Deleter>;

  using UniquePtr = UniquePtrWithDeleter<>;

  template<typename Deleter = std::default_delete<
      fake_interface_pkg::msg::KeypointPose_<ContainerAllocator>>>
  using ConstUniquePtrWithDeleter =
    std::unique_ptr<fake_interface_pkg::msg::KeypointPose_<ContainerAllocator> const, Deleter>;
  using ConstUniquePtr = ConstUniquePtrWithDeleter<>;

  using WeakPtr =
    std::weak_ptr<fake_interface_pkg::msg::KeypointPose_<ContainerAllocator>>;
  using ConstWeakPtr =
    std::weak_ptr<fake_interface_pkg::msg::KeypointPose_<ContainerAllocator> const>;

  // pointer types similar to ROS 1, use SharedPtr / ConstSharedPtr instead
  // NOTE: Can't use 'using' here because GNU C++ can't parse attributes properly
  typedef DEPRECATED__fake_interface_pkg__msg__KeypointPose
    std::shared_ptr<fake_interface_pkg::msg::KeypointPose_<ContainerAllocator>>
    Ptr;
  typedef DEPRECATED__fake_interface_pkg__msg__KeypointPose
    std::shared_ptr<fake_interface_pkg::msg::KeypointPose_<ContainerAllocator> const>
    ConstPtr;

  // comparison operators
  bool operator==(const KeypointPose_ & other) const
  {
    if (this->name != other.name) {
      return false;
    }
    if (this->arm != other.arm) {
      return false;
    }
    if (this->poses != other.poses) {
      return false;
    }
    if (this->constraints != other.constraints) {
      return false;
    }
    if (this->speed != other.speed) {
      return false;
    }
    if (this->gripper_value != other.gripper_value) {
      return false;
    }
    if (this->time != other.time) {
      return false;
    }
    return true;
  }
  bool operator!=(const KeypointPose_ & other) const
  {
    return !this->operator==(other);
  }
};  // struct KeypointPose_

// alias to use template instance with default allocator
using KeypointPose =
  fake_interface_pkg::msg::KeypointPose_<std::allocator<void>>;

// constant definitions

}  // namespace msg

}  // namespace fake_interface_pkg

#endif  // FAKE_INTERFACE_PKG__MSG__DETAIL__KEYPOINT_POSE__STRUCT_HPP_
