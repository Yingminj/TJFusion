// robot_env.cpp
// C++ translation of the provided Python RobotEnv class.
// Implementation file for RobotEnv class.

#include "robot_env.h"

#include <pinocchio/parsers/urdf.hpp>
#include <pinocchio/parsers/srdf.hpp>
#include <pinocchio/algorithm/jacobian.hpp>
#include <pinocchio/algorithm/aba.hpp>
#include <pinocchio/algorithm/kinematics.hpp>
#include <pinocchio/algorithm/geometry.hpp>
#include <pinocchio/algorithm/frames.hpp>
#include <pinocchio/algorithm/rnea.hpp>
#include <pinocchio/algorithm/centroidal.hpp>
#include <pinocchio/algorithm/joint-configuration.hpp>
#include <pinocchio/algorithm/kinematics-derivatives.hpp>
#include <pinocchio/algorithm/crba.hpp>     // For Mass Matrix
#include <pinocchio/algorithm/cholesky.hpp> // For Decomposition & Solve
#include <iostream>
#include <set>
#include <memory>
#include <chrono>


void printYamlNode(const YAML::Node &node)
{
    YAML::Emitter out;
    out << node;
    std::cout << out.c_str() << std::endl;
}


// Placeholder function: you must implement/port the Python `approximate_geom_model`
// that converts the "spheres" config into a Pinocchio geometry model and returns
// link-to-sphere maps. For now this returns default/empty structures.
void approximateGeomModel(
    const YAML::Node &spheres_node,
    pinocchio::Model &model,
    std::unordered_map<size_t, FrameIndex> &sphere_to_frame_indices,
    std::unordered_map<std::string, std::vector<size_t>> &link_to_sphere_indices,
    std::vector<double> *sphere_radii) // optional output pointer
{
    const double default_radius = 0.03;
    size_t global_idx = 0;

    sphere_to_frame_indices.clear();
    link_to_sphere_indices.clear();
    if (sphere_radii) sphere_radii->clear();

    for (auto it = spheres_node.begin(); it != spheres_node.end(); ++it) {
        const std::string link = it->first.as<std::string>();
        const YAML::Node &sphere_list = it->second;

        // ensure link exists in model
        pinocchio::FrameIndex parent_frame_id = model.getFrameId(link);
        if (parent_frame_id == (pinocchio::FrameIndex)-1) {
            std::cerr << "[approximateGeomModel] Warning: link '" << link << "' not found in model. Skipping.\n";
            continue;
        }

        // prepare vector for this link
        std::vector<size_t> &link_spheres = link_to_sphere_indices[link]; // creates empty vector if not exists

        // parent joint for frame placement
        pinocchio::JointIndex parent_joint = model.frames[parent_frame_id].parentJoint;

        int local_sphere_idx = 0;
        for (const auto &sphere_node : sphere_list) {
            // parse center
            Eigen::Vector3d center(0.0, 0.0, 0.0);
            if (sphere_node["center"] && sphere_node["center"].IsSequence() && sphere_node["center"].size() >= 3) {
                center[0] = sphere_node["center"][0].as<double>();
                center[1] = sphere_node["center"][1].as<double>();
                center[2] = sphere_node["center"][2].as<double>();
            } else {
                std::cerr << "[approximateGeomModel] Warning: sphere without valid center for link " 
                          << link << ". Using [0,0,0].\n";
            }

            // parse radius
            double radius = default_radius;
            if (sphere_node["radius"]) {
                radius = sphere_node["radius"].as<double>();
            }

            // create frame name and placement
            std::string frame_name = link + "_sphere_" + std::to_string(local_sphere_idx);
            pinocchio::SE3 placement(Eigen::Matrix3d::Identity(), center);

            // create frame and add to model
            pinocchio::Frame sphere_frame(frame_name, parent_joint, placement, pinocchio::FrameType::OP_FRAME);
            FrameIndex frame_id = model.addFrame(sphere_frame);

            // ✅ store mappings
            sphere_to_frame_indices[global_idx] = frame_id;
            link_spheres.push_back(global_idx);  // ← FIXED: push to this link's vector
            if (sphere_radii) sphere_radii->push_back(radius);

            // debug print
            std::cout << "[approximateGeomModel] link=" << link
                      << " sphere_idx=" << global_idx
                      << " frame_id=" << frame_id
                      << " center=" << center.transpose()
                      << " radius=" << radius << "\n";

            ++local_sphere_idx;
            ++global_idx;
        }
    }

    std::cout << "[approximateGeomModel] Done. total_spheres = " << global_idx
              << ", links_with_spheres = " << link_to_sphere_indices.size() << std::endl;
}


    // // --- Second pass: build link_sphere_map ---
    // for (const auto &kv : link_to_self_spheres)
    // {
    //     const std::string &link = kv.first;
    //     const std::vector<size_t> &self_spheres = kv.second;

    //     std::vector<size_t> obs_spheres;
    //     obs_spheres.reserve(idx);
    //     for (const auto &other_kv : link_to_self_spheres)
    //     {
    //         if (other_kv.first != link)
    //             obs_spheres.insert(obs_spheres.end(), other_kv.second.begin(), other_kv.second.end());
    //     }

    //     link_sphere_map[link] = std::make_pair(self_spheres, obs_spheres);
    // }

    // std::cout << "✅ Built link_sphere_map with " << link_sphere_map.size() << " entries.\n";
