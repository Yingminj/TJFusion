#!/usr/bin/env python3
import rclpy
from rclpy.node import Node
from visualization_msgs.msg import Marker, MarkerArray
import yaml
import os
from tf2_ros import Buffer, TransformListener
import glob
def parse_frames(frames_str):
    """
    Parse TF frames from all_frames_as_string output.
    Return list of frame names.
    """
    frames = []
    for line in frames_str.splitlines():
        if line.startswith("Frame "):
            # 'Frame Base_L exists with parent base_link.'
            # split by space and take 2nd word
            parts = line.split()
            if len(parts) >= 2:
                frames.append(parts[1])
    return frames

class ObjectMarkerPublisher(Node):
    def __init__(self):
        super().__init__('object_marker_publisher')

        self.declare_parameter(
            "yaml_path",
            "/home/tianhao/fabrics/colcon_ws/src/marvin_fabric/config/world_data/objs"
        )

        yaml_path = self.get_parameter("yaml_path").value
        if yaml_path == "":
            raise RuntimeError("Please set parameter yaml_path")

        if not os.path.exists(yaml_path):
            raise FileNotFoundError(f"YAML not found: {yaml_path}")

        self.get_logger().info(f"Loading object data: {yaml_path}")

        yaml_files = glob.glob(os.path.join(yaml_path, "*.yaml"))

        if len(yaml_files) == 0:
            raise FileNotFoundError(f"No YAML files found in {yaml_path}")

        self.get_logger().info(f"Found {len(yaml_files)} YAML files")

        # 读取所有 YAML 文件
        all_objects = {}
        for yf in yaml_files:
            with open(yf, "r") as f:
                data = yaml.safe_load(f)
                if data is not None:
                    all_objects.update(data)  # 合并所有对象字典

        self.get_logger().info(f"Total objects loaded: {len(all_objects)}")
        self.objects = all_objects
        self.pub = self.create_publisher(MarkerArray, "object_markers", 10)
        self.timer = self.create_timer(0.1, self.timer_callback)

        self.tf_buffer = Buffer()
        self.tf_listener = TransformListener(self.tf_buffer, self)
    def find_matching_frame(self, obj_name, default="map"):
        """
        Find a TF frame whose name contains obj_name.
        For multiple matches, choose the shortest name or the one containing 'link'.
        """
        try:
            frames_str = self.tf_buffer.all_frames_as_string()
            frames = parse_frames(frames_str)
        except Exception as e:
            self.get_logger().warn(f"TF read failed: {e}")
            return None

        # find frames containing object name
        matches = [f for f in frames if obj_name.lower() in f.lower()]
        if not matches:
            self.get_logger().warn(f"No TF frame contains '{obj_name}', using default: {default}")
            return None

        # prefer frames containing 'link', then shortest name
        link_matches = [f for f in matches if "link" in f.lower()]
        if link_matches:
            best = sorted(link_matches, key=len)[0]
        else:
            best = sorted(matches, key=len)[0]

        self.get_logger().info(f"Object '{obj_name}' -> matched TF frame: {best}")
        return best
    def timer_callback(self):
        for obj_name, obj in self.objects.items():
           object_frame = self.find_matching_frame(obj_name, "base_link")
           if object_frame is None:
               continue
           print(f"Object: {obj_name}, Frame: {object_frame}")
           pose = self.tf_buffer.lookup_transform(
               "base_link",
               object_frame,
               rclpy.time.Time()
           )
           print(f"Pose: {pose.transform}")
           self.objects.update({obj_name: {"pose": pose.transform}})


def main(args=None):
    rclpy.init(args=args)
    node = ObjectMarkerPublisher()
    rclpy.spin(node)
    node.destroy_node()
    rclpy.shutdown()


if __name__ == '__main__':
    main()
