#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import dataclasses
import importlib.util
import re
from pathlib import Path
from typing import Callable, Optional

import numpy as np
from geometry_msgs.msg import TransformStamped


GRIPPER_OPEN = 0.0
GRIPPER_CLOSE = 1.0


def _load_action_handler():
    translator_dir = Path(__file__).resolve().parent
    candidates = [
        translator_dir / "scripts" / "action_handler.py",
        translator_dir / "translator" / "scripts" / "action_handler.py",
        translator_dir / "translator" / "action_handler.py",
    ]

    for path in candidates:
        if not path.is_file():
            continue
        spec = importlib.util.spec_from_file_location("robot_action_action_handler", path)
        if spec is None or spec.loader is None:
            continue
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module.ActionHandler

    raise ImportError(
        "Unable to locate scripts/action_handler.py relative to robot_action.py"
    )


ActionHandler = _load_action_handler()


class TaskStatus:
    UNKNOWN = "unknown"
    SUCCESS = "success"
    FAIL = "fail"
    STOP = "stop"
    TIMEOUT = "timeout"
    PREEMPT = "preempt"


def normalize_obj_name(name: str) -> str:
    s = str(name).strip()
    s = re.sub(r"(?:_\d+)+$", "", s)
    s = re.sub(r"[_\s]+", " ", s)
    return s.strip().lower()


def tf_to_template(tf_name: str) -> str:
    return normalize_obj_name(tf_name)


def normalize_state_text(value: Optional[str]) -> str:
    if not value:
        return ""
    value = str(value).strip().lower()
    value = re.sub(r"^[a-z]\d+\s*:\s*", "", value)
    value = value.replace("“", '"').replace("”", '"').replace("‘", "'").replace("’", "'")
    value = re.sub(r"\s+", " ", value).strip()
    value = re.sub(r"[.。]+$", "", value).strip()
    return value


def normalize_frame_id(fid: str) -> str:
    return str(fid).strip().lstrip("/")


def extract_siglip_payload(payload: dict):
    siglip = payload.get("siglip2")
    if isinstance(siglip, dict):
        return dict(siglip)
    if any(
        key in payload
        for key in ("best_category", "best_similarity", "total_category", "state_list")
    ):
        return payload
    return None


def quaternion_xyzw_to_matrix(x: float, y: float, z: float, w: float) -> np.ndarray:
    norm = np.sqrt(x * x + y * y + z * z + w * w)
    if norm <= 0.0:
        return np.eye(3, dtype=np.float64)

    x /= norm
    y /= norm
    z /= norm
    w /= norm

    xx, yy, zz = x * x, y * y, z * z
    xy, xz, yz = x * y, x * z, y * z
    wx, wy, wz = w * x, w * y, w * z

    return np.array(
        [
            [1.0 - 2.0 * (yy + zz), 2.0 * (xy - wz), 2.0 * (xz + wy)],
            [2.0 * (xy + wz), 1.0 - 2.0 * (xx + zz), 2.0 * (yz - wx)],
            [2.0 * (xz - wy), 2.0 * (yz + wx), 1.0 - 2.0 * (xx + yy)],
        ],
        dtype=np.float64,
    )


def transform_to_matrix(transform) -> np.ndarray:
    mat = np.eye(4, dtype=np.float64)
    t = transform.translation
    q = transform.rotation
    mat[:3, :3] = quaternion_xyzw_to_matrix(
        float(q.x), float(q.y), float(q.z), float(q.w)
    )
    mat[:3, 3] = [float(t.x), float(t.y), float(t.z)]
    return mat


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
    return q.astype(np.float64)


def matrix_to_transform_stamped(
    mat: np.ndarray,
    parent_frame: str,
    child_frame: str,
    stamp,
) -> TransformStamped:
    qx, qy, qz, qw = rotation_matrix_to_quaternion_xyzw(mat[:3, :3])
    msg = TransformStamped()
    msg.header.stamp = stamp
    msg.header.frame_id = parent_frame
    msg.child_frame_id = child_frame
    msg.transform.translation.x = float(mat[0, 3])
    msg.transform.translation.y = float(mat[1, 3])
    msg.transform.translation.z = float(mat[2, 3])
    msg.transform.rotation.x = float(qx)
    msg.transform.rotation.y = float(qy)
    msg.transform.rotation.z = float(qz)
    msg.transform.rotation.w = float(qw)
    return msg


@dataclasses.dataclass
class Step:
    action_name: str
    target: str
    arm: Optional[str]
    speed: Optional[float]
    correction_mode: str
    finish_home: bool
    fixed_endpoint: bool = False
    approach_count: int = 0
    status_timeout: float = 2.0
    task_finish_timeout: float = 60.0


class ArmResolver:
    def __init__(self, get_last_arm: Callable):
        self._get_last_arm = get_last_arm

    def resolve(self, arm_spec: Optional[str], translation=None) -> str:
        if arm_spec == "copy last one":
            return self._get_last_arm() or "right"
        if arm_spec == "correct":
            if translation is not None and translation.y > 0:
                return "left"
            return "right"
        return arm_spec or "right"


class FixedEndpointManager:
    def __init__(self, threshold=0.02):
        self.threshold = threshold
        self._records = {}

    def apply(self, inst, kps, approach_count, pos_current):
        all_poses = kps[0]["poses"]
        execute_poses = all_poses[approach_count:]

        if inst not in self._records:
            self._records[inst] = {
                "execute_abs": execute_poses,
                "pos_start": pos_current.copy(),
            }
            return kps

        rec = self._records[inst]
        pos_start = rec["pos_start"]
        dist = np.linalg.norm(pos_current - pos_start)

        if dist < self.threshold:
            rec["execute_abs"] = execute_poses
            rec["pos_start"] = pos_current.copy()
            return kps

        execute_abs = rec["execute_abs"]
        execute_positions = np.array(
            [[p.position.x, p.position.y, p.position.z] for p in execute_abs]
        )

        nearest_idx = int(np.linalg.norm(execute_positions - pos_current, axis=1).argmin())
        start_from = min(nearest_idx + 1, len(execute_abs) - 1)
        approach_poses = all_poses[:approach_count]

        kps[0]["poses"] = approach_poses + execute_abs[start_from:]
        kps[0]["gripper_value"] = (
            kps[0]["gripper_value"][:approach_count]
            + kps[0]["gripper_value"][approach_count + start_from:]
        )
        kps[0]["time"] = (
            kps[0]["time"][:approach_count]
            + kps[0]["time"][approach_count + start_from:]
        )
        return kps

    def clear(self, inst):
        self._records.pop(inst, None)
