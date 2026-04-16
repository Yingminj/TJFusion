#include <iostream>

#include "math.h"
#include "float.h"
#include "ctime"

#include "stdio.h"
#include <iostream>
#include <string.h>
#include "rclcpp/rclcpp.hpp"
#include <ament_index_cpp/get_package_share_directory.hpp>

#include "IK/FxRobot.h"
#include "IK/FXMath.h"
// #include "marvin_ros_control/IK/Nsp.h"

#include "tf2_ros/transform_listener.h"
#include "tf2_ros/buffer.h"
#include <tf2_geometry_msgs/tf2_geometry_msgs.hpp>
#include <Eigen/Geometry>
#include "sensor_msgs/msg/joint_state.hpp"
#include "geometry_msgs/msg/pose.hpp"
#include "geometry_msgs/msg/pose_stamped.hpp"
#include "std_msgs/msg/float32.hpp"
#include "std_msgs/msg/bool.hpp"
#include <visualization_msgs/msg/marker_array.hpp>
#include <string>
#include "marvin_msgs/srv/int.hpp"
#include "marvin_msgs/srv/velratio.hpp"
#include "marvin_msgs/msg/jointcmd.hpp"
#include "marvin_msgs/msg/jointfeedback.hpp"
#include "marvin_ros_control/oneEuro_filter.h"

#include "pinocchio/parsers/urdf.hpp"
#include "pinocchio/parsers/srdf.hpp"
#include "pinocchio/algorithm/joint-configuration.hpp"
#include "pinocchio/algorithm/geometry.hpp"
#include "pinocchio/collision/collision.hpp"
#include "pinocchio/algorithm/frames.hpp"
// Pilot the_pilot;
// PilotLmt the_lmt;

geometry_msgs::msg::Pose convertArrayToPose(const double pgA[4][4])
{
	geometry_msgs::msg::Pose pose;

	// Extract position (translation)
	pose.position.x = pgA[0][3] * 0.001;
	pose.position.y = pgA[1][3] * 0.001;
	pose.position.z = pgA[2][3] * 0.001;

	// Extract orientation (convert rotation matrix to quaternion)
	tf2::Matrix3x3 rotation_matrix(
		pgA[0][0], pgA[0][1], pgA[0][2],
		pgA[1][0], pgA[1][1], pgA[1][2],
		pgA[2][0], pgA[2][1], pgA[2][2]);

	tf2::Quaternion quat;
	rotation_matrix.getRotation(quat);

	pose.orientation.x = quat.x();
	pose.orientation.y = quat.y();
	pose.orientation.z = quat.z();
	pose.orientation.w = quat.w();

	return pose;
}

geometry_msgs::msg::PoseStamped transform_pose(const geometry_msgs::msg::PoseStamped &input_pose,
											   const geometry_msgs::msg::TransformStamped &transform)
{
	geometry_msgs::msg::PoseStamped output_pose;

	// Transform the pose
	tf2::doTransform(input_pose, output_pose, transform);

	return output_pose;
}

void extractJointPositions(
	const sensor_msgs::msg::JointState &joint_state,
	const std::vector<std::string> &desired_joint_names,
	double (&joint_positions)[7])
{
	// Create a map from joint names to their positions
	std::map<std::string, double> name_to_position;
	for (size_t i = 0; i < 7; ++i)
	{
		name_to_position[joint_state.name[i]] = joint_state.position[i];
	}

	// Extract positions in the order of desired_joint_names

	for (size_t i = 0; i < 7; ++i)
	{
		const std::string &name = desired_joint_names[i];
		auto it = name_to_position.find(name);
		if (it != name_to_position.end())
		{
			joint_positions[i] = it->second; // Joint position found
		}
		else
		{
			RCLCPP_WARN(rclcpp::get_logger("pilot_arm_node"), "Joint '%s' not found in JointState message", name.c_str());
			joint_positions[i] = 0.0; // Default to 0 if joint not found
		}
	}
}

