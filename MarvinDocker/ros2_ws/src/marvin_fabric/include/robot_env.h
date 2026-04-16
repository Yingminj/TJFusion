// robot_env.h
// Header file for RobotEnv class - C++ translation of Python RobotEnv
// Provides robot simulation environment using Pinocchio for kinematics and dynamics

#ifndef ROBOT_ENV_H
#define ROBOT_ENV_H

#include <pinocchio/multibody/model.hpp>
#include <pinocchio/multibody/data.hpp>
#include <pinocchio/multibody/geometry.hpp>
#include <pinocchio/spatial/se3.hpp>
#include <pinocchio/spatial/motion.hpp>
#include <pinocchio/algorithm/aba.hpp>
#include <Eigen/Dense>
#include <yaml-cpp/yaml.h>

#include <string>
#include <vector>
#include <map>
#include <unordered_map>
#include <utility>

using Eigen::VectorXd;
using Eigen::MatrixXd;
using namespace pinocchio;

// --- Utility Functions ---

// Print YAML node for debugging
void printYamlNode(const YAML::Node &node);

// Approximates geometry model by creating sphere frames from YAML configuration
// Populates sphere_idx_to_frame_idx mapping
void approximateGeomModel(
    const YAML::Node &spheres_node,
    pinocchio::Model &model,
    std::unordered_map<size_t, FrameIndex> &sphere_to_frame_indices,
    std::unordered_map<std::string, std::vector<size_t>> &link_to_sphere_indices,
    std::vector<double> *sphere_radii = nullptr); // optional output pointer

// --- RobotEnv Class ---

class RobotEnv {
public:
    // --- Pinocchio Models & Data ---
    Model model;
    GeometryModel collision_model;
    GeometryModel visual_model;
    Data data;
    GeometryData geom_data;

    // --- Simulation State ---
    VectorXd q_init;  // Initial joint positions
    VectorXd v_init;  // Initial joint velocities
    VectorXd q;       // Current joint positions
    VectorXd v;       // Current joint velocities
    VectorXd a;       // Joint accelerations
    VectorXd default_pose; // Default joint positions
    int simrate;      // Simulation rate (Hz)
    int timestep;     // Current simulation timestep

    // --- Collision/Sphere Data ---
    int sphere_num;   // Total number of collision spheres

    // Map: link name -> (own sphere indices, collision sphere indices)


    // Map: link name -> sphere indices
    // std::map<std::string, std::vector<size_t>> link_to_sphere_indices;

    // Map: sphere index -> frame index
    std::unordered_map<size_t, FrameIndex> sphere_to_frame_indices;
    std::unordered_map<std::string, std::pair<std::vector<size_t>, std::vector<size_t>>> link_sphere_map;
    std::unordered_map<std::string, std::vector<size_t>> link_to_sphere_indices;
    std::vector<double> sphere_radii; // Radii of spheres indexed by sphere index

    // Map: active link -> colliding link names
    std::map<std::string, std::vector<std::string>> active_link_coll_dict;

    // --- Joint Limits ---
    VectorXd min_jnt_torque_lims;
    VectorXd max_jnt_torque_lims;
    VectorXd min_pos_limit;
    VectorXd max_pos_limit;



    // --- Constructor ---
    RobotEnv(const std::string &urdf_path = "",
             const std::string &mesh_path = "",
             const std::string &srdf_path = "",
             const std::string &fabric_config = "",
             int simrate_ = 1000,
             const VectorXd *q_init_ptr = nullptr,
             const VectorXd *v_init_ptr = nullptr);

    // --- Collision Initialization ---
    // Initialize collision objects from YAML config and SRDF
    void init_collision_objects(const std::string& yaml_path,
                                const std::string& srdf_path);

    // --- Simulation Methods ---
    // Step simulation forward with given action (interpreted as acceleration)
    void step_sim(const VectorXd &action);

    // Reset simulation to initial state
    std::pair<VectorXd, VectorXd> reset();

    // --- Kinematics Methods ---
    // Compute forward kinematics and derivatives
    void cal_fk(const VectorXd &qpos, const VectorXd &qvel);

    // Structure to hold frame forward kinematics data
    struct FrameFK {
        SE3 oMf;        // Frame placement (position and orientation)
        Motion v;       // 6D twist (linear and angular velocity)
        VectorXd c;     // Curvature/acceleration term (dJ * v)
        MatrixXd J;     // Frame Jacobian
    };

    // Get forward kinematics for all frames
    std::vector<FrameFK> get_fk();

    // Get sphere velocities, curvatures and jacobians
    // Populates output maps indexed by sphere index
    void get_sphere_vel(std::vector<FrameFK> &frame_fks,
                        std::map<int, Motion> &sphere_velocities,
                        std::map<int, VectorXd> &sphere_curvatures,
                        std::map<int, MatrixXd> &sphere_jacobians);




protected:
    // Virtual method for derived classes to set up fabrics
    virtual void _set_fabrics();
};

#endif // ROBOT_ENV_H
