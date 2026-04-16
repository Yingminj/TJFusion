#include "rclcpp/rclcpp.hpp"
#include <iostream>
#include <string>
#include "ctime"
#include "stdio.h"
#include "sensor_msgs/msg/joint_state.hpp"
#include "geometry_msgs/msg/pose.hpp"
#include "geometry_msgs/msg/pose_stamped.hpp"

#include "std_srvs/srv/trigger.hpp"
#include "std_msgs/msg/bool.hpp"
#include "std_msgs/msg/int16.hpp"
#include "std_msgs/msg/int16_multi_array.hpp"
#include "std_msgs/msg/u_int16_multi_array.hpp"
#include <tf2/LinearMath/Matrix3x3.h>
#include <tf2/LinearMath/Quaternion.h>
#include "marvin_ros_control/marvin_robot.h"
#include "marvin_msgs/msg/jointcmd.hpp"
#include "marvin_msgs/msg/jointfeedback.hpp"
#include "marvin_msgs/srv/int.hpp"
#include "marvin_msgs/srv/velratio.hpp"
#include "marvin_msgs/srv/motor_err_code.hpp"
#include <linux/can.h>
#include <linux/can/raw.h>
#include <sys/socket.h>
#include <sys/ioctl.h>
#include <net/if.h>
#include <unistd.h>
#include <cstring>
#include <thread>
#include <atomic>
#include <poll.h>
#include <iostream>
// #include "tpm/tpm_check.hpp"
class MarvinRobotNode : public rclcpp::Node
{
public:
    MarvinRobotNode() : Node("marvin_robot_node")
    {
        rclcpp::SensorDataQoS sensor_data_qos;
        // Declare the parameter (optional if you launch with YAML)
        this->declare_parameter<std::vector<std::string>>("left_joints");
        this->declare_parameter<std::vector<std::string>>("right_joints");
        this->declare_parameter<std::vector<double>>("left_kd.k", default_k);
        this->declare_parameter<std::vector<double>>("left_kd.d", default_d);
        this->declare_parameter<std::vector<double>>("right_kd.k", default_k);
        this->declare_parameter<std::vector<double>>("right_kd.d", default_d);
        this->declare_parameter<std::vector<double>>("left_kd.kc", default_kc);
        this->declare_parameter<std::vector<double>>("left_kd.dc", default_dc);
        this->declare_parameter<std::vector<double>>("right_kd.kc", default_kc);
        this->declare_parameter<std::vector<double>>("right_kd.dc", default_dc);
        this->declare_parameter<std::string>("robot_ip", "192.168.1.190");
        this->declare_parameter<std::vector<double>>("left_tool");
        this->declare_parameter<std::vector<double>>("right_tool");
        this->declare_parameter("pub_joint_states", true);
        // Get the parameter
        std::vector<std::string> JointNames_A = this->get_parameter("left_joints").as_string_array();
        std::vector<std::string> JointNames_B = this->get_parameter("right_joints").as_string_array();
        // JointNames = joint_names;
        // Add prefix "left_" to each joint name for JointNames_A

        JointNamesBoth.clear();
        for (size_t i = 0; i < 7; i++)
        {
            JointNamesBoth.push_back(JointNames_A[i]);
        }
        for (size_t i = 0; i < 7; i++)
        {
            JointNamesBoth.push_back(JointNames_B[i]);
        }
        // vcan init 
        // Open CAN raw socket
        sock0 = open_can_socket("vcan0");
        sock1 = open_can_socket("vcan1");
        // Instantiate MarvinRobot class
        marvin_robot_ = std::make_shared<MarvinRobot>();

        // Example: IP address passed for connection
        std::string robot_ip = this->get_parameter("robot_ip").as_string();
        if (marvin_robot_->init(robot_ip))
        {
            RCLCPP_INFO(this->get_logger(), "\033[32mRobot is ready.\033[0m");
        }
        else
        {
            RCLCPP_ERROR(this->get_logger(), "Failed to connect to the robot.");
        }

        marvin_robot_->ClearFault(); // Clear any existing faults
        marvin_robot_->SetMode(0);
        std::vector<double> kA = this->get_parameter("left_kd.k").as_double_array();
        std::vector<double> dA = this->get_parameter("left_kd.d").as_double_array();
        std::vector<double> kB = this->get_parameter("right_kd.k").as_double_array();
        std::vector<double> dB = this->get_parameter("right_kd.d").as_double_array();
        std::vector<double> kAc = this->get_parameter("left_kd.kc").as_double_array();
        std::vector<double> dAc = this->get_parameter("left_kd.dc").as_double_array();
        std::vector<double> kBc = this->get_parameter("right_kd.kc").as_double_array();
        std::vector<double> dBc = this->get_parameter("right_kd.dc").as_double_array();
        marvin_robot_->SetKDA(kA, dA); // Set default K and D values
        marvin_robot_->SetKDB(kB, dB); // Set default K and D values
        marvin_robot_->SetKDACart(kAc, dAc); // Set default K and D values
        marvin_robot_->SetKDBCart(kBc, dBc); // Set default K and D values
        marvin_robot_->set_speed(30, 30); // set default speed limit
        // Create timer to periodically get robot state
        std::vector<double> toolA = this->get_parameter("left_tool").as_double_array();
        std::vector<double> toolB = this->get_parameter("right_tool").as_double_array();
        double dynPara_A[10]= {toolA[0], toolA[1], toolA[2], toolA[3], toolA[4], toolA[5], toolA[6], toolA[7], toolA[8], toolA[9]};//质量M 质心 MCP[3] 惯量I[6]  XX,XY,XZ,YY,YZ,ZZ
        double dynPara_B[10]= {toolB[0], toolB[1], toolB[2], toolB[3], toolB[4], toolB[5], toolB[6], toolB[7], toolB[8], toolB[9]};
        marvin_robot_->init_tool_dyna(dynPara_A, dynPara_B);
        pub_joint_states = this->get_parameter("pub_joint_states").as_bool();
        timer_ = this->create_wall_timer(
            std::chrono::milliseconds(4), // Adjust the frequency as needed
            std::bind(&MarvinRobotNode::timer_ctrl_callback, this));

        timer2_ = this->create_wall_timer(
            std::chrono::milliseconds(10), // Adjust the frequency as needed
            std::bind(&MarvinRobotNode::pub_feedback, this));

        writer_thread_ = std::thread(&MarvinRobotNode::forward_to_sdk, this);
        reader_thread_ = std::thread(&MarvinRobotNode::forward_to_sockets, this);

        joint_state_pub_ = this->create_publisher<sensor_msgs::msg::JointState>("joint_states", 10);
        joint_feedback_pub_ = this->create_publisher<marvin_msgs::msg::Jointfeedback>("info/joint_feedback", sensor_data_qos);
        joint_cmd_sub_A_ = this->create_subscription<marvin_msgs::msg::Jointcmd>(
            "control/joint_cmd_A", sensor_data_qos,
            std::bind(&MarvinRobotNode::joint_cmd_callback_A, this, std::placeholders::_1));
        joint_cmd_sub_B_ = this->create_subscription<marvin_msgs::msg::Jointcmd>(
            "control/joint_cmd_B", sensor_data_qos,
            std::bind(&MarvinRobotNode::joint_cmd_callback_B, this, std::placeholders::_1));

        set_drag_service_ = this->create_service<marvin_msgs::srv::Int>(
            "control/set_drag",
            std::bind(&MarvinRobotNode::set_drag_cbk, this, std::placeholders::_1, std::placeholders::_2));
        set_mode_service_ = this->create_service<marvin_msgs::srv::Int>(
            "control/set_mode",
            std::bind(&MarvinRobotNode::set_mode_callback, this, std::placeholders::_1, std::placeholders::_2));
        clear_fault_service_ = this->create_service<std_srvs::srv::Trigger>(
            "control/clear_fault",
            std::bind(&MarvinRobotNode::clearfault_callback, this, std::placeholders::_1, std::placeholders::_2));
        vel_ratio_service_ = this->create_service<marvin_msgs::srv::Int>(
            "control/set_vel_ratio",
            std::bind(&MarvinRobotNode::set_vel_ratio_callback, this, std::placeholders::_1, std::placeholders::_2));

        set_ready_service_ = this->create_service<std_srvs::srv::Trigger>(
            "control/set_ready",
            std::bind(&MarvinRobotNode::set_ready_callback, this, std::placeholders::_1, std::placeholders::_2));
        motor_err_code_service_ = this->create_service<marvin_msgs::srv::MotorErrCode>(
            "control/get_motor_err_code",
            std::bind(&MarvinRobotNode::motor_err_code_callback, this, std::placeholders::_1, std::placeholders::_2));
        arm_state_pub_ = this->create_publisher<std_msgs::msg::Int16MultiArray>("info/arm_state", 10);

        // Jog_subscriber = this->create_subscription<sensor_msgs::msg::JointState>(
        //     "control/jog_cmd", 10,
        //     std::bind(&MarvinRobotNode::jog_callback, this, std::placeholders::_1));

        // for tool communication
        // tool_com_sub_A_ = this->create_subscription<std_msgs::msg::UInt16MultiArray>(
        //     "control/tool_com_A", 10,
        //     std::bind(&MarvinRobotNode::tool_com_callback_A, this, std::placeholders::_1));
        // tool_com_sub_B_ = this->create_subscription<std_msgs::msg::UInt16MultiArray>(
        //     "control/tool_com_B", 10,
        //     std::bind(&MarvinRobotNode::tool_com_callback_B, this, std::placeholders::_1));
        // tool_com_pub_A_ = this->create_publisher<std_msgs::msg::UInt16MultiArray>("control/tool_ret_A", 1);
        // tool_com_pub_B_ = this->create_publisher<std_msgs::msg::UInt16MultiArray>("control/tool_ret_B", 1);
        rclcpp::on_shutdown(std::bind(&MarvinRobotNode::Shutdown, this));
        RCLCPP_INFO(this->get_logger(), "Marvin Robot Node initialized.");
    }

private:

