import numpy as np
from scipy.spatial.transform import Rotation as R

def clamp(x, xmin, xmax):
    return max(xmin, min(x, xmax))

def limit_rotation_xyz(R_target,
                       roll_lim,
                       pitch_lim,
                       yaw_lim,
                       order='zyx'):
    """
    R_target : scipy Rotation
    roll_lim  = (min, max)  rad
    pitch_lim = (min, max)  rad
    yaw_lim   = (min, max)  rad
    """

    # 1. rotation -> euler
    roll, pitch, yaw = R_target.as_euler(order, degrees=False)

    # 2. clamp each axis
    roll  = clamp(roll,  roll_lim[0],  roll_lim[1])
    pitch = clamp(pitch, pitch_lim[0], pitch_lim[1])
    yaw   = clamp(yaw,   yaw_lim[0],   yaw_lim[1])

    # 3. euler -> rotation
    return R.from_euler(order, [roll, pitch, yaw], degrees=False)


# =======================
# 测试
# =======================

# 原始目标 rotation（故意给一个超限的）
R_target = R.from_euler(
    'zyx',
    [np.deg2rad(120),   # yaw
     np.deg2rad(50),    # pitch
     np.deg2rad(80)],   # roll
    degrees=False
)

# 设置限制（±）
roll_limit  = (np.deg2rad(-45), np.deg2rad(45))
pitch_limit = (np.deg2rad(-30), np.deg2rad(30))
yaw_limit   = (np.deg2rad(-90), np.deg2rad(90))

R_limited = limit_rotation_xyz(
    R_target,
    roll_limit,
    pitch_limit,
    yaw_limit
)

# 打印对比
print("Original Euler (deg):",
      np.rad2deg(R_target.as_euler('zyx')))
print("Limited  Euler (deg):",
      np.rad2deg(R_limited.as_euler('zyx')))
