#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
import time
from typing import List, Optional

import numpy as np
import rclpy
from fake_interface_pkg.msg import KeypointPose, KeypointPoseArray
from std_msgs.msg import String

from robotaction.common import Step, TaskStatus


class FusionExecutionMixin:
    def _publish_current_action(self, step: Step, phase: str = "run"):
        msg = String()
        msg.data = json.dumps(
            {
                "state": self.active_state,
                "target": step.target,
                "action_name": step.action_name,
                "arm": step.arm,
                "step_idx": self.active_step_idx + 1,
                "total_steps": len(self.active_steps),
                "phase": phase,
            },
            ensure_ascii=False,
        )
        self.action_pub.publish(msg)

    def _publish_home_action(self, arm: str):
        msg = String()
        msg.data = json.dumps(
            {
                "state": self.active_state,
                "target": "home",
                "action_name": "home",
                "arm": arm,
                "step_idx": self.active_step_idx + 1,
                "total_steps": len(self.active_steps),
                "phase": "home",
            },
            ensure_ascii=False,
        )
        self.action_pub.publish(msg)

    def publish_kp_separately(self, sequence):
        for info in sequence:
            kp_array = KeypointPoseArray()
            kp_array.header.stamp = self.get_clock().now().to_msg()
            kp_array.header.frame_id = self.base_frame

            kp = KeypointPose()
            kp.name = info["name"]
            kp.arm = info["arm"]
            kp.poses = info.get("poses", [])
            kp.constraints = [float(x) for x in info.get("constraints", [1, 1, 1])]
            kp.speed = float(info.get("speed", 1.0))
            kp.gripper_value = [float(x) for x in info.get("gripper_value", [0])]
            kp.time = [float(x) for x in info.get("time", [0])]
            kp_array.poses.append(kp)
            try:
                self.pose_pub.publish(kp_array)
                self.get_logger().info(f"[Publish] '{kp.name}' arm='{kp.arm}'")
            except Exception as e:
                self.get_logger().warning(f"Publish failed: {e}")

    def _home(self, arm):
        home_seq = [{
            "name": "home",
            "arm": arm,
            "poses": [],
            "constraints": [100, 100, 100],
            "speed": 0.3,
            "gripper_value": [0.0, 0.0],
            "time": [0, 0.1],
        }]

        # 连续发送3次，间隔0.1s
        for i in range(3):
            self.publish_kp_separately(home_seq)
            self.get_logger().info(f"[Home] publish {i + 1}/3 arm='{arm}'")
            if i < 2:
                time.sleep(0.1)

    def publish_home_both(self):
        for arm in ["right", "left"]:
            self._home(arm)
            time.sleep(1)

    def publish_home_separately(self, arm):
        self._home(arm)

    def _execute_step_once(self, step: Step, inst: str) -> Optional[List]:
        ts = self._lookup_transform_base_to_instance(inst)
        if ts is None:
            return None

        translation = ts.transform.translation
        arm = self.arm_resolver.resolve(step.arm, translation)
        self.last_arm = arm

        handler = self.template_handlers.get(step.target)
        if handler is None:
            self.get_logger().warning(f"No handler for target '{step.target}'")
            return None

        kps = handler.process_for_object(
            ts.transform,
            step.action_name,
            task_arm=arm,
            task_speed=step.speed,
            correction_mode=step.correction_mode,
        )

        if step.fixed_endpoint and kps:
            pos_current = np.array([translation.x, translation.y, translation.z])
            kps = self.fixed_ep_mgr.apply(inst, kps, step.approach_count, pos_current)
        return kps

    def _run_step(self, step: Step, inst: str) -> str:
        kps = self._execute_step_once(step, inst)
        if kps is None:
            return TaskStatus.FAIL

        approach_count = step.approach_count
        if approach_count > 0 and len(kps) > 0:
            all_poses = kps[0].get("poses", [])
            approach_kps = [
                {
                    **kps[0],
                    "poses": all_poses[:approach_count],
                    "gripper_value": kps[0]["gripper_value"][:approach_count],
                    "time": kps[0]["time"][:approach_count],
                }
            ]
            post_kps = [
                {
                    **kps[0],
                    "poses": all_poses[approach_count:],
                    "gripper_value": kps[0]["gripper_value"][approach_count:],
                    "time": kps[0]["time"][approach_count:],
                }
            ]
            self.get_logger().info(
                f"[Execute] approach 阶段 '{step.action_name}' ({approach_count} frames)"
            )
            self.publish_kp_separately(approach_kps)
            if post_kps[0]["poses"]:
                self.get_logger().info(f"[Execute] post 阶段 '{step.action_name}'")
                self.publish_kp_separately(post_kps)
        else:
            self.get_logger().info(f"[Execute] '{step.action_name}'")
            self.publish_kp_separately(kps)

        return TaskStatus.SUCCESS

    def _run_home_and_wait(
        self,
        arm: Optional[str],
        step: Step,
        allow_preempt: Optional[bool] = None,
    ):
        if not arm:
            self.get_logger().warning("[Home] 无法确定回家机械臂")
            return TaskStatus.FAIL, None

        if allow_preempt is None:
            allow_preempt = self.allow_home_preempt

        self.task_progress_watcher.reset()
        self._publish_home_action(arm)
        self.get_logger().info(f"[Home] 发布 home arm='{arm}', allow_preempt={allow_preempt}")

        if str(arm).strip().lower() == "both":
            self.publish_home_both()
        else:
            self.publish_home_separately(arm)

        home_timeout_sec = max(5.0, float(step.task_finish_timeout))
        start = time.time()
        while rclpy.ok():
            if allow_preempt:
                preempt_state = self._get_preempt_state()
                if preempt_state is not None:
                    self.get_logger().warning(
                        f"[Preempt] home 过程中检测到新稳定状态 '{preempt_state}'，立即切换"
                    )
                    return TaskStatus.PREEMPT, preempt_state

            if self.task_progress_watcher.is_finished(
                silence_after_zero=0.5,
                finish_percentage=0.8,
            ):
                self.get_logger().info(f"[Home] 检测到 home 完成 arm='{arm}'")
                return TaskStatus.SUCCESS, None

            if (time.time() - start) >= home_timeout_sec:
                self.get_logger().warning(f"[Home] 等待 home 完成超时 arm='{arm}'")
                return TaskStatus.TIMEOUT, None
            time.sleep(1)

        return TaskStatus.STOP, None
