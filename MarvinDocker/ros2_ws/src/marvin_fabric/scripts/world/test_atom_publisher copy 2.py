import rclpy
from rclpy.node import Node
from geometry_msgs.msg import Pose, PoseStamped, Quaternion, Point
import numpy as np
from fake_interface_pkg.msg import KeypointPose, KeypointPoseArray  # 替换为你自己的msg包

class TestKeypointPublisher(Node):
    def __init__(self):
        super().__init__('test_keypoint_publisher')
        self.publisher_ = self.create_publisher(KeypointPoseArray, 'fusion_pose', 10)
        self.timer = self.create_timer(1.0, self.timer_callback)  # 1秒发一次

    def timer_callback(self):
        msg = KeypointPoseArray()
        
        
        motion_kp0 = KeypointPose()
        motion_kp0.name = "move1"
        motion_kp0.arm = "right"
        # 模拟轨迹两个点
        pose1 = Pose()
        pose1.position = Point(x=0.4, y=-0.2, z=0.1)
        pose1.orientation = Quaternion(x=0.0, y=0.0, z=0.0, w=1.0)
        pose2 = Pose()
        pose2.position = Point(x=0.4, y=-0.2, z=-0.18)
        pose2.orientation = Quaternion(x=0.0, y=0.0, z=0.0, w=1.0)
        pose3 = Pose()
        pose3.position = Point(x=0.4, y=-0.2, z=0.0)
        pose3.orientation = Quaternion(x=0.0, y=0.0, z=0.0, w=1.0)
        pose4 = Pose()
        pose4.position = Point(x=0.5, y=-0.2, z=0.0)
        pose4.orientation = Quaternion(x=0.0, y=0.0, z=0.0, w=1.0)

        motion_kp0.poses = [pose1, pose2, pose3, pose4]
        motion_kp0.time = [0.0, 0.30, 0.5, 1.0]
        motion_kp0.constraints = [0.0, 0.0, 100.0]
        motion_kp0.speed = 0.5
        motion_kp0.gripper_value = [0.0, 0.95, 0.8, 1.0]
        # 假设发送两个关键点：home 和 motion
        home_kp = KeypointPose()
        home_kp.name = "home"
        home_kp.arm = "right"
        home_kp.constraints = [100.0, 100.0, 100.0]
        home_kp.speed = 1.0
        home_kp.gripper_value = [0.0]

        motion_kp = KeypointPose()
        motion_kp.name = "move1"
        motion_kp.arm = "right"
        # 模拟轨迹两个点
        pose1 = Pose()
        pose1.position = Point(x=0.5, y=-0.2, z=0.0)
        pose1.orientation = Quaternion(x=0.0, y=0.0, z=0.0, w=1.0)
        pose2 = Pose()
        pose2.position = Point(x=0.7, y=-0.2, z=0.0)
        pose2.orientation = Quaternion(x=0.0, y=0.0, z=0.0, w=1.0)
        pose3 = Pose()
        pose3.position = Point(x=0.5, y=-0.2, z=0.0)
        pose3.orientation = Quaternion(x=0.0, y=0.0, z=0.0, w=1.0)
        pose4 = Pose()
        pose4.position = Point(x=0.7, y=-0.2, z=0.0)
        pose4.orientation = Quaternion(x=0.0, y=0.0, z=0.0, w=1.0)
        pose5 = Pose()
        pose5.position = Point(x=0.5, y=-0.2, z=0.0)
        pose5.orientation = Quaternion(x=0.0, y=0.0, z=0.0, w=1.0)
        pose6 = Pose()
        pose6.position = Point(x=0.7, y=-0.2, z=0.0)
        pose6.orientation = Quaternion(x=0.0, y=0.0, z=0.0, w=1.0)
        motion_kp.poses = [pose1, pose2, pose3, pose4, pose5,pose6]
        motion_kp.time = [0.0, 0.30, 0.5, 0.7, 0.9, 1.0]
        motion_kp.constraints = [0.0, 0.0, 100.0]
        motion_kp.speed = 1.0
        motion_kp.gripper_value = [0.0, 0.95, 1.0,0.5,0.3,0.0]

        msg.poses = [motion_kp0]

        self.publisher_.publish(msg)
        self.get_logger().info('Published test KeypointPoseArray')

def main(args=None):
    rclpy.init(args=args)
    node = TestKeypointPublisher()
    try:
        rclpy.spin_once(node)
    except KeyboardInterrupt:
        pass
    node.destroy_node()
    rclpy.shutdown()

if __name__ == '__main__':
    main()
