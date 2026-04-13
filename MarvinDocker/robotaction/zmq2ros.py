#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
import json
import os
import sys

import numpy as np
import zmq
from zmq.error import ZMQError


DEFAULT_ZMQ_ADDR = os.environ.get("RESULT_PUB_ADDR", "tcp://127.0.0.1:8899")


def rotation_matrix_to_quaternion_xyzw(rot: np.ndarray):
    r = np.asarray(rot, dtype=np.float64)
    q = np.empty(4, dtype=np.float64)

    trace = r[0, 0] + r[1, 1] + r[2, 2]
    if trace > 0.0:
        s = 0.5 / np.sqrt(trace + 1.0)
        q[3] = 0.25 / s
        q[0] = (r[2, 1] - r[1, 2]) * s
        q[1] = (r[0, 2] - r[2, 0]) * s
        q[2] = (r[1, 0] - r[0, 1]) * s
    elif r[0, 0] > r[1, 1] and r[0, 0] > r[2, 2]:
        s = 2.0 * np.sqrt(1.0 + r[0, 0] - r[1, 1] - r[2, 2])
        q[3] = (r[2, 1] - r[1, 2]) / s
        q[0] = 0.25 * s
        q[1] = (r[0, 1] + r[1, 0]) / s
        q[2] = (r[0, 2] + r[2, 0]) / s
    elif r[1, 1] > r[2, 2]:
        s = 2.0 * np.sqrt(1.0 + r[1, 1] - r[0, 0] - r[2, 2])
        q[3] = (r[0, 2] - r[2, 0]) / s
        q[0] = (r[0, 1] + r[1, 0]) / s
        q[1] = 0.25 * s
        q[2] = (r[1, 2] + r[2, 1]) / s
    else:
        s = 2.0 * np.sqrt(1.0 + r[2, 2] - r[0, 0] - r[1, 1])
        q[3] = (r[1, 0] - r[0, 1]) / s
        q[0] = (r[0, 2] + r[2, 0]) / s
        q[1] = (r[1, 2] + r[2, 1]) / s
        q[2] = 0.25 * s

    norm = np.linalg.norm(q)
    if norm > 0:
        q = q / norm
    return q.astype(np.float32)


def pose_item_to_pose7(pose_item):
    arr = np.asarray(pose_item, dtype=np.float32)

    if arr.shape == (7,):
        return arr

    if arr.shape == (1, 7):
        return arr[0]

    if arr.shape == (4, 4):
        xyz = arr[:3, 3]
        rot_matrix = arr[:3, :3]

        rot_fix = np.array(
            [
                [-1.0, 0.0, 0.0],
                [0.0, 0.0, 1.0],
                [0.0, 1.0, 0.0],
            ],
            dtype=np.float32,
        )
        rot_matrix = rot_matrix @ rot_fix
        quat_xyzw = rotation_matrix_to_quaternion_xyzw(rot_matrix)
        return np.concatenate([xyz, quat_xyzw], axis=0).astype(np.float32)

    if arr.ndim == 3 and arr.shape[0] == 1 and arr.shape[1:] == (4, 4):
        return pose_item_to_pose7(arr[0])

    return None


def create_subscriber(endpoint: str, topics=None, timeout_ms: int = 1000):
    context = zmq.Context.instance()
    socket = context.socket(zmq.SUB)
    if topics:
        for topic in topics:
            socket.setsockopt(zmq.SUBSCRIBE, topic.encode("utf-8"))
    else:
        socket.setsockopt(zmq.SUBSCRIBE, b"")
    socket.setsockopt(zmq.LINGER, 0)
    socket.setsockopt(zmq.RCVTIMEO, timeout_ms)
    socket.setsockopt(zmq.RCVHWM, 1)
    socket.connect(endpoint)
    return socket


def decode_text(raw_msg):
    if isinstance(raw_msg, bytes):
        return raw_msg.decode("utf-8")
    return str(raw_msg)


def extract_json_text(raw_text: str):
    raw_text = raw_text.strip()
    if not raw_text:
        raise ValueError("empty payload")

    payload_pos = raw_text.find("payload=")
    if payload_pos >= 0:
        raw_text = raw_text[payload_pos + len("payload=") :].strip()

    if raw_text.startswith("{") or raw_text.startswith("["):
        return raw_text

    json_start_candidates = [pos for pos in (raw_text.find("{"), raw_text.find("[")) if pos >= 0]
    if json_start_candidates:
        return raw_text[min(json_start_candidates) :].strip()

    raise ValueError("no json object found in payload")


