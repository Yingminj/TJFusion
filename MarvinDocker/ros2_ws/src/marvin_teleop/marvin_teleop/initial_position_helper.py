#!/usr/bin/env python3

import time
import threading
import numpy as np

import rclpy
from rclpy.node import Node
from marvin_msgs.msg import Jointfeedback
from rclpy.qos import qos_profile_sensor_data as SensorDataQoS
from rich.console import Console
from rich.table import Table
from rich.live import Live

# ==============================
# IK Viewer Node
# ==============================
class IKViewer(Node):
    def __init__(self):
        super().__init__('ik_viewer_node')

        # --------------------------
        # Joint data
        # --------------------------
        self.positions_A = np.zeros(7)
        self.positions_B = np.zeros(7)

        self.declare_parameter(
            'target_A',
            [90.0, -90.0, -90.0, -90.0, 0.0, 0.0, 0.0]
        )

        self.declare_parameter(
            'target_B',
            [-90.0, -90.0, 90.0, -90.0, 0.0, 0.0, 0.0]
        )

        # 读取初始值
        self.target_A = np.array(
            self.get_parameter('target_A').value,
            dtype=float
        )

        self.target_B = np.array(
            self.get_parameter('target_B').value,
            dtype=float
        )
        # --------------------------
        # ROS subscriptions
        # --------------------------
        self.create_subscription(
            Jointfeedback,
            '/info/joint_feedback',
            self.joint_fbk_callback,
            SensorDataQoS
        )

        # --------------------------
        # Terminal UI
        # --------------------------
        self.console = Console()
        self.running = True

        self.display_thread = threading.Thread(
            target=self.display_loop,
            daemon=True
        )
        self.display_thread.start()

        self.get_logger().info("IK Viewer started (terminal dashboard mode)")

    # ==============================
    # ROS callbacks
    # ==============================
    def joint_fbk_callback(self, msg):
        if len(msg.positions) == 14:
            self.positions_A = np.array(msg.positions[:7]*180.0/np.pi)
            self.positions_B = np.array(msg.positions[7:]*180.0/np.pi)

    # ==============================
    # Terminal display loop
    # ==============================
    def display_loop(self):
        with Live(self.make_layout(), refresh_per_second=10, console=self.console) as live:
            while self.running:
                live.update(self.make_layout())
                time.sleep(0.1)

    # ==============================
    # Build tables
    # ==============================
    def make_layout(self):
        table_A = self.make_table(
            title="Arm A Joint Motion",
            current=self.positions_A,
            target=self.target_A
        )

        table_B = self.make_table(
            title="Arm B Joint Motion",
            current=self.positions_B,
            target=self.target_B
        )

        layout = Table.grid(expand=True)
        layout.add_row(table_A)
        layout.add_row(table_B)

        return layout

    def make_table(self, title, current, target):
        table = Table(title=title, expand=True)

        table.add_column("Joint", justify="center")
        # table.add_column("Current(rad)", justify="right")
        # table.add_column("Target(rad)", justify="right")
        table.add_column("Δ(rad)", justify="right")
        table.add_column("Dir", justify="center")
        table.add_column("Magnitude", justify="left")

        for i in range(7):
            cur = current[i]
            tgt = target[i]
            delta = tgt - cur

            # Direction & color
            if abs(delta) < 5.0:
                arrow = "[green]=[/green]"
                color = "green"
            elif delta > 0:
                arrow = "[red]↑[/red]"
                color = "red"
            else:
                arrow = "[blue]↓[/blue]"
                color = "blue"

            # Magnitude bar
            bar_len = int(min(abs(delta) / 90.0, 1.0) * 20)
            bar = "█" * bar_len

            table.add_row(
                f"J{i+1}",
                # f"{cur:+.3f}",
                # f"{tgt:+.3f}",
                f"{delta:+.3f}",
                arrow,
                f"[{color}]{bar}[/{color}]"
            )

        return table

    # ==============================
    # Shutdown
    # ==============================
    def destroy_node(self):
        self.running = False
        super().destroy_node()


# ==============================
# main
# ==============================
def main():
    rclpy.init()
    node = IKViewer()

    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
