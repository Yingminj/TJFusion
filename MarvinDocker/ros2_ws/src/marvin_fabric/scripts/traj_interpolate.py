#!/usr/bin/env python3
import rclpy
from rclpy.node import Node

import numpy as np
from scipy.interpolate import CubicSpline
from scipy.spatial.transform import Rotation as R, Slerp

from geometry_msgs.msg import PoseArray
from visualization_msgs.msg import Marker, MarkerArray
from geometry_msgs.msg import Point

FRAME_ID = "base_link"


class SmoothTrajectoryMarker(Node):
    def __init__(self):
        super().__init__("smooth_traj_from_posearray")

        # Subscribers & Publishers
        self.sub = self.create_subscription(
            PoseArray,
            "/target_pose_array",
            self.pose_array_callback,
            10,
        )
        self.pub = self.create_publisher(
            MarkerArray,
            "/smooth_traj_markers",
            10
        )

        self.have_spline = False
        self.timer = self.create_timer(0.1, self.publish_markers)

    # ----------------------------------------------------------------------
    # Receive PoseArray and build spline + slerp
    # ----------------------------------------------------------------------
    def pose_array_callback(self, msg: PoseArray):
        N = len(msg.poses)
        if N < 2:
            self.get_logger().warn("PoseArray has < 2 poses, skipping")
            return

        self.get_logger().info(f"Received PoseArray with {N} poses")

        # Extract positions & quaternions
        pos = []
        quat = []
        for p in msg.poses:
            pos.append([p.position.x, p.position.y, p.position.z])
            quat.append([p.orientation.x, p.orientation.y, p.orientation.z, p.orientation.w])

        pos = np.array(pos)
        quat = np.array(quat)

        # Define time stamps for waypoints
        t = np.linspace(0, N - 1, N)

        # Save
        self.t = t
        self.pos_pts = pos
        self.quat_pts = quat

        # Position splines (x,y,z)
        self.splines = [
            CubicSpline(t, self.pos_pts[:, i], bc_type="natural")
            for i in range(3)
        ]

        # Orientation slerp
        rotations = R.from_quat(self.quat_pts)
        self.slerp = Slerp(t, rotations)

        self.have_spline = True

    # Helpers
    def pos(self, tq):
        return np.array([s(tq) for s in self.splines])

    def quat(self, tq):
        return self.slerp(tq).as_quat()

    # ----------------------------------------------------------------------
    # Publish marker array
    # ----------------------------------------------------------------------
    def publish_markers(self):
        if not self.have_spline:
            return

        ts = np.linspace(self.t[0], self.t[-1], 200)
        marker_array = MarkerArray()

        # Line strip marker
        line = Marker()
        line.header.frame_id = FRAME_ID
        line.id = 0
        line.type = Marker.LINE_STRIP
        line.action = Marker.ADD
        line.scale.x = 0.01
        line.color.a = 1.0

        for tt in ts:
            p = self.pos(tt)
            line.points.append(Point(x=float(p[0]), y=float(p[1]), z=float(p[2])))

        marker_array.markers.append(line)

        # Arrow markers for orientations
        arrow_id = 1
        for tt in ts[::10]:  # downsample
            p = self.pos(tt)
            q = self.quat(tt)

            arr = Marker()
            arr.header.frame_id = FRAME_ID
            arr.id = arrow_id
            arr.type = Marker.ARROW
            arr.action = Marker.ADD

            arr.pose.position.x = float(p[0])
            arr.pose.position.y = float(p[1])
            arr.pose.position.z = float(p[2])

            arr.pose.orientation.x = float(q[0])
            arr.pose.orientation.y = float(q[1])
            arr.pose.orientation.z = float(q[2])
            arr.pose.orientation.w = float(q[3])

            arr.scale.x = 0.07  # shaft length
            arr.scale.y = 0.015
            arr.scale.z = 0.015
            arr.color.r = 1.0
            arr.color.a = 1.0

            marker_array.markers.append(arr)
            arrow_id += 1

        self.pub.publish(marker_array)


def main(args=None):
    rclpy.init(args=args)
    node = SmoothTrajectoryMarker()
    rclpy.spin(node)
    rclpy.shutdown()


if __name__ == "__main__":
    main()
