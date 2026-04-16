#pragma once

#include "rclcpp/rclcpp.hpp"
#include <iostream>
#include <string>
#include <vector>
#include <sstream>
#include "ctime"
#include "stdio.h"
#include "MarvinSDK.h"
#include "math.h"

// #include "sensor_msgs/msg/joint_state.hpp"
// #include "geometry_msgs/msg/pose.hpp"
// #include "geometry_msgs/msg/pose_stamped.hpp"
// #include "marvin_ros_control/NspEdit/DCAL.h"
// #include "marvin_ros_control/NspEdit/Nsp.h"

constexpr double D2R = 3.14159265358979323846 / 180.0;
constexpr double R2D = 180.0 / 3.14159265358979323846;

class MarvinRobot
{
public:
    MarvinRobot();

    // Initialization function to connect to the robot by its IP address
    bool init(const std::string &robot_ip);

    bool init_tool_dyna(double dynPara_A[10], double dynPara_B[10]);

    bool is_connected() const;

    bool ReadState(std::vector<FX_FLOAT>& joint_positions, std::vector<FX_FLOAT>& joint_velocities, std::vector<FX_FLOAT>& joint_efforts);

    bool readErrCode(long *err_code_A, long *err_code_B);

    bool PosCmd(double joint_cmd_A[7], double joint_cmd_B[7]);

    bool PosCmdA(double joint_cmd_A[7]);

    bool PosCmdB(double joint_cmd_B[7]);

    bool emptyCmd();

    bool SetMode(int mode);

    bool setdrag(bool on_off);

    void servo_off();

    // void set_joint_cmd_A(const std::vector<double> &joint_cmd);

    // void set_joint_cmd_B(const std::vector<double> &joint_cmd);

    void GetState(int &stateA, int &stateB);

    void ClearFault();

    void GetJointHome_A(double *joint_home);

    void GetJointHome_B(double *joint_home);

    void SetKDA(std::vector<double> &k, std::vector<double> &d);
    void SetKDB(std::vector<double> &k, std::vector<double> &d);

    void SetKDACart(std::vector<double> &k, std::vector<double> &d);
    void SetKDBCart(std::vector<double> &k, std::vector<double> &d);

    void set_speed(int vel_scale, int acc_scale);

    bool check_connection();

    double Joint_pos_A[7], Joint_vel_A[7], Joint_eff_A[7];
    double Joint_pos_B[7], Joint_vel_B[7], Joint_eff_B[7];
    double pgA[4][4], pgB[4][4];

private:
    std::shared_ptr<rclcpp::Node> node_;
    std::string robot_ip_;
    bool connected_;

    std::vector<int> parse_ip(const std::string &ip);

    // double joint_cmd_A_[7];
    // double joint_cmd_B_[7];
    double joint_home_A_[7] = {73.599, -63.546, -21.671, -48.365, 0.024, 0.005, 0.008};
    double joint_home_B_[7] = {-73.599, -63.546, 21.671, -48.365, 0.024, 0.005, 0.008};
    double acc_limit, vel_limit;

    int robot_state[2] = {0, 0}; // State for both arms
    double K_A[7] = {5, 3, 2, 3, 2, 1, 1};
    double D_A[7] = {0.4, 0.3, 0.2, 0.3, 0.2, 0.1, 0.1};
    double K_B[7] = {5, 3, 2, 3, 2, 1, 1};
    double D_B[7] = {0.4, 0.3, 0.2, 0.3, 0.2, 0.1, 0.1};
    double K_Ac[7] = {1, 1, 1, 1, 1, 1, 1};
    double D_Ac[7] = {0.4, 0.3, 0.2, 0.3, 0.2, 0.1, 0.1};
    double K_Bc[7] = {1, 1, 1, 1, 1, 1, 1};
    double D_Bc[7] = {0.4, 0.3, 0.2, 0.3, 0.2, 0.1, 0.1};

    FX_INT32 ErrCode_A,ErrCode_B;
    FX_INT32 ArmState_A,ArmState_B;
    char low_spd_flag_A;
    char low_spd_flag_B;
    long MotorErrcodeA[7] = {-1, -1, -1, -1, -1, -1, -1};
    long MotorErrcodeB[7] = {-1, -1, -1, -1, -1, -1, -1};
    size_t frame_idx_L,frame_idx_R; 
    size_t frame_idx_L_prev,frame_idx_R_prev; 
    int frame_lost_thres, frame_lost_count;
};