def split_text_topic_and_payload(raw_text: str):
    raw_text = raw_text.strip()
    if not raw_text:
        raise ValueError("empty payload")

    payload_pos = raw_text.find("payload=")
    if payload_pos >= 0:
        raw_text = raw_text[payload_pos + len("payload=") :].strip()

    if raw_text.startswith("{") or raw_text.startswith("["):
        return None, raw_text

    json_start_candidates = [pos for pos in (raw_text.find("{"), raw_text.find("[")) if pos >= 0]
    if not json_start_candidates:
        raise ValueError("no json object found in payload")

    json_start = min(json_start_candidates)
    topic_text = raw_text[:json_start].strip() or None
    json_text = raw_text[json_start:].strip()
    return topic_text, json_text


def parse_payload(raw_msg):
    raw_text = extract_json_text(decode_text(raw_msg))
    data = json.loads(raw_text)
    if not isinstance(data, dict):
        raise ValueError(f"expected dict payload, got {type(data).__name__}")
    return data


def recv_pending_messages(socket):
    messages = [socket.recv_multipart()]
    while True:
        try:
            messages.append(socket.recv_multipart(flags=zmq.NOBLOCK))
        except zmq.Again:
            break

    if not messages:
        raise ValueError("received empty zmq message")
    return messages


def keep_latest_message_per_topic(messages):
    latest_by_topic = {}
    ordered_topics = []

    for parts in messages:
        try:
            topic, _ = parse_zmq_message(parts)
        except Exception:
            topic = f"__parse_error__:{len(ordered_topics)}"

        topic_key = topic or "/zmq"
        if topic_key not in latest_by_topic:
            ordered_topics.append(topic_key)
        latest_by_topic[topic_key] = parts

    return [latest_by_topic[topic_key] for topic_key in ordered_topics]


def parse_zmq_message(parts):
    if len(parts) == 1:
        raw_text = decode_text(parts[0])
        topic, json_text = split_text_topic_and_payload(raw_text)
        payload = json.loads(json_text)
        if not isinstance(payload, dict):
            raise ValueError(f"expected dict payload, got {type(payload).__name__}")
    else:
        topic = decode_text(parts[0]).strip() or None
        payload = parse_payload(parts[-1])
    return topic, payload


def extract_siglip_payload(payload: dict):
    siglip = payload.get("siglip2")
    if isinstance(siglip, dict):
        return dict(siglip)

    if any(key in payload for key in ("best_category", "best_similarity", "total_category", "state_list")):
        return payload
    return None


def extract_frame_id(payload: dict, default_frame_id: str):
    return default_frame_id


def make_child_frame_id(item: dict, index: int, class_counts: dict):
    child_frame_id = item.get("child_frame_id")
    if child_frame_id:
        return str(child_frame_id)

    cls_name = item.get("name")
    box_id = item.get("box_id")
    if cls_name is not None:
        cls_name = str(cls_name)
        class_counts[cls_name] = class_counts.get(cls_name, 0) + 1
        return f"{cls_name}_{class_counts[cls_name]}"
    if box_id is not None:
        return f"obj_{box_id}"
    return f"obj_{index + 1}"