// }

// ============================================================================
// RobotEnv Class Implementation
// ============================================================================

RobotEnv::RobotEnv(const std::string &urdf_path,
                   const std::string &mesh_path,
                    const std::string &srdf_path,
                     const std::string &fabric_config,
                   int simrate_,
                   const VectorXd *q_init_ptr,
                   const VectorXd *v_init_ptr)
    : simrate(1), timestep(0), sphere_num(0)
{
        // build model and geom models
        std::string meshDir = mesh_path;
        // Note: depending on Pinocchio version, you may need to call
        // pinocchio::urdf::buildModel or pinocchio::urdf::buildModels
        pinocchio::urdf::buildModel(urdf_path, model);
        // Build geometry (collision and visual) if you need geometry parsing from URDF
        // For many URDFs, use buildGeomModel
        try {
            // pinocchio::urdf::buildGeom(model, urdf_path, meshDir, collision_model, visual_model);
            pinocchio::urdf::buildGeom(
			model, urdf_path, pinocchio::COLLISION, collision_model, meshDir);
        } catch (...) {
            // Fallback or ignore; several APIs exist depending on pinocchio version
            std::cerr << "Warning: buildGeom failed. Check Pinocchio URDF geometry API." << std::endl;
        }

        data = Data(model);
        geom_data = GeometryData(collision_model);

        // print joint names
        for (int i=0;i<model.njoints;i++) {
            std::cout << model.names[i] << std::endl;
        }

        init_collision_objects(fabric_config,
                               srdf_path);
        if (!srdf_path.empty())
        {
            pinocchio::srdf::loadReferenceConfigurations(model, srdf_path);
        }

        // 加载后，可以通过 model.referenceConfigurations["name"] 访问
        auto q_home = model.referenceConfigurations.at("resting");  // 例如
        // limits
        min_jnt_torque_lims = -model.effortLimit;
        max_jnt_torque_lims = model.effortLimit;
        min_pos_limit = model.lowerPositionLimit;
        max_pos_limit = model.upperPositionLimit;

        if (q_init_ptr) q_init = *q_init_ptr; else q_init = q_home;
        if (v_init_ptr) v_init = *v_init_ptr; else v_init = VectorXd::Zero(model.nv);
        q = q_init;
        v = v_init;
        a = VectorXd::Zero(model.nv);
        
        simrate = simrate_;

        _set_fabrics();
}