class Pilot_arm_node : public rclcpp::Node
{
public:
	Pilot_arm_node() : Node("pilot_arm_node"), filter_A_(200.0, 5.0, 0.02, 2.0), filter_B_(200.0, 5.0, 0.02, 2.0)
	{
		// init marvine kine.
		const std::string package_name = "marvin_ros_control";
		const std::string package_share_directory = ament_index_cpp::get_package_share_directory(package_name);
		

		this->declare_parameter<std::vector<std::string>>(
			"left_joints",
			std::vector<std::string>{"left_joint1", "left_joint2", "left_joint3", "left_joint4", "left_joint5", "left_joint6", "left_joint7"});
		this->declare_parameter<std::vector<std::string>>(
			"right_joints",
			std::vector<std::string>{"right_joint1", "right_joint2", "right_joint3", "right_joint4", "right_joint5", "right_joint6", "right_joint7"});
		this->declare_parameter<std::string>(
			"config_file","ccs_m6.MvKDCfg");
		this->declare_parameter<std::string>(
			"urdf_file","marvin_CCS_m6.urdf");
		this->declare_parameter<std::string>(
			"srdf_file","marvin_robot.srdf");
		this->declare_parameter<std::string>("eef_name_left", "left_joint7");
		this->declare_parameter<std::string>("eef_name_right", "right_joint7");
		this->declare_parameter<std::string>("elbow_name_left", "left_joint4");
		this->declare_parameter<std::string>("elbow_name_right", "right_joint4");
		this->declare_parameter<std::string>("left_base_name", "base_L");
		this->declare_parameter<std::string>("right_base_name", "base_R");
		this->declare_parameter<std::string>("left_base_nameJ", "base_to_left_arm");
		this->declare_parameter<std::string>("right_base_nameJ", "base_to_right_arm");
		this->declare_parameter<std::vector<double>>(
			"elbow_ref_dir",
			std::vector<double>{0.0, 0.3, 1.0});
		
		// Get the parameter
		joint_namesA_ = this->get_parameter("left_joints").as_string_array();
		joint_namesB_ = this->get_parameter("right_joints").as_string_array();

		ee_nameA = this->get_parameter("eef_name_left").as_string();
		ee_nameB = this->get_parameter("eef_name_right").as_string();
		elbow_nameA = this->get_parameter("elbow_name_left").as_string();
		elbow_nameB = this->get_parameter("elbow_name_right").as_string();
		left_base_name = this->get_parameter("left_base_name").as_string();
		right_base_name = this->get_parameter("right_base_name").as_string();
		left_base_nameJ = this->get_parameter("left_base_nameJ").as_string();
		right_base_nameJ = this->get_parameter("right_base_nameJ").as_string();

		std::vector<double> tmp = this->get_parameter("elbow_ref_dir").as_double_array();
        if (tmp.size() == 3)
			{
				for (int i = 0; i < 3; ++i)
					ref_dir[i] = tmp[i];

				RCLCPP_INFO(this->get_logger(), "ref_dir loaded: [%f, %f, %f]", ref_dir[0], ref_dir[1], ref_dir[2]);
			}
			else
			{
				RCLCPP_WARN(this->get_logger(), "ref_dir size != 3, using default");
			}
		

		RCLCPP_INFO(this->get_logger(), "left_base_name: %s", left_base_name.c_str());
		RCLCPP_INFO(this->get_logger(), "right_base_name: %s", right_base_name.c_str());
		RCLCPP_INFO(this->get_logger(), "eef_nameA: %s", ee_nameA.c_str());
		RCLCPP_INFO(this->get_logger(), "eef_nameB: %s", ee_nameB.c_str());
		// for (size_t i = 0; i < 7; ++i)
		// {
		// 	std::cout << joint_namesA_[i] << std::endl;
		// 	;
		// }

		// for (size_t i = 0; i < 7; ++i)
		// {
		// 	std::cout << joint_namesB_[i] << std::endl;
		// 	;
		// }


		config_file = this->get_parameter("config_file").as_string();
		config_file = package_share_directory + "/config/" + config_file;
		RCLCPP_INFO(this->get_logger(), "\033[1;32mUsing config file: %s\033[0m", config_file.c_str());
		urdf_file = this->get_parameter("urdf_file").as_string();
		urdf_file = package_share_directory + "/config/" + urdf_file;
		srdf_file = this->get_parameter("srdf_file").as_string();
		srdf_file = package_share_directory + "/config/" + srdf_file;
		MakePara(config_file);
		FX_Robot_Init_Type(0, FX_ROBOT_TYPE_PILOT_CCS);
		FX_Robot_Init_Kine(0, DH[0]);
		FX_BOOL ret1 = FX_Robot_Init_Type(1, FX_ROBOT_TYPE_PILOT_CCS);
		FX_BOOL ret2 = FX_Robot_Init_Kine(1, DH[1]);
		FX_Robot_Init_Lmt(0, PNVA[0], BD[0]);
		FX_Robot_Init_Lmt(1, PNVA[1], BD[1]);


		tf_buffer_ = std::make_unique<tf2_ros::Buffer>(this->get_clock());
		tf_listener_ = std::make_shared<tf2_ros::TransformListener>(*tf_buffer_);
		size_t tf_count = 0;

		while (true)
		{
			try
			{
				cached_tf_b_left = tf_buffer_->lookupTransform(
					"base_link", left_base_name, rclcpp::Time(0));
				cached_tf_b_right = tf_buffer_->lookupTransform(
					"base_link", right_base_name, rclcpp::Time(0));
				RCLCPP_INFO(this->get_logger(), "Transform from base_link to right_base_link and left_base_link found");

		// 		T_left_base.translation() = Eigen::Vector3d(
		// 			cached_tf_b_left.transform.translation.x,
		// 			cached_tf_b_left.transform.translation.y,
		// 			cached_tf_b_left.transform.translation.z);
		// 		T_left_base.rotation() = Eigen::Quaterniond(
		// 			cached_tf_b_left.transform.rotation.w,
		// 			cached_tf_b_left.transform.rotation.x,
		// 			cached_tf_b_left.transform.rotation.y,
		// 			cached_tf_b_left.transform.rotation.z);
		// 		T_right_base.translation() = Eigen::Vector3d(
		// 			cached_tf_b_right.transform.translation.x,
		// 			cached_tf_b_right.transform.translation.y,
		// 			cached_tf_b_right.transform.translation.z);
		// 		T_right_base.rotation() = Eigen::Quaterniond(
		// 			cached_tf_b_right.transform.rotation.w,
		// 			cached_tf_b_right.transform.rotation.x,
		// 			cached_tf_b_right.transform.rotation.y,
		// 			cached_tf_b_right.transform.rotation.z);
				break; // Exit the loop if transform is found
			}
			catch (...)
			{
				// RCLCPP_WARN(this->get_logger(), "Waiting for transform from controller_frame to right_base_link");
				tf_count++;
				if (tf_count > 100)
				{
					RCLCPP_ERROR(this->get_logger(), "Failed to get transform from controller_frame to right_base_link after 100 attempts");
					break; // Exit the loop after too many attempts
				}
				std::this_thread::sleep_for(std::chrono::seconds(1));
				continue;
			}
		}

		// for logging 
		// joint_state_publisher_ = this->create_publisher<sensor_msgs::msg::JointState>("joint_states", 10);
		rclcpp::SensorDataQoS sensor_data_qos;
		joint_fb_subscriber_ = this->create_subscription<marvin_msgs::msg::Jointfeedback>(
			"info/joint_feedback", sensor_data_qos,
			std::bind(&Pilot_arm_node::joint_feedback_callback, this, std::placeholders::_1));
		// pose_publisher_ = this->create_publisher<geometry_msgs::msg::PoseStamped>("right_arm/eef_pose", sensor_data_qos);
		pose_publisher_eefA_ = this->create_publisher<geometry_msgs::msg::PoseStamped>("control/eef_cmd_A", sensor_data_qos);
		pose_publisher_eefB_ = this->create_publisher<geometry_msgs::msg::PoseStamped>("control/eef_cmd_B", sensor_data_qos);

		target_pose_subscriberA_ = this->create_subscription<geometry_msgs::msg::PoseStamped>(
			"control/target_poseL", sensor_data_qos,
			std::bind(&Pilot_arm_node::pose_callbackA, this, std::placeholders::_1));
		target_pose_subscriberB_ = this->create_subscription<geometry_msgs::msg::PoseStamped>(
			"control/target_poseR", sensor_data_qos,
			std::bind(&Pilot_arm_node::pose_callbackB, this, std::placeholders::_1));
		left_DS_subscriver_ = this->create_subscription<std_msgs::msg::Bool>(
			"control/gripL", sensor_data_qos,
			std::bind(&Pilot_arm_node::left_DS_callback, this, std::placeholders::_1));
		right_DS_subscriver_ = this->create_subscription<std_msgs::msg::Bool>(
			"control/gripR", sensor_data_qos,
			std::bind(&Pilot_arm_node::right_DS_callback, this, std::placeholders::_1));
		left_zerosw_subscriber_ = this->create_subscription<std_msgs::msg::Bool>(
			"left_controller/zerosw", sensor_data_qos,
			std::bind(&Pilot_arm_node::left_zerosw_callback, this, std::placeholders::_1));
		right_zerosw_subscriber_ = this->create_subscription<std_msgs::msg::Bool>(
			"right_controller/zerosw", sensor_data_qos,
			std::bind(&Pilot_arm_node::right_zerosw_callback, this, std::placeholders::_1));

		pose_A_pub_ = this->create_publisher<geometry_msgs::msg::PoseStamped>("info/eef_left", 10);
		pose_B_pub_ = this->create_publisher<geometry_msgs::msg::PoseStamped>("info/eef_right", 10);
		joint_cmd_publisherA_ = this->create_publisher<marvin_msgs::msg::Jointcmd>("control/joint_cmd_A", sensor_data_qos);
		joint_cmd_publisherB_ = this->create_publisher<marvin_msgs::msg::Jointcmd>("control/joint_cmd_B", sensor_data_qos);
		ik_publisherA_ = this->create_publisher<marvin_msgs::msg::Jointcmd>("control/ik_cmd_A", sensor_data_qos);
		ik_publisherB_ = this->create_publisher<marvin_msgs::msg::Jointcmd>("control/ik_cmd_B", sensor_data_qos);
		collision_pub_A = this->create_publisher<std_msgs::msg::Bool>("info/collision_statusA", sensor_data_qos);
		collision_pub_B = this->create_publisher<std_msgs::msg::Bool>("info/collision_statusB", sensor_data_qos);
		marker_pub_ = this->create_publisher<visualization_msgs::msg::MarkerArray>("info/collision_marker", 10);
		// joint_feedback_publisherA_ = this->create_publisher<marvin_msgs::msg::Jointfeedback>("control/joint_target_A", sensor_data_qos);
		// joint_feedback_publisherB_ = this->create_publisher<marvin_msgs::msg::Jointfeedback>("control/joint_target_B", sensor_data_qos);

		// joint_feedback_subscriberA_ = this->create_subscription<marvin_msgs::msg::Jointfeedback>(
		// 	"control/joint_target_scaled_A", sensor_data_qos,
		// 	std::bind(&Pilot_arm_node::joint_feedback_callbackA, this, std::placeholders::_1));
		// joint_feedback_subscriberB_ = this->create_subscription<marvin_msgs::msg::Jointfeedback>(
		// 	"control/joint_target_scaled_B", sensor_data_qos,
		// 	std::bind(&Pilot_arm_node::joint_feedback_callbackB, this, std::placeholders::_1));

		pin_init();

		timer_A = this->create_wall_timer(
			std::chrono::microseconds(5),
			std::bind(&Pilot_arm_node::on_timer_A, this));
		timer_B = this->create_wall_timer(
			std::chrono::microseconds(5),
			std::bind(&Pilot_arm_node::on_timer_B, this));

		mpc_timer = this->create_wall_timer(
			std::chrono::milliseconds(1),
			std::bind(&Pilot_arm_node::mpc_tick, this));
	}

	void pub_joint_cmdA(double *jv)
	{
		auto joint_state_msg = marvin_msgs::msg::Jointcmd();
		joint_state_msg.header.stamp = this->now();

		joint_state_msg.header.frame_id = left_base_name;

		for (size_t i = 0; i < 7; ++i)
		{
			joint_state_msg.positions[i] = (jv[i] * FXARM_D2R); // Convert radians to degrees
		}

		joint_cmd_publisherA_->publish(joint_state_msg);
	}

