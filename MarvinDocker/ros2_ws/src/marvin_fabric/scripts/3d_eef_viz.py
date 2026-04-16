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
from marvin_msgs.msg import Jointfeedback
import rclpy
import rclpy.logging
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data as SensorDataQoS
from ament_index_python.packages import get_package_share_directory

class ikviewer:
    def __init__(self):
        self.node = rclpy.create_node('ik_viewer_node')
        package_path = get_package_share_directory('marvin_ros_control')
        urdf_path = os.path.join(package_path, 'config', 'marvin_CCS_m3.urdf')
        
        self.robot = pin.RobotWrapper.BuildFromURDF(urdf_path)
        self.mixed_jointsToLockIDs = []
        self.reduced_robot = self.robot.buildReducedRobot(
            list_of_joints_to_lock=self.mixed_jointsToLockIDs,
            reference_configuration=np.array([0] * self.robot.model.nq),
        )
        
        self.vis = MeshcatVisualizer(self.robot.model, self.robot.collision_model, self.robot.visual_model)
        self.vis.initViewer(open=False)
        self.vis.loadViewerModel("pinocchio")
        
        # Get end-effector frame IDs by name
        self.eef_frame_name_left = "Link7_L"
        self.eef_frame_name_right = "Link7_R"
        
        try:
            self.eef_left_id = self.robot.model.getFrameId(self.eef_frame_name_left)
            self.eef_right_id = self.robot.model.getFrameId(self.eef_frame_name_right)
            print(f"Left EEF Frame ID: {self.eef_left_id}")
            print(f"Right EEF Frame ID: {self.eef_right_id}")
        except Exception as e:
            print(f"Error getting frame IDs: {e}")
            self.eef_left_id = None
            self.eef_right_id = None
        
        # Display the end-effector frames
        if self.eef_left_id is not None and self.eef_right_id is not None:
            self.vis.displayFrames(True, frame_ids=[self.eef_left_id, self.eef_right_id], 
                                  axis_length=0.15, axis_width=5)
        
        self.vis.display(pin.neutral(self.robot.model))
        
        # Initialize joint positions (14 joints total)
        self.joint_positions = np.array([0.0] * 14)
        
        # Path recording variables
        self.recording_left = False
        self.recording_right = False
        self.path_left = []
        self.path_right = []
        self.last_record_time_left = None
        self.last_record_time_right = None
        self.record_interval = 0.5  # seconds
        
        # Total distance tracking
        self.total_distance_left = 0.0
        self.total_distance_right = 0.0
        
        # Subscribe to single joint feedback (length 14)
        self.node.create_subscription(
            Jointfeedback,
            '/marvin/joint_feedback',
            self.joint_feedback_callback,
            SensorDataQoS
        )
        
        # Create markers in MeshCat for end-effector visualization
        self.setup_eef_markers()
        
        # Setup control buttons
        self.setup_control_buttons()
        
        # Start visualization thread
        self.vis_thread = threading.Thread(target=self.vis_loop)
        self.vis_thread.daemon = True
        self.vis_thread.start()
    
    def setup_control_buttons(self):
        """Setup control buttons in MeshCat"""
        # Add buttons to MeshCat viewer
        self.vis.viewer["Controls"].set_property("visible", True)
        
        # Note: MeshCat doesn't have native button support, so we'll use keyboard shortcuts
        # Print instructions for the user
        print("\n" + "="*60)
        print("PATH RECORDING CONTROLS:")
        print("="*60)
        print("Left Arm:")
        print("  - Press '1' to START/STOP recording left arm path")
        print("  - Press '2' to CLEAR left arm path")
        print("\nRight Arm:")
        print("  - Press '3' to START/STOP recording right arm path")
        print("  - Press '4' to CLEAR right arm path")
        print("\nBoth Arms:")
        print("  - Press '5' to CLEAR both paths")
        print("="*60 + "\n")
        
        # Start keyboard listener thread
        self.keyboard_thread = threading.Thread(target=self.keyboard_listener)
        self.keyboard_thread.daemon = True
        self.keyboard_thread.start()
    
    def keyboard_listener(self):
        """Listen for keyboard input to control recording"""
        print("Keyboard listener started. Ready for commands...")
        while rclpy.ok():
            try:
                key = input()
                if key == '1':
                    self.toggle_recording_left()
                elif key == '2':
                    self.clear_path_left()
                elif key == '3':
                    self.toggle_recording_right()
                elif key == '4':
                    self.clear_path_right()
                elif key == '5':
                    self.clear_all_paths()
            except:
                break
    
    def toggle_recording_left(self):
        """Toggle recording for left arm"""
        self.recording_left = not self.recording_left
        if self.recording_left:
            print("🔴 Recording LEFT arm path...")
            self.last_record_time_left = time.time()
            self.total_distance_left = 0.0
        else:
            print(f"⏹️  Stopped recording LEFT arm. Total distance: {self.total_distance_left:.4f} m")
            print(f"   Total points recorded: {len(self.path_left)}")
    
    def toggle_recording_right(self):
        """Toggle recording for right arm"""
        self.recording_right = not self.recording_right
        if self.recording_right:
            print("🔴 Recording RIGHT arm path...")
            self.last_record_time_right = time.time()
            self.total_distance_right = 0.0
        else:
            print(f"⏹️  Stopped recording RIGHT arm. Total distance: {self.total_distance_right:.4f} m")
            print(f"   Total points recorded: {len(self.path_right)}")
    
    def clear_path_left(self):
        """Clear left arm path"""
        self.path_left = []
        self.total_distance_left = 0.0
        self.recording_left = False
        self.clear_path_visualization("left")
        print("🗑️  Cleared LEFT arm path")
    
    def clear_path_right(self):
        """Clear right arm path"""
        self.path_right = []
        self.total_distance_right = 0.0
        self.recording_right = False
        self.clear_path_visualization("right")
        print("🗑️  Cleared RIGHT arm path")
    
    def clear_all_paths(self):
        """Clear both paths"""
        self.clear_path_left()
        self.clear_path_right()
        print("🗑️  Cleared ALL paths")
    
    def record_path_point(self, position, path_list, last_time, arm_name):
        """Record a point in the path if enough time has elapsed"""
        current_time = time.time()
        
        if last_time is None or (current_time - last_time) >= self.record_interval:
            path_list.append(position.copy())
            
            # Calculate distance from previous point
            if len(path_list) > 1:
                prev_point = path_list[-2]
                curr_point = path_list[-1]
                distance = np.linalg.norm(curr_point - prev_point)
                
                if arm_name == "left":
                    self.total_distance_left += distance
                    total_dist = self.total_distance_left
                else:
                    self.total_distance_right += distance
                    total_dist = self.total_distance_right
                
                print(f"📍 {arm_name.upper()} point {len(path_list)}: "
                      f"pos=[{curr_point[0]:.3f}, {curr_point[1]:.3f}, {curr_point[2]:.3f}], "
                      f"segment={distance:.4f}m, total={total_dist:.4f}m")
            else:
                print(f"📍 {arm_name.upper()} starting point: "
                      f"[{position[0]:.3f}, {position[1]:.3f}, {position[2]:.3f}]")
            
            return current_time
        
        return last_time
    
    def visualize_path(self, path, color, name):
        """Visualize recorded path as line segments and points"""
        if len(path) < 2:
            return
        
        # Create line segments connecting points
        vertices = np.array(path).T
        
        # Draw path line
        self.vis.viewer[f"path_{name}"]["line"].set_object(
            mg.Line(
                mg.PointsGeometry(vertices),
                mg.LineBasicMaterial(color=color, linewidth=3)
            )
        )
        
        # Draw points along the path
        for i, point in enumerate(path):
            transform = np.eye(4)
            transform[:3, 3] = point
            self.vis.viewer[f"path_{name}"][f"point_{i}"].set_object(
                mg.Sphere(0.01),
                mg.MeshLambertMaterial(color=color, opacity=0.8)
            )
            self.vis.viewer[f"path_{name}"][f"point_{i}"].set_transform(transform)
    
    def clear_path_visualization(self, name):
        """Clear path visualization"""
        self.vis.viewer[f"path_{name}"].delete()
    
    def setup_eef_markers(self):
        """Create enhanced markers for end-effector positions"""
        
        # Left arm marker group
        left_group = self.vis.viewer["eef_marker_left"]
        
        # Outer transparent sphere (red)
        left_group["outer_sphere"].set_object(
            mg.Sphere(0.04),
            mg.MeshLambertMaterial(color=0xff0000, opacity=0.3, transparent=True)
        )
        
        # Inner solid sphere (darker red)
        left_group["inner_sphere"].set_object(
            mg.Sphere(0.02),
            mg.MeshLambertMaterial(color=0xcc0000, opacity=1.0)
        )
        
        # Coordinate frame axes for left
        left_group["frame"].set_object(
            self.create_coordinate_frame(scale=0.08)
        )
        
        # Right arm marker group
        right_group = self.vis.viewer["eef_marker_right"]
        
        # Outer transparent sphere (blue)
        right_group["outer_sphere"].set_object(
            mg.Sphere(0.04),
            mg.MeshLambertMaterial(color=0x0000ff, opacity=0.3, transparent=True)
        )
        
        # Inner solid sphere (darker blue)
        right_group["inner_sphere"].set_object(
            mg.Sphere(0.02),
            mg.MeshLambertMaterial(color=0x0000cc, opacity=1.0)
        )
        
        # Coordinate frame axes for right
        right_group["frame"].set_object(
            self.create_coordinate_frame(scale=0.08)
        )
    
    def create_coordinate_frame(self, scale=0.1):
        """Create a coordinate frame with colored axes"""
        vertices = np.array([
            # X axis (red)
            [0, 0, 0], [scale, 0, 0],
            # Y axis (green)
            [0, 0, 0], [0, scale, 0],
            # Z axis (blue)
            [0, 0, 0], [0, 0, scale]
        ]).T
        
        # Create line segments
        lines = mg.LineSegments(
            mg.PointsGeometry(vertices),
            mg.LineBasicMaterial(
                linewidth=3,
                vertexColors=True
            )
        )
        return lines
    
    def joint_feedback_callback(self, msg):
        """Callback for joint feedback (14 joints)"""
        if len(msg.positions) == 14:
            self.joint_positions = np.array(msg.positions)
    
    def update_eef_markers_from_fk(self, q):
        """Update marker positions based on forward kinematics"""
        if self.eef_left_id is None or self.eef_right_id is None:
            return
        
        # Compute forward kinematics
        pin.framesForwardKinematics(self.robot.model, self.robot.data, q)
        
        # Get left end-effector pose
        left_transform = self.robot.data.oMf[self.eef_left_id]
        left_matrix = left_transform.homogeneous
        left_position = left_transform.translation
        
        # Update all left marker components with the same transform
        self.vis.viewer["eef_marker_left"]["outer_sphere"].set_transform(left_matrix)
        self.vis.viewer["eef_marker_left"]["inner_sphere"].set_transform(left_matrix)
        self.vis.viewer["eef_marker_left"]["frame"].set_transform(left_matrix)
        
        # Record left path if recording is active
        if self.recording_left:
            self.last_record_time_left = self.record_path_point(
                left_position, 
                self.path_left, 
                self.last_record_time_left, 
                "left"
            )
        
        # Get right end-effector pose
        right_transform = self.robot.data.oMf[self.eef_right_id]
        right_matrix = right_transform.homogeneous
        right_position = right_transform.translation
        
        # Update all right marker components with the same transform
        self.vis.viewer["eef_marker_right"]["outer_sphere"].set_transform(right_matrix)
        self.vis.viewer["eef_marker_right"]["inner_sphere"].set_transform(right_matrix)
        self.vis.viewer["eef_marker_right"]["frame"].set_transform(right_matrix)
        
        # Record right path if recording is active
        if self.recording_right:
            self.last_record_time_right = self.record_path_point(
                right_position, 
                self.path_right, 
                self.last_record_time_right, 
                "right"
            )
        
        # Visualize paths
        if len(self.path_left) >= 2:
            self.visualize_path(self.path_left, 0xff0000, "left")
        if len(self.path_right) >= 2:
            self.visualize_path(self.path_right, 0x0000ff, "right")
    
    def vis_loop(self):
        """Main visualization loop"""
        while rclpy.ok():
            # Update robot configuration with all 14 joints
            q = pin.neutral(self.reduced_robot.model)
            q[:14] = self.joint_positions
            
            # Display robot
            self.vis.display(q)
            
            # Update end-effector markers from forward kinematics
            self.update_eef_markers_from_fk(q)
            
            time.sleep(0.01)

if __name__ == "__main__":
    rclpy.init()
    viewer = ikviewer()
    
    try:
        rclpy.spin(viewer.node)
    except KeyboardInterrupt:
        pass
    finally:
        viewer.node.destroy_node()
        rclpy.shutdown()