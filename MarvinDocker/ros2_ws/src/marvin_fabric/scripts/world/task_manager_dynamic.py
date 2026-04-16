import rclpy
from rclpy.node import Node
from visualization_msgs.msg import Marker, MarkerArray
import yaml
import os
from std_msgs.msg import Int16MultiArray, Float32
from geometry_msgs.msg import PoseStamped
import numpy as np
from std_srvs.srv import Trigger
from rclpy.executors import MultiThreadedExecutor
from fake_interface_pkg.msg import KeypointPose,KeypointPoseArray
# from marvin_msgs.msg import KeypointPose,KeypointPoseArray
from scipy.interpolate import CubicSpline,BSpline,make_interp_spline
from scipy.spatial.transform import Rotation as R, Slerp
from scipy.interpolate import PchipInterpolator
from scipy.interpolate import Akima1DInterpolator
class KeyPoint:
    def __init__(self, name, type, arm, position, orientation, constraints, speed):
        self.name = name
        self.type = type # could be "motion" or "gripper" or "home"
        self.arm = arm
        self.position = position
        self.orientation = orientation
        self.constraints = constraints
        self.speed = speed


class AtomicAction:
    def __init__(self, name, type, arm, positions, orientations, constraints, speed, gripper_values=None):
        self.name = name
        self.type = type # could be "motion" or "gripper" or "home"
        self.arm = arm
        self.positions = positions
        self.orientations = orientations
        self.constraints = constraints
        self.gripper_values = gripper_values
        self.time_out = 5.0
        self.speed = speed