	void pub_joint_cmdB(double *jv)
	{
		auto joint_state_msg = marvin_msgs::msg::Jointcmd();
		joint_state_msg.header.stamp = this->now();
		joint_state_msg.header.frame_id = right_base_name;

		for (size_t i = 0; i < 7; ++i)
		{
			joint_state_msg.positions[i] = (jv[i] * FXARM_D2R); // Convert radians to degrees
		}

		joint_cmd_publisherB_->publish(joint_state_msg);
	}

	void pub_ikA(double *jv)
	{
		auto joint_state_msg = marvin_msgs::msg::Jointcmd();
		joint_state_msg.header.stamp = this->now();
		joint_state_msg.header.frame_id = left_base_name;

		for (size_t i = 0; i < 7; ++i)
		{
			joint_state_msg.positions[i] = (jv[i] * FXARM_D2R); // Convert radians to degrees
		}

		ik_publisherA_->publish(joint_state_msg);
	}
	void pub_ikB(double *jv)
	{
		auto joint_state_msg = marvin_msgs::msg::Jointcmd();
		joint_state_msg.header.stamp = this->now();
		joint_state_msg.header.frame_id = right_base_name;

		for (size_t i = 0; i < 7; ++i)
		{
			joint_state_msg.positions[i] = (jv[i] * FXARM_D2R); // Convert radians to degrees
		}

		ik_publisherB_->publish(joint_state_msg);
	}

	// void FKine(double joint_positions[7], double pg[4][4]){
	//     // Convert joint positions from radians to degrees
	//     for (int i = 0; i < 7; ++i) {
	//         joint_positions[i] *= (180.0 / M_PI);
	//     }
	//     FX_Kine_Pilot(&the_pilot, joint_positions, pg);
	// }

private:
	void MakePara(std::string path) // Load the configuration file
	{

		FX_BOOL ret = LOADMvCfg((char *)path.c_str(), TYPE, GRV, DH, PNVA, BD, Mass, MCP, I);
		if (ret == FX_FALSE)
		{
			printf("LOAD ERR\n");
		}
		else
		{

			printf("LOAD OK\n");
			for (int i = 0; i < 2; i++)
			{
				for (int j = 0; j < 8; j++)
				{
					for (int k = 0; k < 4; k++)
					{
						printf("%f ", DH[i][j][k]);
					}
					printf("\n");
				}
				printf("\n");
			}
		}
	}

	void on_timer_A()
	{
		IK_A();
	}

	void on_timer_B()
	{
		IK_B();
	}
	void left_zerosw_callback(const std_msgs::msg::Bool::SharedPtr msg)
	{
		zero_567_A = msg->data;
	}
	void right_zerosw_callback(const std_msgs::msg::Bool::SharedPtr msg)
	{
		zero_567_B = msg->data;
	}

	// void joint_state_callback(const sensor_msgs::msg::JointState::SharedPtr msg)
	// {
	// 	// printf("joint_state_callback: %s\n", msg->header.frame_id.c_str());
	// 	sensor_msgs::msg::JointState joint_state = *msg;

	// 	// std::vector<double> joint_positions_B;

	// 	// Map received joint positions to joint_names_ order

	// 	for (size_t i = 0; i < 7; ++i) {
	// 		joint_positions_A[i] = msg->position[i];
	// 		joint_positions_B[i] = msg->position[i + 7]; // Assuming the second half of the message contains right arm joint positions
	// 	}

	// 	// extractJointPositions(joint_state, joint_namesA_, joint_positions_A);
	// 	// extractJointPositions(joint_state, joint_namesB_, joint_positions_B);

	// 	for (size_t i = 0; i < 7; ++i) {
	// 		joint_positions_AD[i] = joint_positions_A[i] * FXARM_R2D;
	// 	}

	// 	for (size_t i = 0; i < 7; ++i) {
	// 		joint_positions_BD[i] = joint_positions_B[i] * FXARM_R2D;
	// 	}
	// 	FX_Kine_Pilot(&the_pilot, joint_positions_AD, pgA);
	// 	FX_Kine_Pilot(&the_pilot, joint_positions_BD, pgB);
	// 	Eigen::Matrix3d rotation_matrixA;
	// 	rotation_matrixA <<
	// 		pgA[0][0], pgA[0][1], pgA[0][2],
	// 		pgA[1][0], pgA[1][1], pgA[1][2],
	// 		pgA[2][0], pgA[2][1], pgA[2][2];
	// 	Eigen::Matrix3d rotation_matrixB;
	// 	rotation_matrixB <<
	// 		pgB[0][0], pgB[0][1], pgB[0][2],
	// 		pgB[1][0], pgB[1][1], pgB[1][2],
	// 		pgB[2][0], pgB[2][1], pgB[2][2];
	// 	// Eigen::Matrix3d rot90X = Eigen::AngleAxisd(-M_PI / 2, Eigen::Vector3d::UnitY()).toRotationMatrix();
	// 		rotation_matrixA =  rotation_matrixA;
	// 		rotation_matrixB =  rotation_matrixB;
	// 		for (int i = 0; i < 3; ++i) {
	// 			for (int j = 0; j < 3; ++j) {
	// 				pgA[i][j] = rotation_matrixA(i, j);
	// 				pgB[i][j] = rotation_matrixB(i, j);
	// 			}
	// 		}

	// 	// 	}
	// 	// catch (tf2::TransformException& ex) {
	// 	// 	RCLCPP_ERROR(rclcpp::get_logger("pilot_arm_node"), "Transform failed: %s", ex.what());
	// 	// 	return;
	// 	// }

	// }

	void pub_eef_pose()
	{
		geometry_msgs::msg::Pose poseA = convertArrayToPose(pgA);
		geometry_msgs::msg::Pose poseB = convertArrayToPose(pgB);
		geometry_msgs::msg::PoseStamped poseA_base, poseB_base, poseA_, poseB_;
		geometry_msgs::msg::PoseStamped pose_msg_A, pose_msg_B;
		poseA_.header.stamp = this->now();
		poseA_.header.frame_id = left_base_name; // Set the frame_id
		poseA_.pose = poseA;
		poseB_.header.stamp = this->now();
		poseB_.header.frame_id = right_base_name; // Set the frame_id
		poseB_.pose = poseB;

		// try {
		// 	poseA_base = transform_pose(poseA_,
		// 		tf_buffer_->lookupTransform("base_link", left_base_name, rclcpp::Time(0)));
		// 	poseB_base = transform_pose(poseB_,
		// 		tf_buffer_->lookupTransform("base_link", right_base_name, rclcpp::Time(0)));

		poseA_base = transform_pose(poseA_, cached_tf_b_left);
		poseB_base = transform_pose(poseB_, cached_tf_b_right);
		Eigen::Quaterniond quatA(poseA_base.pose.orientation.w,
								 poseA_base.pose.orientation.x,
								 poseA_base.pose.orientation.y,
								 poseA_base.pose.orientation.z);
		Eigen::Quaterniond quatB(poseB_base.pose.orientation.w,
								 poseB_base.pose.orientation.x,
								 poseB_base.pose.orientation.y,
								 poseB_base.pose.orientation.z);
		Eigen::Matrix3d rotation_matrix = quatA.toRotationMatrix();
		// Eigen::Matrix3d rot90Y = Eigen::AngleAxisd(M_PI / 2, Eigen::Vector3d::UnitY()).toRotationMatrix();
		// Eigen::Matrix3d rot90Z = Eigen::AngleAxisd(-M_PI / 2, Eigen::Vector3d::UnitZ()).toRotationMatrix();
		rotation_matrix = rotation_matrix; //* rot90Z.transpose()* rot90Y.transpose();
		quatA = Eigen::Quaterniond(rotation_matrix);
		rotation_matrix = quatB.toRotationMatrix();
		rotation_matrix = rotation_matrix; // * rot90Z* rot90Y.transpose();
		quatB = Eigen::Quaterniond(rotation_matrix);
		poseA_base.pose.orientation.x = quatA.x();
		poseA_base.pose.orientation.y = quatA.y();
		poseA_base.pose.orientation.z = quatA.z();
		poseA_base.pose.orientation.w = quatA.w();
		poseB_base.pose.orientation.x = quatB.x();
		poseB_base.pose.orientation.y = quatB.y();
		poseB_base.pose.orientation.z = quatB.z();
		poseB_base.pose.orientation.w = quatB.w();

		// pose_msg_A.header.stamp = this->now();
		// pose_msg_A.header.frame_id = "base_link"; // Set the frame_id as needed
		// pose_msg_A.pose = poseA_base;
		pose_A_pub_->publish(poseA_base); // Publish the pose message
		// pose_msg_B.header.stamp = this->now();
		// pose_msg_B.header.frame_id = "base_link"; // Set the frame_id as needed
		// pose_msg_B.pose = poseB_base;
		pose_B_pub_->publish(poseB_base); // Publish the pose message
	}