    int open_can_socket(const std::string &ifname)
    {
        int sock = socket(PF_CAN, SOCK_RAW, CAN_RAW);
        if (sock < 0)
        {
            RCLCPP_ERROR(rclcpp::get_logger("CAN"), "Failed to create CAN socket for interface %s", ifname.c_str());
            return -1;
        }

        struct ifreq ifr{};
        std::strncpy(ifr.ifr_name, ifname.c_str(), IFNAMSIZ - 1);
        ifr.ifr_name[IFNAMSIZ - 1] = '\0'; // ensure null-terminated

        if (ioctl(sock, SIOCGIFINDEX, &ifr) < 0)
        {
            RCLCPP_ERROR(rclcpp::get_logger("CAN"), "No such interface: %s", ifname.c_str());
            close(sock);
            return -1;
        }

        struct sockaddr_can addr{};
        addr.can_family = AF_CAN;
        addr.can_ifindex = ifr.ifr_ifindex;

        if (bind(sock, reinterpret_cast<struct sockaddr *>(&addr), sizeof(addr)) < 0)
        {
            RCLCPP_ERROR(rclcpp::get_logger("CAN"), "Failed to bind to CAN interface: %s", ifname.c_str());
            close(sock);
            return -1;
        }

        RCLCPP_INFO(rclcpp::get_logger("CAN"), "Successfully opened CAN socket on interface %s", ifname.c_str());
        return sock;
    }
    void forward_to_sdk()
    {
        struct pollfd fds[2];
        fds[0].fd = sock0;
        fds[0].events = POLLIN;
        fds[1].fd = sock1;
        fds[1].events = POLLIN;

        while (!stop_)
        {
            int ret = poll(fds, 2, 1); // 1 ms timeout
            if (ret < 0)
            {
                perror("poll");
                break;
            }
            else if (ret == 0)
            {
                // Timeout, no frames
                continue;
            }

            // Check vcan0
            if (fds[0].revents & POLLIN)
            {
                struct can_frame frameA{};
                int nbytesA = read(sock0, &frameA, sizeof(frameA));
                if (nbytesA == sizeof(frameA))
                {
                    if (verbose_logging)
                    {
                        std::cout << "[vcan0] CAN frame received: ID=0x"
                                << std::hex << frameA.can_id
                                << " DLC=" << std::dec << (int)frameA.can_dlc
                                << " Data=[";
                        for (int i = 0; i < frameA.can_dlc; i++)
                        {
                            std::cout << std::hex << std::uppercase << (int)frameA.data[i];
                            if (i < frameA.can_dlc - 1) std::cout << " ";
                        }
                        std::cout << "]" << std::dec << std::endl;
                    }

                    sdk_write_canA(frameA);
                }
            }

            // Check vcan1
            if (fds[1].revents & POLLIN)
            {
                struct can_frame frameB{};
                int nbytesB = read(sock1, &frameB, sizeof(frameB));
                if (nbytesB == sizeof(frameB))
                {
                    if(verbose_logging){
                        std::cout << "[vcan1] CAN frame received: ID=0x"
                                << std::hex << frameB.can_id
                                << " DLC=" << std::dec << (int)frameB.can_dlc
                                << " Data=[";
                        for (int i = 0; i < frameB.can_dlc; i++)
                        {
                            std::cout << std::hex << std::uppercase << (int)frameB.data[i];
                            if (i < frameB.can_dlc - 1) std::cout << " ";
                        }
                        std::cout << "]" << std::dec << std::endl;
                    }

                    sdk_write_canB(frameB);
                }
            }
        }
    }

