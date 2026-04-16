#include <Eigen/Dense>
#include "fabric_task_maps.h"
using namespace Eigen;



void joint_limit_fabric(
    const Eigen::VectorXd &pos,
    const Eigen::VectorXd &vel,
    Eigen::MatrixXd &metric,
    Eigen::VectorXd &accel)
{
    const double eps = 1e-2;
    const double l = 10.0;
    const double k = 5.0;
    const double v_max = 1.0;

    int n = pos.size();
    accel.setZero(n);
    metric.setZero(n, n);

    for (int i = 0; i < n; ++i)
    {
        double q = std::max(pos[i], eps);
        double qdot = vel[i];

        if (qdot < 0.0)   // moving toward limit
        {
            // bounded metric
            metric(i, i) = l / (q + eps);

            // smooth barrier gradient
            double grad = -k / (q*q + eps*eps);

            // bounded velocity scaling
            double v = std::min(std::abs(qdot), v_max);

            accel[i] = -v * grad;
        }
    }
}

void joint_damping_fabric(
    const Eigen::VectorXd &vel,
    Eigen::MatrixXd &metric,
    Eigen::VectorXd &accel) 
{
    double b = 15.0; // 阻尼系数

    // metric = b * I
    metric = b * Eigen::MatrixXd::Identity(vel.size(), vel.size());

    // accel = -b * vel
    accel = -b * vel;
}


void default_config_fabric(
    const Eigen::VectorXd &pos,
    Eigen::MatrixXd &metric,
    Eigen::VectorXd &accel)
{
    double dc = 10.0;
    double k = 10.0;
    double transition_rate = 10.0;

    // metric = dc * I
    metric = dc * Eigen::MatrixXd::Identity(pos.size(), pos.size());

    // norm of x
    double norm_x = pos.norm();
    double eps = 1e-6;
    double norm_safe = std::max(norm_x, eps);

    // d/d||x|| of the potential function
    // potential = k * (norm + (1/tr)*log(1 + exp(-2*tr*norm)))
    double dV_dnorm = k * (1.0 - (2.0 / (1.0 + std::exp(2.0 * transition_rate * norm_safe))) );

    // potential_grad = dV_dnorm * (x / ||x||)
    Eigen::VectorXd potential_grad = dV_dnorm * (pos / norm_safe);

    // accel = -potential_grad
    accel = -potential_grad;
}

void attractor_task_fabric(
    const Eigen::VectorXd &pos,
    const Eigen::VectorXd &vel,
    Eigen::MatrixXd &metric,
    Eigen::VectorXd &accel,
    const double attractor_strength)
{
    // 参数（与 Python 版本一致）
    const double k = attractor_strength;
    const double upper_m = 200.0;
    const double lower_m = 10.0;
    const double radial_basis_width = 5.0;
    const double transition_rate = 10.0;
    const double damping = 350.0;

    // 确保输入至少含有前三维
    assert(pos.size() >= 3 && vel.size() >= 3);

    // 取前三维 (位置 + 速度)
    Eigen::Vector3d pos_ = pos.head<3>();
    Eigen::Vector3d vel_ = vel.head<3>();

    double r = pos_.norm();

    // 防止除以 0：当 r 非常小时，令 grad = 0
    const double EPS = 1e-12;

    // === grad(potential) ===
    // analytic derivative: dV/dr = k * tanh(transition_rate * r)
    double ar = transition_rate * r;
    double dV_dr = k * std::tanh(ar);

    Eigen::Vector3d potential_grad = Eigen::Vector3d::Zero();
    if (r > EPS) {
        potential_grad = (dV_dr / r) * pos_;
    } else {
        // r≈0 时 tanh(0)=0，梯度为 0，保持 zero vector
        potential_grad.setZero();
    }

    // === accel ===
    Eigen::Vector3d accel3 = -potential_grad - damping * vel_;

    // === metric ===
    // metric = (upper_m - lower_m)*exp(-(radial_basis_width * r)^2)*I + lower_m*I
    double coeff = (upper_m - lower_m) * std::exp(-std::pow(radial_basis_width * r, 2.0)) + lower_m;
    Eigen::Matrix3d metric3 = coeff * Eigen::Matrix3d::Identity();

    // 写回到引用（保持签名不变，同时确保尺寸正确）
    metric.resize(3, 3);
    metric = metric3;

    accel.resize(3);
    accel = accel3;
}

