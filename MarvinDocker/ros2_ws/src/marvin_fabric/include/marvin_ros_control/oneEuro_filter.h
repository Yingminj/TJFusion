#pragma once

#include <Eigen/Dense>
#include <Eigen/Geometry>
#include <array>
#include <cmath>

class OneEuroFilter1D {
public:
    OneEuroFilter1D(double freq, double min_cutoff = 1.0, double beta = 0.0, double d_cutoff = 1.0)
        : freq_(freq), min_cutoff_(min_cutoff), beta_(beta), d_cutoff_(d_cutoff),
          prev_x_(0.0), prev_dx_(0.0), first_time_(true)
    {}

    double filter(double x, double timestamp) {
        if (first_time_) {
            prev_x_ = x;
            prev_dx_ = 0.0;
            last_timestamp_ = timestamp;
            first_time_ = false;
            return x;
        }

        double dt = timestamp - last_timestamp_;
        if (dt <= 0.0) dt = 1.0 / freq_;
        freq_ = 1.0 / dt;

        double dx = (x - prev_x_) * freq_;
        double edx = smooth(dx, prev_dx_, alpha(d_cutoff_));
        double cutoff = min_cutoff_ + beta_ * std::abs(edx);
        double result = smooth(x, prev_x_, alpha(cutoff));

        prev_x_ = result;
        prev_dx_ = edx;
        last_timestamp_ = timestamp;
        return result;
    }

private:
    double alpha(double cutoff) const {
        double tau = 1.0 / (2.0 * M_PI * cutoff);
        double te = 1.0 / freq_;
        return 1.0 / (1.0 + tau / te);
    }

    double smooth(double x, double prev_x, double a) const {
        return a * x + (1.0 - a) * prev_x;
    }

    double freq_, min_cutoff_, beta_, d_cutoff_;
    double prev_x_, prev_dx_;
    double last_timestamp_;
    bool first_time_;
};

class OneEuroSE3Filter {
public:
    OneEuroSE3Filter(double freq, double min_cutoff = 1.0, double beta = 0.0, double d_cutoff = 1.0)
        : filters_{{
            OneEuroFilter1D(freq, min_cutoff, beta, d_cutoff),
            OneEuroFilter1D(freq, min_cutoff, beta, d_cutoff),
            OneEuroFilter1D(freq, min_cutoff, beta, d_cutoff)
        }},
          freq_(freq), min_cutoff_(min_cutoff), beta_(beta), d_cutoff_(d_cutoff),
          first_time_(true)
    {}

    Eigen::Isometry3d filter(const Eigen::Isometry3d& pose, double timestamp) {
        Eigen::Vector3d t = pose.translation();
        Eigen::Quaterniond q(pose.rotation());

        Eigen::Vector3d t_filtered;
        for (int i = 0; i < 3; ++i) {
            t_filtered[i] = filters_[i].filter(t[i], timestamp);
        }

        if (first_time_) {
            prev_q_ = q;
            last_timestamp_ = timestamp;
            first_time_ = false;
        }

        double dt = timestamp - last_timestamp_;
        if (dt <= 0.0) dt = 1.0 / freq_;
        freq_ = 1.0 / dt;

        double cutoff = min_cutoff_; // you can adapt based on angular velocity if you like
        double a = alpha(cutoff);

        Eigen::Quaterniond q_filtered = prev_q_.slerp(a, q).normalized();

        prev_q_ = q_filtered;
        last_timestamp_ = timestamp;

        Eigen::Isometry3d result = Eigen::Isometry3d::Identity();
        result.linear() = q_filtered.toRotationMatrix();
        result.translation() = t_filtered;

        return result;
    }

private:
    double alpha(double cutoff) const {
        double tau = 1.0 / (2.0 * M_PI * cutoff);
        double te = 1.0 / freq_;
        return 1.0 / (1.0 + tau / te);
    }

    std::array<OneEuroFilter1D, 3> filters_;
    Eigen::Quaterniond prev_q_;
    double freq_, min_cutoff_, beta_, d_cutoff_;
    double last_timestamp_;
    bool first_time_;
};