// generated from rosidl_generator_c/resource/idl__functions.c.em
// with input from fake_interface_pkg:msg/Action.idl
// generated code does not contain a copyright notice
#include "fake_interface_pkg/msg/detail/action__functions.h"

#include <assert.h>
#include <stdbool.h>
#include <stdlib.h>
#include <string.h>

#include "rcutils/allocator.h"


// Include directives for member types
// Member `description`
// Member `goal`
// Member `action`
#include "rosidl_runtime_c/string_functions.h"

bool
fake_interface_pkg__msg__Action__init(fake_interface_pkg__msg__Action * msg)
{
  if (!msg) {
    return false;
  }
  // description
  if (!rosidl_runtime_c__String__init(&msg->description)) {
    fake_interface_pkg__msg__Action__fini(msg);
    return false;
  }
  // goal
  if (!rosidl_runtime_c__String__init(&msg->goal)) {
    fake_interface_pkg__msg__Action__fini(msg);
    return false;
  }
  // action
  if (!rosidl_runtime_c__String__init(&msg->action)) {
    fake_interface_pkg__msg__Action__fini(msg);
    return false;
  }
  return true;
}

void
fake_interface_pkg__msg__Action__fini(fake_interface_pkg__msg__Action * msg)
{
  if (!msg) {
    return;
  }
  // description
  rosidl_runtime_c__String__fini(&msg->description);
  // goal
  rosidl_runtime_c__String__fini(&msg->goal);
  // action
  rosidl_runtime_c__String__fini(&msg->action);
}

bool
fake_interface_pkg__msg__Action__are_equal(const fake_interface_pkg__msg__Action * lhs, const fake_interface_pkg__msg__Action * rhs)
{
  if (!lhs || !rhs) {
    return false;
  }
  // description
  if (!rosidl_runtime_c__String__are_equal(
      &(lhs->description), &(rhs->description)))
  {
    return false;
  }
  // goal
  if (!rosidl_runtime_c__String__are_equal(
      &(lhs->goal), &(rhs->goal)))
  {
    return false;
  }
  // action
  if (!rosidl_runtime_c__String__are_equal(
      &(lhs->action), &(rhs->action)))
  {
    return false;
  }
  return true;
}

bool
fake_interface_pkg__msg__Action__copy(
  const fake_interface_pkg__msg__Action * input,
  fake_interface_pkg__msg__Action * output)
{
  if (!input || !output) {
    return false;
  }
  // description
  if (!rosidl_runtime_c__String__copy(
      &(input->description), &(output->description)))
  {
    return false;
  }
  // goal
  if (!rosidl_runtime_c__String__copy(
      &(input->goal), &(output->goal)))
  {
    return false;
  }
  // action
  if (!rosidl_runtime_c__String__copy(
      &(input->action), &(output->action)))
  {
    return false;
  }
  return true;
}

fake_interface_pkg__msg__Action *
fake_interface_pkg__msg__Action__create()
{
  rcutils_allocator_t allocator = rcutils_get_default_allocator();
  fake_interface_pkg__msg__Action * msg = (fake_interface_pkg__msg__Action *)allocator.allocate(sizeof(fake_interface_pkg__msg__Action), allocator.state);
  if (!msg) {
    return NULL;
  }
  memset(msg, 0, sizeof(fake_interface_pkg__msg__Action));
  bool success = fake_interface_pkg__msg__Action__init(msg);
  if (!success) {
    allocator.deallocate(msg, allocator.state);
    return NULL;
  }
  return msg;
}

void
fake_interface_pkg__msg__Action__destroy(fake_interface_pkg__msg__Action * msg)
{
  rcutils_allocator_t allocator = rcutils_get_default_allocator();
  if (msg) {
    fake_interface_pkg__msg__Action__fini(msg);
  }
  allocator.deallocate(msg, allocator.state);
}