    void forward_to_sockets()
    {
        while (!stop_)
        {
            struct can_frame frameA{}, frameB{};
            // Read frame from SDK (blocking or non-blocking depending on SDK)
            if (sdk_read_canA(frameA))
            {
                // Write to vcan0
                if (sock0 >= 0)
                {
                    int nbytes = write(sock0, &frameA, sizeof(frameA));
                    if (nbytes != sizeof(frameA))
                    {
                        std::cerr << "[vcan0] Failed to write CAN frame" << std::endl;
                    }
                }
            }
            else if (sdk_read_canB(frameB))
            {
                // Write to vcan1
                if (sock1 >= 0)
                {
                    int nbytes = write(sock1, &frameB, sizeof(frameB));
                    if (nbytes != sizeof(frameB))
                    {
                        std::cerr << "[vcan1] Failed to write CAN frame" << std::endl;
                    }
                }
            }
            else
            {
                // avoid busy spin if SDK has no data
                std::this_thread::sleep_for(std::chrono::milliseconds(1));
            }
        }
    }

    bool sdk_read_canA(struct can_frame &frame)
    {
        unsigned char data[256];
        memset(data, 0, sizeof(data));
        long ret_ch = 1;

        long len = OnGetChDataA(data, &ret_ch);
        if (len <= 4)
        {
            return false; // no data or too short
        }

        // ID
        frame.can_id = (data[0] |
                        (data[1] << 8) |
                        (data[2] << 16) |
                        (data[3] << 24));

        // Data length = total - 4
        frame.can_dlc = static_cast<__u8>(len - 4);
        if (frame.can_dlc > 8)
            frame.can_dlc = 8; // clamp to classical CAN

        // Payload
        memcpy(frame.data, &data[4], frame.can_dlc);

        return true;
    }
    bool sdk_read_canB(struct can_frame &frame)
    {
        unsigned char data[256];
        memset(data, 0, sizeof(data));
        long ret_ch = 1;

        long len = OnGetChDataB(data, &ret_ch);
        if (len <= 4)
        {
            return false; // no data or too short
        }

        // ID
        frame.can_id = (data[0] |
                        (data[1] << 8) |
                        (data[2] << 16) |
                        (data[3] << 24));

        // Data length = total - 4
        frame.can_dlc = static_cast<__u8>(len - 4);
        if (frame.can_dlc > 8)
            frame.can_dlc = 8; // clamp to classical CAN

        // Payload
        memcpy(frame.data, &data[4], frame.can_dlc);

        return true;
    }
    bool sdk_write_canA(const struct can_frame &frame)
    {
        unsigned char data[256];
        memset(data, 0, sizeof(data));

        // Encode ID
        data[0] = frame.can_id & 0xFF;
        data[1] = (frame.can_id >> 8) & 0xFF;
        data[2] = (frame.can_id >> 16) & 0xFF;
        data[3] = (frame.can_id >> 24) & 0xFF;

        // Append payload only (no DLC)
        memcpy(&data[4], frame.data, frame.can_dlc);

        long size = 4 + frame.can_dlc;
        long set_ch = 1; // pick correct channel if needed
        return OnSetChDataA(data, size, set_ch);
    }
    bool sdk_write_canB(const struct can_frame &frame)
    {
        unsigned char data[256];
        memset(data, 0, sizeof(data));

        // Encode ID
        data[0] = frame.can_id & 0xFF;
        data[1] = (frame.can_id >> 8) & 0xFF;
        data[2] = (frame.can_id >> 16) & 0xFF;
        data[3] = (frame.can_id >> 24) & 0xFF;

        // Append payload only (no DLC)
        memcpy(&data[4], frame.data, frame.can_dlc);

        long size = 4 + frame.can_dlc;
        long set_ch = 1; // pick correct channel if needed
        return OnSetChDataB(data, size, set_ch);
    }
    
