#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
import threading
from typing import Dict, List, Optional

from fake_interface_pkg.msg import KeypointPoseArray
import rclpy
import yaml
from rclpy.callback_groups import ReentrantCallbackGroup
from rclpy.node import Node
from std_msgs.msg import String
from tf2_ros import Buffer, TransformListener
import sys
sys.path.append("/")  # Ensure robotaction is in the path for imports
from robotaction.common import (
    ActionHandler,
    ArmResolver,
    FixedEndpointManager,
    Step,
    normalize_frame_id,
)
from robotaction.execution import FusionExecutionMixin
from robotaction.state_machine import FusionStateMixin
from robotaction.tf_helpers import FusionTfMixin
from robotaction.watchers import ObjectTfWatcher, StatusWatcher, TaskProgressWatcher


class FusionNode(FusionStateMixin, FusionExecutionMixin, FusionTfMixin, Node):
    def __init__(
        self,
        object_yaml_path,
        status_json_path,
        status_topic,
        progress_topic,
        object_tf_topic=None,
        base_frame="base_link",
        camera_frames=None,
    ):
        super().__init__("robotaction")
        self.timer_group = ReentrantCallbackGroup()
        self.status_group = ReentrantCallbackGroup()
        self.progress_group = ReentrantCallbackGroup()
        self.object_tf_group = ReentrantCallbackGroup()

        with open(object_yaml_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
            self.object_templates = data.get("templates", {})

        self.status_tasks = self._load_status_json(status_json_path)
        self.last_arm = None
        self.base_frame = normalize_frame_id(base_frame)
        self.camera_frames = {
            normalize_frame_id(v)
            for v in (camera_frames or ["camera_rgb_link", "camera_link_rgb"])
        }
        self.object_tf_topic = object_tf_topic

        self.template_handlers = {
            k: ActionHandler(v, node=self)
            for k, v in self.object_templates.items()
        }

        self.tf_buffer = Buffer()
        self.tf_listener = TransformListener(self.tf_buffer, self)
        self.object_tf_watcher = None
        if object_tf_topic:
            self.object_tf_watcher = ObjectTfWatcher(
                self,
                topic=object_tf_topic,
                callback_group=self.object_tf_group,
            )

        self.pose_pub = self.create_publisher(KeypointPoseArray, "/fusion_pose", 10)
        self.action_pub = self.create_publisher(String, "/fusion/current_action", 10)
        self.arm_resolver = ArmResolver(lambda: self.last_arm)
        self.fixed_ep_mgr = FixedEndpointManager()
        self.status_watcher = StatusWatcher(
            self,
            topic=status_topic,
            callback_group=self.status_group,
        )
        self.task_progress_watcher = TaskProgressWatcher(
            self,
            topic=progress_topic,
            callback_group=self.progress_group,
        )
        self.active_state: Optional[str] = None
        self.active_steps: List[Step] = []
        self.active_step_idx = 0
        self.last_ignored_state = None
        self._control_lock = threading.Lock()
        self.timer = self.create_timer(
            0.2,
            self.on_timer,
            callback_group=self.timer_group,
        )
        self._last_tf_stamp_ns: Dict[str, int] = {}

        self.declare_parameter("allow_home_preempt", False)
        self.allow_home_preempt = bool(self.get_parameter("allow_home_preempt").value)
        self.declare_parameter("home_old_arm_on_preempt_switch", False)
        self.home_old_arm_on_preempt_switch = bool(
            self.get_parameter("home_old_arm_on_preempt_switch").value
        )

        self._tf_miss_streak = 0
        self._tf_miss_key = None

        self.get_logger().info(
            f"[Config] status_topic={status_topic}, progress_topic={progress_topic}, "
            f"object_tf_topic={object_tf_topic or '<tf_buffer>'}, base_frame={self.base_frame}"
        )



def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--object_yaml_path", required=True)
    parser.add_argument("--status_json_path", required=True)
    parser.add_argument("--status_topic", default="/siglip/result")
    parser.add_argument("--progress_topic", default="/control/task_percentage")
    parser.add_argument(
        "--object_tf_topic",
        default="",
        help="optional TFMessage topic carrying object transforms from camera frame",
    )
    parser.add_argument("--base_frame", default="base_link")
    parser.add_argument(
        "--camera_frames",
        nargs="*",
        default=["camera_rgb_link", "camera_link_rgb"],
    )
    args = parser.parse_args()

    rclpy.init()
    node = FusionNode(
        object_yaml_path=args.object_yaml_path,
        status_json_path=args.status_json_path,
        status_topic=args.status_topic,
        progress_topic=args.progress_topic,
        object_tf_topic=args.object_tf_topic or None,
        base_frame=args.base_frame,
        camera_frames=args.camera_frames,
    )

    from rclpy.executors import MultiThreadedExecutor

    executor = MultiThreadedExecutor(num_threads=2)
    executor.add_node(node)
    try:
        executor.spin()
    except KeyboardInterrupt:
        pass
    finally:
        try:
            node.destroy_node()
        except Exception:
            pass
        rclpy.shutdown()


if __name__ == "__main__":
    main()