void dir_task_fabric(
    const Eigen::VectorXd &pos,
    const Eigen::VectorXd &vel,
    Eigen::MatrixXd &metric,
    Eigen::VectorXd &accel,
    const double attractor_strength)
{
    // 参数（与 Python 版本一致）
    const double k = attractor_strength;
    const double upper_m = 100.0;
    const double lower_m = 10.0;
    const double radial_basis_width = 5.0;
    const double transition_rate = 10.0;
    const double damping = 120.0;

    // 确保输入至少含有前三维
    assert(pos.size() >= 3 && vel.size() >= 3);

    // 取前三维 (位置 + 速度)
    Eigen::Vector3d pos_ = pos.head<3>();
    Eigen::Vector3d vel_ = vel.head<3>();

    double r = pos_.norm();

    // 防止除以 0：当 r 非常小时，令 grad = 0
    const double EPS = 1e-12;

    // === grad(potential) ===
    // analytic derivative: dV/dr = k * tanh(transition_rate * r)
    double ar = transition_rate * r;
    double dV_dr = k * std::tanh(ar);

    Eigen::Vector3d potential_grad = Eigen::Vector3d::Zero();
    if (r > EPS) {
        potential_grad = (dV_dr / r) * pos_;
    } else {
        // r≈0 时 tanh(0)=0，梯度为 0，保持 zero vector
        potential_grad.setZero();
    }

    // === accel ===
    Eigen::Vector3d accel3 = -potential_grad - damping * vel_;

    // === metric ===
    // metric = (upper_m - lower_m)*exp(-(radial_basis_width * r)^2)*I + lower_m*I
    double coeff = (upper_m - lower_m) * std::exp(-std::pow(radial_basis_width * r, 2.0)) + lower_m;
    Eigen::Matrix3d metric3 = coeff * Eigen::Matrix3d::Identity();

    // 写回到引用（保持签名不变，同时确保尺寸正确）
    metric.resize(3, 3);
    metric = metric3;

    accel.resize(3);
    accel = accel3;
}

void floor_repulsion_fabric(
    const Eigen::VectorXd pos,       // size 1: s = d/r - 1
    const Eigen::VectorXd vel,       // size 1: dz/dt
    Eigen::MatrixXd &metric,         // (1,1)
    Eigen::VectorXd &accel)          // (1)
{
    metric = Eigen::MatrixXd::Zero(1, 1);
    accel  = Eigen::VectorXd::Zero(1);

    const double eps   = 1e-6;
    const double alpha = 1.0;   // repulsion strength
    const double beta  = 0.2;   // damping

    // Extract scalar
    double s  = pos(0);
    double ds = vel(0);

    // 1) Metric: g = 1 / (s + eps)^2    (scalar)
    double g = 1.0 / ((s + eps) * (s + eps));

    // 2) Acceleration: a = alpha * g - beta * ds
    double a = alpha * g - beta * ds;

    // Clip accel
    if (a > 50.0) a = 50.0;
    if (a < -50.0) a = -50.0;

    // Output
    metric(0, 0) = g;
    accel(0)     = a;
}

 void obstacle_avoidance_fabric(
    const Eigen::VectorXd &pos,   // (m,) distance ratios (d/r - 1)
    const Eigen::VectorXd &vel,   // (m,) relative velocities
    Eigen::MatrixXd &metric,      // (m, m) output diagonal metric
    Eigen::VectorXd &accel)       // (m,) output acceleration
{
    const double k_b = 1.0;       // metric scaling
    const double a_b = 100.0;     // potential scaling
    const double eps = 1e-8;

    const int m = pos.size();

    // 初始化输出
    metric = Eigen::MatrixXd::Zero(m, m);
    accel  = Eigen::VectorXd::Zero(m);

    for (int j = 0; j < m; ++j)
    {
        double x = pos(j);
        double v = vel(j);

        // Step 1: only apply repulsion if moving toward obstacle
        double s = (v < 0.0) ? 1.0 : 0.0;

        // Step 2-3: potential gradient dφ/dx = -4 * a_b / (x + eps)^9
        double grad = -4.0 * a_b / std::pow(x + eps, 9);

        // Step 4: acceleration term (repulsion)
        accel(j) = -s * x * x * grad;

        // Step 5: metric term G(x) = k_b / x^2 * I
        metric(j, j) = k_b / (x * x + eps);
    }
}
