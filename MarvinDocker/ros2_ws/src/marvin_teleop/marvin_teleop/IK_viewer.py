#!/usr/bin/env python3
import meshcat
import meshcat.geometry as mg
import numpy as np
import pinocchio as pin
import time
import math
from pinocchio.robot_wrapper import RobotWrapper
from pinocchio.visualize import MeshcatVisualizer
import os
import sys
import threading
from marvin_msgs.msg import Jointcmd
import rclpy
import rclpy.logging
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data as SensorDataQoS
from ament_index_python.packages import get_package_share_directory

class ikviewer:
    def __init__(self):
        self.node = rclpy.create_node('ik_viewer_node')
        package_path = get_package_share_directory('marvin_teleop')
        urdf_path = os.path.join(package_path, 'config', 'marvin_CCS_m6.urdf')
        self.robot = pin.RobotWrapper.BuildFromURDF(urdf_path)

        self.mixed_jointsToLockIDs =[]

        self.reduced_robot = self.robot.buildReducedRobot(
            list_of_joints_to_lock=self.mixed_jointsToLockIDs,
            reference_configuration=np.array([0] * self.robot.model.nq),
        )
        self.vis = MeshcatVisualizer(self.robot.model, self.robot.collision_model, self.robot.visual_model)
        self.vis.initViewer(open=False)
        self.vis.loadViewerModel("pinocchio")
        self.vis.displayFrames(True, frame_ids=[113, 114], axis_length=0.15, axis_width=5)
        self.vis.display(pin.neutral(self.robot.model))
        self.vis.displayFrames(True)
        self.positions_A = np.array([0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0])
        self.positions_B = np.array([0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0])

        self.node.create_subscription(
            Jointcmd,
            'control/ik_cmd_A',
            self.joint_cmd_callback_A,
            SensorDataQoS
        )
        self.node.create_subscription(
            Jointcmd,
            'control/ik_cmd_B',
            self.joint_cmd_callback_B,
            SensorDataQoS
        )


        self.vis_thread = threading.Thread(target=self.vis_thread)
        self.vis_thread.daemon = True  # Ensure the thread exits when the main program does
        self.vis_thread.start()
        
    
    def joint_cmd_callback_A(self, msg):
        if len(msg.positions) == 7:
            self.positions_A = np.array(msg.positions)
        
    def joint_cmd_callback_B(self, msg):
        if len(msg.positions) == 7:
            self.positions_B = np.array(msg.positions)
    def vis_thread(self):
        # Update the visualization with the current joint positions
        while rclpy.ok():
            q = pin.neutral(self.reduced_robot.model)
            q[:7] = self.positions_A  # Set the first 7 joints to positions
            q[7:14] = self.positions_B  # Set the next 7 joints
            # print(self.positions_B)
            self.vis.display(q)
            time.sleep(0.01)

    




if __name__ == "__main__":
    rclpy.init()
    viewer = ikviewer()
    # print("IK Viewer initialized with robot model:", viewer.reduced_robot.model.name)
    try:
        rclpy.spin(viewer.node)
    except KeyboardInterrupt:
        pass
    finally:
        viewer.node.destroy_node()
        rclpy.shutdown()
        # print("IK Viewer node shut down.")

    

    # You can add more functionality here, such as visualizing the robot or performing IK calculations.

