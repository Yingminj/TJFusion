#!/usr/bin/env python3
import os
from typing import List

import mujoco
import mujoco.viewer
import rclpy
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from sensor_msgs.msg import JointState
from std_msgs.msg import Int16MultiArray
from marvin_msgs.msg import Jointcmd, Jointfeedback


class MujocoBridgeNode(Node):
    def __init__(self) -> None:
        super().__init__("mujoco_node")

        self.declare_parameter(
            "xml_path",
            "/ros2_ws/src/marvin_description_new/mjcf/marvin_pro/marvin_pro_mink_with_gripper.xml",
        )
        self.declare_parameter("rate_hz", 200.0)
        self.declare_parameter("publish_arm_state", True)
        self.declare_parameter("render", True)

        self._xml_path = self.get_parameter("xml_path").get_parameter_value().string_value
        self._rate_hz = float(self.get_parameter("rate_hz").get_parameter_value().double_value)
        self._publish_arm_state = bool(
            self.get_parameter("publish_arm_state").get_parameter_value().bool_value
        )
        self._render = bool(self.get_parameter("render").get_parameter_value().bool_value)

        if not os.path.isfile(self._xml_path):
            raise FileNotFoundError(f"MJCF not found: {self._xml_path}")

        self._model = mujoco.MjModel.from_xml_path(self._xml_path)
        self._data = mujoco.MjData(self._model)
        self._viewer = None

        self._arm_joint_names = [
            "Arm_L1_Joint",
            "Arm_L2_Joint",
            "Arm_L3_Joint",
            "Arm_L4_Joint",
            "Arm_L5_Joint",
            "Arm_L6_Joint",
            "Arm_L7_Joint",
            "Arm_R1_Joint",
            "Arm_R2_Joint",
            "Arm_R3_Joint",
            "Arm_R4_Joint",
            "Arm_R5_Joint",
            "Arm_R6_Joint",
            "Arm_R7_Joint",
        ]
        self._gripper_joint_names = [
            "left_gripper_left_finger_joint",
            "left_gripper_right_finger_joint",
            "right_gripper_left_finger_joint",
            "right_gripper_right_finger_joint",
        ]
        self._state_joint_names = self._arm_joint_names + self._gripper_joint_names

        self._joint_qpos_idx, self._joint_qvel_idx, self._joint_ids = self._resolve_joint_indices(
            self._arm_joint_names
        )
        (
            self._state_qpos_idx,
            self._state_qvel_idx,
            self._state_joint_ids,
        ) = self._resolve_joint_indices(self._state_joint_names)
        self._actuator_ids = self._resolve_actuator_ids(self._arm_joint_names, self._joint_ids)

        self._targets_left = self._get_initial_targets(self._joint_qpos_idx[:7])
        self._targets_right = self._get_initial_targets(self._joint_qpos_idx[7:])

        self._fb_pub = self.create_publisher(
            Jointfeedback, "info/joint_feedback", qos_profile_sensor_data
        )
        self._joint_state_pub = self.create_publisher(
            JointState, "joint_states", qos_profile_sensor_data
        )
        self._arm_state_pub = self.create_publisher(Int16MultiArray, "info/arm_state", 10)

        self.create_subscription(
            Jointcmd, "control/joint_cmd_A", self._on_cmd_left, qos_profile_sensor_data
        )
        self.create_subscription(
            Jointcmd, "control/joint_cmd_B", self._on_cmd_right, qos_profile_sensor_data
        )

        if self._rate_hz <= 0:
            raise ValueError("rate_hz must be > 0")

        self._substeps = max(
            1, int(round((1.0 / self._rate_hz) / float(self._model.opt.timestep)))
        )
        self.get_logger().info(
            f"MuJoCo loaded: {self._xml_path} | rate_hz={self._rate_hz} | substeps={self._substeps}"
        )

        if self._render:
            self._viewer = mujoco.viewer.launch_passive(self._model, self._data)
            self.get_logger().info("MuJoCo viewer launched (passive mode)")

        self._timer = self.create_timer(1.0 / self._rate_hz, self._step)

    def _resolve_joint_indices(self, names: List[str]):
        qpos_idx = []
        qvel_idx = []
        joint_ids = []
        for name in names:
            jid = mujoco.mj_name2id(self._model, mujoco.mjtObj.mjOBJ_JOINT, name)
            if jid < 0:
                raise RuntimeError(f"Joint not found in MJCF: {name}")
            joint_ids.append(int(jid))
            qpos_idx.append(int(self._model.jnt_qposadr[jid]))
            qvel_idx.append(int(self._model.jnt_dofadr[jid]))
        return qpos_idx, qvel_idx, joint_ids

    def _resolve_actuator_ids(self, names: List[str], joint_ids: List[int]):
        actuator_ids = []
        for name, joint_id in zip(names, joint_ids):
            aid = mujoco.mj_name2id(self._model, mujoco.mjtObj.mjOBJ_ACTUATOR, name)
            if aid < 0:
                matches = [
                    idx
                    for idx in range(self._model.nu)
                    if int(self._model.actuator_trnid[idx][0]) == joint_id
                ]
                if not matches:
                    raise RuntimeError(
                        f"Actuator not found for joint '{name}' (id {joint_id})"
                    )
                aid = matches[0]
            actuator_ids.append(int(aid))
        return actuator_ids

    def _get_initial_targets(self, qpos_indices: List[int]):
        return [float(self._data.qpos[i]) for i in qpos_indices]

    def _on_cmd_left(self, msg: Jointcmd) -> None:
        if len(msg.positions) != 7:
            self.get_logger().warn("control/joint_cmd_A expected 7 positions")
            return
        self._targets_left = list(msg.positions)

    def _on_cmd_right(self, msg: Jointcmd) -> None:
        if len(msg.positions) != 7:
            self.get_logger().warn("control/joint_cmd_B expected 7 positions")
            return
        self._targets_right = list(msg.positions)

    def _apply_controls(self) -> None:
        targets = self._targets_left + self._targets_right
        for idx, aid in enumerate(self._actuator_ids):
            desired = float(targets[idx])
            if self._model.actuator_ctrlrange is not None and self._model.actuator_ctrlrange.size:
                ctrl_min, ctrl_max = self._model.actuator_ctrlrange[aid]
                if desired < ctrl_min:
                    desired = float(ctrl_min)
                elif desired > ctrl_max:
                    desired = float(ctrl_max)
            self._data.ctrl[aid] = desired

    def _publish_feedback(self) -> None:
        stamp = self.get_clock().now().to_msg()

        msg = Jointfeedback()
        msg.header.stamp = stamp
        positions = []
        velocities = []
        efforts = []
        for qpos_i, qvel_i in zip(self._joint_qpos_idx, self._joint_qvel_idx):
            positions.append(float(self._data.qpos[qpos_i]))
            velocities.append(float(self._data.qvel[qvel_i]))
            if qvel_i < len(self._data.qfrc_actuator):
                efforts.append(float(self._data.qfrc_actuator[qvel_i]))
            else:
                efforts.append(0.0)
        msg.positions = positions
        msg.velocities = velocities
        msg.efforts = efforts
        self._fb_pub.publish(msg)

        joint_state_msg = JointState()
        joint_state_msg.header.stamp = stamp
        joint_state_msg.name = list(self._state_joint_names)
        joint_state_msg.position = [
            float(self._data.qpos[i]) for i in self._state_qpos_idx
        ]
        joint_state_msg.velocity = [
            float(self._data.qvel[i]) for i in self._state_qvel_idx
        ]
        self._joint_state_pub.publish(joint_state_msg)

        if self._publish_arm_state:
            state_msg = Int16MultiArray()
            state_msg.data = [3, 3]
            self._arm_state_pub.publish(state_msg)

    def _step(self) -> None:
        self._apply_controls()
        for _ in range(self._substeps):
            mujoco.mj_step(self._model, self._data)
        if self._viewer is not None:
            self._viewer.sync()
        self._publish_feedback()


def main() -> None:
    rclpy.init()
    node = MujocoBridgeNode()
    try:
        rclpy.spin(node)
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
