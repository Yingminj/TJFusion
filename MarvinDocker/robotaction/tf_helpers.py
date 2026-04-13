#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import time
from typing import Optional

import rclpy
import yaml
from geometry_msgs.msg import TransformStamped
from rclpy.duration import Duration

from robotaction.common import (
    matrix_to_transform_stamped,
    normalize_frame_id,
    normalize_obj_name,
    tf_to_template,
    transform_to_matrix,
)


class FusionTfMixin:
    @staticmethod
    def _stamp_to_ns(stamp) -> int:
        return int(stamp.sec) * 1_000_000_000 + int(stamp.nanosec)

    def _cached_object_frames(self, target_norm: Optional[str] = None):
        if self.object_tf_watcher is None:
            return {}

        now_ns = self.get_clock().now().nanoseconds
        frames = {}
        for child, ts in self.object_tf_watcher.snapshot().items():
            parent = normalize_frame_id(ts.header.frame_id)
            if parent not in self.camera_frames:
                continue
            child_norm = tf_to_template(child)
            if target_norm is not None and child_norm != target_norm:
                continue
            stamp_ns = self._stamp_to_ns(ts.header.stamp)
            age = (now_ns - stamp_ns) / 1e9
            if age <= 2.0:
                frames[child] = ts
        return frames

    def get_camera_link_frames(
        self,
        target: Optional[str] = None,
        wait_fresh: bool = False,
        timeout: float = 0.3,
        poll_interval: float = 0.02,
    ):
        start = time.time()
        target_norm = normalize_obj_name(target) if target is not None else None

        while rclpy.ok():
            frames = {}
            frame_stamp_ns = {}

            try:
                if self.object_tf_watcher is not None:
                    frames = self._cached_object_frames(target_norm)
                    frame_stamp_ns = {
                        child: self._stamp_to_ns(ts.header.stamp)
                        for child, ts in frames.items()
                    }
                else:
                    now = self.get_clock().now()
                    graph = yaml.safe_load(self.tf_buffer.all_frames_as_yaml()) or {}
                    for child, info in graph.items():
                        if not isinstance(info, dict):
                            continue
                        parent = normalize_frame_id(info.get("parent", ""))
                        if parent not in self.camera_frames:
                            continue
                        child_norm = tf_to_template(child)
                        if target_norm is not None and child_norm != target_norm:
                            continue
                        try:
                            ts = self.tf_buffer.lookup_transform(
                                "camera_left_link",
                                child,
                                rclpy.time.Time(),
                                timeout=Duration(seconds=0.05),
                            )
                            age = (
                                now.nanoseconds
                                - (ts.header.stamp.sec * 1e9 + ts.header.stamp.nanosec)
                            ) / 1e9
                            if age <= 2.0:
                                frames[child] = ts
                                frame_stamp_ns[child] = self._stamp_to_ns(ts.header.stamp)
                        except Exception:
                            continue
            except Exception as e:
                self.get_logger().warning(f"get_camera_link_frames failed: {e}")
                return {}

            if not wait_fresh:
                for child, ns in frame_stamp_ns.items():
                    self._last_tf_stamp_ns[child] = ns
                return frames

            fresh = {}
            for child, ts in frames.items():
                ns = frame_stamp_ns[child]
                prev = self._last_tf_stamp_ns.get(child)
                if prev is None or ns > prev:
                    fresh[child] = ts

            if fresh:
                for child, ns in frame_stamp_ns.items():
                    self._last_tf_stamp_ns[child] = ns
                return fresh

            if (time.time() - start) >= timeout:
                return {}
            time.sleep(poll_interval)

    def _lookup_transform_base_to_instance(self, inst: str) -> Optional[TransformStamped]:
        if self.object_tf_watcher is None:
            try:
                return self.tf_buffer.lookup_transform(
                    self.base_frame,
                    inst,
                    rclpy.time.Time(),
                    timeout=Duration(seconds=0.2),
                )
            except Exception as e:
                self.get_logger().warning(f"TF lookup failed for {inst}: {e}")
                return None

        frames = self._cached_object_frames()
        object_ts = frames.get(inst)
        if object_ts is None:
            self.get_logger().warning(f"Object TF not found for {inst} on '{self.object_tf_topic}'")
            return None

        camera_frame = normalize_frame_id(object_ts.header.frame_id)
        try:
            base_to_camera = self.tf_buffer.lookup_transform(
                self.base_frame,
                camera_frame,
                rclpy.time.Time(),
                timeout=Duration(seconds=0.2),
            )
        except Exception as e:
            self.get_logger().warning(
                f"TF lookup failed for {self.base_frame} <- {camera_frame}: {e}"
            )
            return None

        composed = transform_to_matrix(base_to_camera.transform) @ transform_to_matrix(
            object_ts.transform
        )
        return matrix_to_transform_stamped(
            composed,
            self.base_frame,
            inst,
            object_ts.header.stamp,
        )

    def _select_instance(self, step, frames) -> Optional[str]:
        target_norm = normalize_obj_name(step.target)
        candidates = [frame for frame in frames if normalize_obj_name(frame) == target_norm]
        if not candidates:
            debug_names = ", ".join(
                [f"{frame}->{normalize_obj_name(frame)}" for frame in frames.keys()]
            )
            self.get_logger().warning(
                f"[Select] 未找到 target='{step.target}'(norm='{target_norm}'), 可用frames: {debug_names}"
            )
            return None

        def get_y(inst_name):
            ts = self._lookup_transform_base_to_instance(inst_name)
            if ts is None:
                return float("inf")
            return ts.transform.translation.y

        candidates.sort(key=get_y)
        selected = candidates[0]
        self.get_logger().info(
            f"[Select] target='{step.target}' 候选: "
            + ", ".join(f"{cand}(y={get_y(cand):.3f})" for cand in candidates)
            + f" -> 选择: '{selected}'"
        )
        return selected

    def _wait_target_instances_ready(
        self,
        target: str,
        timeout: float = 2.0,
        settle_time: float = 0.25,
        poll_interval: float = 0.03,
    ):
        start = time.time()
        last_set = None
        last_change_t = time.time()
        last_frames = {}
        target_norm = normalize_obj_name(target)

        while rclpy.ok():
            frames = self.get_camera_link_frames(
                target=target_norm,
                wait_fresh=False,
                timeout=0.1,
                poll_interval=0.02,
            )
            cur_set = set(frames.keys())
            if cur_set != last_set:
                last_set = cur_set
                last_change_t = time.time()
                last_frames = frames
            if cur_set and (time.time() - last_change_t) >= settle_time:
                return last_frames
            if (time.time() - start) >= timeout:
                return frames
            time.sleep(poll_interval)