bool
fake_interface_pkg__msg__Action__Sequence__init(fake_interface_pkg__msg__Action__Sequence * array, size_t size)
{
  if (!array) {
    return false;
  }
  rcutils_allocator_t allocator = rcutils_get_default_allocator();
  fake_interface_pkg__msg__Action * data = NULL;

  if (size) {
    data = (fake_interface_pkg__msg__Action *)allocator.zero_allocate(size, sizeof(fake_interface_pkg__msg__Action), allocator.state);
    if (!data) {
      return false;
    }
    // initialize all array elements
    size_t i;
    for (i = 0; i < size; ++i) {
      bool success = fake_interface_pkg__msg__Action__init(&data[i]);
      if (!success) {
        break;
      }
    }
    if (i < size) {
      // if initialization failed finalize the already initialized array elements
      for (; i > 0; --i) {
        fake_interface_pkg__msg__Action__fini(&data[i - 1]);
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
fake_interface_pkg__msg__Action__Sequence__fini(fake_interface_pkg__msg__Action__Sequence * array)
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
      fake_interface_pkg__msg__Action__fini(&array->data[i]);
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

fake_interface_pkg__msg__Action__Sequence *
fake_interface_pkg__msg__Action__Sequence__create(size_t size)
{
  rcutils_allocator_t allocator = rcutils_get_default_allocator();
  fake_interface_pkg__msg__Action__Sequence * array = (fake_interface_pkg__msg__Action__Sequence *)allocator.allocate(sizeof(fake_interface_pkg__msg__Action__Sequence), allocator.state);
  if (!array) {
    return NULL;
  }
  bool success = fake_interface_pkg__msg__Action__Sequence__init(array, size);
  if (!success) {
    allocator.deallocate(array, allocator.state);
    return NULL;
  }
  return array;
}

void
fake_interface_pkg__msg__Action__Sequence__destroy(fake_interface_pkg__msg__Action__Sequence * array)
{
  rcutils_allocator_t allocator = rcutils_get_default_allocator();
  if (array) {
    fake_interface_pkg__msg__Action__Sequence__fini(array);
  }
  allocator.deallocate(array, allocator.state);
}

bool
fake_interface_pkg__msg__Action__Sequence__are_equal(const fake_interface_pkg__msg__Action__Sequence * lhs, const fake_interface_pkg__msg__Action__Sequence * rhs)
{
  if (!lhs || !rhs) {
    return false;
  }
  if (lhs->size != rhs->size) {
    return false;
  }
  for (size_t i = 0; i < lhs->size; ++i) {
    if (!fake_interface_pkg__msg__Action__are_equal(&(lhs->data[i]), &(rhs->data[i]))) {
      return false;
    }
  }
  return true;
}

bool
fake_interface_pkg__msg__Action__Sequence__copy(
  const fake_interface_pkg__msg__Action__Sequence * input,
  fake_interface_pkg__msg__Action__Sequence * output)
{
  if (!input || !output) {
    return false;
  }
  if (output->capacity < input->size) {
    const size_t allocation_size =
      input->size * sizeof(fake_interface_pkg__msg__Action);
    rcutils_allocator_t allocator = rcutils_get_default_allocator();
    fake_interface_pkg__msg__Action * data =
      (fake_interface_pkg__msg__Action *)allocator.reallocate(
      output->data, allocation_size, allocator.state);
    if (!data) {
      return false;
    }
    // If reallocation succeeded, memory may or may not have been moved
    // to fulfill the allocation request, invalidating output->data.
    output->data = data;
    for (size_t i = output->capacity; i < input->size; ++i) {
      if (!fake_interface_pkg__msg__Action__init(&output->data[i])) {
        // If initialization of any new item fails, roll back
        // all previously initialized items. Existing items
        // in output are to be left unmodified.
        for (; i-- > output->capacity; ) {
          fake_interface_pkg__msg__Action__fini(&output->data[i]);
        }
        return false;
      }
    }
    output->capacity = input->size;
  }
  output->size = input->size;
  for (size_t i = 0; i < input->size; ++i) {
    if (!fake_interface_pkg__msg__Action__copy(
        &(input->data[i]), &(output->data[i])))
    {
      return false;
    }
  }
  return true;
}
