cmake_minimum_required(VERSION 3.10)
project(marvin_teleop)

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

# link_directories(${CMAKE_CURRENT_SOURCE_DIR}/lib)
# if(NOT DEFINED CPU_ARCH)
#   message(WARNING "⚠️ CPU_ARCH not set — defaulting to arm64 architecture")
#   set(CPU_ARCH "arm64")
# endif()


file(GLOB_RECURSE KINEMATICS_SOURCES
    ${CMAKE_SOURCE_DIR}/src/fx_sdk/*.c
    ${CMAKE_SOURCE_DIR}/src/fx_sdk/*.cpp
)

add_executable(IK_v2 src/IK_node.cpp ${KINEMATICS_SOURCES})
ament_target_dependencies(IK_v2 rclcpp tf2_ros std_msgs sensor_msgs tf2 tf2_geometry_msgs visualization_msgs marvin_msgs pinocchio hpp-fcl)
target_link_libraries(IK_v2
  pinocchio::pinocchio
  hpp-fcl::hpp-fcl
)

install(TARGETS
  IK_v2
  DESTINATION lib/${PROJECT_NAME})

# Install Python modules or scripts
ament_python_install_package(${PROJECT_NAME})
install(PROGRAMS
  ${PROJECT_NAME}/controller_udp.py
  ${PROJECT_NAME}/controller_udp_new.py
  ${PROJECT_NAME}/IK_viewer.py
  ${PROJECT_NAME}/hardware_sim.py
  ${PROJECT_NAME}/6dof_maker.py
  DESTINATION lib/${PROJECT_NAME}
)

install(DIRECTORY
  launch
  config
  DESTINATION share/${PROJECT_NAME}/
)


install(DIRECTORY include/
  DESTINATION include
)

ament_export_include_directories(
  include
)

if(BUILD_TESTING)
  find_package(ament_lint_auto REQUIRED)
  set(ament_cmake_copyright_FOUND TRUE)
  set(ament_cmake_cpplint_FOUND TRUE)
  ament_lint_auto_find_test_dependencies()
endif()

ament_package()