	void joint_feedback_callback(marvin_msgs::msg::Jointfeedback::SharedPtr msg)
	{
		using namespace pinocchio;
		SE3 T_A_in_world, T_B_in_world;
		eef_points_A.clear();
		eef_points_B.clear();
		collision_status_A.clear();
		collision_status_B.clear();
		for (size_t i = 0; i < 14; ++i)
		{
			q_[i] = msg->positions[i];
			v_[i] = msg->velocities[i];
		}

		// Extract joint positions for left and right arms
		for (size_t i = 0; i < 7; ++i)
		{
			joint_positions_A[i] = msg->positions[i];
			joint_positions_AD[i] = msg->positions[i] * FXARM_R2D;	   // Convert radians to degrees
			joint_positions_B[i] = msg->positions[i + 7];			   // Assuming the second half of the message contains right arm joint positions
			joint_positions_BD[i] = msg->positions[i + 7] * FXARM_R2D; // Convert radians to degrees
		}
		// FX_Kine_Pilot(&the_pilot, joint_positions_AD, pgA);
		// FX_Kine_Pilot(&the_pilot, joint_positions_BD, pgB);
		DH[1];

		FX_Robot_Kine_FK(0, joint_positions_AD, pgA);
		FX_Robot_Kine_FK(1, joint_positions_BD, pgB);

		// for (int i =0;i<4;i++){
		// 	for (int j =0;j<4;j++){
		// 		printf("%f ", pgB[i][j]);
		// 	}
		// 	printf("\n");
		// }
		// printf("---\n");
		pub_eef_pose();
	}

	void pose_callbackA(const geometry_msgs::msg::PoseStamped::SharedPtr msg)
	{
		// printf("pose_callback: %s\n", msg->header.frame_id.c_str());
		geometry_msgs::msg::PoseStamped controller_pose = *msg;
		geometry_msgs::msg::PoseStamped output_pose;
		Eigen::Isometry3d pgAF = Eigen::Isometry3d::Identity();
		rclcpp::Time stamp(controller_pose.header.stamp);
		double timestamp = stamp.seconds();

		// pose in left_base_link frame
		try
		{
			output_pose = transform_pose(controller_pose,
										 tf_buffer_->lookupTransform(left_base_name, controller_pose.header.frame_id, rclcpp::Time(0)));

			pgAF.translation() << output_pose.pose.position.x, output_pose.pose.position.y, output_pose.pose.position.z;
			pgAF.linear() = Eigen::Quaterniond(
								output_pose.pose.orientation.w,
								output_pose.pose.orientation.x,
								output_pose.pose.orientation.y,
								output_pose.pose.orientation.z)
								.toRotationMatrix();
			pgAF = filter_A_.filter(pgAF, timestamp);

			pgAT[0][3] = pgAF.translation().x() * 1000;
			pgAT[1][3] = pgAF.translation().y() * 1000;
			pgAT[2][3] = pgAF.translation().z() * 1000;

			Eigen::Matrix3d rotation_matrix = pgAF.linear();

			Eigen::Matrix3d rot90Y = Eigen::AngleAxisd(M_PI / 2, Eigen::Vector3d::UnitY()).toRotationMatrix();
			Eigen::Matrix3d rot90Z = Eigen::AngleAxisd(-M_PI / 2, Eigen::Vector3d::UnitZ()).toRotationMatrix();
			Eigen::Matrix3d rot90X = Eigen::AngleAxisd(-M_PI / 2, Eigen::Vector3d::UnitX()).toRotationMatrix();
			Eigen::Matrix3d rotx = Eigen::AngleAxisd(-M_PI / 8, Eigen::Vector3d::UnitX()).toRotationMatrix();
			rotation_matrix = rotation_matrix * rot90X * rot90Y * rot90Z;
			rotation_matrix = rotation_matrix* rotx;
			geometry_msgs::msg::PoseStamped pose_msg;
			pose_msg.header.stamp = this->now();
			pose_msg.header.frame_id = left_base_name; // Set the frame_id
			Eigen::Quaterniond quat_msg = Eigen::Quaterniond(rotation_matrix);
			pose_msg.pose.position.x = output_pose.pose.position.x;
			pose_msg.pose.position.y = output_pose.pose.position.y;
			pose_msg.pose.position.z = output_pose.pose.position.z;
			pose_msg.pose.orientation.x = quat_msg.x();
			pose_msg.pose.orientation.y = quat_msg.y();
			pose_msg.pose.orientation.z = quat_msg.z();
			pose_msg.pose.orientation.w = quat_msg.w();
			if (true)
			{
				pose_publisher_eefA_->publish(pose_msg);
				for (int i = 0; i < 3; ++i)
				{
					for (int j = 0; j < 3; ++j)
					{
						pgAT[i][j] = rotation_matrix(i, j);
					}
				}
				pgAT[3][0] = 0.0;
				pgAT[3][1] = 0.0;
				pgAT[3][2] = 0.0;
				pgAT[3][3] = 1.0;
			}
		}
		catch (tf2::TransformException &ex)
		{
			RCLCPP_ERROR(rclcpp::get_logger("logger"), "Transform failed: %s", ex.what());
		}
	}

	void pose_callbackB(const geometry_msgs::msg::PoseStamped::SharedPtr msg)
	{
		// printf("pose_callback: %s\n", msg->header.frame_id.c_str());
		geometry_msgs::msg::PoseStamped controller_pose = *msg;
		geometry_msgs::msg::PoseStamped output_pose;
		Eigen::Isometry3d pgBF = Eigen::Isometry3d::Identity();
		rclcpp::Time stamp(controller_pose.header.stamp);
		double timestamp = stamp.seconds();

		// pose in right_base_link frame
		try
		{
			output_pose = transform_pose(controller_pose,
										 tf_buffer_->lookupTransform(right_base_name, controller_pose.header.frame_id, rclcpp::Time(0)));

			pgBF.translation() << output_pose.pose.position.x, output_pose.pose.position.y, output_pose.pose.position.z;
			pgBF.linear() = Eigen::Quaterniond(
								output_pose.pose.orientation.w,
								output_pose.pose.orientation.x,
								output_pose.pose.orientation.y,
								output_pose.pose.orientation.z)
								.toRotationMatrix();
			pgBF = filter_B_.filter(pgBF, timestamp);

			pgBT[0][3] = pgBF.translation().x() * 1000;
			pgBT[1][3] = pgBF.translation().y() * 1000;
			pgBT[2][3] = pgBF.translation().z() * 1000;
			// tf2::Quaternion quat;
			// quat.setX(pgBF.rotation().x());
			// quat.setY(pgBF.rotation().y());
			// quat.setZ(pgBF.rotation().z());
			// quat.setW(pgBF.rotation().w());
			// Eigen::Quaterniond eigen_quat(quat.w(), quat.x(), quat.y(), quat.z());
			Eigen::Matrix3d rotation_matrix = pgBF.linear();

			Eigen::Matrix3d rot90Y = Eigen::AngleAxisd(M_PI / 2, Eigen::Vector3d::UnitY()).toRotationMatrix();
			Eigen::Matrix3d rot90Z = Eigen::AngleAxisd(M_PI / 2, Eigen::Vector3d::UnitZ()).toRotationMatrix();
			Eigen::Matrix3d rot90X = Eigen::AngleAxisd(M_PI / 2, Eigen::Vector3d::UnitX()).toRotationMatrix();
			Eigen::Matrix3d rotx = Eigen::AngleAxisd(M_PI / 8, Eigen::Vector3d::UnitX()).toRotationMatrix();
			rotation_matrix = rotation_matrix * rot90X * rot90Y * rot90Z;
			rotation_matrix = rotation_matrix * rotx;
			geometry_msgs::msg::PoseStamped pose_msg;
			pose_msg.header.stamp = this->now();
			pose_msg.header.frame_id = right_base_name; // Set the frame_id
			Eigen::Quaterniond quat_msg = Eigen::Quaterniond(rotation_matrix);
			pose_msg.pose.position.x = output_pose.pose.position.x;
			pose_msg.pose.position.y = output_pose.pose.position.y;
			pose_msg.pose.position.z = output_pose.pose.position.z;
			pose_msg.pose.orientation.x = quat_msg.x();
			pose_msg.pose.orientation.y = quat_msg.y();
			pose_msg.pose.orientation.z = quat_msg.z();
			pose_msg.pose.orientation.w = quat_msg.w();
			if (true)
			{
				pose_publisher_eefB_->publish(pose_msg);
				for (int i = 0; i < 3; ++i)
				{
					for (int j = 0; j < 3; ++j)
					{
						pgBT[i][j] = rotation_matrix(i, j);
					}
				}
				pgBT[3][0] = 0.0;
				pgBT[3][1] = 0.0;
				pgBT[3][2] = 0.0;
				pgBT[3][3] = 1.0;
			}
		}
		catch (tf2::TransformException &ex)
		{
			RCLCPP_ERROR(rclcpp::get_logger("logger"), "Transform failed: %s", ex.what());
		}
	}

