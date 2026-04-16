#include "marvin_ros_control/marvin_robot.h"


    MarvinRobot::MarvinRobot():connected_(false) {}

    // Initialization function to connect to the robot by its IP address
    bool MarvinRobot::init(const std::string &robot_ip)
    {   
       
        std::vector<int> ip_parts = parse_ip(robot_ip);

        if (ip_parts.size() != 4)
        {
            RCLCPP_ERROR(rclcpp::get_logger("marvin_robot"), "Invalid IP address format.");
            return false;
        }

        // Call the SDK's OnLinkTo function
        OnLinkTo(ip_parts[0], ip_parts[1], ip_parts[2], ip_parts[3]);
        frame_idx_L_prev = -1;
        frame_idx_R_prev = -1;
        frame_lost_count = 0;
        frame_lost_thres = 100;
        int time_accum = 0;
        while (true){
            
            OnGetServoErr_A(MotorErrcodeA);
            std::cout << "Servo Error Codes A: "<<std::hex<<MotorErrcodeA[0] << ", " << MotorErrcodeA[1] << ", " << MotorErrcodeA[2] << ", "
                      << MotorErrcodeA[3] << ", " << MotorErrcodeA[4] << ", " << MotorErrcodeA[5] << ", " << MotorErrcodeA[6] << std::dec<< std::endl;
                      OnGetServoErr_B(MotorErrcodeB);
            std::cout << "Servo Error Codes B: "<<std::hex<< MotorErrcodeB[0] << ", " << MotorErrcodeB[1] << ", " << MotorErrcodeB[2] << ", "
                      << MotorErrcodeB[3] << ", " << MotorErrcodeB[4] << ", " << MotorErrcodeB[5] << ", " << MotorErrcodeB[6] << std::dec<< std::endl;
            bool all_servos_ok = true;
            for (size_t i = 0; i < 7; i++)
                      {
                        if (MotorErrcodeA[i] == 0 || MotorErrcodeB[i] == 0)
                        {
                            // std::cout << "Servo " << i << " is OK." << std::endl;
                        }
                        else
                        {
                            // std::cout << "Servo " << i << " has an error: A=" << std::hex << MotorErrcodeA[i] 
                            //           << ", B=" << MotorErrcodeB[i] << std::dec << std::endl;
                            all_servos_ok = false;
                        }
                      }
                      
            ClearFault();
            servo_off();
            OnLocalLogOff();
            // Sleep for 1 second before retrying
            rclcpp::sleep_for(std::chrono::seconds(1));
            time_accum += 1;
            if (all_servos_ok) {
                // RCLCPP_INFO(rclcpp::get_logger("marvin_robot"), "All servos initialized successfully");
                // RCLCPP_INFO(rclcpp::get_logger("marvin_robot"), "\033[32mRobot is ready\033[0m");
            connected_ = true;

            std::vector<float> joint_positions, joint_velocities, joint_efforts;
            ReadState(joint_positions, joint_velocities, joint_efforts);
            // for (size_t i = 0; i < 7; i++) {
            //     joint_cmd_A_[i] = joint_positions[i]*FXARM_R2D;
            //     joint_cmd_B_[i] = joint_positions[i+7]*FXARM_R2D; // Assuming the second half of the vector is for B
            // // Assuming the second half of the vector is for B
            // }
                
            // double kinePara_A[7]= {0,0,0,0,0,0,0};
            // double kinePara_B[7]= {0,0,0,0,0,0,0};

            // OnSetTool_A(kinePara_A, dynPara_A);
            // OnSetTool_B(kinePara_B, dynPara_B);

            return true;
            }
            if (time_accum > 20) // Wait for 5 seconds before giving up
            {
                RCLCPP_ERROR(rclcpp::get_logger("marvin_robot"), "Failed to connect to robot after multiple attempts.");
                break;}
        }
        
        return false;
        
    }

    bool MarvinRobot::init_tool_dyna(double dynPara_A[10], double dynPara_B[10]){
        OnClearSet();
        double kinePara_A[7]= {0,0,0,0,0,0,0};
        double kinePara_B[7]= {0,0,0,0,0,0,0};
        OnSetTool_A(kinePara_A, dynPara_A);
        OnSetTool_B(kinePara_B, dynPara_B);
        bool success = OnSetSend();
        usleep(100000);
        return success;
    }

    bool MarvinRobot::is_connected() const
    {
        return connected_;
    }

    bool MarvinRobot::ReadState(std::vector<float>& joint_positions, std::vector<float>& joint_velocities, std::vector<float>& joint_efforts){

        
        DCSS* Ret = new DCSS();
        OnGetBuf(Ret);
        frame_idx_L = Ret->m_Out[0].m_OutFrameSerial;
        frame_idx_R = Ret->m_Out[1].m_OutFrameSerial;
        StateCtr state_A =Ret->m_State[0];
        StateCtr state_B =Ret->m_State[1];
        ArmState_A = state_A.m_CurState;
        ArmState_B = state_B.m_CurState;
        ErrCode_A = state_A.m_ERRCode;
        ErrCode_B = state_B.m_ERRCode;
        RT_OUT RT_out_A =  Ret->m_Out[0];
        RT_OUT RT_out_B =  Ret->m_Out[1];
        low_spd_flag_A = RT_out_A.m_LowSpdFlag;
        low_spd_flag_B = RT_out_B.m_LowSpdFlag;

        joint_positions.clear(); // Clear the vector to store new joint positions
        joint_velocities.clear(); // Clear the vector to store new joint velocities
        joint_efforts.clear(); // Clear the vector to store new joint efforts

        for (int i = 0; i < 7; ++i) {
            Joint_pos_A[i] = RT_out_A.m_FB_Joint_Pos[i] * D2R ; // Convert degrees to radians
            // Joint_pos_B[i] = RT_out_B.m_FB_Joint_Pos[i] * D2R ; // Convert degrees to radians
            joint_positions.push_back(Joint_pos_A[i]);
            // joint_positions.push_back(Joint_pos_B[i]);
            Joint_vel_A[i] = RT_out_A.m_FB_Joint_Vel[i] * D2R; // Convert degrees to radians
            // Joint_vel_B[i] = RT_out_B.m_FB_Joint_Vel[i] * D2R; // Convert degrees to radians
            joint_velocities.push_back(Joint_vel_A[i]);
            // joint_velocities.push_back(Joint_vel_B[i]);
            Joint_eff_A[i] = RT_out_A.m_FB_Joint_SToq[i];
            // Joint_eff_B[i] = RT_out_B.m_FB_Joint_SToq[i];
            joint_efforts.push_back(Joint_eff_A[i]);
            // joint_efforts.push_back(Joint_eff_B[i]);
        }
        for (int i = 0; i < 7; ++i) {
            // Joint_pos_A[i] = RT_out_A.m_FB_Joint_Pos[i] * D2R ; // Convert degrees to radians
            Joint_pos_B[i] = RT_out_B.m_FB_Joint_Pos[i] * D2R ; // Convert degrees to radians
            // joint_positions.push_back(Joint_pos_A[i]);
            joint_positions.push_back(Joint_pos_B[i]);
            // Joint_vel_A[i] = RT_out_A.m_FB_Joint_Vel[i] * D2R; // Convert degrees to radians
            Joint_vel_B[i] = RT_out_B.m_FB_Joint_Vel[i] * D2R; // Convert degrees to radians
            // joint_velocities.push_back(Joint_vel_A[i]);
            joint_velocities.push_back(Joint_vel_B[i]);
            // Joint_eff_A[i] = RT_out_A.m_FB_Joint_SToq[i];
            Joint_eff_B[i] = RT_out_B.m_FB_Joint_SToq[i];
            // joint_efforts.push_back(Joint_eff_A[i]);
            joint_efforts.push_back(Joint_eff_B[i]);
        }
        
        robot_state[0] = ArmState_A; // Update the robot state
        robot_state[1] = ArmState_B; // Update the robot state for B
        return true;
    }

    bool MarvinRobot::check_connection(){
        if (frame_idx_L == frame_idx_L_prev || frame_idx_R == frame_idx_R_prev) {
            // std::cout<<"frame id Left: "<<frame_idx_L<<" frame id Right: "<<frame_idx_R<<std::endl;
            // return false; // No new data received
            frame_lost_count +=1;
        }
        else {
            frame_lost_count = 0;
            frame_idx_L_prev = frame_idx_L;
            frame_idx_R_prev = frame_idx_R;
        }
        if(frame_lost_count > frame_lost_thres){
            return false;
        }
        else{
            return true;
        }
    }

    bool MarvinRobot::readErrCode(long *err_code_A, long *err_code_B)
    {   
        OnGetServoErr_A(MotorErrcodeA);
        OnGetServoErr_B(MotorErrcodeB);

        for (int i = 0; i < 7; i++) {
            err_code_A[i] = MotorErrcodeA[i];
            err_code_B[i] = MotorErrcodeB[i];
        }
        return true;
        
    }

    bool MarvinRobot::PosCmd(double joint_cmd_A[7], double joint_cmd_B[7]){
        
        OnClearSet();
        OnSetJointCmdPos_A(joint_cmd_A);
        OnSetJointCmdPos_B(joint_cmd_B);

        // Send via SDK
        // long status = OnSetChDataB(data_ptr, size_int, set_ch);

        // std::cout<<"send can status: "<<status<<std::endl;
        bool success = OnSetSend();
        return success;
    }

    bool MarvinRobot::PosCmdA(double joint_cmd_A[7]){
        
        OnClearSet();
        OnSetJointCmdPos_A(joint_cmd_A);
        bool success = OnSetSend();
        return success;
    }

    bool MarvinRobot::PosCmdB(double joint_cmd_B[7]){
        
        OnClearSet();
        OnSetJointCmdPos_B(joint_cmd_B);
        bool success = OnSetSend();
        return success;
    }

    bool MarvinRobot::emptyCmd(){
        OnClearSet();
        bool success = OnSetSend();
        return success;
    }

    bool MarvinRobot::SetMode(int mode){// mode 0: idle, 1: position, 2: CartTorque, 3: torque
        // servo_off();
        if (low_spd_flag_A != 1 || low_spd_flag_B != 1) {
            RCLCPP_ERROR(rclcpp::get_logger("marvin_robot"), "Robot is in moving, please stop and try again.");
            return false;
        }
        ClearFault();
        OnClearSet();


        // ARM_STATE_IDLE = 0,           //////// 下伺服
        // ARM_STATE_POSITION = 1,		//////// 位置跟随
        // ARM_STATE_PVT = 2,			//////// PVT
        // ARM_STATE_TORQ = 3,			//////// 扭矩
        if (mode == 0){        
        OnSetTargetState_A(mode);
        OnSetTargetState_B(mode);
    }
        else if (mode == 1) {
            OnSetTargetState_A(mode);
            OnSetTargetState_B(mode);
            // OnSetJointLmt_A(100,100);
 	        // OnSetJointLmt_B(100,100);
        }
        else if (mode == 2) {
            //not available
            OnSetTargetState_A(mode);
            OnSetTargetState_B(mode);
            OnSetImpType_A(2); // Set impedance type to 0
            OnSetImpType_B(2); // Set impedance type to 0
            // OnSetImpType_A(2); // Set impedance type to 0
            // OnSetImpType_B(2); // Set impedance type to 0
            // // Type = 1 关节阻抗
            // // Type = 2 坐标阻抗
            // // Type = 3 力控

            
            // OnSetCartKD_A(K_Ac, D_Ac,2);
            // OnSetCartKD_B(K_Bc, D_Bc,2);
        }

        else if (mode == 3) {

            OnSetTargetState_A(mode);
            OnSetTargetState_B(mode);
            OnSetImpType_A(1); // Set impedance type to 0
            OnSetImpType_B(1); // Set impedance type to 0
            // OnSetJointLmt_A(80,80);
 	        // OnSetJointLmt_B(80,80);
            // Type = 1 关节阻抗
            // Type = 2 坐标阻抗
            // Type = 3 力控


            OnSetJointKD_A(K_A, D_A);
            OnSetJointKD_B(K_B, D_B);
        }

        else if (mode == 4) {

            OnSetTargetState_A(3);
            OnSetTargetState_B(3);
            OnSetImpType_A(2); // Set impedance type to 0
            OnSetImpType_B(2); // Set impedance type to 0
            // OnSetJointLmt_A(80,80);
 	        // OnSetJointLmt_B(80,80);
            // Type = 1 关节阻抗
            // Type = 2 坐标阻抗
            // Type = 3 力控
            int type = 2; 
            OnSetCartKD_A(K_Ac, D_Ac,type);
            OnSetCartKD_A(K_Bc, D_Bc,type);
        }
        // else if (mode == 4) {
        //     // OnSetJointLmt_A(100,100);
 	    //     // OnSetJointLmt_B(100,100);
        //     OnSetImpType_A(1); // Set impedance type to 0
        //     OnSetImpType_B(1);
        //     OnSetCartKD_A(K_A, D_A,1);
        //     OnSetCartKD_B(K_B, D_B,1);
        // }
        else {
            RCLCPP_ERROR(rclcpp::get_logger("marvin_robot"), "Invalid mode.");
            return false;
        }
        OnSetSend();
        usleep(100000);
        return true;
    }
    bool MarvinRobot::setdrag(bool on_off)
    {
        int drag_mode; // 1 for drag mode, 0 for idle mode
        if(on_off){
            drag_mode = 1; // Set to drag mode
        } 
        else {
            drag_mode = 0; // Set to idle mode
        }
        OnClearSet();
        OnSetDragSpace_A(drag_mode); // Set target state to drag
        OnSetDragSpace_B(drag_mode); // Set target state to drag for B
        OnSetSend();
        usleep(100000); // Sleep for 100 ms to ensure the command is processed
        return true;
    }
    void MarvinRobot::servo_off()
    {
        OnClearSet();
        OnSetTargetState_A(0); // Set target state to idle
        OnSetTargetState_B(0); // Set target state to idle for B
        OnSetSend();
        usleep(100000); // Sleep for 100 ms to ensure the command is processed
    }



    void MarvinRobot::GetState(int &stateA, int &stateB)
    {
        stateA = robot_state[0]; // Return the current robot state
        stateB = robot_state[1]; // Return the current robot state for B
    }

    
    void MarvinRobot::ClearFault()
    {   
        
        OnClearErr_A();
        OnClearErr_B();

    }
    void MarvinRobot::GetJointHome_A(double *joint_home)
    {
        for (int i = 0; i < 7; ++i)
        {
            joint_home[i] = joint_home_A_[i];
        }
    }
    void MarvinRobot::GetJointHome_B(double *joint_home)
    {
        for (int i = 0; i < 7; ++i)
        {
            joint_home[i] = joint_home_B_[i];
        }
    }
    void MarvinRobot::SetKDA(std::vector<double> &k, std::vector<double> &d)
    {
        if (k.size() == 7 && d.size() == 7)
        {
            for (size_t i = 0; i < 7; ++i)
            {
                K_A[i] = k[i];
                D_A[i] = d[i];
            }
        }
        else
        {
            RCLCPP_ERROR(rclcpp::get_logger("marvin_robot"), "K and D must have exactly 7 elements each.");
        }
    }
    void MarvinRobot::SetKDB(std::vector<double> &k, std::vector<double> &d)
    {
        if (k.size() == 7 && d.size() == 7)
        {
            for (size_t i = 0; i < 7; ++i)
            {
                K_B[i] = k[i];
                D_B[i] = d[i];
            }
        }
        else
        {
            RCLCPP_ERROR(rclcpp::get_logger("marvin_robot"), "K and D must have exactly 7 elements each.");
        }
    }

    void MarvinRobot::SetKDACart(std::vector<double> &k, std::vector<double> &d)
    {
        if (k.size() == 7 && d.size() == 7)
        {
            for (size_t i = 0; i < 7; ++i)
            {
                K_Ac[i] = k[i];
                D_Ac[i] = d[i];
            }
        }
        else
        {
            RCLCPP_ERROR(rclcpp::get_logger("marvin_robot"), "Cart K and D must have exactly 7 elements each.");
        }
    }
    void MarvinRobot::SetKDBCart(std::vector<double> &k, std::vector<double> &d)
    {
        if (k.size() == 7 && d.size() == 7)
        {
            for (size_t i = 0; i < 7; ++i)
            {
                K_Bc[i] = k[i];
                D_Bc[i] = d[i];
            }
        }
        else
        {
            RCLCPP_ERROR(rclcpp::get_logger("marvin_robot"), "Cart K and D must have exactly 7 elements each.");
        }
    }

    void MarvinRobot::set_speed(int vel_scale, int acc_scale){
        OnClearSet();
        OnSetJointLmt_A(vel_scale,acc_scale);
        OnSetJointLmt_B(vel_scale,acc_scale);
        OnSetSend();
        usleep(100000);
        // acc_limit = acc_scale;
        // vel_limit = vel_scale;
     
    }
 
    std::vector<int> MarvinRobot::parse_ip(const std::string &ip)
    {
        std::vector<int> ip_parts;
        std::stringstream ss(ip);
        std::string segment;
        while (std::getline(ss, segment, '.'))
        {
            ip_parts.push_back(std::stoi(segment));
        }
        return ip_parts;
    }




    // Pilot the_pilot;
	// PilotLmt the_lmt;
    
