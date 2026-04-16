import rclpy
from rclpy.node import Node

from geometry_msgs.msg import PoseStamped
from std_msgs.msg import String, Bool

class PointExecutorFSM(Node):
    def __init__(self):
        super().__init__("point_executor_node")

        # 发布机械臂目标位姿
        self.pose_pub = self.create_publisher(PoseStamped, "/arm/target_pose", 10)
        self.eef_L_state_sub = self.create_subscription(Bool, "/arm/eef_state_L", self.eef_L_callback, 10)
        self.eef_R_state_sub = self.create_subscription(Bool, "/arm/eef_state_R", self.eef_R_callback, 10)

        # 发布夹爪指令
        self.gripper_pub = self.create_publisher(String, "/gripper/cmd", 10)

        # 状态机变量
        self.points = []
        self.index = 0
        self.state = "IDLE"

        # 10Hz timer
        self.timer = self.create_timer(0.1, self.update)

    # --------------------------------------------------------
    # 外部调用：开始任务
    # --------------------------------------------------------
    def start(self, object_name):
        self.points = self.get_child_points_world(object_name)
        self.index = 0
        self.state = "EXECUTE"
        self.get_logger().info(f"Start executing {len(self.points)} points.")

    # --------------------------------------------------------
    # timer 驱动状态机
    # --------------------------------------------------------
    def update(self):
        if self.state == "IDLE":
            return

        if self.state == "EXECUTE":

            if self.index >= len(self.points):
                self.get_logger().info("Task finished. Return to IDLE.")
                self.state = "IDLE"
                return

            point = self.points[self.index]
            done = self.execute_point(point)

            if done:
                self.index += 1

    # --------------------------------------------------------
    # 执行单个 point
    # --------------------------------------------------------
    def execute_point(self, point):

        target_pos = point["position"]
        target_ori = point["orientation"]
        target_gripper = point["gripper"]

        # 1. 发布位置姿态
        pose_msg = PoseStamped()
        pose_msg.header.stamp = self.get_clock().now().to_msg()
        pose_msg.header.frame_id = "world"

        pose_msg.pose.position.x = target_pos[0]
        pose_msg.pose.position.y = target_pos[1]
        pose_msg.pose.position.z = target_pos[2]

        pose_msg.pose.orientation.x = target_ori[0]
        pose_msg.pose.orientation.y = target_ori[1]
        pose_msg.pose.orientation.z = target_ori[2]
        pose_msg.pose.orientation.w = target_ori[3]

        self.pose_pub.publish(pose_msg)

        # 假设你的控制器会执行并告诉你是否到达
        reached = self.check_reached(target_pos)

        if not reached:
            return False  # 继续运动

        # 2. 夹爪操作
        if target_gripper in ["open", "close"]:
            cmd = String()
            cmd.data = target_gripper
            self.gripper_pub.publish(cmd)
            self.get_logger().info(f"Gripper: {target_gripper}")

        return True

    def eef_L_callback(self, msg):
        # 这里可以处理末端执行器状态反馈
        self.eef_L_state = msg.data
    def eef_R_callback(self, msg):
        # 这里可以处理末端执行器状态反馈
        self.eef_R_state = msg.data
    # --------------------------------------------------------
    # 判断机械臂是否到达目标（你可以替换为 TF 或 feedback）
    # --------------------------------------------------------
    def check_reached(self, target_pos, threshold=0.01):
        # TODO: Replace with your actual feedback
        # 简单版：直接返回 True（你后面可换成 feedback 判断）
        return True

    # --------------------------------------------------------
    # 从上层接口获取点（你已有此函数）
    # --------------------------------------------------------
    def get_child_points_world(self, object_name):
        # Example implementation
        # 这里你用你的实际逻辑替换
        return [
            {
                "position": [0.4, 0.0, 0.3],
                "orientation": [0, 0, 0, 1],
                "gripper": "open"
            },
            {
                "position": [0.4, 0.0, 0.1],
                "orientation": [0, 0, 0, 1],
                "gripper": "close"
            }
        ]


def main(args=None):
    rclpy.init(args=args)
    node = PointExecutorFSM()
    rclpy.spin(node)
    node.destroy_node()
    rclpy.shutdown()


if __name__ == "__main__":
    main()