	inline double clamp(double val, double min_val, double max_val)
	{
		return std::max(min_val, std::min(max_val, val));
	}

	// rotationOrder = Eigen::XYZ, Eigen::ZYX etc.
	Eigen::Matrix3d limitRotationAxisAngle(
		const Eigen::Matrix3d &R1,
		const Eigen::Matrix3d &R2,
		double max_angle_deg)
	{
		// Relative rotation from R1 to R2
		Eigen::Matrix3d R_rel = R2 * R1.transpose();

		Eigen::AngleAxisd aa(R_rel);
		double angle = aa.angle();		  // [0, pi]
		Eigen::Vector3d axis = aa.axis(); // unit vector

		double max_angle_rad = max_angle_deg * M_PI / 180.0;

		// If angle is zero (or very small), return R1 directly (no rotation)
		if (angle < 1e-12)
		{
			return R1;
		}

		// Clamp angle to max_angle_rad by scaling if necessary
		if (angle > max_angle_rad)
		{
			angle = max_angle_rad;
		}
		else if (angle < -max_angle_rad)
		{
			angle = -max_angle_rad;
		}

		// Normalize the axis to ensure it is a unit vector
		axis.normalize();

		// If the angle is zero after clamping, return R1 directly
		{
			/* code */
		}

		// Rebuild limited relative rotation
		Eigen::AngleAxisd aa_limited(angle, axis);
		Eigen::Matrix3d R_limited_rel = aa_limited.toRotationMatrix();

		// Apply limited rotation relative to R1
		return R_limited_rel * R1;
	}

	Eigen::Matrix3d scaleRotationAxisAngle(
		const Eigen::Matrix3d &R1,
		const Eigen::Matrix3d &R2,
		double scale_factor,
		double max_angle_deg = 180.0 // Default max angle in degrees
	)
	{
		// Relative rotation from R1 to R2
		Eigen::Matrix3d R_rel = R2 * R1.transpose();

		// Convert to angle-axis representation
		Eigen::AngleAxisd aa(R_rel);
		double angle = aa.angle();		  // [0, pi]
		Eigen::Vector3d axis = aa.axis(); // unit vector

		// Convert max angle to radians
		double max_angle_rad = max_angle_deg * M_PI / 180.0;

		// If angle is very small, return R1 (no rotation)
		if (angle < 1e-12)
		{
			return R1;
		}

		// Apply scale factor to the rotation angle
		angle *= scale_factor;

		// Clamp angle to max_angle_rad
		if (angle > max_angle_rad)
		{
			angle = max_angle_rad;
		}
		else if (angle < -max_angle_rad)
		{
			angle = -max_angle_rad;
		}

		// If the angle is zero after scaling and clamping, return R1
		if (std::abs(angle) < 1e-12)
		{
			return R1;
		}

		// Normalize the axis to ensure it is a unit vector
		axis.normalize();

		// Rebuild limited relative rotation with scaled angle
		Eigen::AngleAxisd aa_limited(angle, axis);
		Eigen::Matrix3d R_limited_rel = aa_limited.toRotationMatrix();

		// Apply limited rotation relative to R1
		return R_limited_rel * R1;
	}

	inline double wrapTo180(double angle_deg)
	{
		angle_deg = fmod(angle_deg + 180.0, 360.0);
		if (angle_deg < 0)
			angle_deg += 360.0;
		return angle_deg - 180.0;
	}

	Eigen::Vector3d minimizeAbsRPY(const Eigen::Vector3d &rpy_deg)
	{
		// Wrap input angles to [-180,180]
		Eigen::Vector3d A;
		for (int i = 0; i < 3; ++i)
			A[i] = wrapTo180(rpy_deg[i]);

		// Compute alternative solution B:
		// B[0] = yaw + 180, B[1] = 180 - pitch, B[2] = roll + 180
		Eigen::Vector3d B;
		B[0] = wrapTo180(A[0] + 180.0);
		B[1] = wrapTo180(180.0 - A[1]);
		B[2] = wrapTo180(A[2] + 180.0);

		// Compare sums of absolute angles
		double normA = A.cwiseAbs().sum();
		double normB = B.cwiseAbs().sum();

		return (normA <= normB) ? A : B;
	}

	Eigen::Matrix3d limitRotationRPY(
		const Eigen::Matrix3d &R1,
		const Eigen::Matrix3d &R2,
		const Eigen::Vector3d &max_rpy_deg // [roll_limit, pitch_limit, yaw_limit]
	)
	{
		// Relative rotation from R1 to R2
		Eigen::Matrix3d R_rel = R2 * R1.transpose();

		// Extract RPY in radians, order: ZYX (yaw, pitch, roll)
		// Eigen::Vector3d rpy = R_rel.eulerAngles(2, 1, 0); // yaw, pitch, roll (rad)
		// rpy = minimizeAbsRPY(rpy * 180.0 / M_PI); // Convert to degrees and minimize absolute angles

		tf2::Matrix3x3 m;
		m.setValue(R_rel(0, 0), R_rel(0, 1), R_rel(0, 2),
				   R_rel(1, 0), R_rel(1, 1), R_rel(1, 2),
				   R_rel(2, 0), R_rel(2, 1), R_rel(2, 2));

		double roll, pitch, yaw;
		m.getRPY(roll, pitch, yaw);
		Eigen::Vector3d rpy;
		rpy[0] = yaw * 180.0 / M_PI;   // yaw
		rpy[1] = pitch * 180.0 / M_PI; // pitch
		rpy[2] = roll * 180.0 / M_PI;  // roll

		std::cout << "rpy before limit: " << rpy.transpose() << std::endl;
		// Clamp each angle independently
		for (int i = 0; i < 3; ++i)
		{
			rpy[i] = std::clamp(rpy[i], -max_rpy_deg[i], max_rpy_deg[i]);
		}

		// Convert back to radians
		rpy = rpy * M_PI / 180.0;

		// Rebuild limited relative rotation
		Eigen::Matrix3d R_limited_rel;
		R_limited_rel =
			Eigen::AngleAxisd(rpy[0], Eigen::Vector3d::UnitZ()) * // yaw
			Eigen::AngleAxisd(rpy[1], Eigen::Vector3d::UnitY()) * // pitch
			Eigen::AngleAxisd(rpy[2], Eigen::Vector3d::UnitX());  // roll

		// Apply limited rotation relative to R1
		return R_limited_rel * R1;
	}

