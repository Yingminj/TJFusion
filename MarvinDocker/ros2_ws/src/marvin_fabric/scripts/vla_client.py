#!/usr/bin/env python3
"""
ROS2 PoseStamped subscriber node.

Subscribes to a topic publishing geometry_msgs/PoseStamped messages and logs
position and orientation.

Usage:
    ros2 run <package> pose_subscriber --ros-args -p topic:=/pose

This script is intended to be run inside a ROS2 Python package. For quick
manual testing you can run it with:
    python3 scripts/pose_subscriber.py --topic /pose

Requires: ROS2 (rclpy) or for quick non-ROS testing, run with no ROS installed
and it will print instructions.
"""
import argparse
import sys
#from openpi_client import image_tools
#from openpi_client import websocket_client_policy
import cv2
import rclpy
from rclpy.node import Node
from geometry_msgs.msg import PoseStamped
from std_msgs.msg import Float64MultiArray,Float32,Int16MultiArray
import pinocchio as pin
import numpy as np

class PoseSubscriber(Node):
    def __init__(self):
        super().__init__('pose_subscriber')
        self.topic = "/libero/actions"
        self.get_logger().info(f'Subscribing to: {self.topic}')
        self.sub = self.create_subscription(
            Float64MultiArray,
            self.topic,
            self.callback_action,
            10,
        )
        self.subR = self.create_subscription(
            PoseStamped,
            "/info/eef_right",
            self.callback_eef_R,
            10,
        )
        self.cmd_pub_R = self.create_publisher(PoseStamped, "/control/target_poseR", 10)
        self.gripper_controller_pub_R = self.create_publisher(Float32, 'control/gripperValueR', 10)
        self.current_eef_pose = None   # pin.SE3
        self.target_eef_pose = None    # pin.SE3
        self.target_constraint_pub = self.create_publisher(Int16MultiArray, "control/eef_constraint", 10)

    def callback_eef_R(self, msg: PoseStamped):
        p = msg.pose.position
        q = msg.pose.orientation

        quat = pin.Quaternion(q.w, q.x, q.y, q.z)
        quat.normalize()

        self.current_eef_pose = pin.SE3(
            quat.toRotationMatrix(),
            np.array([p.x, p.y, p.z])
        )

        # 第一次初始化 target
        if self.target_eef_pose is None:
            self.target_eef_pose = self.current_eef_pose

    # =====================================================
    # EEF 增量 action
    # =====================================================
    def callback_action(self, msg: Float64MultiArray):
        if self.current_eef_pose is None:
            return
        # self.get_logger().info("current EEF pose:")
        # self.get_logger().info(f"Position: {self.current_eef_pose.translation}")
        data = msg.data
        if len(data) < 6:
            self.get_logger().warn("Action length < 6")
            return

        # -------- se(3) 增量 --------
        v = np.array(data[0:3])     # translation
        w = np.array(data[3:6])     # rotation
        gripper_data = data[6]
        print("g:",gripper_data)
        delta = pin.Motion(v, w)

        # -------- T_target = T_current * exp(delta) --------
        self.target_eef_pose = self.current_eef_pose * pin.exp6(delta)

        # -------- debug --------
        pos = self.target_eef_pose.translation
        self.get_logger().info(
            f"EEF target pos: [{pos[0]:.3f}, {pos[1]:.3f}, {pos[2]:.3f}]"
        )

        constraint_msg = Int16MultiArray()
        constraint_msg.data = [50, 50, 50, 50, 50, 50]
        self.target_constraint_pub.publish(constraint_msg)

        target_eef_pose_msg = PoseStamped()
        target_eef_pose_msg.header.stamp = self.get_clock().now().to_msg()
        target_eef_pose_msg.header.frame_id = "base_link"
        target_eef_pose_msg.pose.position.x = pos[0]
        target_eef_pose_msg.pose.position.y = pos[1]
        target_eef_pose_msg.pose.position.z = pos[2]
        quat = pin.Quaternion(self.target_eef_pose.rotation)
        target_eef_pose_msg.pose.orientation.w = quat.w
        target_eef_pose_msg.pose.orientation.x = quat.x
        target_eef_pose_msg.pose.orientation.y = quat.y
        target_eef_pose_msg.pose.orientation.z = quat.z
        self.cmd_pub_R.publish(target_eef_pose_msg)
        self.gripper_controller_pub_R.publish(Float32(data=gripper_data))

def main(argv=None):
   
    
    rclpy.init()
    node = PoseSubscriber()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
