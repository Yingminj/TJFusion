# Null Space IK 优化改进文档

## 修改日期
2025-12-22

## 修改概述
将7自由度机械臂的null space（零空间）IK求解方法从基于参考关节角度的方法改为基于几何约束的方法。

## 修改位置
文件: `src/fx_sdk/FxRobot.cpp`
- 第一处: 约1559-1601行
- 第二处: 约1913-1960行

## 原方法 vs 新方法

### 原方法（已废弃）
使用参考关节角度（J1, J2）计算elbow的参考位置：
```cpp
// 通过参考关节角度计算J2的Z轴方向
ref_j2_z_dir[0] = cosvj1 * sinvj2;
ref_j2_z_dir[1] = sinvj1 * sinvj2;
ref_j2_z_dir[2] = cosvj2;

// 计算参考elbow位置
ref_elbow_pos = pa + ref_j2_z_dir * L1;
```

**问题**: 这种方法依赖于预设的参考关节角度，不能自适应地根据末端姿态调整elbow位置。

### 新方法（当前实现）
使用shoulder-to-wrist向量和wrist姿态组成的平面来确定elbow的最优位置：

#### 算法步骤：

1. **定义shoulder-to-wrist向量**
   ```cpp
   shoulder_to_wrist = va2b  // 从shoulder(pa)指向wrist(pb)的向量
   ```

2. **提取wrist的Z轴方向**
   ```cpp
   wrist_z_axis = m_flan的第三列  // 末端执行器的Z轴方向
   ```

3. **计算平面法向量**
   ```cpp
   plane_normal = shoulder_to_wrist × wrist_z_axis
   ```
   这个平面包含了shoulder-to-wrist向量和wrist的Z轴

4. **计算elbow方向向量**
   ```cpp
   ref_vx = plane_normal × shoulder_to_wrist
   ```
   这个向量：
   - 垂直于shoulder-to-wrist向量
   - 位于上述定义的平面内
   - 指向elbow应该所在的方向

5. **计算最终的elbow位置**
   ```cpp
   ref_near_elbow_pos = Core + ref_vx * cyclr
   ```
   其中Core是肩-腕连线上的某个关键点，cyclr是到elbow的距离

## 优势

1. **几何直观性**: elbow位于由shoulder-wrist向量和wrist姿态定义的平面上，更符合人体工学
2. **自适应性**: 自动根据末端执行器的姿态调整elbow位置
3. **避免奇异性**: 更好地利用冗余自由度，减少奇异配置
4. **任务空间优化**: elbow的位置与末端任务直接相关

## 用户自定义方向支持

代码仍然支持用户通过`m_Input_IK_ZSPType`和`m_Input_IK_ZSPPara`指定自定义的elbow方向：

```cpp
if (solve_para->m_Input_IK_ZSPType == FX_PILOT_NSP_TYPES_NEAR_DIR)
{
    // 用户可以指定一个平面法向量
    // 系统会基于这个法向量计算elbow方向
    ref_norm = solve_para->m_Input_IK_ZSPPara
    ref_vx = ref_norm × va2b
}
```

## 数学原理

对于7自由度机械臂，给定末端位置和姿态后，还有1个自由度（null space）。这个自由度表现为elbow可以绕shoulder-wrist轴旋转。

新方法通过以下几何约束确定这个旋转角度：
- Elbow应该位于由shoulder-wrist向量和wrist Z轴张成的平面上
- 这确保了elbow的位置与末端执行器的姿态协调一致

## 测试建议

1. 测试不同的末端姿态下elbow位置的合理性
2. 验证在接近奇异位形时的行为
3. 检查与障碍物避免的兼容性
4. 确认与原有的参考关节角度方法相比的性能改进

## 相关参数

- `pa`: shoulder关节位置
- `pb`: wrist关节位置
- `va2b`: shoulder到wrist的向量
- `m_flan`: 末端执行器的姿态矩阵（4×4齐次变换矩阵）
- `Core`: shoulder-wrist线段上的圆心点
- `cyclr`: 从Core到elbow的距离（null space圆的半径）

## 注意事项

1. 当shoulder-wrist向量与wrist Z轴平行时，叉积可能接近零，需要注意数值稳定性
2. `FX_VectNorm`函数应该能够处理接近零的向量
3. 建议在实际应用中监控`plane_normal`的模长，必要时添加异常处理