class KeypointMarkerPublisher(Node):
    def __init__(self):
        super().__init__("keypoint_marker_publisher")

        self.pub = self.create_publisher(MarkerArray, "keypoint_markers", 10)
        self.trajectory_marker_pub = self.create_publisher(MarkerArray, "trajectory_markers", 10)
        self.target_pub_L = self.create_publisher(PoseStamped, "control/target_poseL", 10)
        self.target_pub_R = self.create_publisher(PoseStamped, "control/target_poseR", 10)
        self.target_constraint_pub = self.create_publisher(Int16MultiArray, "control/eef_constraint", 10)
        self.speed_scale_pub = self.create_publisher(Int16MultiArray, "control/speed_scale", 10)
        self.eef_pose_sub_L = self.create_subscription(PoseStamped, "info/eef_left", self.eef_L_pose_callback, 10)
        self.eef_pose_sub_R = self.create_subscription(PoseStamped, "info/eef_right", self.eef_R_pose_callback, 10)
        self.gripper_controller_pub_L = self.create_publisher(Float32, 'control/gripperValueL', 10)
        self.gripper_controller_pub_R = self.create_publisher(Float32, 'control/gripperValueR', 10)
        
        self.sub_ready = self.create_subscription( Int16MultiArray,"/arm/eef_state", self.ready_callback, 10)
        self.gohome_srv_L = self.create_client(Trigger, "/reset_left_arm")
        self.gohome_srv_R = self.create_client(Trigger, "/reset_right_arm")
        self.run_service = self.create_service(Trigger, "/start_task_execution", self.start_task_callback)
        self.task_sub = self.create_subscription(KeypointPoseArray, "/fusion_pose", self.task_callback, 10)
        self.timer = self.create_timer(0.05, self.timer_cbk)
        self.eef_ready_flag = [1,1]  # left, right
        
        self.get_logger().info("Keypoint marker publisher started.")
        # self.action_len = 0
        self.task = []
        
        self.eef_pos_L = (0.0, 0.0, 0.0)
        self.eef_pos_R = (0.0, 0.0, 0.0)
        self.time_out = 10.0
        self.time = self.get_clock().now()
        self.constraint_msg = Int16MultiArray()
        self.constraint_msg.data = [1, 1, 1, 1, 1, 1]
        # self.get_points()
        # self.task_callback_test()

    def ready_callback(self, msg):
        self.eef_ready_flag[0] = msg.data[0]
        self.eef_ready_flag[1] = msg.data[1]
        # print(f"EEF ready state updated: {self.eef_ready_flag}")
    def start_task_callback(self, request, response):
        self.get_logger().info("Starting task execution.")
        self.get_points()
        print(f"Total keypoints loaded: {len(self.task)}")
        for kp in self.task:
            print(f"Keypoint: {kp.name}, Position: {kp.position}, Orientation: {kp.orientation}, Constraints: {kp.constraints}")
        # self.action_len = len(self.task)
        response.success = True
        response.message = "Task execution started."
        return response
    
    def task_callback(self, msg: KeypointPoseArray):
        kp: KeypointPose
        self.time =   self.get_clock().now()
        for kp in msg.poses:
            name = kp.name
            # arm = kp.get("arm", "left")
            arm = kp.arm
            # if name.startswith("gripper"):
            #     px = kp.gripper_value
            #     Key = AtomicAction(name, "gripper", arm, [px, 0 , 0], [0 ,0, 0, 0], [0,  0, 0],0)
                # continue
            if name == "home":
                Key = AtomicAction(name, "home", arm, [0.0, 0.0, 0.0], [0, 0, 0, 1], [1, 1, 1], 0.8)
            else:
                poses = kp.poses
                # px, py, pz = kp["position"]
                times = kp.time

                if len(poses) >1:
                    # Extract positions & quaternions
                    N = len(poses)
                    pos = []
                    quat = []
                    for p in poses:
                        pos.append(np.asarray([p.position.x, p.position.y, p.position.z]))
                        quat.append(np.asarray([p.orientation.x, p.orientation.y, p.orientation.z, p.orientation.w]))

                    pos = np.array(pos)
                    quat = np.array(quat)
                    gripper_value = np.array(kp.gripper_value)

                    # Define time stamps for waypoints
                    # t = np.linspace(0.0, 1.0, N)
                    t = np.asarray(times)
                    t_gripper = np.asarray(times)  # Normalize to [0, 1]
                    speed_scale = (1.2 - kp.speed)*2.0
                    num_pts = int(20 * N * speed_scale)
                    
                    # Save
                    ts = np.linspace(0.0, times[-1], num_pts)  # downsample to 10 points
                    # ts_gripper = np.linspace(t_gripper[0], t_gripper[-1], 20*N)  # downsample to 10 points
                    self.pos_pts = pos
                    self.quat_pts = quat
                    k=N-1
                    # Position splines (x,y,z)
                    self.splines = [
                        # make_interp_spline(t, self.pos_pts[:, i], k=3)
                        # PchipInterpolator(t, self.pos_pts[:, i]) for i in range(3)
                        Akima1DInterpolator(t, self.pos_pts[:, i],method='makima')
                        for i in range(3)
                    ]
                    self.gripperSplines = [
                        # CubicSpline(t_gripper, gripper_value, bc_type="natural")
                        Akima1DInterpolator(t_gripper, gripper_value,method='makima')
                        
                    ]

                    # Orientation slerp
                    rotations = R.from_quat(self.quat_pts)
                    self.slerp = Slerp(t, rotations)
                    p_list = []
                    q_list = []
                    g_list = []
                    for tt in ts:  # downsample
                        p = self.pos(tt)
                        q = self.quat(tt)
                        g = float(self.gripper(tt)[0])
                        print(g)
                        p_list.append(p)
                        q_list.append(q)
                        g_list.append(g)
                    constraints = kp.constraints    
                    speed = kp.speed
                    Key = AtomicAction(name, "motion", arm, p_list, q_list, constraints, speed, g_list)

                else:
                    pose: PoseStamped = kp.poses[0] 
                    trans = np.asarray([pose.position.x, pose.position.y, pose.position.z])
                    rot = np.asarray([pose.orientation.x, pose.orientation.y, pose.orientation.z, pose.orientation.w])
                    constraints = kp.constraints
                    speed = kp.speed
                    Key = AtomicAction(name, "motion", arm, [trans], [rot], constraints, speed, kp.gripper_value.tolist())

            self.task.append(Key) 
        
            
    
    
    def pos(self, tq):
        return np.array([s(tq) for s in self.splines])

    def quat(self, tq):
        return self.slerp(tq).as_quat()

    def gripper(self, tq):
        return [g(tq) for g in self.gripperSplines]

    def eef_L_pose_callback(self, msg):
        self.eef_pos_L = msg.pose.position.x, msg.pose.position.y, msg.pose.position.z
    def eef_R_pose_callback(self, msg):
        self.eef_pos_R = msg.pose.position.x, msg.pose.position.y, msg.pose.position.z
    def pop_task(self):
        self.task.pop(0)
        self.time = self.get_clock().now()

    def publish_trajectory_markers(self):
        """Publish trajectory visualization markers for all motion actions in the task queue"""
        from geometry_msgs.msg import Point
        marker_array = MarkerArray()
        marker_id = 0

        # First, send DELETE_ALL marker to clear all previous markers
        delete_marker = Marker()
        delete_marker.action = Marker.DELETEALL
        marker_array.markers.append(delete_marker)

        for action in self.task:
            if action.type != "motion" or len(action.positions) == 0:
                continue

            # Determine color based on arm
            if action.arm == "left":
                r, g, b = 0.2, 0.6, 1.0  # Light blue for left arm
            else:
                r, g, b = 1.0, 0.4, 0.2  # Orange for right arm

            # Generate smooth spline trajectory if we have multiple waypoints
            interpolated_points = []

            if len(action.positions) > 1:
                # Create spline interpolation for smooth trajectory
                positions = np.array(action.positions)
                N = len(positions)

            interpolated_points = action.positions

            # Create LINE_STRIP marker for smooth trajectory path
            line_marker = Marker()
            line_marker.header.frame_id = "base_link"
            line_marker.header.stamp = self.get_clock().now().to_msg()
            line_marker.ns = f"{action.name}_trajectory"
            line_marker.id = marker_id
            marker_id += 1
            line_marker.type = Marker.LINE_STRIP
            line_marker.action = Marker.ADD

            line_marker.scale.x = 0.005  # Line width
            line_marker.color.r = r
            line_marker.color.g = g
            line_marker.color.b = b
            line_marker.color.a = 0.8

            # Add interpolated points to the line strip for smooth curve
            for pos in interpolated_points:
                point = Point()
                point.x = float(pos[0])
                point.y = float(pos[1])
                point.z = float(pos[2])
                line_marker.points.append(point)

            marker_array.markers.append(line_marker)

            # Add sphere markers for original waypoints only
            for wp_idx, (pos, orient) in enumerate(zip(action.positions, action.orientations)):
                sphere = Marker()
                sphere.header.frame_id = "base_link"
                sphere.header.stamp = self.get_clock().now().to_msg()
                sphere.ns = f"{action.name}_waypoints"
                sphere.id = marker_id
                marker_id += 1
                sphere.type = Marker.SPHERE
                sphere.action = Marker.ADD

                sphere.pose.position.x = float(pos[0])
                sphere.pose.position.y = float(pos[1])
                sphere.pose.position.z = float(pos[2])
                sphere.pose.orientation.x = float(orient[0])
                sphere.pose.orientation.y = float(orient[1])
                sphere.pose.orientation.z = float(orient[2])
                sphere.pose.orientation.w = float(orient[3])

                # Larger spheres for first/last waypoints, smaller for intermediate
                if wp_idx == 0:
                    sphere.scale.x = 0.02
                    sphere.scale.y = 0.02
                    sphere.scale.z = 0.02
                    sphere.color.a = 1.0
                elif wp_idx == len(action.positions) - 1:
                    sphere.scale.x = 0.025
                    sphere.scale.y = 0.025
                    sphere.scale.z = 0.025
                    sphere.color.a = 1.0
                else:
                    sphere.scale.x = 0.005
                    sphere.scale.y = 0.005
                    sphere.scale.z = 0.005
                    sphere.color.a = 0.6

                sphere.color.r = r
                sphere.color.g = g
                sphere.color.b = b

                marker_array.markers.append(sphere)

            # Add text label for the action name at the first waypoint
            if len(action.positions) > 0:
                text = Marker()
                text.header.frame_id = "base_link"
                text.header.stamp = self.get_clock().now().to_msg()
                text.ns = f"{action.name}_label"
                text.id = marker_id
                marker_id += 1
                text.type = Marker.TEXT_VIEW_FACING
                text.action = Marker.ADD

                text.pose.position.x = float(action.positions[0][0])
                text.pose.position.y = float(action.positions[0][1])
                text.pose.position.z = float(action.positions[0][2]) + 0.05

                text.scale.z = 0.02
                text.color.r = 1.0
                text.color.g = 1.0
                text.color.b = 1.0
                text.color.a = 1.0

                text.text = action.name
                marker_array.markers.append(text)
            break

        # Publish the marker array
        self.trajectory_marker_pub.publish(marker_array)

    def timer_cbk(self):
        # print("tick")
        # Publish trajectory markers for visualization
        if len(self.task) > 0:
            self.publish_trajectory_markers()

        if len(self.task) > 0:

        
            current_action = self.task[0]
            print(f"Current action: {current_action.name}, Type: {current_action.type}, Arm: {current_action.arm}")
            # if current_action.type == "gripper":
            #     gripper_value = Float32()
            #     gripper_value.data = current_action.positions[0]
            #     if current_action.arm == "left":
            #         self.gripper_controller_pub_L.publish(gripper_value)
            #     else:
            #         self.gripper_controller_pub_R.publish(gripper_value)
            #     print(f"Publishing gripper command for keypoint: {current_action.name}, value: {gripper_value.data}")
            #     self.pop_task()
            #     return
            
            if current_action.type == "home":
                self.speed_scale_pub.publish(Int16MultiArray(data=[100, 100]))

                self.constraint_msg.data = [100, 100, 100, 100, 100, 100]
                self.target_constraint_pub.publish(self.constraint_msg)
                if current_action.arm == "left":
                    self.gohome_srv_L.wait_for_service()
                    req = Trigger.Request()
                    future = self.gohome_srv_L.call_async(req)
                else:
                    self.gohome_srv_R.wait_for_service()
                    req = Trigger.Request()
                    future = self.gohome_srv_R.call_async(req)
                
                self.pop_task()
               
                return
            elif current_action.type == "motion":
                
                print(f"Publishing target pose for keypoint: {current_action.name}")
                if len(current_action.positions) ==0:
                    self.pop_task()
                    self.get_logger().info(f"Keypoint {current_action.name} completed.")
                    return

                pose_msg = PoseStamped()
                pose_msg.header.stamp = self.get_clock().now().to_msg()
                pose_msg.header.frame_id = "base_link"
                if current_action.arm == "left":
                    dist = np.linalg.norm(np.array(self.eef_pos_L) - np.array(current_action.positions[0]))
                    self.constraint_msg.data[0] = int(current_action.constraints[0])
                    self.constraint_msg.data[1] = int(current_action.constraints[1])
                    self.constraint_msg.data[2] = int(current_action.constraints[2])

                    
                    # if dist<0.01 and self.eef_ready_flag[0] == 0:
                    #     self.task.pop(0)
                else:
                    dist = np.linalg.norm(np.array(self.eef_pos_R) - np.array(current_action.positions[0]))
                    self.constraint_msg.data[3] = int(current_action.constraints[0])
                    self.constraint_msg.data[4] = int(current_action.constraints[1])
                    self.constraint_msg.data[5] = int(current_action.constraints[2])

                    # if dist<0.01 or self.eef_ready_flag[1] == 0:
                    #     self.task.pop(0)
                
                self.speed_scale_pub.publish(Int16MultiArray(data=[int(current_action.speed*100), int(current_action.speed*100)]))
                self.target_constraint_pub.publish(self.constraint_msg)
                if len(current_action.positions) >0:
                    pose_msg.pose.position.x = current_action.positions[0][0]
                    pose_msg.pose.position.y = current_action.positions[0][1]
                    pose_msg.pose.position.z = current_action.positions[0][2]
                    # print(f"position: {current_action.position}")
                    pose_msg.pose.orientation.x = current_action.orientations[0][0]
                    pose_msg.pose.orientation.y = current_action.orientations[0][1]
                    pose_msg.pose.orientation.z = current_action.orientations[0][2]
                    pose_msg.pose.orientation.w = current_action.orientations[0][3]
                    if current_action.arm == "left":
                        self.target_pub_L.publish(pose_msg)
                    else:
                        self.target_pub_R.publish(pose_msg)

                    gripper_value = Float32()
                    gripper_value.data = current_action.gripper_values[0]
                    if current_action.arm == "left":
                        self.gripper_controller_pub_L.publish(gripper_value)
                    else:
                        self.gripper_controller_pub_R.publish(gripper_value)
                    print(f"Publishing gripper command for keypoint: {current_action.name}, value: {gripper_value.data}")
                    self.time_lapse = self.get_clock().now() - self.time
                    
                    # Check timeout first
                    if self.time_lapse.nanoseconds / 1e9 > current_action.time_out:
                        self.get_logger().warn(f"Keypoint {current_action.name} timed out after {current_action.time_out}s. Distance: {dist:.3f}. Continuing to next action.")
                        self.pop_task()
                        return

                    if dist<0.1 and len(current_action.positions) >1:
                        current_action.positions.pop(0)
                        current_action.orientations.pop(0)
                        current_action.gripper_values.pop(0)
                        self.time = self.get_clock().now()  # Reset timeout for next waypoint
                    elif dist<0.015:
                        self.pop_task()
                        self.get_logger().info(f"Keypoint {current_action.name} completed.")
                    
                    print(f"Distance to target: {dist}")

               
                
                
                return


def main(args=None):
    rclpy.init(args=args)
    node = KeypointMarkerPublisher()

    executor = MultiThreadedExecutor()
    executor.add_node(node)

    try:
        executor.spin()
    finally:
        node.destroy_node()
        rclpy.shutdown()



if __name__ == "__main__":
    main()