class BridgeRosPublisher:
    def __init__(self, node_name: str = "zmq2ros"):
        import rclpy
        from geometry_msgs.msg import TransformStamped
        from rclpy.node import Node
        from rclpy.qos import DurabilityPolicy, HistoryPolicy, QoSProfile, ReliabilityPolicy
        from std_msgs.msg import String
        from tf2_msgs.msg import TFMessage

        class _Node(Node):
            def __init__(self):
                super().__init__(node_name)
                self.qos = QoSProfile(
                    history=HistoryPolicy.KEEP_LAST,
                    depth=1,
                    reliability=ReliabilityPolicy.RELIABLE,
                )
                try:
                    from tf2_ros.qos import DynamicBroadcasterQoS

                    self.tf_qos = DynamicBroadcasterQoS()
                except ImportError:
                    self.tf_qos = QoSProfile(
                        history=HistoryPolicy.KEEP_LAST,
                        depth=100,
                        reliability=ReliabilityPolicy.RELIABLE,
                        durability=DurabilityPolicy.VOLATILE,
                    )

        self.rclpy = rclpy
        self.TransformStamped = TransformStamped
        self.TFMessage = TFMessage
        self.String = String
        self.node = _Node()
        self.string_publishers = {}
        self.tf_publishers = {}

    def get_string_publisher(self, topic_name: str):
        pub = self.string_publishers.get(topic_name)
        if pub is None:
            pub = self.node.create_publisher(self.String, topic_name, self.node.qos)
            self.string_publishers[topic_name] = pub
            self.node.get_logger().info(f"ROS String topic -> {topic_name}")
        return pub

    def get_tf_publisher(self, topic_name: str):
        pub = self.tf_publishers.get(topic_name)
        if pub is None:
            pub = self.node.create_publisher(self.TFMessage, topic_name, self.node.tf_qos)
            self.tf_publishers[topic_name] = pub
            self.node.get_logger().info(f"ROS TF topic -> {topic_name}")
        return pub

    def publish_json(self, topic_name: str, payload: dict):
        msg = self.String()
        msg.data = json.dumps(payload, ensure_ascii=False)
        self.get_string_publisher(topic_name).publish(msg)

    def publish_tf_items(self, topic_name: str, tf_items, frame_id: str):
        if not isinstance(tf_items, list) or not tf_items:
            return

        tf_msg = self.TFMessage()
        stamp = self.node.get_clock().now().to_msg()
        class_counts = {}

        for index, item in enumerate(tf_items):
            if not isinstance(item, dict):
                continue

            translation = item.get("translation", {})
            rotation = item.get("rotation", {})

            transform = self.TransformStamped()
            transform.header.stamp = stamp
            transform.header.frame_id = str(item.get("frame_id") or frame_id)
            transform.child_frame_id = make_child_frame_id(item, index, class_counts)

            transform.transform.translation.x = float(translation.get("x", 0.0))
            transform.transform.translation.y = float(translation.get("y", 0.0))
            transform.transform.translation.z = float(translation.get("z", 0.0))
            transform.transform.rotation.x = float(rotation.get("x", 0.0))
            transform.transform.rotation.y = float(rotation.get("y", 0.0))
            transform.transform.rotation.z = float(rotation.get("z", 0.0))
            transform.transform.rotation.w = float(rotation.get("w", 1.0))
            tf_msg.transforms.append(transform)

        if tf_msg.transforms:
            self.get_tf_publisher(topic_name).publish(tf_msg)

    def publish_yomni_tf(self, topic_name: str, payload: dict, frame_id: str):
        if not payload or not payload.get("ok", False):
            return

        objects = payload.get("objects", [])
        pose_list = payload.get("pose", [])
        obj_ids = payload.get("obj_ids", [])
        class_names = payload.get("class_names", [])
        tf_msg = self.TFMessage()
        stamp = self.node.get_clock().now().to_msg()
        class_counts = {}

        if isinstance(objects, list) and objects:
            for i, obj in enumerate(objects):
                if not isinstance(obj, dict):
                    continue
                pose7 = pose_item_to_pose7(obj.get("pose"))
                if pose7 is None:
                    continue

                transform = self.TransformStamped()
                transform.header.stamp = stamp
                transform.header.frame_id = frame_id
                transform.child_frame_id = make_child_frame_id(obj, i, class_counts)
                transform.transform.translation.x = float(pose7[0])
                transform.transform.translation.y = float(pose7[1])
                transform.transform.translation.z = float(pose7[2])
                transform.transform.rotation.x = float(pose7[3])
                transform.transform.rotation.y = float(pose7[4])
                transform.transform.rotation.z = float(pose7[5])
                transform.transform.rotation.w = float(pose7[6])
                tf_msg.transforms.append(transform)
        else:
            for i, pose_item in enumerate(pose_list):
                pose7 = pose_item_to_pose7(pose_item)
                if pose7 is None:
                    continue

                item = {}
                if i < len(class_names) and class_names[i]:
                    item["name"] = class_names[i]
                if i < len(obj_ids):
                    obj_id_item = obj_ids[i]
                    if isinstance(obj_id_item, (list, tuple)) and len(obj_id_item) >= 2:
                        item["box_id"] = obj_id_item[1]

                transform = self.TransformStamped()
                transform.header.stamp = stamp
                transform.header.frame_id = frame_id
                transform.child_frame_id = make_child_frame_id(item, i, class_counts)
                transform.transform.translation.x = float(pose7[0])
                transform.transform.translation.y = float(pose7[1])
                transform.transform.translation.z = float(pose7[2])
                transform.transform.rotation.x = float(pose7[3])
                transform.transform.rotation.y = float(pose7[4])
                transform.transform.rotation.z = float(pose7[5])
                transform.transform.rotation.w = float(pose7[6])
                tf_msg.transforms.append(transform)

        if tf_msg.transforms:
            self.get_tf_publisher(topic_name).publish(tf_msg)

    def destroy(self):
        self.node.destroy_node()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--zmq_addr", default=DEFAULT_ZMQ_ADDR)
    parser.add_argument(
        "--zmq_topic",
        action="append",
        default=[],
        help="optional ZMQ SUB topic prefix, can be repeated",
    )
    parser.add_argument("--default_frame_id", default="camera_rgb_link")
    args = parser.parse_args()

    try:
        import rclpy
    except ImportError:
        sys.stderr.write("rclpy is required for this script.\n")
        sys.exit(1)

    rclpy.init()
    ros_pub = BridgeRosPublisher()
    if "://0.0.0.0:" in args.zmq_addr:
        ros_pub.node.get_logger().warning(
            "ZMQ SUB is connecting to 0.0.0.0. Use the publisher host IP or 127.0.0.1 instead."
        )
    sub = create_subscriber(args.zmq_addr, topics=args.zmq_topic)

    ros_pub.node.get_logger().info(f"ZMQ SUB <- {args.zmq_addr}")
    topic_filter_text = ", ".join(args.zmq_topic) if args.zmq_topic else "<all>"
    ros_pub.node.get_logger().info(f"ZMQ topic filter <- {topic_filter_text}")
    ros_pub.node.get_logger().info("[Bridge ROS] publish to the same ROS topic as incoming ZMQ topic")

    try:
        wait_log_count = 0
        recv_count = 0
        while rclpy.ok():
            try:
                messages = recv_pending_messages(sub)
            except zmq.Again:
                wait_log_count += 1
                if wait_log_count % 5 == 0:
                    ros_pub.node.get_logger().info(
                        f"waiting for zmq message from {args.zmq_addr}"
                    )
                rclpy.spin_once(ros_pub.node, timeout_sec=0.01)
                continue
            except ZMQError as exc:
                ros_pub.node.get_logger().error(f"zmq recv failed: {exc}")
                rclpy.spin_once(ros_pub.node, timeout_sec=0.1)
                continue

            wait_log_count = 0
            messages = keep_latest_message_per_topic(messages)

            for parts in messages:
                try:
                    topic, payload = parse_zmq_message(parts)
                except Exception as exc:
                    ros_pub.node.get_logger().error(f"failed to parse zmq payload: {exc}")
                    continue

                recv_count += 1
                ros_pub.node.get_logger().info(
                    f"received zmq message #{recv_count} parts={len(parts)}"
                )
                if topic:
                    ros_pub.node.get_logger().info(f"received zmq topic: {topic}")

                frame_id = extract_frame_id(payload, args.default_frame_id)
                tf_items = None
                if isinstance(payload.get("tf"), list):
                    tf_items = payload["tf"]
                elif isinstance(payload.get("transforms"), list):
                    tf_items = payload["transforms"]

                ros_topic = topic or "/zmq"

                if tf_items is not None:
                    ros_pub.publish_tf_items(ros_topic, tf_items, frame_id)
                elif isinstance(payload.get("yomni"), dict):
                    ros_pub.publish_yomni_tf(ros_topic, payload["yomni"], frame_id)
                elif any(key in payload for key in ("objects", "pose", "obj_ids", "class_names")):
                    ros_pub.publish_yomni_tf(ros_topic, payload, frame_id)
                else:
                    ros_pub.publish_json(ros_topic, payload)
            rclpy.spin_once(ros_pub.node, timeout_sec=0.0)
    except KeyboardInterrupt:
        pass
    finally:
        try:
            sub.close()
        except Exception:
            pass
        ros_pub.destroy()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