    void jog_callback(const sensor_msgs::msg::JointState::SharedPtr msg)
    {
        RCLCPP_INFO(this->get_logger(), "Jog command received: %s", msg->name[0].c_str());
        // Check if the message contains valid joint names
        // Check if the joint names match the expected names
        std::vector<double> joint_positionsA(7, 0.0); // Initialize with zeros
        std::vector<double> joint_positionsB(7, 0.0); // Initialize with zeros
        for (size_t i = 0; i < 7; ++i)
        {
            for (const auto &name : msg->name)
            {
                if (name == JointNames_A[i])
                {
                    RCLCPP_INFO(this->get_logger(), "Jog command for joint: %s", name.c_str());
                    joint_positionsA[i] = msg->position[i]; // Set the position for joint A
                }
            }
        }

        for (size_t i = 7; i < 14; ++i)
        {
            for (const auto &name : msg->name)
            {
                if (name == JointNames_B[i])
                {
                    RCLCPP_INFO(this->get_logger(), "Jog command for joint: %s", name.c_str());
                    joint_positionsB[i - 7] = msg->position[i]; // Set the position for joint B
                }
            }
        }
        // if(msg->data == 1){
        // 	jog_mode = true;
        // 	RCLCPP_INFO(this->get_logger(), "Jog mode enabled");
        // }
        // else if(msg->data == 0){
        // 	jog_mode = false;
        // 	RCLCPP_INFO(this->get_logger(), "Jog mode disabled");
        // }
        // else{
        // 	RCLCPP_WARN(this->get_logger(), "Invalid jog command: %d", msg->data);
        // }
    }

    void timer_ctrl_callback()
    {
        if (marvin_robot_->is_connected())
        {
            // marvin_robot_->ReadState();
            ReadRobotState();

            if (robot_ready)
            {   
                if(new_cmd_A && new_cmd_B){
                    marvin_robot_->PosCmd(joint_cmd_A_, joint_cmd_B_); // Call PosCmd to send joint commands}
                }
                else if(new_cmd_A){
                    marvin_robot_->PosCmdA(joint_cmd_A_);
                }
                else if(new_cmd_B){
                    marvin_robot_->PosCmdB(joint_cmd_B_);
                }
                else {
                    marvin_robot_->emptyCmd();
                }
                

            }
            else{
                marvin_robot_->emptyCmd();
            }
            new_cmd_A = false;
            new_cmd_B = false;
            // WriteToolCom();
            // ReadToolCom();
            
        }
        else
        {
            RCLCPP_WARN(this->get_logger(), "Robot not connected. Skipping state retrieval.");
        }
    }

