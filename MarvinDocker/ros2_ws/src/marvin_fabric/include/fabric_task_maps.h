#pragma once
#include <Eigen/Dense>
using namespace Eigen;

// --- Task Maps ---

inline Eigen::VectorXd upper_joint_limit_task_map(const Eigen::VectorXd &qpos, const Eigen::VectorXd &max_pos_limit)
{
    // upper_limit - qpos
    return max_pos_limit - qpos;
}

inline Eigen::VectorXd lower_joint_limit_task_map(const Eigen::VectorXd &qpos, const Eigen::VectorXd &min_pos_limit)
{
    // qpos - lower_limit
    return qpos - min_pos_limit;
}

inline Eigen::VectorXd default_config_task_map(const Eigen::VectorXd &qpos, const Eigen::VectorXd &default_config)
{
    // qpos - default_config
    return qpos - default_config;
}

inline Eigen::VectorXd attractor_task_map(const Eigen::VectorXd &x, const Eigen::VectorXd &goal_pos)
{
    // x: 6D [pos(3), rot_vec(3)]
    // returns 6D error: [pos_err; rot_err]
    // fully differentiable in PyTorch
    Eigen::VectorXd pos = x.head<3>();
    Eigen::VectorXd pos_err = pos - goal_pos.head<3>();
    return pos_err;
}
// inline  Eigen::VectorXd direction_task_map(const Eigen::VectorXd &x, const Eigen::VectorXd &goal_pos)
// {
//     // x: 6D [pos(3), rot_vec(3)]
//     // returns 6D error: [pos_err; rot_err]
//     // fully differentiable in PyTorch
//     Eigen::VectorXd pos = x.head<3>();
//     Eigen::VectorXd pos_err = pos - goal_pos.head<3>();
//     return pos_err;
// }

inline Eigen::VectorXd obstacle_avoidance_task_map(
    const Eigen::Vector3d &x,
    const Eigen::Vector3d &obs_pos,
    double obs_radius)
{
    Eigen::Vector3d diff = obs_pos - x;
    double norm = diff.norm();
    if (norm < 1e-8)
        norm = 1e-8;

    Eigen::VectorXd f(1);
    f(0) = norm / obs_radius - 1.0;
    return f;
}

inline Eigen::VectorXd floor_repulsion_task_map(
    const Eigen::Vector3d &x,
    const double floor_height,
    double obs_radius)
{
    float norm = x[2] - floor_height;

    if (norm < 1e-8)
        norm = 1e-8;

    Eigen::VectorXd f(1);
    f(0) = norm / obs_radius - 1.0;
    return f;
}

// --- Task Map Jacobians ---
inline Eigen::MatrixXd upper_joint_limit_jacobian(const Eigen::VectorXd &qpos)
{
    // Jacobian is -I
    return -Eigen::MatrixXd::Identity(qpos.size(), qpos.size());
}
inline Eigen::MatrixXd lower_joint_limit_jacobian(const Eigen::VectorXd &qpos)
{
    // Jacobian is I
    return Eigen::MatrixXd::Identity(qpos.size(), qpos.size());
}
inline Eigen::MatrixXd default_config_jacobian(const Eigen::VectorXd &qpos)
{
    // Jacobian is I
    return Eigen::MatrixXd::Identity(qpos.size(), qpos.size());
}
inline Eigen::MatrixXd attractor_task_jacobian(const Eigen::VectorXd &x)
{
    Eigen::MatrixXd J = Eigen::MatrixXd::Identity(x.size(), x.size());
    return J;
}
inline Eigen::MatrixXd obstacle_avoidance_task_jacobian(
    const Eigen::VectorXd &x,
    const Eigen::Vector3d &obs_pos,
    double obs_radius)
{
    Eigen::Vector3d diff = obs_pos - x.head<3>();
    double norm = diff.norm();
    if (norm < 1e-8)
        norm = 1e-8;

    Eigen::RowVector3d J_x = -diff.transpose() / (obs_radius * norm);
    return J_x; // (1x3)
}

inline Eigen::MatrixXd floor_avoidance_task_jacobian(
    const Eigen::VectorXd &x)
{
    Eigen::RowVector3d J_x;
    J_x << 0.0, 0.0, 1.0;
    return J_x; // (1x3)
}

// --- Joint Limit Fabrics ---
void joint_limit_fabric(
    const Eigen::VectorXd &pos,
    const Eigen::VectorXd &vel,
    Eigen::MatrixXd &metric,
    Eigen::VectorXd &accel);

    void joint_damping_fabric(
    const Eigen::VectorXd &vel,
    Eigen::MatrixXd &metric,
    Eigen::VectorXd &accel);
// --- Default Config Fabrics ---
void default_config_fabric(
    const Eigen::VectorXd &pos,
    Eigen::MatrixXd &metric,
    Eigen::VectorXd &accel);
void attractor_task_fabric(
    const Eigen::VectorXd &pos,
    const Eigen::VectorXd &vel,
    Eigen::MatrixXd &metric,
    Eigen::VectorXd &accel,
const double attractor_strength = 50.0);

void dir_task_fabric(
    const Eigen::VectorXd &pos,
    const Eigen::VectorXd &vel,
    Eigen::MatrixXd &metric,
    Eigen::VectorXd &accel,
const double attractor_strength = 50.0);

void floor_repulsion_fabric(
    const Eigen::VectorXd pos,       // s = d/r - 1
    const Eigen::VectorXd vel,       // dz/dt (or ds/dt)
    Eigen::MatrixXd &metric,   // scalar metric
    Eigen::VectorXd &accel);       // (m,) output acceleration

void obstacle_avoidance_fabric(
    const Eigen::VectorXd &pos,   // (m,) distance ratios (d/r - 1)
    const Eigen::VectorXd &vel,   // (m,) relative velocities
    Eigen::MatrixXd &metric,      // (m, m) output diagonal metric
    Eigen::VectorXd &accel);       // (m,) output acceleration

// VectorXd compute_accel(const MatrixXd& M_r_total, const VectorXd& f_r_total)
// {
//     // 计算 M_r_total 的伪逆
//     JacobiSVD<MatrixXd> svd(M_r_total, ComputeThinU | ComputeThinV);
//     double tolerance = 1e-9;
//     VectorXd singularValues_inv = svd.singularValues();

//     for (int i = 0; i < singularValues_inv.size(); ++i)
//     {
//         if (singularValues_inv(i) > tolerance)
//             singularValues_inv(i) = 1.0 / singularValues_inv(i);
//         else
//             singularValues_inv(i) = 0.0;
//     }

//     MatrixXd pinv = svd.matrixV() * singularValues_inv.asDiagonal() * svd.matrixU().transpose();

//     // 伪逆求解：accel = pinv(M_r_total) * f_r_total
//     VectorXd accel = pinv * f_r_total;

//     return accel;
// }