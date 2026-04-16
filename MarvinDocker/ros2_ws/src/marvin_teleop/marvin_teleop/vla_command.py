#!/usr/bin/env python3
import numpy as np
import pinocchio as pin
import meshcat
import meshcat.geometry as mg
import time
import threading
import os
import math
import rclpy
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data as SensorDataQoS

from geometry_msgs.msg import PoseStamped, Twist
from pinocchio.visualize import MeshcatVisualizer
from ament_index_python.packages import get_package_share_directory






class EEFViewer(Node):
    def __init__(self):
        super().__init__("eef_viewer_node")

        # ================= Robot =================
        package_path = get_package_share_directory("marvin_teleop")
        urdf_path = os.path.join(package_path, "config", "marvin_CCS_m3.urdf")

        self.robot = pin.RobotWrapper.BuildFromURDF(urdf_path)
        self.model = self.robot.model
        self.data = self.robot.data

        # ⚠️ 改成你真实的 eef frame
        self.eef_name = "eef_A"
        self.eef_frame_id = self.model.getFrameId(self.eef_name)

        # ================= Meshcat =================
        self.vis = MeshcatVisualizer(
            self.model,
            self.robot.collision_model,
            self.robot.visual_model
        )
        self.vis.initViewer(open=False)
        self.vis.loadViewerModel("pinocchio")
        self.vis.display(pin.neutral(self.model))

        # 显示 eef frame
        self.vis.displayFrames(
            True,
            frame_ids=[self.eef_frame_id],
            axis_length=0.12,
            axis_width=4
        )

        # 目标 EEF frame（单独一个可视 marker）
        self.add_axis("eef_target", length=0.15)

        # ================= EEF Pose State =================
        self.current_eef_pose = None        # pin.SE3
        self.target_eef_pose = None         # pin.SE3

        # ================= ROS Subs =================
        self.create_subscription(
            PoseStamped,
            "/control/eef_pose_A",
            self.eef_pose_callback,
            SensorDataQoS
        )

        self.create_subscription(
            Twist,
            "/control/eef_action_A",
            self.eef_action_callback,
            SensorDataQoS
        )

        # ================= Thread =================
        self._running = True
        self.vis_thread_handle = threading.Thread(target=self.vis_thread)
        self.vis_thread_handle.daemon = True
        self.vis_thread_handle.start()

    # =====================================================
    # Callbacks
    # =====================================================
    def eef_pose_callback(self, msg: PoseStamped):
        """ 当前 EEF 绝对位姿 """
        p = msg.pose.position
        q = msg.pose.orientation

        quat = pin.Quaternion(q.w, q.x, q.y, q.z)
        quat.normalize()

        self.current_eef_pose = pin.SE3(
            quat.toRotationMatrix(),
            np.array([p.x, p.y, p.z])
        )

        # 初始化 target
        if self.target_eef_pose is None:
            self.target_eef_pose = self.current_eef_pose

    def eef_action_callback(self, msg: Twist):
        """ EEF 局部坐标系下的增量 """
        if self.target_eef_pose is None:
            return

        v = msg.linear
        w = msg.angular

        # se(3) twist
        delta = pin.Motion(
            np.array([v.x, v.y, v.z]),
            np.array([w.x, w.y, w.z])
        )

        # T_new = T_old * exp(delta)
        self.target_eef_pose = self.target_eef_pose * pin.exp6(delta)

    # =====================================================
    def vis_thread(self):
        rate = 0.01

        while rclpy.ok() and self._running:
            # 显示 robot（静态或 joint 驱动都行）
            self.vis.display(pin.neutral(self.model))

            # 显示 target frame
            if self.target_eef_pose is not None:
                self.vis.viewer["eef_target"].set_transform(
                    self.target_eef_pose.homogeneous
                )

            time.sleep(rate)

    # =====================================================
    def shutdown(self):
        self._running = False
        self.destroy_node()

    def add_axis(self, name, length=0.15, radius=0.005):
        """Create an XYZ axis in Meshcat (compatible with all versions)"""
        self.vis.viewer[name]["x"].set_object(
            mg.Cylinder(length, radius),
            mg.MeshLambertMaterial(color=0xff0000)
        )
        self.vis.viewer[name]["y"].set_object(
            mg.Cylinder(length, radius),
            mg.MeshLambertMaterial(color=0x00ff00)
        )
        self.vis.viewer[name]["z"].set_object(
            mg.Cylinder(length, radius),
            mg.MeshLambertMaterial(color=0x0000ff)
        )

        # X axis
        self.vis.viewer[name]["x"].set_transform(
            pin.SE3(
                pin.rpy.rpyToMatrix(0, math.pi / 2, 0),
                np.array([length / 2, 0, 0])
            ).homogeneous
        )

        # Y axis
        self.vis.viewer[name]["y"].set_transform(
            pin.SE3(
                pin.rpy.rpyToMatrix(-math.pi / 2, 0, 0),
                np.array([0, length / 2, 0])
            ).homogeneous
        )

        # Z axis
        self.vis.viewer[name]["z"].set_transform(
            pin.SE3(
                np.eye(3),
                np.array([0, 0, length / 2])
            ).homogeneous
        )


# =========================================================
def main():
    rclpy.init()
    node = EEFViewer()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.shutdown()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