	void IK_A()
	{
		auto now = std::chrono::steady_clock::now();
		auto duration = std::chrono::duration_cast<std::chrono::milliseconds>(now - grip_L_stamp);

		if (duration.count() > 20000)
		{
			return; // Skip IK calculation if the right DSwitch is pressed within 0.1 seconds
		}
		if(!left_hooked){
			for (int i = 0; i < 7; ++i) {
				ref_jointA[i] = joint_positions_AD[i];
			}
		}
		
		FX_DOUBLE ret_joint[7], q_D[7];
		FX_BOOL solved;
		FX_BOOL IsOutRange, Inrange;
		FX_BOOL Is123Deg;
		FX_BOOL Is567Deg;
		// FX_DOUBLE ref_dir[3] = {0, -0.3, 1.0};
		FX_InvKineSolvePara solve_para;
		solve_para.m_Input_IK_ZSPType = FX_PILOT_NSP_TYPES_NEAR_DIR;
		solve_para.m_Input_IK_ZSPPara[0] = ref_dir[0];
		solve_para.m_Input_IK_ZSPPara[1] = - ref_dir[1];
		solve_para.m_Input_IK_ZSPPara[2] = ref_dir[2];

		memcpy(solve_para.m_Input_IK_RefJoint, ref_jointA, sizeof(ref_jointA));
		memcpy(solve_para.m_Input_IK_TargetTCP, pgAT, sizeof(pgAT));
		solved = FX_Robot_Kine_IK(0, &solve_para);
		if (solved){

			memcpy(ret_joint, solve_para.m_Output_RetJoint, sizeof(ret_joint));


			// double max_diff = 0.0;
			// for (int i = 4; i < 7; ++i) {
			// 	double diff = std::abs(joint_positions_AD[i] - ret_joint[i]);
			// 	if (diff > max_diff) {
			// 		max_diff = diff;
			// 	}
			// }
			// // max_diff = std::abs(ret_joint[4] - joint_positions_AD[4]);
			// double diff[7];

			// if (max_diff > 100.0){
			// 	for (int i = 4; i < 7; ++i) {
			// 		ret_joint[i] = joint_positions_AD[i];
			// 	}
			// }
			
		if (solve_para.m_Output_IsJntExd){
				return;
			}
		pub_ikA(ret_joint);
		

		if (left_dswitch)
		{
			if (!left_dswitch_last)
			{
				// RCLCPP_INFO(this->get_logger(), "left gripped!");
				double norm_disp = (pgAT[0][3] - pgA[0][3]) * (pgAT[0][3] - pgA[0][3]) + (pgAT[1][3] - pgA[1][3]) * (pgAT[1][3] - pgA[1][3]) + (pgAT[2][3] - pgA[2][3]) * (pgAT[2][3] - pgA[2][3]);
				if (norm_disp < 100 * 100)
				{
					left_hooked = true;
				}
			}
			if (solved == FX_TRUE && left_hooked)
			{

				
				// 
				// 	pub_joint_cmdA(ret_joint);
				// }
				// else{
				// 	pub_joint_cmdA(joint_positions_AD);
				// }
				if(!will_coll_A){
				memcpy(ret_jointA, ret_joint, sizeof(ret_jointA));
				}
				else{
					memcpy(ret_jointA, joint_positions_AD, sizeof(ret_jointA));
				}
				pub_joint_cmdA(ret_jointA);
			}
		}
	}
		// for(int i = 0; i < 7; i++) {
		// 	printf("Joint %d: %.5lf\n", i + 1, ret_joint[i]);
		// }
		// for (int i = 0; i < 4; ++i) {
		// 	for (int j = 0; j < 4; ++j) {
		// 		printf("%.5lf	", pg[i][j]);
		// 	}
		// 	printf("\n");
		// }
	}

	void IK_B()
	{
		auto now = std::chrono::steady_clock::now();
		auto duration = std::chrono::duration_cast<std::chrono::milliseconds>(now - grip_R_stamp);

		if (duration.count() > 20000)
		{
			return; // Skip IK calculation if the right DSwitch is pressed within 0.1 seconds
		}

		for (int i = 0; i < 7; ++i) {
			ref_jointB[i] = joint_positions_BD[i];
		}
		
		// max_diff = std::abs(ret_joint[4] - joint_positions_AD[4]);
		
		FX_DOUBLE ret_joint[7], q_bD[7];
		FX_BOOL solved;
		FX_BOOL IsOutRange, Inrange;
		FX_BOOL Is123Deg;
		FX_BOOL Is567Deg;
		// FX_DOUBLE ref_dir[3] = {0, 0.3, 1.0};
		FX_InvKineSolvePara solve_para;
		solve_para.m_Input_IK_ZSPType = FX_PILOT_NSP_TYPES_NEAR_DIR;
		solve_para.m_Input_IK_ZSPPara[0] = -ref_dir[0];
		solve_para.m_Input_IK_ZSPPara[1] = -ref_dir[1];
		solve_para.m_Input_IK_ZSPPara[2] = -ref_dir[2];

		memcpy(solve_para.m_Input_IK_RefJoint, ref_jointB, sizeof(ref_jointB));
		memcpy(solve_para.m_Input_IK_TargetTCP, pgBT, sizeof(pgBT));
		solved = FX_Robot_Kine_IK(1, &solve_para);
		if (solved){

			memcpy(ret_joint, solve_para.m_Output_RetJoint, sizeof(ret_joint));


			// double max_diff = 0.0;
			// for (int i = 4; i < 7; ++i) {
			// 	double diff = std::abs(joint_positions_BD[i] - ret_joint[i]);
			// 	if (diff > max_diff) {
			// 		max_diff = diff;
			// 	}
			// }
			// // max_diff = std::abs(ret_joint[4] - joint_positions_AD[4]);
			// double diff[7];

			// if (max_diff > 100.0){
			// 	for (int i = 4; i < 7; ++i) {
			// 		ret_joint[i] = joint_positions_BD[i];
			// 	}
			// }
			
			// for (int i=0; i<7; i++){
			// 	if (ret_joint[i] > solve_para.m_Output_RunLmtP[i])
			// 			{
			// 				ret_joint[i] = solve_para.m_Output_RunLmtP[i];
			// 			}
			// 			if (ret_joint[i] < solve_para.m_Output_RunLmtN[i])
			// 			{
			// 				ret_joint[i] = solve_para.m_Output_RunLmtN[i];
			// 			}
			// }
			if (solve_para.m_Output_IsJntExd){
				return;
			}
			pub_ikB(ret_joint);
			

			if (right_dswitch)
			{
				if (!right_dswitch_last)
				{
					// RCLCPP_INFO(this->get_logger(),"right gripped!");
					double norm_disp = (pgBT[0][3] - pgB[0][3]) * (pgBT[0][3] - pgB[0][3]) + (pgBT[1][3] - pgB[1][3]) * (pgBT[1][3] - pgB[1][3]) + (pgBT[2][3] - pgB[2][3]) * (pgBT[2][3] - pgB[2][3]);
					if (norm_disp < 150 * 150)
					{
						right_hooked = true;
					}
				}
				if (solved == FX_TRUE && right_hooked)
				{

					
					// if(!will_coll_A){
					// 	pub_joint_cmdA(ret_joint);
					// }
					// else{
					// 	pub_joint_cmdA(joint_positions_AD);
					// }
					if(!will_coll_B){	
						memcpy(ret_jointB, ret_joint, sizeof(ret_jointB));
					}
					else{
						memcpy(ret_jointB, joint_positions_BD, sizeof(ret_jointB));
					}
					pub_joint_cmdB(ret_jointB);
				}
			}
		}
	}
	
	void left_DS_callback(const std_msgs::msg::Bool::SharedPtr msg)
	{
		left_dswitch_last = left_dswitch;
		left_dswitch = msg->data;
		grip_L_stamp = std::chrono::steady_clock::now();
		if (!left_dswitch)
		{
			left_hooked = false;
		}
		// RCLCPP_INFO(rclcpp::get_logger("pilot_arm_node"), "Left DSwitch: %s", left_dswitch ? "ON" : "OFF");
	}
	void right_DS_callback(const std_msgs::msg::Bool::SharedPtr msg)
	{
		right_dswitch_last = right_dswitch;
		right_dswitch = msg->data;
		grip_R_stamp = std::chrono::steady_clock::now();
		if (!right_dswitch)
		{
			right_hooked = false;
		}
		// RCLCPP_INFO(rclcpp::get_logger("pilot_arm_node"), "Right DSwitch: %s", right_dswitch ? "ON" : "OFF");
	}

