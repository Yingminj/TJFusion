#!/usr/bin/env python3
import rclpy
from rclpy.node import Node
from geometry_msgs.msg import TransformStamped
from tf2_ros import TransformBroadcaster
import math
import time


class DummyTFBroadcaster(Node):
    def __init__(self):
        super().__init__('dummy_tf_broadcaster')

        self.br = TransformBroadcaster(self)

        # define objects and initial poses
        self.objects = {
            "mug": {
                "parent": "base_link",
                "xyz": [0.3, 0.0, -0.1],
                "rpy": [0.0, 0.0,  math.radians(90)],
            },
            "drawer": {
                "parent": "base_link",
                "xyz": [0.7, 0.3, 0.0],
                "rpy": [0.0, 0.0, math.radians(180)],
            }
        }

        # broadcast at 30 Hz
        timer_period = 1.0 / 60.0
        self.timer = self.create_timer(timer_period, self.broadcast_objects)

        self.get_logger().info("Dummy TF Broadcaster started")

    def broadcast_objects(self):
        now = self.get_clock().now()

        for name, data in self.objects.items():
            t = TransformStamped()

            t.header.stamp = now.to_msg()
            t.header.frame_id = data["parent"]
            t.child_frame_id = name

            # position
            t.transform.translation.x = data["xyz"][0]
            t.transform.translation.y = data["xyz"][1]
            t.transform.translation.z = data["xyz"][2]

            # convert RPY to quaternion
            q = self.rpy_to_quaternion(*data["rpy"])
            t.transform.rotation.x = q[0]
            t.transform.rotation.y = q[1]
            t.transform.rotation.z = q[2]
            t.transform.rotation.w = q[3]

            # publish
            self.br.sendTransform(t)

    @staticmethod
    def rpy_to_quaternion(roll, pitch, yaw):
        cy = math.cos(yaw * 0.5)
        sy = math.sin(yaw * 0.5)
        cp = math.cos(pitch * 0.5)
        sp = math.sin(pitch * 0.5)
        cr = math.cos(roll * 0.5)
        sr = math.sin(roll * 0.5)

        qx = sr * cp * cy - cr * sp * sy
        qy = cr * sp * cy + sr * cp * sy
        qz = cr * cp * sy - sr * sp * cy
        qw = cr * cp * cy + sr * sp * sy

        return [qx, qy, qz, qw]


def main(args=None):
    rclpy.init(args=args)
    node = DummyTFBroadcaster()
    rclpy.spin(node)
    node.destroy_node()
    rclpy.shutdown()


if __name__ == '__main__':
    main()
