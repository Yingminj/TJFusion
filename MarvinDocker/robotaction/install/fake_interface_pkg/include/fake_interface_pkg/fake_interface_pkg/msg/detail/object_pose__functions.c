// generated from rosidl_generator_c/resource/idl__functions.c.em
// with input from fake_interface_pkg:msg/ObjectPose.idl
// generated code does not contain a copyright notice
#include "fake_interface_pkg/msg/detail/object_pose__functions.h"

#include <assert.h>
#include <stdbool.h>
#include <stdlib.h>
#include <string.h>

#include "rcutils/allocator.h"


// Include directives for member types
// Member `header`
#include "std_msgs/msg/detail/header__functions.h"
// Member `poses`
#include "fake_interface_pkg/msg/detail/pose__functions.h"

bool
fake_interface_pkg__msg__ObjectPose__init(fake_interface_pkg__msg__ObjectPose * msg)
{
  if (!msg) {
    return false;
  }
  // header
  if (!std_msgs__msg__Header__init(&msg->header)) {
    fake_interface_pkg__msg__ObjectPose__fini(msg);
    return false;
  }
  // poses
  if (!fake_interface_pkg__msg__Pose__Sequence__init(&msg->poses, 0)) {
    fake_interface_pkg__msg__ObjectPose__fini(msg);
    return false;
  }
  return true;
}

void
fake_interface_pkg__msg__ObjectPose__fini(fake_interface_pkg__msg__ObjectPose * msg)
{
  if (!msg) {
    return;
  }
  // header
  std_msgs__msg__Header__fini(&msg->header);
  // poses
  fake_interface_pkg__msg__Pose__Sequence__fini(&msg->poses);
}

bool
fake_interface_pkg__msg__ObjectPose__are_equal(const fake_interface_pkg__msg__ObjectPose * lhs, const fake_interface_pkg__msg__ObjectPose * rhs)
{
  if (!lhs || !rhs) {
    return false;
  }
  // header
  if (!std_msgs__msg__Header__are_equal(
      &(lhs->header), &(rhs->header)))
  {
    return false;
  }
  // poses
  if (!fake_interface_pkg__msg__Pose__Sequence__are_equal(
      &(lhs->poses), &(rhs->poses)))
  {
    return false;
  }
  return true;
}

bool
fake_interface_pkg__msg__ObjectPose__copy(
  const fake_interface_pkg__msg__ObjectPose * input,
  fake_interface_pkg__msg__ObjectPose * output)
{
  if (!input || !output) {
    return false;
  }
  // header
  if (!std_msgs__msg__Header__copy(
      &(input->header), &(output->header)))
  {
    return false;
  }
  // poses
  if (!fake_interface_pkg__msg__Pose__Sequence__copy(
      &(input->poses), &(output->poses)))
  {
    return false;
  }
  return true;
}

fake_interface_pkg__msg__ObjectPose *
fake_interface_pkg__msg__ObjectPose__create()
{
  rcutils_allocator_t allocator = rcutils_get_default_allocator();
  fake_interface_pkg__msg__ObjectPose * msg = (fake_interface_pkg__msg__ObjectPose *)allocator.allocate(sizeof(fake_interface_pkg__msg__ObjectPose), allocator.state);
  if (!msg) {
    return NULL;
  }
  memset(msg, 0, sizeof(fake_interface_pkg__msg__ObjectPose));
  bool success = fake_interface_pkg__msg__ObjectPose__init(msg);
  if (!success) {
    allocator.deallocate(msg, allocator.state);
    return NULL;
  }
  return msg;
}

void
fake_interface_pkg__msg__ObjectPose__destroy(fake_interface_pkg__msg__ObjectPose * msg)
{
  rcutils_allocator_t allocator = rcutils_get_default_allocator();
  if (msg) {
    fake_interface_pkg__msg__ObjectPose__fini(msg);
  }
  allocator.deallocate(msg, allocator.state);
}