	void pin_init()
	{
		const std::string package_name = "marvin_ros_control";
		const std::string package_share_directory = ament_index_cpp::get_package_share_directory(package_name);

		const std::string urdf_filename = urdf_file;
		const std::string srdf_filename = srdf_file;

		RCLCPP_INFO(this->get_logger(), "URDF: %s", urdf_filename.c_str());
		RCLCPP_INFO(this->get_logger(), "SRDF: %s", srdf_filename.c_str());

		// Load Pinocchio model
		pinocchio::urdf::buildModel(urdf_filename, model_);
		data_ = pinocchio::Data(model_);

		pinocchio::urdf::buildGeom(
			model_, urdf_filename, pinocchio::COLLISION, geom_model_, package_share_directory);

		ee_idA = model_.getJointId(ee_nameA);
		ee_idB = model_.getJointId(ee_nameB);


		left_base_id = model_.getFrameId(left_base_name);
		right_base_id = model_.getFrameId(right_base_name);

		geom_model_.addAllCollisionPairs();
		pinocchio::srdf::removeCollisionPairs(model_, geom_model_, srdf_filename);

		geom_data_ = pinocchio::GeometryData(geom_model_);

		pinocchio::srdf::loadReferenceConfigurations(model_, srdf_filename);

		// Fallback default config
		q_ = model_.referenceConfigurations["resting"];
		v_ = pinocchio::Model::TangentVectorType::Zero(model_.nv);

		// left reduced model

		std::cout << "Left reduced model joint names: " << std::endl;
		for (const auto &name : joint_namesA_)
		{
			std::cout << name << std::endl;
		}
		// right reduced model
		std::cout << "Right reduced model joint names: " << std::endl;
		for (const auto &name : joint_namesB_)
		{
			std::cout << name << std::endl;
		}
		// 1. Get joint IDs to lock
		for (const auto &name : joint_namesA_)
			joint_to_lockB.push_back(model_.getJointId(name));

		for (const auto &name : joint_namesB_)
			joint_to_lockA.push_back(model_.getJointId(name));

		// 3. Build reduced models
		pinocchio::forwardKinematics(model_, data_, q_);
		pinocchio::buildReducedModel(model_, joint_to_lockA, q_, model_A);
		pinocchio::buildReducedModel(model_, joint_to_lockB, q_, model_B);
		data_A = pinocchio::Data(model_A);
		data_B = pinocchio::Data(model_B);
		elbow_idA = model_A.getJointId(elbow_nameA);
		elbow_idB = model_B.getJointId(elbow_nameB);

		T_left_base = data_.oMf[left_base_id];
		T_right_base = data_.oMf[right_base_id];
		std::cout<<"12"<<std::endl;
		pinocchio::forwardKinematics(model_, data_, q_);
		pinocchio::updateFramePlacements(model_, data_);

		pinocchio::FrameIndex frame_a_id = model_.getFrameId("left_link7");
		pinocchio::FrameIndex frame_b_id = model_.getFrameId("left_tool");

		// Get absolute placements (w.r.t. world)
		const pinocchio::SE3 &oMf_a = data_.oMf[frame_a_id];
		const pinocchio::SE3 &oMf_b = data_.oMf[frame_b_id];

		// Compute relative transform from frame_a to frame_b
		pinocchio::SE3 aMb = oMf_a.inverse() * oMf_b;

		// std::cout << "Relative transformation (frame_a -> frame_b):\n" << aMb << std::endl;
		// std::cout << "Translation:\n" << aMb.translation() << std::endl;
		// std::cout << "Rotation:\n" << aMb.rotation() << std::endl;
	}

	void mpc_tick()
	{
		using namespace pinocchio;

		SE3 T_A_in_world, T_B_in_world;
		eef_points_A.clear();
		eef_points_B.clear();
		collision_status_A.clear();
		collision_status_B.clear();
		int last_safe_idx_A = 0;
		int last_safe_idx_B = 0;
		std::vector<pinocchio::Model::ConfigVectorType> q_i__;

		Eigen::VectorXd v_abs_ = v_.cwiseAbs();
		double max_v = v_abs_.maxCoeff();
		for (size_t i = 2; i < 15; ++i)
		{
			pinocchio::Model::ConfigVectorType q_i_(model_.nq);
			for (size_t j = 0; j < model_.nq; ++j)
			{
				q_i_[j] = q_[j] + i * mpc_dt_ * v_[j];
				// std::cout << "q_[" << i << "]: " << q_i_[i] << std::endl;
			}
			q_i__.push_back(q_i_);
			pinocchio::forwardKinematics(model_, data_, q_i_);
			pinocchio::updateGeometryPlacements(model_, data_, geom_model_, geom_data_);

			T_A_in_world = data_.oMi[ee_idA];
			T_B_in_world = data_.oMi[ee_idB];

			

			// std::cout << "T_ee_in_world.translation()[" << T_ee_in_world << std::endl;
			eef_points_A.push_back(T_A_in_world.translation());
			eef_points_B.push_back(T_B_in_world.translation());

			bool in_collision = computeCollisions(model_, data_, geom_model_, geom_data_, q_i_, true);

			// std::cout << "Collision status: " << (in_collision ? "In collision" : "No collision") << std::endl;
			collision_status_A.push_back(in_collision);
			collision_status_B.push_back(in_collision);
		}

		for (size_t i = 0; i < 7; ++i)
		{
			if (collision_status_A[i])
			{
				last_safe_idx_A = i;
				// for (size_t j = 0; j < 7; ++j)
				// {
				// 	ret_jointAS[j] = q_i__[last_safe_idx_A][j];
				// }
				break;
			}
		}
		for (size_t i = 0; i < 7; ++i)
		{
			if (collision_status_B[i])
			{
				last_safe_idx_B = i;
				break;
				// for (size_t j = 0; j < 7; ++j)
				// {
				// 	ret_jointBS[j] = q_i__[last_safe_idx_B][j];
				// }
			}
		}

		publishMarkerArray();
		if (max_v < 0.02)
		{
			// std_msgs::msg::Bool msg;
			// msg.data = false;
			// collision_pub_A->publish(msg);
			// collision_pub_B->publish(msg);
			// //   return;
			will_coll_A = false;
			will_coll_B = false;
		}
		else
		{
			bool all_false_A = std::all_of(collision_status_A.begin(), collision_status_A.end(), [](bool v)
										   { return !v; });
			if (all_false_A)
			{
				std_msgs::msg::Bool msg;
				msg.data = false;
				collision_pub_A->publish(msg);
				will_coll_A = false;
				std::copy(ret_jointA, ret_jointA + 7, ret_jointAS);
			}
			else
			{
				std_msgs::msg::Bool msg;
				msg.data = true;
				collision_pub_A->publish(msg);
				will_coll_A = true;
			}
			bool all_false_B = std::all_of(collision_status_B.begin(), collision_status_B.end(), [](bool v)
										   { return !v; });
			if (all_false_B)
			{
				std_msgs::msg::Bool msg;
				msg.data = false;
				collision_pub_B->publish(msg);
				will_coll_B = false;
				std::copy(ret_jointB, ret_jointB + 7, ret_jointBS);
			}
			else
			{
				std_msgs::msg::Bool msg;
				msg.data = true;
				collision_pub_B->publish(msg);
				will_coll_B = true;
			}
		}
		//   pub_joint_cmdA(ret_jointAS);
		//   pub_joint_cmdB(ret_jointBS);
		publishMarkerArray();
	}