void RobotEnv::init_collision_objects(const std::string& yaml_path,
                                      const std::string& srdf_path)
{
        YAML::Node config = YAML::LoadFile(yaml_path);
        YAML::Node spheres = config["geometry"]["marvin_collision"]["spheres"];
        YAML::Node default_pose_node = config["default_pose"];
        default_pose = VectorXd(model.nq);
        for (size_t i = 0; i < default_pose_node.size(); ++i) {
            default_pose[i] = default_pose_node[i].as<double>();
        }
        // count spheres
        sphere_num = 0;
        for (auto it = spheres.begin(); it != spheres.end(); ++it) {
            std::string link = it->first.as<std::string>();
            sphere_num += it->second.size();
            std::cout << "Link: " << link << ", Number of spheres: " << it->second.size() << std::endl;
        }

        YAML::Node active_links_node = config["active_links"];
        std::vector<std::string> active_links;
        for (auto it = active_links_node.begin(); it != active_links_node.end(); ++it)
            active_links.push_back(it->as<std::string>());

        // call approximateGeomModel (placeholder)
        // std::unordered_map<size_t, pinocchio::FrameIndex> sphere_map;
        approximateGeomModel(spheres, model, sphere_to_frame_indices, link_to_sphere_indices, &sphere_radii);

        // for (auto &[link, pair] : link_sphere_map)
        // {
        //     const auto &[self_ids, obs_ids] = pair;
        //     std::cout << "🔸 Link: " << link
        //             << " | self: " << self_ids.size()
        //             << " | obs: " << obs_ids.size() << std::endl;
        // }
        // link_to_sphere_indices = approx.link_to_sphere_indices;
        // sphere_to_frame_indices = approx.sphere_to_frame_indices;

        // If SRDF exists: load reference configurations and remove collision pairs per SRDF
        try {
            collision_model.addAllCollisionPairs();
            // removeCollisionPairs(model, collision_model, srdf_path);
        } catch (...) {
            // ignore if API not present
        }

        // // print collision pairs
        std::vector<std::pair<int,int>> pairs;
        for (const auto &pair : collision_model.collisionPairs) {
            int fA = collision_model.geometryObjects[pair.first].parentFrame;
            int fB = collision_model.geometryObjects[pair.second].parentFrame;
            std::string nameA = model.frames[fA].name;
            std::string nameB = model.frames[fB].name;
            std::cout << "Collision Pair: " << nameA << " - " << nameB << std::endl;
            pairs.emplace_back(nameA==""? -1 : fA, nameB==""? -1 : fB);
        }

        // // build active_link_coll_dict
        std::set<std::string> active_set(active_links.begin(), active_links.end());
        for (const auto &p : collision_model.collisionPairs) {
            int fA = collision_model.geometryObjects[p.first].parentFrame;
            int fB = collision_model.geometryObjects[p.second].parentFrame;
            std::string nameA = model.frames[fA].name;
            std::string nameB = model.frames[fB].name;
            if (active_set.count(nameA)) active_link_coll_dict[nameA].push_back(nameB);
            if (active_set.count(nameB)) active_link_coll_dict[nameB].push_back(nameA);
        }
        std::cout << "Active link collision dict constructed." << std::endl;
        // // assemble link_sphere_map (link -> (own_spheres, coll_spheres))
        for (const auto &link : active_links) {
            if (link_to_sphere_indices.count(link)) {
                std::vector<size_t> link_ids = link_to_sphere_indices[link];
                std::vector<size_t> coll_sphere_indices;
                for (const auto &coll_link : active_link_coll_dict[link]) {
                    if (link_to_sphere_indices.count(coll_link)) {
                        auto &v = link_to_sphere_indices[coll_link];
                        coll_sphere_indices.insert(coll_sphere_indices.end(), v.begin(), v.end());
                    }
                }
                if (!link_ids.empty() && !coll_sphere_indices.empty()) {
                    link_sphere_map[link] = {link_ids, coll_sphere_indices};
                }
            }
        }
        std::cout << "Link-sphere map constructed." << std::endl;

        for (const auto &kv : link_sphere_map) {
            const auto &link = kv.first;
            const auto &pair = kv.second;
            std::cout << "Link: " << link
                      << " | own spheres: " << pair.first.size()
                      << " | coll spheres: " << pair.second.size() << std::endl;
                      for (const auto &id : pair.first) {
                          std::cout << "  - own sphere idx: " << id << std::endl;
                      }
                      for (const auto &id : pair.second) {
                          std::cout << "  - coll sphere idx: " << id << std::endl;
                      }
        }
        data = Data(model); // reset data after modifying model
}

void RobotEnv::step_sim(const VectorXd &action)
{
        cal_fk(q, v);
        VectorXd qpos = q;
        VectorXd qvel = v + action / double(simrate);
        q = qpos + qvel / double(simrate);
        v = qvel;
        ++timestep;
}

std::pair<VectorXd, VectorXd> RobotEnv::reset()
{
        timestep = 0;
        q = q_init;
        v = v_init;
        cal_fk(q, v);
        return {q, v};
}

void RobotEnv::cal_fk(const VectorXd &qpos, const VectorXd &qvel)
{   
        // for (int i=0;i<model.nq;i++) {
        //     std::cout << "qvel[" << i << "] = " << qvel[i] << std::endl;
        // }
        pinocchio::forwardKinematics(model, data, qpos, qvel);
        pinocchio::updateFramePlacements(model, data);
        // pinocchio::updateGeometryPlacements(model, data, collision_model, geom_data);
        pinocchio::computeJointJacobians(model, data, qpos);
        pinocchio::computeJointJacobiansTimeVariation(model, data, qpos, qvel);
        // pinocchio::computeForwardKinematicsDerivatives(model, data, qpos, qvel,a);
}

