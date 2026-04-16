import numpy as np
import matplotlib.pyplot as plt
from scipy.interpolate import splrep, splev
# 四条二次曲线，描述四个角的干涉边界 (a, b, c)
# y = a*x^2 + b*x + c
curves = [
    (0.0084307, -1.3321, 100.0),   # upper-left boundary
    (0.014684, 1.8496, 100.0),     # upper-right boundary
    (-0.021823, -2.5292, -107.0),  # lower-left boundary
    (-0.018004, 2.3205, -100.0)    # lower-right boundary
]

# Joint 6 & 7 limits
joint6_min, joint6_max = -60, 60
joint7_min, joint7_max = -90, 90

# Sampling x range (joint6)
x = np.linspace(joint6_min, joint6_max, 1000)

# Compute each boundary curve
y_upper_right = curves[0][0]*x**2 + curves[0][1]*x + curves[0][2]
y_upper_left = curves[1][0]*x**2 + curves[1][1]*x + curves[1][2]
y_lower_left = curves[2][0]*x**2 + curves[2][1]*x + curves[2][2]
y_lower_right = curves[3][0]*x**2 + curves[3][1]*x + curves[3][2]

a, b, c = curves[0]
c = c - joint7_max  # Adjust c for intersection with joint7_max line

D = b**2 - 4*a*c  # discriminant

if D < 0:
    print("No real roots.")
elif D == 0:
    x = -b / (2*a)
    print("One real root:", x)
else:
    x1 = (-b + np.sqrt(D)) / (2*a)
    x2 = (-b - np.sqrt(D)) / (2*a)
    # print("Roots:", x1, x2)
    y_innersect1 = (x2, joint7_max)




a, b, c = curves[1]
c = c - joint7_max  # Adjust c for intersection with joint7_max line

D = b**2 - 4*a*c  # discriminant

if D < 0:
    print("No real roots.")
elif D == 0:
    x = -b / (2*a)
    print("One real root:", x)
else:
    x1 = (-b + np.sqrt(D)) / (2*a)
    x2 = (-b - np.sqrt(D)) / (2*a)
    # print("Roots:", x1, x2)
    y_innersect2 = (x1, joint7_max)


num_points = 1000  # number of points you want
x_points = np.linspace(y_innersect2[0], y_innersect1[0], num_points)
y_points = np.full_like(x_points, joint7_max)

# combine into (x, y) pairs
points_upper = np.column_stack((x_points, y_points))



a, b, c = curves[2]
c = c - joint7_min  # Adjust c for intersection with joint7_min line

D = b**2 - 4*a*c  # discriminant

if D < 0:
    print("No real roots.")
elif D == 0:
    x = -b / (2*a)
    print("One real root:", x)
else:
    x1 = (-b + np.sqrt(D)) / (2*a)
    x2 = (-b - np.sqrt(D)) / (2*a)
    # print("Roots:", x1, x2)
    y_innersect3 = (x2, joint7_min)

a, b, c = curves[3]
c = c - joint7_min  # Adjust c for intersection with joint7_min line

D = b**2 - 4*a*c  # discriminant

if D < 0:
    print("No real roots.")
elif D == 0:
    x = -b / (2*a)
    print("One real root:", x)
else:
    x1 = (-b + np.sqrt(D)) / (2*a)
    x2 = (-b - np.sqrt(D)) / (2*a)
    print("Roots:", x1, x2)
    y_innersect4 = (x1, joint7_min)


x_points = np.linspace(y_innersect3[0], y_innersect4[0], num_points)
y_points = np.full_like(x_points, joint7_min)

# combine into (x, y) pairs
points_lower = np.column_stack((x_points, y_points))





# num_points = 50  # number of points you want
# x_points = np.linspace(x1, x2, num_points)
# y_points = np.full_like(x_points, joint7_min)

# # combine into (x, y) pairs
# points_lower = np.column_stack((x_points, y_points))

y_upper_right_lim = (joint6_max, y_upper_right[-1])
y_upper_left_lim = (joint6_min, y_upper_left[0])
y_lower_left_lim = (joint6_min, y_lower_left[0])
y_lower_right_lim = (joint6_max, y_lower_right[-1])


# num_points = 100  # number of points you want
y_points = np.linspace(y_upper_left_lim[1], y_lower_left_lim[1], num_points)
x_points = np.full_like(y_points, joint6_min)
# combine into (x, y) pairs
points_left = np.column_stack((x_points, y_points))

y_points = np.linspace(y_upper_right_lim[1], y_lower_right_lim[1], num_points)
x_points = np.full_like(y_points, joint6_max)
# combine into (x, y) pairs
points_right = np.column_stack((x_points, y_points))

mask = y_upper_right <= joint7_max
y_upper_right_trimed = y_upper_right[mask]
x_trimmed1 = x[mask]
points_upper_right = np.column_stack((x_trimmed1, y_upper_right_trimed))

mask = y_upper_left <= joint7_max
y_upper_left_trimed = y_upper_left[mask]
x_trimmed2 = x[mask]
points_upper_left = np.column_stack((x_trimmed2, y_upper_left_trimed))

mask = y_lower_left >= joint7_min
y_lower_left_trimed = y_lower_left[mask]
x_trimmed3 = x[mask]
points_lower_left = np.column_stack((x_trimmed3, y_lower_left_trimed))

