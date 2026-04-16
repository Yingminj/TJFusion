#!/usr/bin/env python3
import rclpy
from rclpy.node import Node
from geometry_msgs.msg import TransformStamped
import tf2_ros
import tkinter as tk
from math import radians
import numpy as np
import threading


def rpy_to_quaternion(roll, pitch, yaw):
    """Convert RPY to quaternion."""
    cy = np.cos(yaw * 0.5)
    sy = np.sin(yaw * 0.5)
    cp = np.cos(pitch * 0.5)
    sp = np.sin(pitch * 0.5)
    cr = np.cos(roll * 0.5)
    sr = np.sin(roll * 0.5)

    q = [
        cr * cp * cy + sr * sp * sy,  # x
        sr * cp * cy - cr * sp * sy,  # y
        cr * sp * cy + sr * cp * sy,  # z
        cr * cp * sy - sr * sp * cy,  # w
    ]
    return q


class StaticTFGUI(Node):
    def __init__(self):
        super().__init__("static_tf_gui")

        self.br = tf2_ros.TransformBroadcaster(self)

        # Current TF values
        self.tf_data = {
            "x": 0.0,
            "y": 0.0,
            "z": 0.0,
            "roll": 0.0,
            "pitch": 0.0,
            "yaw": 0.0
        }

        # Publish at 30 Hz
        self.timer = self.create_timer(0.033, self.publish_tf)

        # Start Tkinter UI thread
        self.start_tk_ui()

    def publish_tf(self):
        t = TransformStamped()
        t.header.stamp = self.get_clock().now().to_msg()
        t.header.frame_id = "base_link"
        t.child_frame_id = "camera_link"

        # Translation
        t.transform.translation.x = self.tf_data["x"]
        t.transform.translation.y = self.tf_data["y"]
        t.transform.translation.z = self.tf_data["z"]

        # Rotation (converted to quaternion)
        qx, qy, qz, qw = rpy_to_quaternion(
            self.tf_data["roll"],
            self.tf_data["pitch"],
            self.tf_data["yaw"]
        )
        t.transform.rotation.x = qx
        t.transform.rotation.y = qy
        t.transform.rotation.z = qz
        t.transform.rotation.w = qw

        self.br.sendTransform(t)

    def start_tk_ui(self):
        thread = threading.Thread(target=self.tk_thread, daemon=True)
        thread.start()

    def tk_thread(self):
        root = tk.Tk()
        root.title("TF2 Static Publisher GUI (base_link → camera_link)")

        sliders = {
            "x": (-1.0, 1.0),
            "y": (-1.0, 1.0),
            "z": (-1.0, 1.0),
            "roll": (-3.14, 3.14),
            "pitch": (-3.14, 3.14),
            "yaw": (-3.14, 3.14),
        }

        for i, (key, (vmin, vmax)) in enumerate(sliders.items()):
            tk.Label(root, text=key).grid(row=i, column=0)
            scale = tk.Scale(
                root,
                from_=vmin, to=vmax,
                resolution=0.001,
                orient=tk.HORIZONTAL,
                length=300,
                command=lambda val, k=key: self.update_value(k, float(val))
            )
            scale.grid(row=i, column=1)

        root.mainloop()

    def update_value(self, key, val):
        self.tf_data[key] = val


def main(args=None):
    rclpy.init(args=args)
    node = StaticTFGUI()
    rclpy.spin(node)
    node.destroy_node()
    rclpy.shutdown()


if __name__ == "__main__":
    main()
