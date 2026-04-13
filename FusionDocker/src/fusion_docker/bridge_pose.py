from __future__ import annotations

from typing import Any

import numpy as np


def rotation_matrix_to_quaternion_xyzw(rot: np.ndarray) -> np.ndarray:
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


def pose_item_to_pose7(pose_item: Any) -> np.ndarray | None:
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
        quat_xyzw = rotation_matrix_to_quaternion_xyzw(rot_matrix @ rot_fix)
        return np.concatenate([xyz, quat_xyzw], axis=0).astype(np.float32)
    if arr.ndim == 3 and arr.shape[0] == 1 and arr.shape[1:] == (4, 4):
        return pose_item_to_pose7(arr[0])
    return None


def build_tf_payload_from_flowpose_result(
    payload: dict[str, Any] | None,
    *,
    frame_id: str = "camera_rgb_link",
) -> list[dict[str, Any]]:
    if not isinstance(payload, dict) or payload.get("status") != "ok":
        return []

    objects = payload.get("objects", [])
    if not isinstance(objects, list):
        return []

    class_counts: dict[str, int] = {}
    transforms: list[dict[str, Any]] = []
    for index, obj in enumerate(objects, start=1):
        if not isinstance(obj, dict):
            continue
        pose7 = pose_item_to_pose7(obj.get("pose"))
        if pose7 is None:
            continue

        class_name = str(obj.get("name", "")).strip()
        if class_name:
            class_counts[class_name] = class_counts.get(class_name, 0) + 1
            child_frame_id = f"{class_name}_{class_counts[class_name]}"
        else:
            child_frame_id = f"obj_{index}"

        transforms.append(
            {
                "frame_id": frame_id,
                "child_frame_id": child_frame_id,
                "translation": {
                    "x": float(pose7[0]),
                    "y": float(pose7[1]),
                    "z": float(pose7[2]),
                },
                "rotation": {
                    "x": float(pose7[3]),
                    "y": float(pose7[4]),
                    "z": float(pose7[5]),
                    "w": float(pose7[6]),
                },
            }
        )
    return transforms
