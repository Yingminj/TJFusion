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

class KeyPoint:
    def __init__(self, name, type, position, orientation, constraints, speed):
        self.name = name
        self.type = type # could be "motion" or "gripper" or "home"
        self.position = position
        self.orientation = orientation
        self.constraints = constraints
        self.speed = speed

class KeypointMarkerPublisher(Node):
    def __init__(self):
        super().__init__("keypoint_marker_publisher")

        self.declare_parameter(
            "yaml_path",
            "/home/marvin/ros2_ws/src/marvin_fabric/config/world_data/tasks/drawer.yaml"
        )
        yaml_path = self.get_parameter("yaml_path").value

        if not os.path.exists(yaml_path):
            raise FileNotFoundError(f"YAML not found: {yaml_path}")

        with open(yaml_path, "r") as f:
            self.data = yaml.safe_load(f)

        self.pub = self.create_publisher(MarkerArray, "keypoint_markers", 10)
        self.target_pub = self.create_publisher(PoseStamped, "control/target_poseL", 10)
        self.target_constraint_pub = self.create_publisher(Int16MultiArray, "control/eef_constraint", 10)
        self.speed_scale_pub = self.create_publisher(Int16MultiArray, "control/speed_scale", 10)
        self.eef_pose_sub_L = self.create_subscription(PoseStamped, "info/eef_left", self.eef_L_pose_callback, 10)
        self.gripper_controller_pub_L = self.create_publisher(Float32, 'control/gripperValueL', 10)
        
        self.sub_ready = self.create_subscription( Int16MultiArray,"/arm/eef_state", self.ready_callback, 10)
        self.gohome_srv = self.create_client(Trigger, "/reset_left_arm")
        self.run_service = self.create_service(Trigger, "/start_task_execution", self.start_task_callback)
        self.timer = self.create_timer(0.2, self.timer_cbk)
        self.eef_ready_flag = [1,1]  # left, right

        self.get_logger().info("Keypoint marker publisher started.")
        self.action_len = 0
        self.task = []
        self.eef_pos_L = (0.0, 0.0, 0.0)
        # self.get_points()
        

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
        self.action_len = len(self.task)
        response.success = True
        response.message = "Task execution started."
        return response
    

    def get_points(self):
        # marker_array = MarkerArray()
        # marker_id = 0

        keypoints = self.data.get("keypoints", [])
        # frame_id = "drawer"  # TF frame

        for kp in keypoints:
            name = kp["name"]
            if name.startswith("gripper"):
                px = kp["gripper_value"]
                Key = KeyPoint(name, "gripper", [px, 0 , 0], [0 ,0, 0, 0], [0,  0, 0],0)
                # continue
            elif name == "home":
                Key = KeyPoint(name, "home", [0.0, 0.0, 0.0], [0, 0, 0, 1], [1, 1, 1], 0.5)
            else:
                px, py, pz = kp["position"]
                rx, ry, rz, rw = kp.get("orientation", [0, 0, 0, 1])
                constraints = kp.get("constraints", [1,1,1])
                speed = kp.get("speed", 0.5)
                Key = KeyPoint(name, "motion", [px, py, pz], [rx, ry, rz, rw], constraints, speed)
            self.task.append(Key)   
    
    def eef_L_pose_callback(self, msg):
        self.eef_pos_L = msg.pose.position.x, msg.pose.position.y, msg.pose.position.z
    
    def timer_cbk(self):
        print("tick")
        if len(self.task) > 0:
        #     gripper_value = Float32()
        #     gripper_value.data = 0.0
        #     self.gripper_controller_pub_L.publish(gripper_value)
        #     self.speed_scale_pub.publish(Int16MultiArray(data=[50, 50]))
        #     # self.gohome_srv.wait_for_service()
        #     req = Trigger.Request()
        #     # future = self.gohome_srv.call(req)
        #     # rclpy.spin_until_future_complete(self, future)
        #     # if future.result().success:
        #     #     print("All tasks completed. Returned to home position.")
        #     # else:
        #     #     print("Failed to return to home position.")
          
            
        
            current_action = self.task[0]
            if current_action.type == "gripper":
                gripper_value = Float32()
                gripper_value.data = current_action.position[0]
                self.gripper_controller_pub_L.publish(gripper_value)
                print(f"Publishing gripper command for keypoint: {current_action.name}, value: {gripper_value.data}")
                self.task.pop(0)
                return
            elif current_action.type == "home":
                self.speed_scale_pub.publish(Int16MultiArray(data=[50, 50]))
                self.gohome_srv.wait_for_service()
                req = Trigger.Request()
                future = self.gohome_srv.call_async(req)
                
                self.task.pop(0)
               
                return
            else:
                print(f"Publishing target pose for keypoint: {current_action.name}")
                
                self.speed_scale_pub.publish(Int16MultiArray(data=[int(current_action.speed*100), 50]))
                pose_msg = PoseStamped()
                pose_msg.header.stamp = self.get_clock().now().to_msg()
                pose_msg.header.frame_id = "base_link"
                pose_msg.pose.position.x = current_action.position[0]
                pose_msg.pose.position.y = current_action.position[1]
                pose_msg.pose.position.z = current_action.position[2]
                pose_msg.pose.orientation.x = current_action.orientation[0]
                pose_msg.pose.orientation.y = current_action.orientation[1]
                pose_msg.pose.orientation.z = current_action.orientation[2]
                pose_msg.pose.orientation.w = current_action.orientation[3]

                constraint_msg = Int16MultiArray()
                constraint_msg.data = [1, 1, 1, 1, 1, 1]
                constraint_msg.data[0] = current_action.constraints[0]
                constraint_msg.data[1] = current_action.constraints[1]
                constraint_msg.data[2] = current_action.constraints[2]

                self.target_pub.publish(pose_msg)
                self.target_constraint_pub.publish(constraint_msg)
                dist = np.linalg.norm(np.array(self.eef_pos_L) - np.array(current_action.position))
                print(f"Distance to target: {dist}")
                if dist<0.01 and self.eef_ready_flag[0] == 0:
                    self.task.pop(0)
                
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
