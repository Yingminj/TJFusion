#!/usr/bin/env python3
import rclpy
from rclpy.node import Node
from std_msgs.msg import Float32
import tkinter as tk
from threading import Thread

class SliderPublisher(Node):
    def __init__(self):
        super().__init__('slider_publisher')
        self.publisher_ = self.create_publisher(Float32, '/control/gripperValueL', 10)

    def publish_value(self, value: float):
        msg = Float32()
        msg.data = float(value)
        self.publisher_.publish(msg)
        self.get_logger().info(f"Published: {msg.data:.2f}")


class TkinterGUI:
    def __init__(self, ros_node: SliderPublisher):
        self.node = ros_node
        self.root = tk.Tk()
        self.root.title("ROS2 Slider Publisher")

        # Slider 0 → 1, step size 0.01
        self.slider = tk.Scale(
            self.root,
            from_=0.0,
            to=1.0,
            resolution=0.01,
            orient=tk.HORIZONTAL,
            length=300,
            label="Slider Value",
            command=self.on_slider_change
        )
        self.slider.pack(padx=20, pady=20)

        # Label to show current published value
        self.value_label = tk.Label(self.root, text="Current Value: 0.00")
        self.value_label.pack(pady=10)

    def on_slider_change(self, val):
        self.node.publish_value(val)
        self.value_label.config(text=f"Current Value: {float(val):.2f}")

    def run(self):
        self.root.mainloop()


def ros_spin(node):
    rclpy.spin(node)


def main():
    rclpy.init()
    node = SliderPublisher()

    # Run ROS2 spin in a background thread
    ros_thread = Thread(target=ros_spin, args=(node,), daemon=True)
    ros_thread.start()

    # Run Tkinter GUI
    gui = TkinterGUI(node)
    gui.run()

    node.destroy_node()
    rclpy.shutdown()


if __name__ == "__main__":
    main()
