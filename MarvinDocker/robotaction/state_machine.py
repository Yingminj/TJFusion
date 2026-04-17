#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
import time
from typing import List, Optional

import rclpy

from robotaction.common import Step, TaskStatus, normalize_obj_name, normalize_state_text


class FusionStateMixin:
    def _is_home_step(self, step: Step):
        if str(step.action_name).strip().lower() == "home":
            return True
        if normalize_obj_name(step.target) == "home":
            return True
        return False

    def _normalize_arm_text(self, arm: Optional[str]) -> str:
        return str(arm or "").strip().lower()

    def _first_action_arm_of_state(self, state_name: Optional[str]) -> Optional[str]:
        if not state_name:
            return None
        tasks = self.status_tasks.get(state_name)
        if self._is_home_token(tasks):
            tasks = self._home_task_default()
        if not isinstance(tasks, list) or len(tasks) == 0:
            return None
        first = tasks[0] or {}
        return first.get("arm")

    @staticmethod
    def _normalize_action_signature(
        target: Optional[str], action_name: Optional[str], arm: Optional[str]
    ):
        target_n = normalize_obj_name(target or "")
        action_n = str(action_name or "").strip().lower()
        arm_n = str(arm or "right").strip().lower()
        return target_n, action_n, arm_n

    def _step_signature(self, step: Step):
        return self._normalize_action_signature(step.target, step.action_name, step.arm)

    def _first_action_signature_of_state(self, state_name: Optional[str]):
        if not state_name:
            return None
        tasks = self.status_tasks.get(state_name)
        if self._is_home_token(tasks):
            tasks = self._home_task_default()
        if not isinstance(tasks, list) or len(tasks) == 0:
            return None
        first = tasks[0] or {}
        return self._normalize_action_signature(
            first.get("target"),
            first.get("action_name"),
            first.get("arm"),
        )

    def _current_running_arm(self, step: Step) -> str:
        if self.last_arm:
            return self._normalize_arm_text(self.last_arm)
        return self._normalize_arm_text(self.arm_resolver.resolve(step.arm, None))

    def _load_status_json(self, status_json_path: str):
        with open(status_json_path, "r", encoding="utf-8") as f:
            data = json.load(f) or {}
        nodes = data.get("nodes", [])
        mapping = {}
        for node in nodes:
            state_name = normalize_state_text(node.get("state_description"))
            if not state_name:
                continue
            mapping[state_name] = node.get("next_action")
        return mapping

    def _build_steps_for_state(self, state_name: str, tasks) -> List[Step]:
        steps = []
        for i, task in enumerate(tasks):
            steps.append(
                Step(
                    action_name=task.get("action_name", f"step_{i}"),
                    target=task.get("target", ""),
                    arm=task.get("arm"),
                    speed=task.get("speed"),
                    correction_mode=task.get("correction_mode", "org"),
                    finish_home=bool(
                        task.get("finish_home", task.get("finfish_home", False))
                    ),
                    fixed_endpoint=task.get("fixed_endpoint", False),
                    approach_count=task.get("approach_count", 0),
                    status_timeout=float(task.get("status_timeout", 2.0)),
                    task_finish_timeout=float(task.get("task_finish_timeout", 60.0)),
                )
            )
        return steps

    @staticmethod
    def _is_home_token(value) -> bool:
        return isinstance(value, str) and value.strip().lower() == "home"

    @staticmethod
    def _home_task_default():
        return [
            {
                "target": "home",
                "action_name": "home",
                "arm": "both",
                "speed": 1.0,
                "correction_mode": "forward",
                "task_finish_timeout": 60.0,
            }
        ]

    def _reset_tf_miss_streak(self):
        self._tf_miss_streak = 0
        self._tf_miss_key = None

    def _activate_state(self, state_name: str):
        tasks = self.status_tasks.get(state_name)
        self._reset_tf_miss_streak()
        if tasks is None:
            if self.last_ignored_state != state_name:
                self.get_logger().info(f"[State] '{state_name}' -> null,跳过")
                self.last_ignored_state = state_name
            self.active_state = None
            self.active_steps = []
            self.active_step_idx = 0
            return

        if self._is_home_token(tasks):
            tasks = self._home_task_default()

        if not isinstance(tasks, list) or len(tasks) == 0:
            self.get_logger().info(f"[State] '{state_name}' -> empty,跳过")
            self.active_state = None
            self.active_steps = []
            self.active_step_idx = 0
            self.last_ignored_state = state_name
            return

        self.active_state = state_name
        self.active_steps = self._build_steps_for_state(state_name, tasks)
        self.active_step_idx = 0
        self.last_ignored_state = None
        self.get_logger().info(
            f"[State] 激活状态 '{state_name}'，共 {len(self.active_steps)} 个动作"
        )

    def _has_actions_for_state(self, state_name: Optional[str]) -> bool:
        if not state_name:
            return False
        tasks = self.status_tasks.get(state_name)
        if self._is_home_token(tasks):
            return True
        return isinstance(tasks, list) and len(tasks) > 0

    def _get_preempt_state(self) -> Optional[str]:
        stable_state = self.status_watcher.get_stable_state()
        if stable_state is None:
            return None
        if stable_state == self.active_state:
            return None
        if not self._has_actions_for_state(stable_state):
            return None

        if 0 <= self.active_step_idx < len(self.active_steps):
            current_step = self.active_steps[self.active_step_idx]
            current_sig = self._step_signature(current_step)
            next_first_sig = self._first_action_signature_of_state(stable_state)
            if next_first_sig is not None and current_sig == next_first_sig:
                self.get_logger().info(
                    f"[Preempt] 忽略状态切换 '{self.active_state}' -> '{stable_state}'，"
                    f"因首动作与当前动作相同: target='{current_step.target}', "
                    f"action='{current_step.action_name}', arm='{current_step.arm}'"
                )
                return None
        return stable_state

    def _wait_until_finished_or_preempt(
        self,
        step: Step,
        silence_after_zero=0.5,
        poll_interval=1,
        allow_preempt=True,
    ):
        start = time.time()
        while rclpy.ok():
            if allow_preempt:
                preempt_state = self._get_preempt_state()
                if preempt_state is not None:
                    next_arm_raw = self._first_action_arm_of_state(preempt_state)
                    next_arm = self._normalize_arm_text(next_arm_raw) if next_arm_raw else ""
                    cur_arm = self._current_running_arm(step)
                    if (
                        self.home_old_arm_on_preempt_switch
                        and cur_arm and next_arm and cur_arm != next_arm
                    ):
                        self.get_logger().warning(
                            f"[Preempt] arm变化: current='{cur_arm}' -> next='{next_arm}'，先执行home"
                        )
                        home_status, _ = self._run_home_and_wait(
                            cur_arm,
                            step,
                            allow_preempt=False,
                        )
                        if home_status != TaskStatus.SUCCESS:
                            self.get_logger().warning(
                                f"[Preempt] home未成功(status={home_status})，本次不切状态"
                            )
                            return home_status, None
                    self.get_logger().warning(
                        f"[Preempt] 执行中检测到新稳定状态 '{preempt_state}'，立即切换"
                    )
                    return TaskStatus.PREEMPT, preempt_state

            if self.task_progress_watcher.is_finished(
                silence_after_zero=silence_after_zero,
                finish_percentage=0.97,
            ):
                self.get_logger().info("[Progress] 当前机械臂动作结束")
                return TaskStatus.SUCCESS, None

            if (time.time() - start) >= step.task_finish_timeout:
                self.get_logger().warning(
                    f"[Progress] 等待 /control/task_percentage 结束超时 action='{step.action_name}'"
                )
                return TaskStatus.TIMEOUT, None
            time.sleep(poll_interval)
        return TaskStatus.STOP, None

    def on_timer(self):
        if not self._control_lock.acquire(blocking=False):
            return
        try:
            stable_state = self.status_watcher.get_stable_state()
            if self.active_state is None:
                if stable_state is None:
                    return
                self._activate_state(stable_state)
                return

            if self.active_step_idx >= len(self.active_steps):
                if self.active_steps and self.active_steps[-1].finish_home:
                    actual_arm = self.last_arm
                    self.get_logger().info(f"[FinishHome] 状态切换前执行home arm='{actual_arm}'")
                    home_status, _ = self._run_home_and_wait(actual_arm, self.active_steps[-1])
                    if home_status != TaskStatus.SUCCESS:
                        self.get_logger().warning(
                            f"[FinishHome] home 执行异常 status='{home_status}' arm='{actual_arm}'"
                        )
                self.get_logger().info(f"[State] '{self.active_state}' 当前动作组已完成")
                self.active_state = None
                self.active_steps = []
                self.active_step_idx = 0
                return

            step = self.active_steps[self.active_step_idx]
            if self._is_home_step(step):
                arm = self.arm_resolver.resolve(step.arm, None)
                home_status, home_preempt_state = self._run_home_and_wait(arm, step)
                if home_status == TaskStatus.SUCCESS:
                    is_last_step = self.active_step_idx == len(self.active_steps) - 1
                    if not is_last_step:
                        self.active_step_idx += 1
                        return
                    self.active_state = None
                    self.active_steps = []
                    self.active_step_idx = 0
                    return
                if home_status == TaskStatus.PREEMPT:
                    old_state = self.active_state
                    self.active_state = None
                    self.active_steps = []
                    self.active_step_idx = 0
                    self.get_logger().warning(
                        f"[Preempt] home 过程中中断状态 '{old_state}'，切换到 '{home_preempt_state}'"
                    )
                    self._activate_state(home_preempt_state)
                return

            frames = self._wait_target_instances_ready(
                target=step.target,
                timeout=2.0,
                settle_time=0.25,
                poll_interval=0.03,
            )
            if not frames:
                miss_key = (
                    self.active_state,
                    self.active_step_idx,
                    normalize_obj_name(step.target),
                    self._normalize_arm_text(step.arm),
                )
                if self._tf_miss_key != miss_key:
                    self._tf_miss_key = miss_key
                    self._tf_miss_streak = 0

                self._tf_miss_streak += 1
                self.get_logger().warning(
                    f"[TF] 未等到 target='{step.target}' 的TF,跳过本周期 "
                    f"(连续{self._tf_miss_streak}/2)"
                )

                if self._tf_miss_streak >= 2:
                    arm = self._normalize_arm_text(self.arm_resolver.resolve(step.arm, None))
                    # arm = self._current_running_arm(step) or self._normalize_arm_text(
                    #     self.arm_resolver.resolve(step.arm, None)
                    # )
                    self.get_logger().warning(
                        f"[TF] 连续2次未获取到 '{step.target}',执行home arm='{arm}'，并重新查询状态"
                    )
                    home_status, _ = self._run_home_and_wait(arm, step, allow_preempt=False)
                    if home_status != TaskStatus.SUCCESS:
                        self.get_logger().warning(
                            f"[TF] 连续丢失后home异常 status='{home_status}' arm='{arm}'"
                        )

                    # 退出当前状态，下一周期重新按稳定状态选择
                    self.active_state = None
                    self.active_steps = []
                    self.active_step_idx = 0
                    self._reset_tf_miss_streak()
                return
            
            self._reset_tf_miss_streak()
            inst = self._select_instance(step, frames)
            if inst is None:
                return

            self.get_logger().info(
                f"[Step] state='{self.active_state}' "
                f"step={self.active_step_idx + 1}/{len(self.active_steps)} "
                f"target='{step.target}' action='{step.action_name}'"
            )

            self.task_progress_watcher.reset()
            self._publish_current_action(step, phase="run")
            status = self._run_step(step, inst)
            if status != TaskStatus.SUCCESS:
                self.get_logger().warning(
                    f"[Step] 执行失败 target='{step.target}' action='{step.action_name}'"
                )
                return

            wait_status, preempt_state = self._wait_until_finished_or_preempt(
                step,
                silence_after_zero=0.5,
                poll_interval=0.05,
                allow_preempt=False,
            )
            if wait_status == TaskStatus.PREEMPT:
                old_state = self.active_state
                self.active_state = None
                self.active_steps = []
                self.active_step_idx = 0
                self.get_logger().warning(
                    f"[Preempt] 中断状态 '{old_state}'，切换到 '{preempt_state}'"
                )
                self._activate_state(preempt_state)
                return

            if wait_status == TaskStatus.TIMEOUT:
                self.get_logger().warning(
                    f"[Step] 机械臂动作结束等待超时 target='{step.target}' action='{step.action_name}'"
                )
                return

            if wait_status != TaskStatus.SUCCESS:
                self.get_logger().warning(f"[Step] 等待动作结束异常 status='{wait_status}'")
                return

            is_last_step = self.active_step_idx == len(self.active_steps) - 1
            if not is_last_step:
                self.active_step_idx += 1
                self.get_logger().info(
                    f"[State] '{self.active_state}' 当前动作完成，继续执行下一个绑定动作 "
                    f"{self.active_step_idx + 1}/{len(self.active_steps)}"
                )
                return

            if step.finish_home:
                actual_arm = self.last_arm
                home_status, home_preempt_state = self._run_home_and_wait(actual_arm, step)
                if home_status == TaskStatus.PREEMPT:
                    old_state = self.active_state
                    self.active_state = None
                    self.active_steps = []
                    self.active_step_idx = 0
                    self.get_logger().warning(
                        f"[Preempt] home 过程中中断状态 '{old_state}'，切换到 '{home_preempt_state}'"
                    )
                    self._activate_state(home_preempt_state)
                    return
                if home_status == TaskStatus.TIMEOUT:
                    self.get_logger().warning(
                        f"[Home] home 动作结束等待超时 arm='{actual_arm}'"
                    )
                    return
                if home_status != TaskStatus.SUCCESS:
                    self.get_logger().warning(
                        f"[Home] home 执行异常 status='{home_status}' arm='{actual_arm}'"
                    )
                    return

            finished_state = self.active_state
            self.get_logger().info(f"[State] '{finished_state}' 全部动作已完成，开始检查状态")
            time.sleep(1)
            next_state = self.status_watcher.wait_stable_state(timeout=0.5, poll_interval=0.1)

            self.active_state = None
            self.active_steps = []
            self.active_step_idx = 0

            if next_state is None:
                self.get_logger().warning("[State] 动作组结束后 0.5s 内未等到稳定状态")
                return
            if next_state != finished_state:
                self.get_logger().info(
                    f"[State] 动作组后检测到状态切换: '{finished_state}' -> '{next_state}'"
                )
            else:
                self.get_logger().info(f"[State] 动作组后稳定状态仍为 '{finished_state}'")
        finally:
            self._control_lock.release()
