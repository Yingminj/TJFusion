// generated from rosidl_generator_c/resource/idl__functions.c.em
// with input from fake_interface_pkg:msg/Pose.idl
// generated code does not contain a copyright notice
#include "fake_interface_pkg/msg/detail/pose__functions.h"

#include <assert.h>
#include <stdbool.h>
#include <stdlib.h>
#include <string.h>

#include "rcutils/allocator.h"


// Include directives for member types
// Member `position`
#include "geometry_msgs/msg/detail/point__functions.h"
// Member `orientation`
#include "geometry_msgs/msg/detail/quaternion__functions.h"
// Member `obj_name`
#include "rosidl_runtime_c/string_functions.h"

bool
fake_interface_pkg__msg__Pose__init(fake_interface_pkg__msg__Pose * msg)
{
  if (!msg) {
    return false;
  }
  // position
  if (!geometry_msgs__msg__Point__init(&msg->position)) {
    fake_interface_pkg__msg__Pose__fini(msg);
    return false;
  }
  // orientation
  if (!geometry_msgs__msg__Quaternion__init(&msg->orientation)) {
    fake_interface_pkg__msg__Pose__fini(msg);
    return false;
  }
  // obj_id
  // obj_name
  if (!rosidl_runtime_c__String__init(&msg->obj_name)) {
    fake_interface_pkg__msg__Pose__fini(msg);
    return false;
  }
  return true;
}

void
fake_interface_pkg__msg__Pose__fini(fake_interface_pkg__msg__Pose * msg)
{
  if (!msg) {
    return;
  }
  // position
  geometry_msgs__msg__Point__fini(&msg->position);
  // orientation
  geometry_msgs__msg__Quaternion__fini(&msg->orientation);
  // obj_id
  // obj_name
  rosidl_runtime_c__String__fini(&msg->obj_name);
}

bool
fake_interface_pkg__msg__Pose__are_equal(const fake_interface_pkg__msg__Pose * lhs, const fake_interface_pkg__msg__Pose * rhs)
{
  if (!lhs || !rhs) {
    return false;
  }
  // position
  if (!geometry_msgs__msg__Point__are_equal(
      &(lhs->position), &(rhs->position)))
  {
    return false;
  }
  // orientation
  if (!geometry_msgs__msg__Quaternion__are_equal(
      &(lhs->orientation), &(rhs->orientation)))
  {
    return false;
  }
  // obj_id
  if (lhs->obj_id != rhs->obj_id) {
    return false;
  }
  // obj_name
  if (!rosidl_runtime_c__String__are_equal(
      &(lhs->obj_name), &(rhs->obj_name)))
  {
    return false;
  }
  return true;
}

bool
fake_interface_pkg__msg__Pose__copy(
  const fake_interface_pkg__msg__Pose * input,
  fake_interface_pkg__msg__Pose * output)
{
  if (!input || !output) {
    return false;
  }
  // position
  if (!geometry_msgs__msg__Point__copy(
      &(input->position), &(output->position)))
  {
    return false;
  }
  // orientation
  if (!geometry_msgs__msg__Quaternion__copy(
      &(input->orientation), &(output->orientation)))
  {
    return false;
  }
  // obj_id
  output->obj_id = input->obj_id;
  // obj_name
  if (!rosidl_runtime_c__String__copy(
      &(input->obj_name), &(output->obj_name)))
  {
    return false;
  }
  return true;
}

fake_interface_pkg__msg__Pose *
fake_interface_pkg__msg__Pose__create()
{
  rcutils_allocator_t allocator = rcutils_get_default_allocator();
  fake_interface_pkg__msg__Pose * msg = (fake_interface_pkg__msg__Pose *)allocator.allocate(sizeof(fake_interface_pkg__msg__Pose), allocator.state);
  if (!msg) {
    return NULL;
  }
  memset(msg, 0, sizeof(fake_interface_pkg__msg__Pose));
  bool success = fake_interface_pkg__msg__Pose__init(msg);
  if (!success) {
    allocator.deallocate(msg, allocator.state);
    return NULL;
  }
  return msg;
}

void
fake_interface_pkg__msg__Pose__destroy(fake_interface_pkg__msg__Pose * msg)
{
  rcutils_allocator_t allocator = rcutils_get_default_allocator();
  if (msg) {
    fake_interface_pkg__msg__Pose__fini(msg);
  }
  allocator.deallocate(msg, allocator.state);
}


