from __future__ import annotations

import math
from typing import Sequence

from fusion_docker.models import Pose


def coerce_pose(values: Sequence[float], label: str = "pose") -> Pose:
    if len(values) != 7:
        raise ValueError(f"{label} must contain 7 values, got {len(values)}")
    return tuple(float(item) for item in values)  # type: ignore[return-value]


def normalize_quaternion(quaternion: Sequence[float]) -> tuple[float, float, float, float]:
    qx, qy, qz, qw = (float(value) for value in quaternion)
    norm = math.sqrt(qx * qx + qy * qy + qz * qz + qw * qw)
    if norm == 0:
        return (0.0, 0.0, 0.0, 1.0)
    return (qx / norm, qy / norm, qz / norm, qw / norm)


def quat_multiply(
    left: Sequence[float],
    right: Sequence[float],
) -> tuple[float, float, float, float]:
    lx, ly, lz, lw = (float(value) for value in left)
    rx, ry, rz, rw = (float(value) for value in right)
    return (
        lw * rx + lx * rw + ly * rz - lz * ry,
        lw * ry - lx * rz + ly * rw + lz * rx,
        lw * rz + lx * ry - ly * rx + lz * rw,
        lw * rw - lx * rx - ly * ry - lz * rz,
    )


def quat_conjugate(quaternion: Sequence[float]) -> tuple[float, float, float, float]:
    qx, qy, qz, qw = (float(value) for value in quaternion)
    return (-qx, -qy, -qz, qw)


def rotate_vector(
    vector: Sequence[float],
    quaternion: Sequence[float],
) -> tuple[float, float, float]:
    vx, vy, vz = (float(value) for value in vector)
    q = normalize_quaternion(quaternion)
    pure = (vx, vy, vz, 0.0)
    rotated = quat_multiply(quat_multiply(q, pure), quat_conjugate(q))
    return (rotated[0], rotated[1], rotated[2])


def compose_pose(base_pose: Pose, relative_pose: Pose) -> Pose:
    bx, by, bz, bqx, bqy, bqz, bqw = base_pose
    rx, ry, rz, rqx, rqy, rqz, rqw = relative_pose

    rotated_translation = rotate_vector((rx, ry, rz), (bqx, bqy, bqz, bqw))
    absolute_translation = (
        bx + rotated_translation[0],
        by + rotated_translation[1],
        bz + rotated_translation[2],
    )
    absolute_rotation = quat_multiply(
        normalize_quaternion((bqx, bqy, bqz, bqw)),
        normalize_quaternion((rqx, rqy, rqz, rqw)),
    )

    return (
        absolute_translation[0],
        absolute_translation[1],
        absolute_translation[2],
        absolute_rotation[0],
        absolute_rotation[1],
        absolute_rotation[2],
        absolute_rotation[3],
    )