bool
fake_interface_pkg__msg__ObjectPose__Sequence__init(fake_interface_pkg__msg__ObjectPose__Sequence * array, size_t size)
{
  if (!array) {
    return false;
  }
  rcutils_allocator_t allocator = rcutils_get_default_allocator();
  fake_interface_pkg__msg__ObjectPose * data = NULL;

  if (size) {
    data = (fake_interface_pkg__msg__ObjectPose *)allocator.zero_allocate(size, sizeof(fake_interface_pkg__msg__ObjectPose), allocator.state);
    if (!data) {
      return false;
    }
    // initialize all array elements
    size_t i;
    for (i = 0; i < size; ++i) {
      bool success = fake_interface_pkg__msg__ObjectPose__init(&data[i]);
      if (!success) {
        break;
      }
    }
    if (i < size) {
      // if initialization failed finalize the already initialized array elements
      for (; i > 0; --i) {
        fake_interface_pkg__msg__ObjectPose__fini(&data[i - 1]);
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
fake_interface_pkg__msg__ObjectPose__Sequence__fini(fake_interface_pkg__msg__ObjectPose__Sequence * array)
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
      fake_interface_pkg__msg__ObjectPose__fini(&array->data[i]);
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

fake_interface_pkg__msg__ObjectPose__Sequence *
fake_interface_pkg__msg__ObjectPose__Sequence__create(size_t size)
{
  rcutils_allocator_t allocator = rcutils_get_default_allocator();
  fake_interface_pkg__msg__ObjectPose__Sequence * array = (fake_interface_pkg__msg__ObjectPose__Sequence *)allocator.allocate(sizeof(fake_interface_pkg__msg__ObjectPose__Sequence), allocator.state);
  if (!array) {
    return NULL;
  }
  bool success = fake_interface_pkg__msg__ObjectPose__Sequence__init(array, size);
  if (!success) {
    allocator.deallocate(array, allocator.state);
    return NULL;
  }
  return array;
}

void
fake_interface_pkg__msg__ObjectPose__Sequence__destroy(fake_interface_pkg__msg__ObjectPose__Sequence * array)
{
  rcutils_allocator_t allocator = rcutils_get_default_allocator();
  if (array) {
    fake_interface_pkg__msg__ObjectPose__Sequence__fini(array);
  }
  allocator.deallocate(array, allocator.state);
}

bool
fake_interface_pkg__msg__ObjectPose__Sequence__are_equal(const fake_interface_pkg__msg__ObjectPose__Sequence * lhs, const fake_interface_pkg__msg__ObjectPose__Sequence * rhs)
{
  if (!lhs || !rhs) {
    return false;
  }
  if (lhs->size != rhs->size) {
    return false;
  }
  for (size_t i = 0; i < lhs->size; ++i) {
    if (!fake_interface_pkg__msg__ObjectPose__are_equal(&(lhs->data[i]), &(rhs->data[i]))) {
      return false;
    }
  }
  return true;
}

bool
fake_interface_pkg__msg__ObjectPose__Sequence__copy(
  const fake_interface_pkg__msg__ObjectPose__Sequence * input,
  fake_interface_pkg__msg__ObjectPose__Sequence * output)
{
  if (!input || !output) {
    return false;
  }
  if (output->capacity < input->size) {
    const size_t allocation_size =
      input->size * sizeof(fake_interface_pkg__msg__ObjectPose);
    rcutils_allocator_t allocator = rcutils_get_default_allocator();
    fake_interface_pkg__msg__ObjectPose * data =
      (fake_interface_pkg__msg__ObjectPose *)allocator.reallocate(
      output->data, allocation_size, allocator.state);
    if (!data) {
      return false;
    }
    // If reallocation succeeded, memory may or may not have been moved
    // to fulfill the allocation request, invalidating output->data.
    output->data = data;
    for (size_t i = output->capacity; i < input->size; ++i) {
      if (!fake_interface_pkg__msg__ObjectPose__init(&output->data[i])) {
        // If initialization of any new item fails, roll back
        // all previously initialized items. Existing items
        // in output are to be left unmodified.
        for (; i-- > output->capacity; ) {
          fake_interface_pkg__msg__ObjectPose__fini(&output->data[i]);
        }
        return false;
      }
    }
    output->capacity = input->size;
  }
  output->size = input->size;
  for (size_t i = 0; i < input->size; ++i) {
    if (!fake_interface_pkg__msg__ObjectPose__copy(
        &(input->data[i]), &(output->data[i])))
    {
      return false;
    }
  }
  return true;
}