    void ReadRobotState()
    {
        // This function can be used to publish joint states if needed
        // For now, we will just print the joint names
        std::vector<FX_FLOAT> joint_positions, joint_velocities, joint_efforts;
        if (marvin_robot_->ReadState(joint_positions, joint_velocities, joint_efforts))
        {   
            if(!marvin_robot_->check_connection())
            {
                RCLCPP_ERROR(this->get_logger(), "Robot connection lost.");
                //exit the program
                rclcpp::shutdown();
            }
            sensor_msgs::msg::JointState joint_state_msg;
            geometry_msgs::msg::PoseStamped pose_msg;
            joint_state_msg.header.stamp = this->now();
            pose_msg.header.stamp = this->now();

            joint_state_msg.name = JointNamesBoth;

            joint_state_msg.position.resize(14, 0.0); // Initialize positions to zero
            joint_state_msg.velocity.resize(14, 0.0); // Initialize velocities
            joint_state_msg.effort.resize(14, 0.0);   // Initialize efforts
            // Convert joint_positions (FX_FLOAT, likely float) to double for ROS message
            for (size_t i = 0; i < 14; ++i)
            {
                joint_state_msg.position[i] = static_cast<double>(joint_positions[i]);
                joint_state_msg.velocity[i] = static_cast<double>(joint_velocities[i]);
                joint_state_msg.effort[i] = static_cast<double>(joint_efforts[i]);
            }
            if(counter_%5==0 && pub_joint_states){
                joint_state_pub_->publish(joint_state_msg);
            }
        }
        else
        {
            RCLCPP_ERROR(this->get_logger(), "Failed to read joint states from the robot.");
        }
        counter_++;
        if (counter_ % 100 == 0) {
            int robot_stateA_, robot_stateB_;
            marvin_robot_->GetState(robot_stateA_, robot_stateB_); // Get the current robot state
            if (!robot_ready)
                robot_stateA_ = -1;
            if (!robot_ready)
                robot_stateB_ = -1;
            robot_stateA = robot_stateA_;
            robot_stateB = robot_stateB_;
            std_msgs::msg::Int16MultiArray state_msg;
            state_msg.data.push_back(static_cast<int16_t>(robot_stateA));
            state_msg.data.push_back(static_cast<int16_t>(robot_stateB));
            arm_state_pub_->publish(state_msg);
            counter_ = 0;
        }
    }

    // void ReadToolCom(){
    //     long tagA = OnGetChDataA(data_ptrA_in, &ret_chA);
    //     long tagB = OnGetChDataB(data_ptrB_in, &ret_chB);
    //     std_msgs::msg::UInt16MultiArray msgA, msgB;
    //     msgA.data.clear();
    //     msgB.data.clear();
    //     for(int i=0; i<tagA; i++){
    //         msgA.data.push_back(static_cast<uint16_t>(data_ptrA_in[i]));
    //     }
    //     for(int i=0; i<tagB; i++){
    //         msgB.data.push_back(static_cast<uint16_t>(data_ptrB_in[i]));
    //     }
    //     if (tagA > 0)
    //         tool_com_pub_A_->publish(msgA);
    //     if (tagB > 0)
    //         tool_com_pub_B_->publish(msgB);
    //     // RCLCPP_INFO(this->get_logger(), "Tool Com A received %ld bytes, Tool Com B received %ld bytes", tagA, tagB);
    // }

    // void WriteToolCom(){
    //     if(dataA_len>0){
    //         OnSetChDataA(data_ptrA_out, dataA_len, ret_chA);
    //         dataA_len = 0;
    //     }
    //     if(dataB_len>0){
    //         OnSetChDataB(data_ptrB_out, dataB_len, ret_chB);
    //         // RCLCPP_INFO(this->get_logger(), "Tool Com B sent %d bytes", dataB_len);
    //         dataB_len = 0;
    //     }

    // }

    // void tool_com_callback_A(const std_msgs::msg::UInt16MultiArray::SharedPtr msg)
    // {
    //     if (!msg->data.empty())
    //     {
    //         // Limit to the buffer size
    //         dataA_len = std::min(msg->data.size(), static_cast<size_t>(256));

    //         for (size_t i = 0; i < dataA_len; ++i) {
    //             data_ptrA_out[i] = static_cast<unsigned char>(msg->data[i] & 0xFF);
    //         }
    //     }
    //     else
    //     {
    //         dataA_len = 0; // No data received
    //     }
    // }


    // void tool_com_callback_B(const std_msgs::msg::UInt16MultiArray::SharedPtr msg)
    // {
    //     if (!msg->data.empty())
    //     {
    //         // Limit to the buffer size
    //         dataB_len = std::min(msg->data.size(), static_cast<size_t>(256));

    //         for (size_t i = 0; i < dataB_len; ++i)
    //         {
    //             data_ptrB_out[i] = static_cast<unsigned char>(msg->data[i] & 0xFF);
    //         }
    //     }
    //     else
    //     {
    //         dataB_len = 0; // No data received
    //     }
    // }

    void motor_err_code_callback(const std::shared_ptr<marvin_msgs::srv::MotorErrCode::Request> request,
                                 std::shared_ptr<marvin_msgs::srv::MotorErrCode::Response> response)
    {
        long MotorErrcodeA[7] = {-1, -1, -1, -1, -1, -1, -1};
        long MotorErrcodeB[7] = {-1, -1, -1, -1, -1, -1, -1};
        marvin_robot_->readErrCode(MotorErrcodeA, MotorErrcodeB);
        response->error_code.clear();
        for (int i = 0; i < 7; i++)
        {
            response->error_code.push_back(static_cast<int16_t>(MotorErrcodeA[i]));
        }
        for (int i = 0; i < 7; i++)
        {
            response->error_code.push_back(static_cast<int16_t>(MotorErrcodeB[i]));
        }
        response->success = true;
        RCLCPP_INFO(this->get_logger(), "Motor error codes retrieved and sent in response.");
    }