std::vector<RobotEnv::FrameFK> RobotEnv::get_fk()
{
        std::vector<FrameFK> out;
        out.reserve(model.nframes);
        // std::cout << "Getting FK for " << model.nframes << " frames." << std::endl;
        pinocchio::Data::Matrix6x J_i(6, model.nv);
        pinocchio::Data::Matrix6x dJ(6, model.nv);
        for (int i=0;i<model.nframes;i++) {
            FrameFK f;
            f.oMf = data.oMf[i];
            // Frame velocity
            pinocchio::Motion v_frame = pinocchio::getFrameVelocity(model, data, i, pinocchio::LOCAL_WORLD_ALIGNED);
            f.v = v_frame;
            
            // Frame Jacobian time variation
            pinocchio::getFrameJacobianTimeVariation(model, data, i, pinocchio::LOCAL_WORLD_ALIGNED, dJ);
            f.c = dJ * v;
            // Frame Jacobian
            J_i = pinocchio::getFrameJacobian(model, data, i, pinocchio::LOCAL_WORLD_ALIGNED);
            f.J = J_i;
            out.push_back(std::move(f));
        }
        return out;
}

void RobotEnv::get_sphere_vel(std::vector<FrameFK> &frame_fks,
                               std::map<int, Motion> &sphere_velocities,
                               std::map<int, VectorXd> &sphere_curvatures,
                               std::map<int, MatrixXd> &sphere_jacobians)
{
        sphere_velocities.clear();
        sphere_curvatures.clear();
        sphere_jacobians.clear();

        for (int i=0;i<sphere_num;i++) {
            int frame_id = sphere_to_frame_indices[i];
            // Motion v_o = pinocchio::getFrameVelocity(model, data, frame_id, LOCAL_WORLD_ALIGNED);
            // MatrixXd dJ;
            // pinocchio::getFrameJacobianTimeVariation(model, data, frame_id, LOCAL_WORLD_ALIGNED, dJ);
            // VectorXd c_frame = dJ * v;
            // MatrixXd J_frame = pinocchio::getFrameJacobian(model, data, frame_id, LOCAL_WORLD_ALIGNED);
            // MatrixXd J_linear = J_frame.block(0,0,3, model.nv);
            Motion v_o = frame_fks[frame_id].v;
            VectorXd c_frame = frame_fks[frame_id].c;
            MatrixXd J_frame = frame_fks[frame_id].J;
            MatrixXd J_linear = J_frame.block(0,0,3, model.nv);

            sphere_velocities[i] = v_o;
            sphere_curvatures[i] = c_frame;
            sphere_jacobians[i] = J_linear;
            // std::cout << "Sphere " << i << ": velocity = [" << v_o.linear().transpose() <<"]" << std::endl;
            // std::cout << "Sphere " << i << ": curvature = [" << c_frame.transpose() << "]" << std::endl;
            // std::cout << "Sphere " << i << ": jacobian = [" << J_linear << "]" << std::endl;
        }
}

void RobotEnv::_set_fabrics()
{
    // abstract in Python. Provide default or override in derived class.
}

// ============================================================================
// Main / Usage Example
// ============================================================================
// int main(int argc, char **argv)
// {
//     std::string urdf = "/home/tianhao/fabrics/torch-fabrics/Models/marvin_ccs.urdf";
//     std::string meshes = "/home/tianhao/fabrics/torch-fabrics/Models";
//     VectorXd q_init = VectorXd::Zero(14);
//     VectorXd v_init = VectorXd::Ones(14);
//     RobotEnv env(urdf, meshes, 1000, &q_init, &v_init);
//     auto state = env.reset();

//     VectorXd action = VectorXd::Zero(env.model.nv);
//     env.step_sim(action);

//     auto frames = env.get_fk();
//     // std::cout << "Number of frames: " << frames.size() << std::endl;
//     std::map<int, Motion> sphere_vels;
//     std::map<int, VectorXd> sphere_curvs;
//     std::map<int, MatrixXd> sphere_jacs;
//     env.get_sphere_vel(frames, sphere_vels, sphere_curvs, sphere_jacs);
    

//     auto t_start = std::chrono::high_resolution_clock::now();

//     for(int i=0;i<1000;i++) {
//         env.step_sim(action);
//     }

//     auto t_end = std::chrono::high_resolution_clock::now();
//     auto elapsed_ms = std::chrono::duration_cast<std::chrono::milliseconds>(t_end - t_start).count();
//     std::chrono::duration<double> elapsed_s = t_end - t_start;

//     std::cout << "Start time: " << std::chrono::duration_cast<std::chrono::milliseconds>(t_start.time_since_epoch()).count() << " ms since epoch\n";
//     std::cout << "End time:   " << std::chrono::duration_cast<std::chrono::milliseconds>(t_end.time_since_epoch()).count() << " ms since epoch\n";
//     std::cout << "Elapsed: " << elapsed_ms << " ms (" << elapsed_s.count() << " s)\n";

//     return 0;
// }