	void publishMarkerArray()
	{
		visualization_msgs::msg::MarkerArray marker_array;
		for (size_t i = 0; i < eef_points_A.size(); ++i)
		{
			visualization_msgs::msg::Marker marker;
			marker.header.frame_id = "base_link";
			marker.header.stamp = this->now();
			marker.ns = "eef_pointsA";
			marker.id = static_cast<int>(i);
			marker.type = visualization_msgs::msg::Marker::SPHERE;
			marker.action = visualization_msgs::msg::Marker::ADD;
			marker.pose.position.x = eef_points_A[i].x();
			marker.pose.position.y = eef_points_A[i].y();
			marker.pose.position.z = eef_points_A[i].z();
			marker.scale.x = 0.02; // Diameter of the sphere
			marker.scale.y = 0.02;
			marker.scale.z = 0.02;
			if (collision_status_A[i])
			{
				marker.color.r = 1.0f; // Red color for collision
				marker.color.g = 0.0f;
				marker.color.b = 0.0f;
			}
			else
			{
				marker.color.r = 0.0f; // Green color for no collision
				marker.color.g = 1.0f;
				marker.color.b = 0.0f;
			}
			marker.color.a = 1.0;							  // Fully opaque
			marker.lifetime = rclcpp::Duration(0, 100000000); // Lifetime of the marker

			marker_array.markers.push_back(marker);
		}
		for (size_t i = 0; i < eef_points_B.size(); ++i)
		{
			visualization_msgs::msg::Marker marker;
			marker.header.frame_id = "base_link";
			marker.header.stamp = this->now();
			marker.ns = "eef_pointsB";
			marker.id = static_cast<int>(i);
			marker.type = visualization_msgs::msg::Marker::SPHERE;
			marker.action = visualization_msgs::msg::Marker::ADD;
			marker.pose.position.x = eef_points_B[i].x();
			marker.pose.position.y = eef_points_B[i].y();
			marker.pose.position.z = eef_points_B[i].z();
			marker.scale.x = 0.02; // Diameter of the sphere
			marker.scale.y = 0.02;
			marker.scale.z = 0.02;
			if (collision_status_B[i])
			{
				marker.color.r = 1.0f; // Red color for collision
				marker.color.g = 0.0f;
				marker.color.b = 0.0f;
			}
			else
			{
				marker.color.r = 0.0f; // Green color for no collision
				marker.color.g = 1.0f;
				marker.color.b = 0.0f;
			}
			marker.color.a = 1.0;							  // Fully opaque
			marker.lifetime = rclcpp::Duration(0, 100000000); // Lifetime of the marker

			marker_array.markers.push_back(marker);
		}

		marker_pub_->publish(marker_array);
	}

	std::array<double, 3> rot_to_rpy(const Eigen::Matrix3d& R)
	{
		double sy = std::sqrt(R(0,0) * R(0,0) + R(1,0) * R(1,0));
		bool singular = sy < 1e-6;

		double roll, pitch, yaw;
		if (!singular) {
			roll  = std::atan2(R(2,1), R(2,2));
			pitch = std::atan2(-R(2,0), sy);
			yaw   = std::atan2(R(1,0), R(0,0));
		} else {
			roll  = std::atan2(-R(1,2), R(1,1));
			pitch = std::atan2(-R(2,0), sy);
			yaw   = 0.0;
		}

		return {roll, pitch, yaw};  // [roll, pitch, yaw]
	}

	std::shared_ptr<tf2_ros::TransformListener> tf_listener_{nullptr};
	std::unique_ptr<tf2_ros::Buffer> tf_buffer_;
	rclcpp::TimerBase::SharedPtr timer_A, timer_B;
	double pgA[4][4], pgB[4][4], pgAT[4][4], pgBT[4][4];
	double joint_positions_B[7], joint_positions_BD[7];
	double joint_positions_A[7], joint_positions_AD[7];
	FX_DOUBLE ret_jointA[7], ret_jointB[7];
	FX_DOUBLE ret_jointAS[7], ret_jointBS[7];
	FX_DOUBLE ref_jointA[7], ref_jointB[7];

	FX_INT32L TYPE[2];
	FX_DOUBLE GRV[2][3];
	FX_DOUBLE DH[2][8][4];
	FX_DOUBLE PNVA[2][7][4];
	FX_DOUBLE BD[2][4][3];

	FX_DOUBLE Mass[2][7];
	FX_DOUBLE MCP[2][7][3];
	FX_DOUBLE I[2][7][6];

	double ref_dir[3];
	//
	std::string ee_nameA, ee_nameB,
		elbow_nameA, elbow_nameB,
		left_base_name, right_base_name,
		left_base_nameJ, right_base_nameJ,
		config_file, urdf_file, srdf_file;
	pinocchio::FrameIndex ee_idA, ee_idB, elbow_idA, elbow_idB,
		left_base_id, right_base_id;
	float mpc_dt_ = 0.02; // MPC time step
	bool in_collision_ = false;
	pinocchio::Model model_, model_A, model_B;
	pinocchio::Data data_, data_A, data_B;
	pinocchio::GeometryModel geom_model_;
	pinocchio::GeometryData geom_data_;
	pinocchio::Model::ConfigVectorType q_, qAs_, qBs_;
	pinocchio::Model::TangentVectorType v_, v2_;
	rclcpp::Publisher<std_msgs::msg::Bool>::SharedPtr collision_pub_A,
		collision_pub_B;
	bool will_coll_A, will_coll_B;
	rclcpp::Publisher<visualization_msgs::msg::MarkerArray>::SharedPtr marker_pub_;
	std::vector<Eigen::Vector3d> eef_points_A, eef_points_B;
	std::vector<bool> collision_status_A, collision_status_B;
	rclcpp::TimerBase::SharedPtr mpc_timer;

	int no_collision_itr_A = -1;
	int no_collision_itr_B = -1;
	// Pilot and PilotLmt objects are initialized in the constructor
	// Pilot the_pilot;
	// PilotLmt the_lmt;
	rclcpp::Subscription<marvin_msgs::msg::Jointfeedback>::SharedPtr joint_fb_subscriber_;
	rclcpp::Subscription<std_msgs::msg::Bool>::SharedPtr left_DS_subscriver_;
	rclcpp::Subscription<std_msgs::msg::Bool>::SharedPtr right_DS_subscriver_;
	rclcpp::Subscription<std_msgs::msg::Bool>::SharedPtr left_zerosw_subscriber_;
	rclcpp::Subscription<std_msgs::msg::Bool>::SharedPtr right_zerosw_subscriber_;
	rclcpp::Publisher<marvin_msgs::msg::Jointcmd>::SharedPtr joint_cmd_publisherA_, joint_cmd_publisherB_, ik_publisherA_, ik_publisherB_;
	rclcpp::Publisher<marvin_msgs::msg::Jointfeedback>::SharedPtr joint_feedback_publisherA_, joint_feedback_publisherB_;
	rclcpp::Subscription<marvin_msgs::msg::Jointfeedback>::SharedPtr joint_feedback_subscriberA_, joint_feedback_subscriberB_;
	rclcpp::Publisher<geometry_msgs::msg::PoseStamped>::SharedPtr pose_publisher_, pose_publisher_eefA_, pose_publisher_eefB_, pose_A_pub_, pose_B_pub_;
	rclcpp::Subscription<geometry_msgs::msg::PoseStamped>::SharedPtr target_pose_subscriberA_, target_pose_subscriberB_;

	std::vector<std::string> joint_namesA_;
	std::vector<std::string> joint_namesB_;
	OneEuroSE3Filter filter_A_;
	OneEuroSE3Filter filter_B_;

	geometry_msgs::msg::TransformStamped cached_tf_b_left, cached_tf_b_right;

	bool left_dswitch = false, right_dswitch = false;
	bool left_dswitch_last = false, right_dswitch_last = false;
	bool left_hooked = false, right_hooked = false;
	bool zero_567_A = false;
	bool zero_567_B = false;

	std::chrono::steady_clock::time_point grip_L_stamp, grip_R_stamp;

	pinocchio::SE3 T_left_base, T_right_base;
	std::vector<pinocchio::JointIndex> joint_to_lockA, joint_to_lockB;
};

int main(int argc, char **argv)
{
	rclcpp::init(argc, argv);
	auto node = std::make_shared<Pilot_arm_node>();

	// Test6();
	// node->Test6();

	rclcpp::spin(node);
	rclcpp::shutdown();
	return 0;
}