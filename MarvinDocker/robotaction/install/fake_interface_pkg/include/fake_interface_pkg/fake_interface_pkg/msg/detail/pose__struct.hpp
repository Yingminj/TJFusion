// generated from rosidl_generator_cpp/resource/idl__struct.hpp.em
// with input from fake_interface_pkg:msg/Pose.idl
// generated code does not contain a copyright notice

#ifndef FAKE_INTERFACE_PKG__MSG__DETAIL__POSE__STRUCT_HPP_
#define FAKE_INTERFACE_PKG__MSG__DETAIL__POSE__STRUCT_HPP_

#include <algorithm>
#include <array>
#include <memory>
#include <string>
#include <vector>

#include "rosidl_runtime_cpp/bounded_vector.hpp"
#include "rosidl_runtime_cpp/message_initialization.hpp"


// Include directives for member types
// Member 'position'
#include "geometry_msgs/msg/detail/point__struct.hpp"
// Member 'orientation'
#include "geometry_msgs/msg/detail/quaternion__struct.hpp"

#ifndef _WIN32
# define DEPRECATED__fake_interface_pkg__msg__Pose __attribute__((deprecated))
#else
# define DEPRECATED__fake_interface_pkg__msg__Pose __declspec(deprecated)
#endif

namespace fake_interface_pkg
{

namespace msg
{

// message struct
template<class ContainerAllocator>
struct Pose_
{
  using Type = Pose_<ContainerAllocator>;

  explicit Pose_(rosidl_runtime_cpp::MessageInitialization _init = rosidl_runtime_cpp::MessageInitialization::ALL)
  : position(_init),
    orientation(_init)
  {
    if (rosidl_runtime_cpp::MessageInitialization::ALL == _init ||
      rosidl_runtime_cpp::MessageInitialization::ZERO == _init)
    {
      this->obj_id = 0l;
      this->obj_name = "";
    }
  }

  explicit Pose_(const ContainerAllocator & _alloc, rosidl_runtime_cpp::MessageInitialization _init = rosidl_runtime_cpp::MessageInitialization::ALL)
  : position(_alloc, _init),
    orientation(_alloc, _init),
    obj_name(_alloc)
  {
    if (rosidl_runtime_cpp::MessageInitialization::ALL == _init ||
      rosidl_runtime_cpp::MessageInitialization::ZERO == _init)
    {
      this->obj_id = 0l;
      this->obj_name = "";
    }
  }

  // field types and members
  using _position_type =
    geometry_msgs::msg::Point_<ContainerAllocator>;
  _position_type position;
  using _orientation_type =
    geometry_msgs::msg::Quaternion_<ContainerAllocator>;
  _orientation_type orientation;
  using _obj_id_type =
    int32_t;
  _obj_id_type obj_id;
  using _obj_name_type =
    std::basic_string<char, std::char_traits<char>, typename std::allocator_traits<ContainerAllocator>::template rebind_alloc<char>>;
  _obj_name_type obj_name;

  // setters for named parameter idiom
  Type & set__position(
    const geometry_msgs::msg::Point_<ContainerAllocator> & _arg)
  {
    this->position = _arg;
    return *this;
  }
  Type & set__orientation(
    const geometry_msgs::msg::Quaternion_<ContainerAllocator> & _arg)
  {
    this->orientation = _arg;
    return *this;
  }
  Type & set__obj_id(
    const int32_t & _arg)
  {
    this->obj_id = _arg;
    return *this;
  }
  Type & set__obj_name(
    const std::basic_string<char, std::char_traits<char>, typename std::allocator_traits<ContainerAllocator>::template rebind_alloc<char>> & _arg)
  {
    this->obj_name = _arg;
    return *this;
  }

  // constant declarations

  // pointer types
  using RawPtr =
    fake_interface_pkg::msg::Pose_<ContainerAllocator> *;
  using ConstRawPtr =
    const fake_interface_pkg::msg::Pose_<ContainerAllocator> *;
  using SharedPtr =
    std::shared_ptr<fake_interface_pkg::msg::Pose_<ContainerAllocator>>;
  using ConstSharedPtr =
    std::shared_ptr<fake_interface_pkg::msg::Pose_<ContainerAllocator> const>;

  template<typename Deleter = std::default_delete<
      fake_interface_pkg::msg::Pose_<ContainerAllocator>>>
  using UniquePtrWithDeleter =
    std::unique_ptr<fake_interface_pkg::msg::Pose_<ContainerAllocator>, Deleter>;

  using UniquePtr = UniquePtrWithDeleter<>;

  template<typename Deleter = std::default_delete<
      fake_interface_pkg::msg::Pose_<ContainerAllocator>>>
  using ConstUniquePtrWithDeleter =
    std::unique_ptr<fake_interface_pkg::msg::Pose_<ContainerAllocator> const, Deleter>;
  using ConstUniquePtr = ConstUniquePtrWithDeleter<>;

  using WeakPtr =
    std::weak_ptr<fake_interface_pkg::msg::Pose_<ContainerAllocator>>;
  using ConstWeakPtr =
    std::weak_ptr<fake_interface_pkg::msg::Pose_<ContainerAllocator> const>;

  // pointer types similar to ROS 1, use SharedPtr / ConstSharedPtr instead
  // NOTE: Can't use 'using' here because GNU C++ can't parse attributes properly
  typedef DEPRECATED__fake_interface_pkg__msg__Pose
    std::shared_ptr<fake_interface_pkg::msg::Pose_<ContainerAllocator>>
    Ptr;
  typedef DEPRECATED__fake_interface_pkg__msg__Pose
    std::shared_ptr<fake_interface_pkg::msg::Pose_<ContainerAllocator> const>
    ConstPtr;

  // comparison operators
  bool operator==(const Pose_ & other) const
  {
    if (this->position != other.position) {
      return false;
    }
    if (this->orientation != other.orientation) {
      return false;
    }
    if (this->obj_id != other.obj_id) {
      return false;
    }
    if (this->obj_name != other.obj_name) {
      return false;
    }
    return true;
  }
  bool operator!=(const Pose_ & other) const
  {
    return !this->operator==(other);
  }
};  // struct Pose_

// alias to use template instance with default allocator
using Pose =
  fake_interface_pkg::msg::Pose_<std::allocator<void>>;

// constant definitions

}  // namespace msg

}  // namespace fake_interface_pkg

#endif  // FAKE_INTERFACE_PKG__MSG__DETAIL__POSE__STRUCT_HPP_
