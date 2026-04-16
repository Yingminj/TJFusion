#!/usr/bin/env python3
import rclpy
from rclpy.node import Node
from geometry_msgs.msg import PoseStamped
from std_msgs.msg import Float32,Bool, Int32
from std_srvs.srv import Trigger
import socket
import json 
from rclpy.qos import qos_profile_sensor_data 
import struct
from tf2_ros import Buffer, TransformListener, LookupException, ConnectivityException, ExtrapolationException
import tf2_geometry_msgs
import numpy as np

class PoseGripMsg:
    def __init__(self, px=0.0, py=0.0, pz=0.0,
                 qx=0.0, qy=0.0, qz=0.0, qw=1.0):
        self.px = px
        self.py = py
        self.pz = pz
        self.qx = qx
        self.qy = qy
        self.qz = qz
        self.qw = qw

    def pack(self):
        # '>7f?f': 大端，7个float
        data = {
            "px": self.px,
            "py": self.py,
            "pz": self.pz,
            "qx": self.qx,
            "qy": self.qy,
            "qz": self.qz,
            "qw": self.qw,
        }
        return json.dumps(data).encode('utf-8')
    
class UDPPoseReceiver(Node):

    def __init__(self):
        super().__init__('udp_pose_receiver')

        # ROS Publisher
        self.publisher_A = self.create_publisher(PoseStamped, 'control/target_poseL', qos_profile_sensor_data)
        self.grip_switch_A = self.create_publisher(Bool,'control/gripL', qos_profile_sensor_data)
        self.publisher_B = self.create_publisher(PoseStamped, 'control/target_poseR', qos_profile_sensor_data)
        self.grip_switch_B = self.create_publisher(Bool,'control/gripR', qos_profile_sensor_data)
        self.trigger_value_A = self.create_publisher(Float32, 'control/gripperValueL', 10)
        self.trigger_value_B = self.create_publisher(Float32, 'control/gripperValueR', 10)
        self.tcp_sub_A = self.create_subscription(PoseStamped, 'info/eef_left', self.tcp_callback_A, qos_profile_sensor_data)
        self.tcp_sub_B = self.create_subscription(PoseStamped, 'info/eef_right', self.tcp_callback_B, qos_profile_sensor_data)
        # self.zerosw_A_pub_ = self.create_publisher(Bool, 'left_controller/zerosw', qos_profile_sensor_data)
        # self.zerosw_B_pub_ = self.create_publisher(Bool, 'right_controller/zerosw', qos_profile_sensor_data)
        self.record_State_sub = self.create_subscription(Int32, 'recorder/status', self.recorder_cbk, 10)
        self.cli = self.create_client(Trigger, 'toggle_recording')
        self.pos_scale = 1.1
        self.height_offset = -0.10
        self.last_buttonX = False
        self.max_x =1.8
        self.min_x =0.15
        self.max_y =1.8
        self.min_y =-1.8
        self.max_z =1.8
        self.min_z =0.5
        self.clip_pos = True

        # UDP 设置
        self.udp_ip = '0.0.0.0'   # 本机监听所有地址
        self.udp_portA = 9000      # 和 Unity 保持一致
        self.udp_portB = 9001      # 和 Unity 保持一致
        self.udp_fb_A = 9002      # 和 Unity 保持一致
        self.udp_fb_B = 9003      # 和 Unity 保持一致
        self.udP_record = 9004
        self.vr_ip = '192.168.11.124'

        self.socka = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.socka.bind((self.udp_ip, self.udp_portA))
        self.socka.setblocking(False)  # 非阻塞模式
        self.sockb = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sockb.bind((self.udp_ip, self.udp_portB))
        self.sockb.setblocking(False)  # 非阻塞模式
        

        self.sock_fb_A = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock_fb_A.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        self.sock_fb_B = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock_fb_B.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        self.sockrecord = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sockrecord.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)

        self.discovery_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.discovery_sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        self.discovery_sock.bind(('0.0.0.0', 9999))
        self.discovery_sock.setblocking(False)


        self.tf_buffer = Buffer()
        self.tf_listener = TransformListener(self.tf_buffer, self)
        # 定时器：每 0.1 ms 检查一次是否有数据
        self.timer = self.create_timer(0.01, self.listen_udp_A)
        self.timerb = self.create_timer(0.01, self.listen_udp_B)
        self.timeriscovery = self.create_timer(1.0, self.listen_discovery)


        self.get_logger().info(f'Listening UDP on {self.udp_ip}:{self.udp_portA}, {self.udp_ip}:{self.udp_portB}')

    def listen_discovery(self):
        try:
            data, addr = self.discovery_sock.recvfrom(1024)
            message = data.decode('utf-8')
            if message == "DISCOVER_VR":
                response = "VR_HOST_HERE"
                self.discovery_sock.sendto(response.encode('utf-8'), addr)
                self.get_logger().info(f"Responded to discovery from {addr}")
                self.vr_ip = addr[0]  # 更新 VR 设备的 IP 地址
        except BlockingIOError:
            # 没有数据就跳过
            pass

    def listen_udp_A(self):
        try:
            data, addr = self.socka.recvfrom(1024)
            message = data.decode('utf-8')
            pose_data = json.loads(message)

            # ---- 数据解析 ----
            x, y, z = pose_data['px'], pose_data['py'], pose_data['pz'] + self.height_offset
            if self.clip_pos:
                x = max(self.min_x, min(self.max_x, x))
                y = max(self.min_y, min(self.max_y, y))
                z = max(self.min_z, min(self.max_z, z))

            pose_msg = PoseStamped()
            pose_msg.header.stamp = self.get_clock().now().to_msg()
            pose_msg.header.frame_id = "tracking_base_link"
            pose_msg.pose.position.x = x * self.pos_scale
            pose_msg.pose.position.y = y * self.pos_scale
            pose_msg.pose.position.z = z * self.pos_scale
            pose_msg.pose.orientation.x = pose_data['qx']
            pose_msg.pose.orientation.y = pose_data['qy']
            pose_msg.pose.orientation.z = pose_data['qz']
            pose_msg.pose.orientation.w = pose_data['qw']

            # ---- TF 坐标转换 ----
            try:
                transform = self.tf_buffer.lookup_transform(
                    'base_link',             # target_frame
                    pose_msg.header.frame_id,  # source_frame = tracking_base_link
                    rclpy.time.Time()
                )

                # 转换到 base_link 坐标系
                pose_converted = tf2_geometry_msgs.do_transform_pose(pose_msg, transform)
                pose_converted.header.frame_id = 'base_link'

                # 发布转换后的 Pose
                self.publisher_A.publish(pose_converted)
            except (LookupException, ConnectivityException, ExtrapolationException) as e:
                self.get_logger().warn(f"Transform failed in listen_udp_A: {e}")
                # 如果 TF 不可用，则直接使用原 frame
                self.publisher_A.publish(pose_msg)

            # ---- 其他触发器消息 ----
            grip_msg = pose_data['grip']
            trigger_msg = pose_data['triggerValue']
            self.grip_switch_A.publish(Bool(data=grip_msg))
            self.trigger_value_A.publish(Float32(data=trigger_msg))

            # ---- 录制控制按钮 ----
            buttonX = pose_data['buttonX']
            if buttonX and not self.last_buttonX:
                self.send_request()
                self.get_logger().info("Request sent to toggle recording")
            self.last_buttonX = buttonX

        except BlockingIOError:
            pass
        
    def listen_udp_B(self):
        try:
            data, addr = self.sockb.recvfrom(1024)
            message = data.decode('utf-8')
            pose_data = json.loads(message)
            x, y, z = pose_data['px'], pose_data['py'], pose_data['pz'] + self.height_offset
            if self.clip_pos:
                x = max(self.min_x, min(self.max_x, x))
                y = max(self.min_y, min(self.max_y, y))
                z = max(self.min_z, min(self.max_z, z))
            pose_msg = PoseStamped()
            pose_msg.header.stamp = self.get_clock().now().to_msg()
            pose_msg.header.frame_id = "tracking_base_link"  # 根据实际情况修改
            pose_msg.pose.position.x = x * self.pos_scale
            pose_msg.pose.position.y = y * self.pos_scale
            pose_msg.pose.position.z = z * self.pos_scale
            pose_msg.pose.orientation.x = pose_data['qx']
            pose_msg.pose.orientation.y = pose_data['qy']
            pose_msg.pose.orientation.z = pose_data['qz']
            pose_msg.pose.orientation.w = pose_data['qw']
            # ---- TF 坐标转换 ----
            try:
                transform = self.tf_buffer.lookup_transform(
                    'base_link',             # target_frame
                    pose_msg.header.frame_id,  # source_frame = tracking_base_link
                    rclpy.time.Time()
                )

                # 转换到 base_link 坐标系
                pose_converted = tf2_geometry_msgs.do_transform_pose(pose_msg, transform)
                pose_converted.header.frame_id = 'base_link'

                # 发布转换后的 Pose
                self.publisher_B.publish(pose_converted)
            except (LookupException, ConnectivityException, ExtrapolationException) as e:
                self.get_logger().warn(f"Transform failed in listen_udp_A: {e}")
                # 如果 TF 不可用，则直接使用原 frame
                self.publisher_B.publish(pose_msg)
            # ---- 其他触发器消息 ----
            grip_msg = pose_data['grip']
            trigger_msg = pose_data['triggerValue']
            self.grip_switch_B.publish(Bool(data=grip_msg))
            self.trigger_value_B.publish(Float32(data=trigger_msg))

        except BlockingIOError:
            # 没有数据就跳过
            pass
    def tcp_callback_A(self, msg):


        try:
            # 这里 target_frame 是目标坐标系
            transform = self.tf_buffer.lookup_transform(
                'tracking_base_link',      # target_frame
                'base_link',    # source_frame
                self.get_clock().now()
            )

            # 用 tf2_geometry_msgs 做变换
            pose_out = tf2_geometry_msgs.do_transform_pose(msg.pose, transform)
            Posemsg = PoseGripMsg(
            px=pose_out.position.x/ self.pos_scale,
            py=pose_out.position.y/ self.pos_scale,
            pz=pose_out.position.z/ self.pos_scale - self.height_offset,
            qx=pose_out.orientation.x,
            qy=pose_out.orientation.y,
            qz=pose_out.orientation.z,
            qw=pose_out.orientation.w,
            )
            # self.get_logger().info(f"Transformed pose: {pose_out}")
            self.sock_fb_A.sendto(Posemsg.pack(), (self.vr_ip, self.udp_fb_A))
            # self.get_logger().info(f'Sent feedback to A')

        except (LookupException, ConnectivityException, ExtrapolationException) as e:
            # self.get_logger().warn(f"Transform failed: {e}")
            pass

        
    def tcp_callback_B(self, msg):
        try:
            # 这里 target_frame 是目标坐标系
            transform = self.tf_buffer.lookup_transform(
                'tracking_base_link',      # target_frame
                'base_link',    # source_frame
                self.get_clock().now()
            )

            # 用 tf2_geometry_msgs 做变换
            pose_out = tf2_geometry_msgs.do_transform_pose(msg.pose, transform)
            Posemsg = PoseGripMsg(
            px=pose_out.position.x/ self.pos_scale,
            py=pose_out.position.y/ self.pos_scale,
            pz=pose_out.position.z/ self.pos_scale - self.height_offset,
            qx=pose_out.orientation.x,
            qy=pose_out.orientation.y,
            qz=pose_out.orientation.z,
            qw=pose_out.orientation.w,
            )
            # self.get_logger().info(f"Transformed pose: {pose_out}")
            self.sock_fb_B.sendto(Posemsg.pack(), (self.vr_ip, self.udp_fb_B))
            # self.get_logger().info(f'Sent feedback to B')

        except (LookupException, ConnectivityException, ExtrapolationException) as e:
            # self.get_logger().warn(f"Transform failed: {e}")
            pass

    def recorder_cbk(self, msg):
        if msg.data == 1:
            # self.get_logger().info("Recorder started")
            self.sockrecord.sendto(b"1", (self.vr_ip, self.udP_record))
        elif msg.data == 0:
            # self.get_logger().info("Recorder stopped")
            self.sockrecord.sendto(b"0", (self.vr_ip, self.udP_record))
        else:
            self.get_logger().warn(f"Unknown recorder status: {msg.data}")

    def send_request(self):
        # Non-blocking call
        future = self.cli.call_async(Trigger.Request())
        # Do NOT spin_until_future_complete
        # Optionally, you can add a callback later:
        future.add_done_callback(self.response_callback)

    def response_callback(self, future):
        try:
            response = future.result()
            self.get_logger().info(f'Result: {response.success}, {response.message}')
        except Exception as e:
            self.get_logger().error(f'Service call failed: {e}')

def main(args=None):
    rclpy.init(args=args)
    node = UDPPoseReceiver()
    rclpy.spin(node)
    node.destroy_node()
    rclpy.shutdown()

if __name__ == '__main__':
    main()
