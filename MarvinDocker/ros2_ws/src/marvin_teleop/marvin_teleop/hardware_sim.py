#!/usr/bin/env python3

import rclpy
from rclpy.node import Node
from marvin_msgs.msg import Jointfeedback
from sensor_msgs.msg import JointState
from std_msgs.msg import Header


class HardwareSimulator(Node):
    """
    Hardware simulator node that publishes joint feedback with default resting pose
    from the SRDF configuration file.
    """

    def __init__(self):
        super().__init__('hardware_simulator')

        # Default resting pose from config/marvin_robot.srdf
        # Order: L1,L2,L3,L4,L5,L6,L7,R1,R2,R3,R4,R5,R6,R7
        # Values are in radians as specified in the SRDF file
        self.default_positions = [
            1.57,   # Joint1_L
            -1.57,  # Joint2_L
            -1.57,  # Joint3_L
            -1.57,  # Joint4_L
            0.0,    # Joint5_L
            0.0,    # Joint6_L
            0.0,    # Joint7_L
            -1.57,  # Joint1_R
            -1.57,  # Joint2_R
            1.57,   # Joint3_R
            -1.57,  # Joint4_R
            0.0,    # Joint5_R
            0.0,    # Joint6_R
            0.0     # Joint7_R
        ]

        # Joint names in order
        self.joint_names = [
            'Joint1_L', 'Joint2_L', 'Joint3_L', 'Joint4_L', 'Joint5_L', 'Joint6_L', 'Joint7_L',
            'Joint1_R', 'Joint2_R', 'Joint3_R', 'Joint4_R', 'Joint5_R', 'Joint6_R', 'Joint7_R'
        ]

        # Initialize velocities and efforts to zero
        self.default_velocities = [0.0] * 14
        self.default_efforts = [0.0] * 14

        # Create publisher for joint feedback
        self.joint_feedback_pub = self.create_publisher(
            Jointfeedback,
            'info/joint_feedback',
            10
        )

        # Create publisher for joint states
        self.joint_state_pub = self.create_publisher(
            JointState,
            'joint_states',
            10
        )

        # Create timer to publish at 100Hz (10ms period)
        self.timer = self.create_timer(0.01, self.publish_feedback)

        self.get_logger().info('Hardware Simulator Node initialized')
        self.get_logger().info('Publishing default resting pose from SRDF to info/joint_feedback and joint_states')

    def publish_feedback(self):
        """
        Publish joint feedback and joint state messages with default resting pose values.
        """
        # Get current timestamp
        current_time = self.get_clock().now().to_msg()

        # Publish Jointfeedback message
        feedback_msg = Jointfeedback()
        feedback_msg.header = Header()
        feedback_msg.header.stamp = current_time
        feedback_msg.header.frame_id = 'world'
        feedback_msg.positions = self.default_positions
        feedback_msg.velocities = self.default_velocities
        feedback_msg.efforts = self.default_efforts
        self.joint_feedback_pub.publish(feedback_msg)

        # Publish JointState message
        joint_state_msg = JointState()
        joint_state_msg.header = Header()
        joint_state_msg.header.stamp = current_time
        joint_state_msg.name = self.joint_names
        joint_state_msg.position = self.default_positions
        joint_state_msg.velocity = self.default_velocities
        joint_state_msg.effort = self.default_efforts
        self.joint_state_pub.publish(joint_state_msg)


def main(args=None):
    rclpy.init(args=args)

    hardware_sim = HardwareSimulator()

    try:
        rclpy.spin(hardware_sim)
    except KeyboardInterrupt:
        pass
    finally:
        hardware_sim.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
