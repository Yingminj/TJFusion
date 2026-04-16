import rclpy
from rclpy.node import Node
from geometry_msgs.msg import Pose, PoseStamped, Quaternion, Point
import numpy as np
from fake_interface_pkg.msg import KeypointPose, KeypointPoseArray  # 替换为你自己的msg包
import time
class TestKeypointPublisher(Node):
    def __init__(self):
        super().__init__('test_keypoint_publisher')
        self.publisher_ = self.create_publisher(KeypointPoseArray, 'fusion_pose', 10)
        # self.timer = self.create_timer(1.0, self.timer_callback)  # 1秒发一次
        self.count = 0
        self.y_offset = 0.0
        self.timer_callback()

    def timer_callback(self):
        msg = KeypointPoseArray()
        
        
        motion_kp0 = KeypointPose()
        motion_kp0.name = "move1"
        motion_kp0.arm = "right"
        # 模拟轨迹两个点
        pose1 = Pose()
        pose1.position = Point(x=0.4, y=-0.2+self.y_offset, z=0.1)
        pose1.orientation = Quaternion(x=0.0, y=0.0, z=0.0, w=1.0)
        pose2 = Pose()
        pose2.position = Point(x=0.4, y=-0.2+self.y_offset, z=-0.18)
        pose2.orientation = Quaternion(x=0.0, y=0.0, z=0.0, w=1.0)
        pose3 = Pose()
        pose3.position = Point(x=0.4, y=-0.2+self.y_offset, z=0.0)
        pose3.orientation = Quaternion(x=0.0, y=0.0, z=0.0, w=1.0)
        pose4 = Pose()
        pose4.position = Point(x=0.5, y=-0.2+self.y_offset, z=0.0)
        pose4.orientation = Quaternion(x=0.0, y=0.0, z=0.0, w=1.0)

        motion_kp0.poses = [pose1, pose2, pose3, pose4]
        motion_kp0.time = [0.0, 0.30, 0.5, 1.0]
        motion_kp0.constraints = [0.0, 0.0, 100.0]
        motion_kp0.speed = 0.5
        motion_kp0.gripper_value = [0.0, 0.95, 0.8, 1.0]
        home_kp = KeypointPose()
        home_kp.name = "home"
        home_kp.arm = "right"
        home_kp.constraints = [100.0, 100.0, 100.0]
        home_kp.speed = 0.5
        home_kp.gripper_value = [0.0]
        msg.poses = [motion_kp0]

        self.publisher_.publish(msg)
        self.count += 1
        self.y_offset += 0.02
        print(self.y_offset)
        time.sleep(2.0)
        msg.poses = [home_kp]
        self.publisher_.publish(msg)
        self.get_logger().info('Published test KeypointPoseArray')
        if self.count>10:
            self.destroy_node()
    def destroy_node(self):
        self.get_logger().info('Destroying test KeypointPublisher')
        super().destroy_node()

def main(args=None):
    rclpy.init(args=args)
    node = TestKeypointPublisher()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    node.destroy_node()
    rclpy.shutdown()

if __name__ == '__main__':
    main()
