import rclpy
from rclpy.node import Node
from visualization_msgs.msg import Marker, MarkerArray
import yaml
import os

class KeypointMarkerPublisher(Node):
    def __init__(self):
        super().__init__("keypoint_marker_publisher")

        self.declare_parameter(
            "yaml_path",
            "/home/tianhao/fabrics/colcon_ws/src/marvin_fabric/config/world_data/drawer.yaml"
        )
        yaml_path = self.get_parameter("yaml_path").value

        if not os.path.exists(yaml_path):
            raise FileNotFoundError(f"YAML not found: {yaml_path}")

        with open(yaml_path, "r") as f:
            self.data = yaml.safe_load(f)

        self.pub = self.create_publisher(MarkerArray, "/keypoint_markers", 10)

        self.timer = self.create_timer(0.2, self.publish_markers)

        self.get_logger().info("Keypoint marker publisher started.")

    def publish_markers(self):
        marker_array = MarkerArray()
        marker_id = 0

        keypoints = self.data.get("keypoints", [])
        frame_id = "base_link"  # TF frame

        for kp in keypoints:
            name = kp["name"]
            px, py, pz = kp["position"]

            # ---------------------
            # 1. Sphere Marker
            # ---------------------
            sphere = Marker()
            sphere.header.frame_id = frame_id
            sphere.header.stamp = rclpy.time.Time().to_msg()

            sphere.ns = name + "_sphere"
            sphere.id = marker_id
            marker_id += 1

            sphere.type = Marker.SPHERE
            sphere.action = Marker.ADD

            sphere.pose.position.x = px
            sphere.pose.position.y = py
            sphere.pose.position.z = pz

            sphere.scale.x = 0.02
            sphere.scale.y = 0.02
            sphere.scale.z = 0.02

            sphere.color.r = 1.0
            sphere.color.g = 0.2
            sphere.color.b = 0.2
            sphere.color.a = 1.0

            marker_array.markers.append(sphere)

            # ---------------------
            # 2. Text Label Marker
            # ---------------------
            text = Marker()
            text.header.frame_id = frame_id
            text.header.stamp = rclpy.time.Time().to_msg()

            text.ns = name + "_text"
            text.id = marker_id
            marker_id += 1

            text.type = Marker.TEXT_VIEW_FACING
            text.action = Marker.ADD

            # Text position slightly above the point
            text.pose.position.x = px
            text.pose.position.y = py
            text.pose.position.z = pz + 0.03

            
            text.scale.z = 0.02  # text height


            text.color.r = 1.0
            text.color.g = 1.0
            text.color.b = 1.0
            text.color.a = 1.0

            text.text = name  # <-- label content

            marker_array.markers.append(text)

        self.pub.publish(marker_array)


def main(args=None):
    rclpy.init(args=args)
    node = KeypointMarkerPublisher()
    rclpy.spin(node)
    node.destroy_node()
    rclpy.shutdown()


if __name__ == "__main__":
    main()
