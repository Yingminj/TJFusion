cmake_minimum_required(VERSION 3.10)
project(marvin_ros_control)

if(CMAKE_COMPILER_IS_GNUCXX OR CMAKE_CXX_COMPILER_ID MATCHES "Clang")
  add_compile_options(-Wall -Wextra -Wpedantic)
endif()


if(NOT CMAKE_CXX_STANDARD)
  set(CMAKE_CXX_STANDARD 17)
endif()

# find dependencies
find_package(ament_cmake REQUIRED)
find_package(rclcpp REQUIRED)
find_package(tf2_ros REQUIRED)
find_package(tf2_geometry_msgs REQUIRED)
find_package(std_msgs REQUIRED)
find_package(std_srvs REQUIRED)
find_package(sensor_msgs REQUIRED)
find_package(geometry_msgs REQUIRED)
find_package(visualization_msgs REQUIRED)
find_package(marvin_msgs REQUIRED) 
find_package(Eigen3 REQUIRED)  # If using Eigen
find_package(tf2 REQUIRED)
find_package(pinocchio REQUIRED)
find_package(hpp-fcl REQUIRED)

# Specify the path to the MarvinSDK header and library
# (Replace these paths with the actual ones)
# set(MARVIN_SDK_DIR "/home/marvin/marvin_sdk")


include_directories(
  ${EIGEN3_INCLUDE_DIRS}
  ${pinocchio_INCLUDE_DIRS}
  include)

link_directories(${CMAKE_CURRENT_SOURCE_DIR}/lib)
if(NOT DEFINED CPU_ARCH)
  message(WARNING "⚠️ CPU_ARCH not set — defaulting to arm64 architecture")
  set(CPU_ARCH "arm64")
endif()

if(CPU_ARCH STREQUAL "x86" OR CPU_ARCH STREQUAL "x86_64")
  message(STATUS "🏗️ Building for x86_64 architecture")
  set(MARVIN_LIB_NAME "libMarvinSDK_x86.so")
elseif(CPU_ARCH STREQUAL "arm64" OR CPU_ARCH STREQUAL "aarch64")
  message(STATUS "🏗️ Building for arm64 architecture")
  set(MARVIN_LIB_NAME "libMarvinSDK_arm64.so")
else()
  message(FATAL_ERROR "❌ Unsupported architecture '${CPU_ARCH}'. Use -DCPU_ARCH=x86 or -DCPU_ARCH=arm64")
endif()

find_library(MARVIN_SDK_LIB
  NAMES MarvinSDK ${MARVIN_LIB_NAME}
  PATHS ${CMAKE_CURRENT_SOURCE_DIR}/lib
  NO_DEFAULT_PATH
)

if(NOT MARVIN_SDK_LIB)
  message(FATAL_ERROR "❌ Could not find ${MARVIN_LIB_NAME}.so in ${CMAKE_CURRENT_SOURCE_DIR}/lib")
else()
  message(STATUS "✅ Found Marvin SDK library: ${MARVIN_SDK_LIB}")
endif()


add_executable(marvin_robot_node src/marvin_robot_node.cpp src/marvin_robot.cpp)
target_link_libraries(marvin_robot_node ${MARVIN_SDK_LIB})
ament_target_dependencies(marvin_robot_node rclcpp sensor_msgs geometry_msgs std_msgs marvin_msgs tf2 std_srvs)


install(TARGETS
  marvin_robot_node
  DESTINATION lib/${PROJECT_NAME})

# Install Python modules or scripts
install(DIRECTORY
  launch
  config
  DESTINATION share/${PROJECT_NAME}/
)

install(FILES ${MARVIN_SDK_LIB}
    DESTINATION lib
)

install(DIRECTORY include/
  DESTINATION include
)

ament_export_include_directories(
  include
)

if(BUILD_TESTING)
  find_package(ament_lint_auto REQUIRED)
  # the following line skips the linter which checks for copyrights
  # comment the line when a copyright and license is added to all source files
  set(ament_cmake_copyright_FOUND TRUE)
  # the following line skips cpplint (only works in a git repo)
  # comment the line when this package is in a git repo and when
  # a copyright and license is added to all source files
  set(ament_cmake_cpplint_FOUND TRUE)
  ament_lint_auto_find_test_dependencies()
endif()

ament_package()
