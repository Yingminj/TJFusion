import numpy as np
from scipy.spatial.transform import Rotation as R

def correct_orientation(pos, quat, mode="none", arm=None,
                       z_up=np.array([0., 0., 1.], dtype=float),
                       x_forward=np.array([1., 0., 0.], dtype=float),
                       z_thresh_deg=20,
                       x_thresh_deg=90):
    """
    统一的姿态校正函数
    
    mode 选项:
    - "reverse": 反向模式(Z轴朝下,X轴朝后)
    - "condition_forward": 条件前向模式
    - "forward": 前向模式（返回单位四元数）
    - "none": 不进行校正
    - "disorder": 无序模式,自动识别最接近XY平面的轴作为X轴
    """
    q = np.array(quat, dtype=float)
    if np.linalg.norm(q) < 1e-8:
        return pos, np.array([0.0, 0.0, 0.0, 1.0], dtype=float)
    
    # mode == "none": 直接返回原始姿态
    if mode == "none":
        return pos, q
    
    # mode == "forward": 返回单位四元数
    if mode == "forward":
        R_mat = R.from_quat(q).as_matrix()
        z_axis = R_mat[:, 2]
        z_axis /= np.linalg.norm(z_axis)
        z_up_norm = z_up / np.linalg.norm(z_up)
        cos_z = np.clip(np.dot(z_axis, z_up_norm), -1.0, 1.0)
        angle_z_deg = np.degrees(np.arccos(cos_z))
        
        if angle_z_deg > z_thresh_deg:
            new_z = -z_up_norm
            old_x = R_mat[:, 0]
            new_x = old_x - np.dot(old_x, new_z) * new_z
            if np.linalg.norm(new_x) < 1e-6:
                new_x = np.array([1., 0., 0.]) - np.dot([1., 0., 0.], new_z) * new_z
            new_x /= np.linalg.norm(new_x)
            new_y = np.cross(new_z, new_x)
            new_y /= np.linalg.norm(new_y)
            R_mat = np.column_stack([new_x, new_y, new_z])
        
        x_axis = R_mat[:, 0]
        x_axis /= np.linalg.norm(x_axis)
        x_forward_norm = x_forward / np.linalg.norm(x_forward)
        cos_x = np.clip(np.dot(x_axis, x_forward_norm), -1.0, 1.0)
        angle_x_deg = np.degrees(np.arccos(cos_x))
        
        if angle_x_deg > x_thresh_deg:
            new_x = x_forward.copy()
            new_z = R_mat[:, 2]
            new_y = np.cross(new_z, new_x)
            new_y /= np.linalg.norm(new_y)
            new_z = np.cross(new_x, new_y)
            new_z /= np.linalg.norm(new_z)
        
        return pos, np.array([0.0, 0.0, 0.0, 1.0], dtype=float)

    # mode == "disorder": 无序模式 - 自动识别最接近XY平面的轴作为X轴
    if mode == "disorder":
        R_mat = R.from_quat(q).as_matrix()
        
        # 获取当前的三个轴
        axis_x = R_mat[:, 0]
        axis_y = R_mat[:, 1]
        axis_z = R_mat[:, 2]
        
        # 归一化
        axis_x /= np.linalg.norm(axis_x)
        axis_y /= np.linalg.norm(axis_y)
        axis_z /= np.linalg.norm(axis_z)
        
        # 计算每个轴与Z轴([0,0,1])的夹角（范围 [0, 180]）
        z_standard = np.array([0., 0., 1.])
        
        angle_x_to_z = np.degrees(np.arccos(np.clip(np.dot(axis_x, z_standard), -1.0, 1.0)))
        angle_y_to_z = np.degrees(np.arccos(np.clip(np.dot(axis_y, z_standard), -1.0, 1.0)))
        angle_z_to_z = np.degrees(np.arccos(np.clip(np.dot(axis_z, z_standard), -1.0, 1.0)))
        
        
        # 找出最接近XY平面的轴（与Z轴夹角最接近90°）
        angles = [angle_x_to_z, angle_y_to_z, angle_z_to_z]
        distances_to_90 = [abs(a - 90.0) for a in angles]
        min_dist = min(distances_to_90)
        tol_deg = 10.0  # 容差：视为并列接近90°
        candidates = [i for i, d in enumerate(distances_to_90) if d - min_dist <= tol_deg]
        axes = [axis_x, axis_y, axis_z]

        if len(candidates) == 1:
            selected_idx = candidates[0]
        else:
            # 并列时，选与 [1,0,0] 夹角最小的作为 X 轴
            x_forward_norm = np.array([1., 0., 0.])
            angle_to_x_forward = []
            for idx in candidates:
                a = axes[idx]
                a = a / np.linalg.norm(a)
                cos_val = np.clip(np.dot(a, x_forward_norm), -1.0, 1.0)
                angle_to_x_forward.append(np.degrees(np.arccos(cos_val)))
            selected_idx = candidates[int(np.argmin(angle_to_x_forward))]
        
        selected_axis = axes[selected_idx]
        
        
        # 步骤1：直接设置Z轴为[0,0,1]
        new_z = np.array([0., 0., 1.])
        
        # 步骤2：投影选中的轴到XY平面作为新X轴
        new_x = selected_axis - np.dot(selected_axis, new_z) * new_z
        new_x_norm = np.linalg.norm(new_x)
        
        if new_x_norm < 1e-6:
            # 选中的轴平行于Z轴，选择默认方向[1,0,0]
            new_x = np.array([1., 0., 0.])
        else:
            new_x /= new_x_norm
        
        # 步骤3：用右手法则计算Y轴：Y = Z × X
        new_y = np.cross(new_z, new_x)
        new_y /= np.linalg.norm(new_y)
        
        # 组合旋转矩阵
        R_mat = np.column_stack([new_x, new_y, new_z])
        
        # 步骤4：检测X轴方向，如果与[1,0,0]夹角过大则反向
        x_axis_final = R_mat[:, 0]
        x_forward_norm = np.array([1., 0., 0.])
        cos_x = np.clip(np.dot(x_axis_final, x_forward_norm), -1.0, 1.0)
        angle_x_deg = np.degrees(np.arccos(cos_x))
        if angle_x_deg > x_thresh_deg:
            # 绕Z轴旋转180度
            rotation_matrix_180 = np.array([
                [-1., 0., 0.],
                [0., -1., 0.],
                [0., 0., 1.]
            ])
            R_mat = R_mat @ rotation_matrix_180
        
        quat_corrected = R.from_matrix(R_mat).as_quat()
        return pos, quat_corrected

    # mode == "reverse": Z轴朝上，X轴根据手臂方向调整
    if mode == "reverse":
        R_mat = R.from_quat(q).as_matrix()
        z_axis = R_mat[:, 2]
        z_axis /= np.linalg.norm(z_axis)
        z_up_norm = z_up / np.linalg.norm(z_up)
        cos_z = np.clip(np.dot(z_axis, z_up_norm), -1.0, 1.0)
        angle_z_deg = np.degrees(np.arccos(cos_z))
        if angle_z_deg > z_thresh_deg:
            new_z = z_up.copy()
            old_x = R_mat[:, 0]
            new_x = old_x - np.dot(old_x, new_z) * new_z
            new_x /= np.linalg.norm(new_x)
            new_y = np.cross(new_z, new_x)
            new_y /= np.linalg.norm(new_y)
            R_mat = np.column_stack([new_x, new_y, new_z])
        x_axis = R_mat[:, 0]
        x_axis /= np.linalg.norm(x_axis)
        x_forward_norm = x_forward / np.linalg.norm(x_forward)
        cos_x = np.clip(np.dot(x_axis, x_forward_norm), -1.0, 1.0)
        angle_x_deg = np.degrees(np.arccos(cos_x)) 
        if angle_x_deg > x_thresh_deg:
            new_x = -x_axis
            new_z = R_mat[:, 2]
            new_y = np.cross(new_z, new_x)
            new_y /= np.linalg.norm(new_y)
            new_z = np.cross(new_x, new_y)
            new_z /= np.linalg.norm(new_z)
            R_mat = np.column_stack([new_x, new_y, new_z])
        x_axis_final = R_mat[:, 0]
        x_axis_final /= np.linalg.norm(x_axis_final)
        x_forward_norm = x_forward / np.linalg.norm(x_forward)
        cross_prod = np.cross(x_forward_norm, x_axis_final)
        rotation_direction = cross_prod[2]  # 正数表示逆时针，负数表示顺时针
        
        if arm == "right":
            if rotation_direction < 0: 
                # 创建绕 z 轴逆时针 90 度的旋转矩阵
                angle_rad = np.pi / 2  # 90 度
                rotation_matrix = np.array([
                    [np.cos(angle_rad), -np.sin(angle_rad), 0],
                    [np.sin(angle_rad), np.cos(angle_rad), 0],
                    [0, 0, 1]
                ])
                # 将旋转矩阵应用到 R_mat
                R_mat = R_mat @ rotation_matrix
                # 提取旋转后的坐标轴
                new_x = R_mat[:, 0]
                new_y = R_mat[:, 1]
                new_z = R_mat[:, 2]
        elif arm == "left":
            if rotation_direction > 0:
                print(f"[DEBUG] Left arm: rotating x CW 90 degrees")
                # 创建绕 z 轴顺时针 90 度的旋转矩阵
                angle_rad = -np.pi / 2  # -90 度（顺时针）
                rotation_matrix = np.array([
                    [np.cos(angle_rad), -np.sin(angle_rad), 0],
                    [np.sin(angle_rad), np.cos(angle_rad), 0],
                    [0, 0, 1]
                ])
                # 将旋转矩阵应用到 R_mat
                R_mat = R_mat @ rotation_matrix
                # 提取旋转后的坐标轴
                new_x = R_mat[:, 0]
                new_y = R_mat[:, 1]
                new_z = R_mat[:, 2]

        quat_corrected = R.from_matrix(R_mat).as_quat()

        return pos, quat_corrected

    return pos, quat_corrected