    void set_ready_callback(const std::shared_ptr<std_srvs::srv::Trigger::Request> request,
                            std::shared_ptr<std_srvs::srv::Trigger::Response> response)
    {
        if (marvin_robot_->is_connected())
        {
            robot_ready = true;
            response->success = true;
            response->message = "Robot is ready.";
            RCLCPP_INFO(this->get_logger(), "Robot is ready.");
        }
        else
        {
            response->success = false;
            response->message = "Robot not connected. Cannot set ready state.";
            RCLCPP_WARN(this->get_logger(), "Robot not connected. Cannot set ready state.");
        }
    }

    void joint_cmd_callback_A(const marvin_msgs::msg::Jointcmd::SharedPtr msg)
    {
        rclcpp::Time now = this->now();
        if ((now - msg->header.stamp).seconds() > 0.1)
        {
            return;
        }
        // Handle incoming joint commands
        
        if (marvin_robot_->is_connected())
        {
            std::vector<double> joint_positions(msg->positions.begin(), msg->positions.end());

            if (joint_positions.size() == 7) // Ensure we have 7 joint positions
            {
                new_cmd_A = true;
                set_joint_cmd_A(joint_positions);
            }
            else
            {
                std::cout << joint_positions.size() << std::endl;
                RCLCPP_ERROR(this->get_logger(), "Received joint command with incorrect number of positions.");
            }
        }
        else
        {
            RCLCPP_WARN(this->get_logger(), "Robot not connected. Cannot process joint command.");
        }
    }

    void joint_cmd_callback_B(const marvin_msgs::msg::Jointcmd::SharedPtr msg)
    {
        // Ignore if message is too old (older than 100ms)
        rclcpp::Time now = this->now();
        if ((now - msg->header.stamp).seconds() > 0.1)
        {
            return;
        }
        
        // Handle incoming joint commands
        if (marvin_robot_->is_connected())
        {
            std::vector<double> joint_positions(msg->positions.begin(), msg->positions.end());

            if (joint_positions.size() == 7) // Ensure we have 7 joint positions
            {
                new_cmd_B = true;
                set_joint_cmd_B(joint_positions);
            }
            else
            {
                std::cout << joint_positions.size() << std::endl;
                RCLCPP_ERROR(this->get_logger(), "Received joint command with incorrect number of positions.");
            }
        }
        else
        {
            RCLCPP_WARN(this->get_logger(), "Robot not connected. Cannot process joint command.");
        }
    }

    void set_joint_cmd_A(const std::vector<double> &joint_cmd)
    {
        if (joint_cmd.size() == 7)
        {
            for (size_t i = 0; i < joint_cmd.size(); ++i)
            {
                joint_cmd_A_[i] = joint_cmd[i] * (180.0 / M_PI); // Convert radians to degrees
            }
        }
        else
        {
            RCLCPP_ERROR(rclcpp::get_logger("marvin_robot"), "Joint command A must have exactly 7 elements.");
        }
    }

    void set_joint_cmd_B(const std::vector<double> &joint_cmd)
    {
        if (joint_cmd.size() == 7)
        {
            for (size_t i = 0; i < joint_cmd.size(); ++i)
            {
                joint_cmd_B_[i] = joint_cmd[i] * (180.0 / M_PI); // Convert radians to degrees
            }
        }
        else
        {
            RCLCPP_ERROR(rclcpp::get_logger("marvin_robot"), "Joint command B must have exactly 7 elements.");
        }
    }

    void set_mode_callback(const std::shared_ptr<marvin_msgs::srv::Int::Request> request,
                           std::shared_ptr<marvin_msgs::srv::Int::Response> response)
    {   
        if (open_tool_ch){
            open_tool_ch = false;
            RCLCPP_INFO(this->get_logger(), "Tool communication channel closed for mode change.");
        }
        if (marvin_robot_->is_connected())
        {
            if (robot_stateA == -1 || robot_stateB == -1)
            {
                response->success = false;
                response->message = "Arms not ready. Cannot set mode.";
                RCLCPP_WARN(this->get_logger(), "Arms not ready. Cannot set mode.");
                return;
            }
            int mode = request->data; // Get the mode from the request
            if (mode != 0 && mode != 1 && mode != 2 && mode != 3)
            {
                response->success = false;
                response->message = "Invalid mode requested. Valid modes are 0, 1, or 3. 2 not used";
                RCLCPP_ERROR(this->get_logger(), "Invalid mode requested: %d. Valid modes are 0, 1, or 3. 2 not used", mode);
                return;
            }
           
            if (marvin_robot_->SetMode(mode))
            {
                response->success = true;
                RCLCPP_INFO(this->get_logger(), "Mode set to %d successfully.", mode);
            }
            else
            {
                response->success = false;
                RCLCPP_ERROR(this->get_logger(), "Failed to set mode to %d.", mode);
            }
        }
        else
        {
            response->success = false;
            RCLCPP_WARN(this->get_logger(), "Robot not connected. Cannot set mode.");
        }
    }

