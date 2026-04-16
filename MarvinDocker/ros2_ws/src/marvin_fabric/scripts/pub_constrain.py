from rclpy.node import Node
import rclpy
from std_msgs.msg import Int16MultiArray


class WheelPublisher(Node):
    def __init__(self):
        super().__init__("wheel_publisher")

        self.publisher = self.create_publisher(
            Int16MultiArray,
            '/control/eef_constraint',
            10
        )
        self.publisher_speed = self.create_publisher(
            Int16MultiArray,
            '/control/speed_scale',
            10
        )

        timer_period = 1.0  # 1 Hz
        self.timer = self.create_timer(timer_period, self.timer_callback)

    def timer_callback(self):
        msg = Int16MultiArray()
        msg.data = [100, 100, 100, 100, 100, 100]
        self.publisher.publish(msg)
        self.get_logger().info(f"Publishing: {msg.data}")
        msg2 = Int16MultiArray()
        msg2.data = [100, 100]
        self.publisher_speed.publish(msg2)
        self.get_logger().info(f"Publishing speed scale: {msg2.data}")


def main(args=None):
    rclpy.init(args=args)
    node = WheelPublisher()
    rclpy.spin(node)
    node.destroy_node()
    rclpy.shutdown()


if __name__ == '__main__':
    main()
