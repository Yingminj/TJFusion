"""ROS2 订阅 /joint_states 的位置控制脚本.

修改：
1. 原先固定往返控制改为从 /joint_states 话题获取目标位置 (pos_des)。
2. 使用 Timer 以固定频率(默认50Hz)下发 control_pos_force。
3. 加入软限位 (基于初始化时扫描得到的 min/max)，防止越界。
4. 优雅关闭：节点销毁时关闭串口。
"""

import math
import time
# 安装后入口点方式运行需要包内相对导入；源码直接运行 fallback
try:
    from .DM_CAN import *  # type: ignore  # noqa
except ImportError:
    from DM_CAN import *  # type: ignore  # noqa
from rclpy.executors import MultiThreadedExecutor
import rclpy
from rclpy.node import Node
from sensor_msgs.msg import JointState
from std_msgs.msg import Float32,Float32MultiArray,Int32MultiArray


# 全局（保持与原结构兼容）
Motor1, Motor2, MotorControl1 = None, None, None
Motor1_min_pos, Motor1_max_pos = 0.0, 0.0
Motor2_min_pos, Motor2_max_pos = 0.0, 0.0
auto_calibrate = False


class GripperMotorNode(Node):
    def __init__(self):
        super().__init__('dm_gripper_motor_node')
        self.declare_parameter('current_limit', 0.0)  # i_des 标幺*10000 的值
        self.declare_parameter('vel_cmd', 0.0)         # Vel_des
        # self.declare_parameter('rate_hz', 50.0)
        # self.declare_parameter('joint_name_motor1', 'gripperL')
        # self.declare_parameter('joint_name_motor2', 'gripperR')
        # self.declare_parameter('use_joint_names', True)
        self.declare_parameter('auto_calibrate', False)
        self.declare_parameter('Motor1_min_pos', 0.0)
        self.declare_parameter('Motor1_max_pos', 1.0)
        self.declare_parameter('Motor2_min_pos', 0.0)
        self.declare_parameter('Motor2_max_pos', 1.0)
        self.declare_parameter('left_motor_id', 1)
        self.declare_parameter('right_motor_id', 2)
        self.q1 = 0.0
        self.q2 = 0.0  # Motor2 目标位置缓存
        self.vel_cmd = int(self.get_parameter('vel_cmd').get_parameter_value().integer_value)
        self.i_des = int(self.get_parameter('current_limit').get_parameter_value().integer_value)
        self.current_desired_pos_m1 = 0.0
        self.current_desired_pos_m2 = 0.0
        self.have_joint_state = False
        self.left_id = int(self.get_parameter('left_motor_id').get_parameter_value().integer_value)
        self.right_id = int(self.get_parameter('right_motor_id').get_parameter_value().integer_value)
        self.timer = self.create_timer(0.001, self.control_timer_callback)  # 100 Hz

        
        # self.publishertoolcomA = self.create_publisher(UInt16MultiArray, "control/tool_com_A", 10)
        # self.subscribertoolcomA = self.create_subscription(
        #     UInt16MultiArray,
        #     "control/tool_ret_A",
        #     self.can_callbackA,
        #     10)
        # self.publishertoolcomB = self.create_publisher(UInt16MultiArray, "control/tool_com_B", 10)
        # self.subscribertoolcomB = self.create_subscription(
        #     UInt16MultiArray,
        #     "control/tool_ret_B",
        #     self.can_callbackB,
        #     10)
        self._init_motors()
        self._calibrate_limits()

        # 订阅 joint_states
        qos = rclpy.qos.QoSProfile(depth=10)
        self.subscriptionL = self.create_subscription(
            Float32, '/control/gripperValueL', self.left_callback, qos)
        self.subscriptionR = self.create_subscription(
            Float32, '/control/gripperValueR', self.right_callback, qos)
        
        self.feed_back_publisher_R = self.create_publisher(Float32MultiArray, '/gripper/feedback_R', 10)
        self.feed_back_publisher_L = self.create_publisher(Float32MultiArray, '/gripper/feedback_L', 10)
        self.feed_back_publisher_L_err = self.create_publisher(Int32MultiArray, '/gripper/feedback_L_err', 5)
        self.feed_back_publisher_R_err = self.create_publisher(Int32MultiArray, '/gripper/feedback_R_err', 5)
        # self.timer = self.create_timer(0.01, self.timer_callback)  # 10 Hz
        self.get_logger().info('Gripper motor node started. Waiting joint states...')
    def control_timer_callback(self):
        MotorControl1.controlMIT(Motor1, 3.0, 0.12, self.q1, self.vel_cmd, self.i_des)
        MotorControl1.controlMIT(Motor2, 3.0, 0.12, self.q2, self.vel_cmd, self.i_des)
        MotorControl1.recv()

        
        q_fb_R = Motor2.getPosition()
        dq_fb_R = Motor2.getVelocity()
        tau_fb_R = Motor2.getTorque()
        err_fb_R = Motor2.getErr()
        temp_mos_fb_R = Motor2.getTempMos()
        temp_motor_fb_R = Motor2.getTempMotor()

        msgR = Float32MultiArray()
        msgR.data = [float(q_fb_R), float(dq_fb_R), float(tau_fb_R), float(temp_mos_fb_R), float(temp_motor_fb_R)]
        self.feed_back_publisher_R.publish(msgR)
        
        msgR_err = Int32MultiArray()
        msgR_err.data = [int(err_fb_R)]
        self.feed_back_publisher_R_err.publish(msgR_err)

        q_fb_L = Motor1.getPosition()
        dq_fb_L = Motor1.getVelocity()
        tau_fb_L = Motor1.getTorque()
        err_fb_L = Motor1.getErr()
        temp_mos_fb_L = Motor1.getTempMos()
        temp_motor_fb_L = Motor1.getTempMotor()
        
        msgL = Float32MultiArray()
        msgL.data = [float(q_fb_L), float(dq_fb_L), float(tau_fb_L), float(temp_mos_fb_L), float(temp_motor_fb_L)]
        self.feed_back_publisher_L.publish(msgL)

        msgL_err = Int32MultiArray()
        msgL_err.data = [int(err_fb_L)]
        self.feed_back_publisher_L_err.publish(msgL_err)
        
        
        
        # self.get_logger().info(f'GripperR pos_fb:{q_fb:.4f}')

    # ---------------- 初始化与标定 ----------------
    def _init_motors(self):
        global Motor1, Motor2, MotorControl1
    
        Motor1 = Motor(DM_Motor_Type.DM4310, self.left_id, self.left_id+0x10)
        # Motor1 = Motor(DM_Motor_Type.DM4310, 0x01, 0x11)
        Motor2 = Motor(DM_Motor_Type.DM4310, self.right_id, self.right_id+0x10)
        MotorControl1 = MotorControl()
        MotorControl1.addMotor(Motor1)
        MotorControl1.add_to_ch(Motor1, 'left')

        MotorControl1.addMotor(Motor2)
        MotorControl1.add_to_ch(Motor2, 'right')
        
        # if MotorControl1.switchControlMode(Motor1, Control_Type.MIT):
        #     self.get_logger().info('Motor1 switch MIT success')
        # if MotorControl1.switchControlMode(Motor2, Control_Type.MIT):
        #     self.get_logger().info('Motor2 switch MIT success')
        # MotorControl1.save_motor_param(Motor1)
        # MotorControl1.save_motor_param(Motor2)
        MotorControl1.enable(Motor1)
        # self.motor1_send()
        MotorControl1.enable(Motor2)
        # self.motor2_send()
        self.get_logger().info('Motors enabled')
        # MotorControl1.set_zero_position(Motor1)
        # MotorControl1.set_zero_position(Motor2)
    # def can_callbackA(self, msg: UInt16MultiArray):
        
    #     data = msg.data
    #     # data_bytes = bytes(data)
    #     MotorControl1.recv(data)
    #     m_pos = Motor1.getPosition()
    #     print(m_pos)
    # def can_callbackB(self, msg: UInt16MultiArray):
    #     print("Received CAN message B")
    #     data = msg.data
    #     # data_bytes = bytes(data)
    #     MotorControl1.recv(data)
    #     m_pos = Motor2.getPosition()
    #     print(m_pos)

    def _calibrate_limits(self):
        global Motor1_min_pos, Motor1_max_pos, Motor2_min_pos, Motor2_max_pos, auto_calibrate
        auto_calibrate = self.get_parameter('auto_calibrate').get_parameter_value().bool_value
        if auto_calibrate:
            # 简单往复动作，用原逻辑测 min/max
            for _ in range(200):
                MotorControl1.controlMIT(Motor1, 0.0,1.0, 0, 3, 0.0)
                MotorControl1.controlMIT(Motor2, 0.0,1.0, 0, 3, 0.0)
                time.sleep(0.005)
            MotorControl1.refresh_motor_status(Motor1)
            MotorControl1.refresh_motor_status(Motor2)
            Motor1_min_pos = Motor1.getPosition()
            Motor2_min_pos = Motor2.getPosition()
            for _ in range(200):
                MotorControl1.controlMIT(Motor1,  0.0,1.0, 0, -3, 0.0)
                MotorControl1.controlMIT(Motor2,  0.0,1.0, 0, -3, 0.0)
                time.sleep(0.005)
            Motor1_max_pos = Motor1.getPosition()
            Motor2_max_pos = Motor2.getPosition()
            self.get_logger().warn(f'Limits M1[min_pos,max_pos]:[{Motor1_min_pos:.6f},{Motor1_max_pos:.6f}] M2[min_pos,max_pos]:[{Motor2_min_pos:.6f},{Motor2_max_pos:.6f}]')
        else:
            Motor1_min_pos = self.get_parameter('Motor1_min_pos').get_parameter_value().double_value
            Motor2_min_pos = self.get_parameter('Motor2_min_pos').get_parameter_value().double_value
            Motor1_max_pos = self.get_parameter('Motor1_max_pos').get_parameter_value().double_value
            Motor2_max_pos = self.get_parameter('Motor2_max_pos').get_parameter_value().double_value

    # ---------------- 回调与控制 ----------------
    def left_callback(self, msg: Float32):
        if MotorControl1 is None:
            return
        # 限幅
        self.q1 = self._clamp(np.clip(msg.data, 0.0, 1.0), Motor1_min_pos, Motor1_max_pos)
        # q2 = self._clamp(self.current_desired_pos_m2, Motor2_min_pos, Motor2_max_pos)
        # vel_cmd = int(self.get_parameter('vel_cmd').get_parameter_value().integer_value)
        # i_des = int(self.get_parameter('current_limit').get_parameter_value().integer_value)
        # MotorControl1.controlMIT(Motor1, 3.0, 0.12, q1, vel_cmd, i_des)
        # q_fb = Motor1.getPosition()
        # self.get_logger().info(f'GripperL pos_fb:{q_fb:.4f}')
        # self.motor1_send()
    
    def right_callback(self, msg: Float32):
        if MotorControl1 is None:
            return
        # 限幅
        self.q2 = self._clamp(np.clip(msg.data, 0.0, 1.0), Motor2_min_pos, Motor2_max_pos)
        
        # vel_cmd = int(self.get_parameter('vel_cmd').get_parameter_value().integer_value)
        # i_des = int(self.get_parameter('current_limit').get_parameter_value().integer_value)
        # MotorControl1.controlMIT(Motor2, 3.0, 0.12, q2, vel_cmd, i_des)
        # q_fb = Motor2.getPosition()
        # self.get_logger().info(f'GripperR pos_fb:{q_fb:.4f}')
        # self.motor2_send()
    
    def _clamp(self, v, vmin, vmax):
        v = v*(vmax - vmin) + vmin
        return v

    # def control_timer_callback(self):
    #     # if MotorControl1 is None or not self.have_joint_state:
    #     #     return
    #     # # 限幅
    #     # q1 = self._clamp(self.current_desired_pos_m1, Motor1_min_pos, Motor1_max_pos)
    #     # q2 = self._clamp(self.current_desired_pos_m2, Motor2_min_pos, Motor2_max_pos)
    #     # vel_cmd = int(self.get_parameter('vel_cmd').get_parameter_value().integer_value)
    #     # i_des = int(self.get_parameter('current_limit').get_parameter_value().integer_value)
    #     # MotorControl1.controlMIT(Motor1, 10, 1, q1, vel_cmd, i_des)
    #     # MotorControl1.controlMIT(Motor2, 10, 1, q2, vel_cmd, i_des)
    #     self.motor1_send()
    #     self.motor2_send()
    # def motor1_send(self):
    #     data = MotorControl1.data_send[Motor1.SlaveID]
    #     # print("data:", data)
    #     if data is not []:
    #         msg = UInt16MultiArray()
    #         msg.data = [int(x) for x in data]  # convert to int list
    #         MotorControl1.data_send[Motor1.SlaveID] = []
    #         self.publishertoolcomA.publish(msg)

    # def motor2_send(self):
    #     data = MotorControl1.data_send[Motor2.SlaveID]
    #     # print("data:", data)
    #     if data is not []:
    #         msg = UInt16MultiArray()
    #         msg.data = [int(x) for x in data]  # convert to int list
    #         MotorControl1.data_send[Motor2.SlaveID] = []  # 发送后清空，等待下一次更新
    #         self.publishertoolcomB.publish(msg)
    
    def destroy_node(self):  # 资源释放
        return super().destroy_node()


def main(args=None):
    rclpy.init(args=args)

    gripper_node = GripperMotorNode()


    # Use a MultiThreadedExecutor if callbacks might block each other
    # executor = MultiThreadedExecutor()
    # executor.add_node(gripper_node)

    try:
        # executor.spin()
        rclpy.spin(gripper_node)
    except KeyboardInterrupt:
        pass
    finally:
        # executor.shutdown()
        gripper_node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':  # 兼容直接运行
    main()