    void set_drag_cbk(const std::shared_ptr<marvin_msgs::srv::Int_Request> request,
                      std::shared_ptr<marvin_msgs::srv::Int_Response> response)
    {
        
        if (marvin_robot_->is_connected())
        {
            if (robot_stateA == -1 || robot_stateB == -1)
            {
                response->success = false;
                response->message = "Arms not ready. Cannot set drag mode.";
                RCLCPP_WARN(this->get_logger(), "Arms not ready. Cannot set drag mode.");
                return;
            }
            if(request->data==0){
                marvin_robot_->setdrag(request->data); // Set drag mode to true
                response->success = true;

                response->message = "Drag mode turned off successfully.";
                RCLCPP_INFO(this->get_logger(), "Drag mode turned off successfully.");
            }
            else if(request->data==1){
                marvin_robot_->setdrag(request->data); // Set drag mode to false
                response->success = true;
                response->message = "Drag mode turned on successfully.";
                RCLCPP_INFO(this->get_logger(), "Drag mode turned on successfully.");
            }

        }
        else
        {
            response->success = false;
            response->message = "Robot not connected. Cannot set drag mode.";
            RCLCPP_WARN(this->get_logger(), "Robot not connected. Cannot set drag mode.");
        }
    }

    void set_vel_ratio_callback(const std::shared_ptr<marvin_msgs::srv::Int::Request> request,
                                std::shared_ptr<marvin_msgs::srv::Int::Response> response)
    {   
        
        if (marvin_robot_->is_connected())
        {

            // if (open_tool_ch){
            //     open_tool_ch = false;
            //     RCLCPP_INFO(this->get_logger(), "Tool communication channel closed for vel change.");
            //     return;
            // }

            if (robot_stateA == 0 && robot_stateB == 0)
            {

                if (request->data == 0)
                {
                    marvin_robot_->set_speed(30, 30);
                    response->success = true;
                    // RCLCPP_INFO(this->get_logger(), "Velocity and acceleration scale set to 30.");
                    response->message = "Velocity and acceleration scale set to 30.";
                }
                else if (request->data == 1)
                {
                    marvin_robot_->set_speed(50, 50);
                    response->success = true;
                    // RCLCPP_INFO(this->get_logger(), "Velocity and acceleration scale set to 50.");
                    response->message = "Velocity and acceleration scale set to 50.";
                }
                else if (request->data == 2)
                {
                    marvin_robot_->set_speed(80, 80);
                    response->success = true;
                    response->message = "Velocity and acceleration scale set to 80.";
                }
                else if (request->data == 3)
                {
                    marvin_robot_->set_speed(100, 100);
                    response->success = true;
                    response->message = "Velocity and acceleration scale set to 100.";
                }
                else
                {
                    response->success = false;
                    RCLCPP_ERROR(this->get_logger(), "Invalid velocity ratio requested: %d. Valid ratios are 0, 1, 2, 3.", request->data);
                    response->message = "Invalid velocity ratio requested.";
                }
            }
            else
            {
                response->success = false;
                RCLCPP_WARN(this->get_logger(), "Robot not in idle state. Cannot set velocity ratio.");
                response->message = "Robot not in idle state. Cannot set velocity ratio.";
            }
        }
        else
        {
            response->success = false;
            RCLCPP_WARN(this->get_logger(), "Robot not connected. Cannot set velocity ratio.");
            response->message = "Robot not connected. Cannot set velocity ratio.";
        }
        open_tool_ch = true;
    }

    // void set_vel_ratio_callback(const std::shared_ptr<marvin_msgs::srv::Velratio::Request> request,
    //                        std::shared_ptr<marvin_msgs::srv::Velratio::Response> response)
    // {
    //     if (marvin_robot_->is_connected())
    //     {
    //         int vel_scale = request->vel;
    //         int acc_scale = request->acc;
    //         marvin_robot_->set_speed(vel_scale, acc_scale);
    //         response->success = true;
    //         RCLCPP_INFO(this->get_logger(), "Velocity and acceleration scale set to %d and %d.", vel_scale, acc_scale);
    //     }
    //     else
    //     {
    //         response->success = false;
    //         RCLCPP_WARN(this->get_logger(), "Robot not connected. Cannot set velocity ratio.");
    //     }
    // }

    void clearfault_callback(const std::shared_ptr<std_srvs::srv::Trigger::Request> request,
                             std::shared_ptr<std_srvs::srv::Trigger::Response> response)
    {
        marvin_robot_->ClearFault();
    }

    void pub_feedback()
    {
        if (marvin_robot_->is_connected())
        {
            marvin_msgs::msg::Jointfeedback joint_feedback_msg;
            joint_feedback_msg.header.stamp = this->now();

            // Populate the feedback message with current joint states

            for (size_t i = 0; i < 7; ++i)
            {
                joint_feedback_msg.positions[i] = marvin_robot_->Joint_pos_A[i];
                joint_feedback_msg.velocities[i] = marvin_robot_->Joint_vel_A[i];
                joint_feedback_msg.efforts[i] = marvin_robot_->Joint_eff_A[i];
                // if (!left_ready)
                //     joint_cmd_A_[i] = marvin_robot_->Joint_pos_A[i] * (180.0 / M_PI);
                // ;
            }
            for (size_t i = 0; i < 7; ++i)
            {
                joint_feedback_msg.positions[i + 7] = marvin_robot_->Joint_pos_B[i];
                joint_feedback_msg.velocities[i + 7] = marvin_robot_->Joint_vel_B[i];
                joint_feedback_msg.efforts[i + 7] = marvin_robot_->Joint_eff_B[i];
                // if (!right_ready)
                //     joint_cmd_B_[i] = marvin_robot_->Joint_pos_B[i] * (180.0 / M_PI);
                // ;
            }
            joint_feedback_pub_->publish(joint_feedback_msg);
        }
    }