mask = y_lower_right >= joint7_min
y_lower_right_trimed = y_lower_right[mask]
x_trimmed4 = x[mask]
points_lower_right = np.column_stack((x_trimmed4, y_lower_right_trimed))

points_all = np.vstack((points_upper, points_lower, points_left, points_right,
                        points_upper_right, points_upper_left,
                        points_lower_left, points_lower_right))


# points_all: (N,2)
x = points_all[:,0]
y = points_all[:,1]

# 极坐标
theta = np.arctan2(y, x)  # [-pi, pi]
r = np.sqrt(x**2 + y**2)

# 对 theta 离散化，找每个角度的最大半径
theta_bins = np.linspace(-np.pi, np.pi, 360)
r_max = np.full_like(theta_bins, np.nan)

for i, t in enumerate(theta_bins):
    mask = (theta >= t) & (theta < t + (2*np.pi/360))
    if np.any(mask):
        r_max[i] = np.max(r[mask])*0.95
nan_mask = np.isnan(r_max)
r_max[nan_mask] = np.interp(theta_bins[nan_mask], theta_bins[~nan_mask], r_max[~nan_mask])
import yaml

# 假设 r_max 已经计算好了
r_max = r_max.tolist()  # 转成列表，yaml可读

# 保存到 YAML 文件
with open('r_max.yaml', 'w') as f:
    yaml.dump({'r_max': r_max}, f, default_flow_style=True)

print("Saved r_max to r_max.yaml")

# 转回笛卡尔坐标画边界
x_boundary = r_max * np.cos(theta_bins)
y_boundary = r_max * np.sin(theta_bins)

plt.figure(figsize=(6,6))
plt.plot(points_all[:,0], points_all[:,1], 'o', label='Points')
plt.plot(x_boundary, y_boundary, 'o', label='Polar Boundary')

plt.axis('equal')
plt.grid(True)
plt.legend()
plt.xlabel('j6')
plt.ylabel('j7')
plt.title('2D Points and Polar Boundary')
plt.show()
# # Plot setup
# plt.figure(figsize=(12, 8))

# # Fill allowed region
# # plt.fill_between(x, y_lower, y_upper, color='orange', alpha=0.3, label='Allowed region')

# # Plot the four interference boundaries
# # plt.plot(x_trimmed1, y_upper_right_trimed, 'r--', linewidth=2, label='Upper-right interference')
# # plt.plot(x_trimmed2, y_upper_left_trimed, 'g--', linewidth=2, label='Upper-left interference')
# # plt.plot(x_trimmed3, y_lower_left_trimed, 'b--', linewidth=2, label='Lower-left interference')
# # plt.plot(x_trimmed4, y_lower_right_trimed, 'm--', linewidth=2, label='Lower-right interference')

# # plt.scatter(*y_upper_right_lim, color='r', s=50)
# # plt.scatter(*y_upper_left_lim, color='g', s=50)
# # plt.scatter(*y_lower_left_lim, color='b', s=50)
# # plt.scatter(*y_lower_right_lim, color='m', s=50)

# # plt.scatter(*y_innersect1, color='k', s=100, marker='x')
# # plt.scatter(*y_innersect2, color='k', s=100, marker='x')
# # plt.scatter(*y_innersect3, color='k', s=100, marker='x')
# # plt.scatter(*y_innersect4, color='k', s=100, marker='x')

# # Draw the hard joint limits
# plt.axvline(joint6_min, color='gray', linestyle='--', linewidth=1.5, label=f'Joint6 min ({joint6_min}°)')
# plt.axvline(joint6_max, color='gray', linestyle='--', linewidth=1.5, label=f'Joint6 max ({joint6_max}°)')
# plt.axhline(joint7_min, color='gray', linestyle='--', linewidth=1.5, label=f'Joint7 min ({joint7_min}°)')
# plt.axhline(joint7_max, color='gray', linestyle='--', linewidth=1.5, label=f'Joint7 max ({joint7_max}°)')

# # plt.scatter(points_upper[:, 0], points_upper[:, 1], color='r', s=10) 
# # plt.scatter(points_lower[:, 0], points_lower[:, 1], color='b', s=10)
# # plt.scatter(points_left[:, 0], points_left[:, 1], color='g', s=10)
# # plt.scatter(points_right[:, 0], points_right[:, 1], color='m', s=10)
# # plt.scatter(points_upper_right[:, 0], points_upper_right[:, 1], color='orange', s=5)
# # plt.scatter(points_upper_left[:, 0], points_upper_left[:, 1], color='orange', s=5)
# # plt.scatter(points_lower_left[:, 0], points_lower_left[:, 1], color='orange', s=5)
# # plt.scatter(points_lower_right[:, 0], points_lower_right[:, 1], color='orange', s=5)
# plt.scatter(points_all[:, 0], points_all[:, 1], color='orange', s=5)

# # Axis and labels
# plt.xlabel('Joint 6 (°)', fontsize=12)
# plt.ylabel('Joint 7 (°)', fontsize=12)
# plt.title('Joint 6–7 Coupled Motion Limits (Allowed Region in Orange)', fontsize=14, fontweight='bold')
# plt.legend(fontsize=9, loc='best')
# plt.grid(True, alpha=0.3)

# # Limits
# plt.xlim(joint6_min - 10, joint6_max + 10)
# plt.ylim(joint7_min - 10, joint7_max + 10)

# plt.tight_layout()
# plt.show()