bool
fake_interface_pkg__msg__Pose__Sequence__init(fake_interface_pkg__msg__Pose__Sequence * array, size_t size)
{
  if (!array) {
    return false;
  }
  rcutils_allocator_t allocator = rcutils_get_default_allocator();
  fake_interface_pkg__msg__Pose * data = NULL;

  if (size) {
    data = (fake_interface_pkg__msg__Pose *)allocator.zero_allocate(size, sizeof(fake_interface_pkg__msg__Pose), allocator.state);
    if (!data) {
      return false;
    }
    // initialize all array elements
    size_t i;
    for (i = 0; i < size; ++i) {
      bool success = fake_interface_pkg__msg__Pose__init(&data[i]);
      if (!success) {
        break;
      }
    }
    if (i < size) {
      // if initialization failed finalize the already initialized array elements
      for (; i > 0; --i) {
        fake_interface_pkg__msg__Pose__fini(&data[i - 1]);
      }
      allocator.deallocate(data, allocator.state);
      return false;
    }
  }
  array->data = data;
  array->size = size;
  array->capacity = size;
  return true;
}

void
fake_interface_pkg__msg__Pose__Sequence__fini(fake_interface_pkg__msg__Pose__Sequence * array)
{
  if (!array) {
    return;
  }
  rcutils_allocator_t allocator = rcutils_get_default_allocator();

  if (array->data) {
    // ensure that data and capacity values are consistent
    assert(array->capacity > 0);
    // finalize all array elements
    for (size_t i = 0; i < array->capacity; ++i) {
      fake_interface_pkg__msg__Pose__fini(&array->data[i]);
    }
    allocator.deallocate(array->data, allocator.state);
    array->data = NULL;
    array->size = 0;
    array->capacity = 0;
  } else {
    // ensure that data, size, and capacity values are consistent
    assert(0 == array->size);
    assert(0 == array->capacity);
  }
}

fake_interface_pkg__msg__Pose__Sequence *
fake_interface_pkg__msg__Pose__Sequence__create(size_t size)
{
  rcutils_allocator_t allocator = rcutils_get_default_allocator();
  fake_interface_pkg__msg__Pose__Sequence * array = (fake_interface_pkg__msg__Pose__Sequence *)allocator.allocate(sizeof(fake_interface_pkg__msg__Pose__Sequence), allocator.state);
  if (!array) {
    return NULL;
  }
  bool success = fake_interface_pkg__msg__Pose__Sequence__init(array, size);
  if (!success) {
    allocator.deallocate(array, allocator.state);
    return NULL;
  }
  return array;
}

void
fake_interface_pkg__msg__Pose__Sequence__destroy(fake_interface_pkg__msg__Pose__Sequence * array)
{
  rcutils_allocator_t allocator = rcutils_get_default_allocator();
  if (array) {
    fake_interface_pkg__msg__Pose__Sequence__fini(array);
  }
  allocator.deallocate(array, allocator.state);
}

bool
fake_interface_pkg__msg__Pose__Sequence__are_equal(const fake_interface_pkg__msg__Pose__Sequence * lhs, const fake_interface_pkg__msg__Pose__Sequence * rhs)
{
  if (!lhs || !rhs) {
    return false;
  }
  if (lhs->size != rhs->size) {
    return false;
  }
  for (size_t i = 0; i < lhs->size; ++i) {
    if (!fake_interface_pkg__msg__Pose__are_equal(&(lhs->data[i]), &(rhs->data[i]))) {
      return false;
    }
  }
  return true;
}

bool
fake_interface_pkg__msg__Pose__Sequence__copy(
  const fake_interface_pkg__msg__Pose__Sequence * input,
  fake_interface_pkg__msg__Pose__Sequence * output)
{
  if (!input || !output) {
    return false;
  }
  if (output->capacity < input->size) {
    const size_t allocation_size =
      input->size * sizeof(fake_interface_pkg__msg__Pose);
    rcutils_allocator_t allocator = rcutils_get_default_allocator();
    fake_interface_pkg__msg__Pose * data =
      (fake_interface_pkg__msg__Pose *)allocator.reallocate(
      output->data, allocation_size, allocator.state);
    if (!data) {
      return false;
    }
    // If reallocation succeeded, memory may or may not have been moved
    // to fulfill the allocation request, invalidating output->data.
    output->data = data;
    for (size_t i = output->capacity; i < input->size; ++i) {
      if (!fake_interface_pkg__msg__Pose__init(&output->data[i])) {
        // If initialization of any new item fails, roll back
        // all previously initialized items. Existing items
        // in output are to be left unmodified.
        for (; i-- > output->capacity; ) {
          fake_interface_pkg__msg__Pose__fini(&output->data[i]);
        }
        return false;
      }
    }
    output->capacity = input->size;
  }
  output->size = input->size;
  for (size_t i = 0; i < input->size; ++i) {
    if (!fake_interface_pkg__msg__Pose__copy(
        &(input->data[i]), &(output->data[i])))
    {
      return false;
    }
  }
  return true;
}
