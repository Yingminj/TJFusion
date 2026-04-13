# 用于描述一个关键点
string name              # 关键点名称
string arm               # 使用的机械臂，left/right

# 位姿信息
geometry_msgs/Pose[] poses

# 约束和速度
float32[3] constraints   # xyz旋转约束
float32 speed            # 移动速度

# 手爪控制
float32[] gripper_value    # 手爪开闭程度

float32[] time