    // void collision_callback_A(const std_msgs::msg::Bool::SharedPtr msg)
    // {
    //     collision_status_A = msg->data;
    // }
    // void collision_callback_B(const std_msgs::msg::Bool::SharedPtr msg)
    // {
    //     collision_status_B = msg->data;
    // }

    void Shutdown()
    {
        if (marvin_robot_->is_connected())
        {
            marvin_robot_->ClearFault();

            marvin_robot_->servo_off();  // Turn off servos
            marvin_robot_->ClearFault(); // Clear any faults
            close(sock0);
            close(sock1);
            std::cout << "Shutdown complete. Robot servos turned off and faults cleared." << std::endl;
        }
        else
        {
            std::cout << "Robot not connected. No shutdown actions performed." << std::endl;
        }
    }

    // std::vector<std::string> JointNames = {"Joint1", "Joint2", "Joint3", "Joint4", "Joint5", "Joint6", "Joint7"};
    std::vector<std::string> JointNames_A, JointNames_B, JointNamesBoth;

    std::shared_ptr<MarvinRobot> marvin_robot_;
    rclcpp::TimerBase::SharedPtr timer_, timer2_;
    rclcpp::Publisher<sensor_msgs::msg::JointState>::SharedPtr joint_state_pub_;
    rclcpp::Publisher<geometry_msgs::msg::PoseStamped>::SharedPtr pose_A_pub_;
    rclcpp::Subscription<marvin_msgs::msg::Jointcmd>::SharedPtr joint_cmd_sub_A_, joint_cmd_sub_B_;
    rclcpp::Subscription<std_msgs::msg::Bool>::SharedPtr collision_sub_A_, collision_sub_B_;
    rclcpp::Subscription<sensor_msgs::msg::JointState>::SharedPtr Jog_subscriber;

    // rclcpp::Subscription<std_msgs::msg::UInt16MultiArray>::SharedPtr tool_com_sub_A_, tool_com_sub_B_;
    rclcpp::Service<marvin_msgs::srv::Int>::SharedPtr set_mode_service_;
    rclcpp::Service<marvin_msgs::srv::Int>::SharedPtr set_drag_service_;
    rclcpp::Service<marvin_msgs::srv::Int>::SharedPtr vel_ratio_service_;
    rclcpp::Service<std_srvs::srv::Trigger>::SharedPtr set_ready_service_;
    rclcpp::Publisher<marvin_msgs::msg::Jointfeedback>::SharedPtr joint_feedback_pub_;
    rclcpp::Publisher<std_msgs::msg::Int16MultiArray>::SharedPtr arm_state_pub_;
    // rclcpp::Publisher<std_msgs::msg::UInt16MultiArray>::SharedPtr tool_com_pub_A_, tool_com_pub_B_;
    rclcpp::Service<marvin_msgs::srv::MotorErrCode>::SharedPtr motor_err_code_service_;
    rclcpp::Service<std_srvs::srv::Trigger>::SharedPtr clear_fault_service_;
    std::vector<double> default_k = {2.0, 2.0, 2.0, 1.6, 1.0, 1.0, 1.0};
    std::vector<double> default_d = {0.6, 0.6, 0.6, 0.4, 0.2, 0.2, 0.2};
    std::vector<double> default_kc = {3000,3000,3000,60,60,60,10};
    std::vector<double> default_dc = {0.1,0.1,0.1,0.3,0.3,0.3,1};
    bool cmd_recievedA = false, cmd_recievedB = false;
    bool collision_status_A = true, collision_status_B = true;
    bool jog_mode = false;
    double joint_cmd_A_[7];
    double joint_cmd_B_[7];
    bool robot_ready = false;
    bool new_cmd_A = false, new_cmd_B = false;
    int robot_stateA, robot_stateB;
    int counter_=0;
    unsigned char data_ptrA_in[256], data_ptrB_in[256];
    unsigned char data_ptrA_out[256] = {0};
    unsigned char data_ptrB_out[256] = {0};
    long ret_chA=1, ret_chB=1;
    long dataA_len = 0, dataB_len = 0;
    bool open_tool_ch = false;
    int sock_;
    std::atomic<bool> stop_;
    std::thread writer_thread_;
    std::thread reader_thread_;
    int sock0, sock1;
    bool verbose_logging = false;
    bool pub_joint_states = true;
};

int main(int argc, char **argv)
{
    rclcpp::init(argc, argv);
    rclcpp::spin(std::make_shared<MarvinRobotNode>());
    rclcpp::shutdown();
    return 0;
}
