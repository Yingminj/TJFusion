#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
import threading
import time
from collections import deque
from typing import Dict, Optional

import rclpy
from geometry_msgs.msg import TransformStamped
from std_msgs.msg import Float32, String
from tf2_msgs.msg import TFMessage

from robotaction.common import (
    extract_siglip_payload,
    normalize_frame_id,
    normalize_state_text,
)


class StatusWatcher:
    def __init__(self, node, topic: str, stable_frames=2, callback_group=None):
        self._node = node
        self._lock = threading.Lock()
        self._stable_frames = stable_frames
        self._recent_states = deque(maxlen=stable_frames)
        self._sub = node.create_subscription(
            String,
            topic,
            self._cb,
            10,
            callback_group=callback_group,
        )

    def _cb(self, msg: String):
        try:
            payload = json.loads(msg.data)
            payload = extract_siglip_payload(payload) or payload
            if not isinstance(payload, dict):
                return
            if "ok" in payload and not payload.get("ok", False):
                return
            best_category = payload.get("best_category")
            if not best_category:
                return
            normalized = normalize_state_text(best_category)
            if not normalized:
                return
            with self._lock:
                self._recent_states.append(normalized)
        except Exception as e:
            self._node.get_logger().warning(f"[StatusWatcher] parse fail: {e}")

    def get_stable_state(self) -> Optional[str]:
        with self._lock:
            if len(self._recent_states) < self._stable_frames:
                return None
            values = list(self._recent_states)
        if len(set(values)) == 1:
            return values[-1]
        return None

    def wait_stable_state(self, timeout=2.0, poll_interval=0.1):
        start = time.time()
        while rclpy.ok():
            stable = self.get_stable_state()
            if stable is not None:
                return stable
            if (time.time() - start) >= timeout:
                return None
            time.sleep(poll_interval)


class TaskProgressWatcher:
    def __init__(self, node, topic: str, callback_group=None):
        self._node = node
        self._lock = threading.Lock()
        self._latest_value: Optional[float] = None
        self._last_msg_time: Optional[float] = None
        self._seen_active = False
        self._seen_zero = False
        self._reset_time = time.time()
        self._sub = node.create_subscription(
            Float32,
            topic,
            self._cb,
            10,
            callback_group=callback_group,
        )

    def _cb(self, msg: Float32):
        now = time.time()
        value = float(msg.data)
        with self._lock:
            if now < self._reset_time:
                return
            self._latest_value = value
            self._last_msg_time = now
            if value > 1e-6:
                self._seen_active = True
            elif self._seen_active and abs(value) <= 1e-6:
                self._seen_zero = True

    def reset(self):
        with self._lock:
            self._latest_value = None
            self._last_msg_time = None
            self._seen_active = False
            self._seen_zero = False
            self._reset_time = time.time()

    def is_finished(self, silence_after_zero=1, finish_percentage=0.97):
        now = time.time()
        with self._lock:
            seen_active = self._seen_active
            seen_zero = self._seen_zero
            last_msg_time = self._last_msg_time
            latest_value = self._latest_value

        # 必须先激活，才允许按百分比完成
        if seen_active and latest_value is not None and latest_value >= finish_percentage:
            return True

        # 必须先激活，再回零并静默一段时间
        return bool(
            seen_active
            and seen_zero
            and last_msg_time is not None
            and (now - last_msg_time) >= silence_after_zero
        )


class ObjectTfWatcher:
    def __init__(self, node, topic: str, callback_group=None):
        self._node = node
        self._lock = threading.Lock()
        self._latest: Dict[str, TransformStamped] = {}
        self._sub = node.create_subscription(
            TFMessage,
            topic,
            self._cb,
            10,
            callback_group=callback_group,
        )

    def _cb(self, msg: TFMessage):
        with self._lock:
            for tf_msg in msg.transforms:
                child = normalize_frame_id(tf_msg.child_frame_id)
                if not child:
                    continue
                copied = TransformStamped()
                copied.header = tf_msg.header
                copied.child_frame_id = child
                copied.transform = tf_msg.transform
                copied.header.frame_id = normalize_frame_id(copied.header.frame_id)
                self._latest[child] = copied

    def snapshot(self) -> Dict[str, TransformStamped]:
        with self._lock:
            return dict(self._latest)
