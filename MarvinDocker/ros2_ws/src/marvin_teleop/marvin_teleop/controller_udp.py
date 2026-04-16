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
        self.trigger_pose_A = self.create_publisher(Bool,'control/enableL', qos_profile_sensor_data)
        self.publisher_B = self.create_publisher(PoseStamped, 'control/target_poseR', qos_profile_sensor_data)
        self.trigger_pose_B = self.create_publisher(Bool,'control/enableR', qos_profile_sensor_data)
        self.trigger_value_A = self.create_publisher(Float32, 'control/gripperValueL', 10)
        self.trigger_value_B = self.create_publisher(Float32, 'control/gripperValueR', 10)
        self.tcp_sub_A = self.create_subscription(PoseStamped, 'info/eef_left', self.tcp_callback_A, qos_profile_sensor_data)
        self.tcp_sub_B = self.create_subscription(PoseStamped, 'info/eef_right', self.tcp_callback_B, qos_profile_sensor_data)
        self.publisher_EL = self.create_publisher(PoseStamped, 'control/Elbow_left', qos_profile_sensor_data)
        self.publisher_ER = self.create_publisher(PoseStamped, 'control/Elbow_right', qos_profile_sensor_data)
        # self.record_State_sub = self.create_subscription(Int32, 'recorder/status', self.recorder_cbk, 10)
        # self.cli = self.create_client(Trigger, 'toggle_recording')
        self.pos_scale = 1.1
        self.height_offset = -0.10
        self.last_buttonX = False
        self.max_x =1.8
        self.min_x =0.15
        self.max_y =1.8
        self.min_y =-1.8
        self.max_z =1.8
        self.min_z =0.5
        robot_ip = self.declare_parameter('robot_ip', '192.168.1.100').value
        self.base_height = self.declare_parameter('base_height', 1.0).value
        # UDP 设置
        self.udp_ip = '0.0.0.0'   # 本机监听所有地址
        self.udp_portA = 9000      # 和 Unity 保持一致
        self.udp_portB = 9001      # 和 Unity 保持一致
        self.udp_fb_A = 9002      # 和 Unity 保持一致
        self.udp_fb_B = 9003      # 和 Unity 保持一致
        self.udp_portC = 9004      # 和 Unity 保持一致
        
        self.subnet = '.'.join(robot_ip.split('.')[:3]) + '.'
        print("subnet:",self.subnet)
        self.vr_ip = self.subnet +'124'
        print("vr_ip:",self.vr_ip)
        # Discovery settings: listen for headset broadcasts to learn its IP
        self.discovery_ip = '0.0.0.0'
        self.discovery_port = 8888
        # Broadcaster settings: periodically announce this node so headsets can discover it
        self.broadcast_name = 'ApexHost'
        self.broadcast_model = 'Orin_agx'
        self.broadcast_app_version = '251223'

        self.socka = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.socka.bind((self.udp_ip, self.udp_portA))
        self.socka.setblocking(False)  # 非阻塞模式
        self.sockb = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sockb.bind((self.udp_ip, self.udp_portB))
        self.sockb.setblocking(False)  # 非阻塞模式
        self.sockc = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sockc.bind((self.udp_ip, self.udp_portC))
        self.sockc.setblocking(False)  # 非阻塞模式
        # Discovery socket: listens for headset broadcast/heartbeat so we can update `self.vr_ip`
        self.sock_discovery = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        # allow reusing address for rapid restart
        self.sock_discovery.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            self.sock_discovery.bind((self.discovery_ip, self.discovery_port))
        except Exception as e:
            self.get_logger().warn(f'Could not bind discovery socket {self.discovery_ip}:{self.discovery_port}: {e}')
        self.sock_discovery.setblocking(False)

        # Broadcaster socket: will send broadcast packets announcing this node
        self.sock_bcast = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock_bcast.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        

        self.sock_fb_A = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock_fb_A.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        self.sock_fb_B = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock_fb_B.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        # self.sockrecord = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        # self.sockrecord.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)


        self.tf_buffer = Buffer()
        self.tf_listener = TransformListener(self.tf_buffer, self)
        # 定时器：每 0.1 ms 检查一次是否有数据
        self.timer = self.create_timer(0.01, self.listen_udp_A)
        self.timerb = self.create_timer(0.01, self.listen_udp_B)
        self.timerc = self.create_timer(0.01, self.listen_udp_C)
        # Discovery timer: check for headset broadcasts once per 0.5s
        self.discovery_timer = self.create_timer(1.0, self.listen_discovery)
        # Broadcast timer: send presence once per second
        self.broadcast_timer = self.create_timer(1.0, self.send_broadcast)

        self.user_height = 1.65

        self.torso_height=self.user_height*0.66
        self.height_offset = self.torso_height - self.base_height

        self.get_logger().info(f'Listening UDP on {self.udp_ip}:{self.udp_portA}, {self.udp_ip}:{self.udp_portB}')

    def listen_udp_A(self):
        try:
            data, addr = self.socka.recvfrom(1024)
            message = data.decode('utf-8')
            pose_data = json.loads(message)
            x, y, z = pose_data['px'], pose_data['py'], pose_data['pz'] + self.height_offset
            if x < self.min_x:
                x = self.min_x
            if y > self.max_y:
                y = self.max_y
            if z < self.min_z:
                z = self.min_z
            if z > self.max_z:
                z = self.max_z
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
            grip_msg = pose_data['grip']
            trigger_msg = pose_data['triggerValue']
            # zero_sw = pose_data['buttonY']
            # if grip_msg == 1:
            self.publisher_A.publish(pose_msg)
            # Only publish if pose is within allowed range
            x, y, z = pose_msg.pose.position.x, pose_msg.pose.position.y, pose_msg.pose.position.z
            # if 0.1 <= x <= 1.2 and -1.0 <= y <= 1.0 and 0.8 <= z <= 1.8:
            self.trigger_pose_A.publish(Bool(data=grip_msg))
            self.trigger_value_A.publish(Float32(data=trigger_msg))

            # inside listen_udp_A after parsing pose_data
            buttonX = pose_data['buttonX']

            # Edge detection: only trigger when pressed down once
            if buttonX and not self.last_buttonX:
                # self.send_request()
                # self.get_logger().info("Request sent to toggle recording")
                pass

            # Update last state
            self.last_buttonX = buttonX



            # self.zerosw_A_pub_.publish(Bool(data=zero_sw))


            # self.get_logger().info(f'Received and published pose: {pose_msg}')
        except BlockingIOError:
            # 没有数据就跳过
            pass
    def listen_udp_B(self):
        try:
            data, addr = self.sockb.recvfrom(1024)
            message = data.decode('utf-8')
            pose_data = json.loads(message)
            x, y, z = pose_data['px'], pose_data['py'], pose_data['pz'] + self.height_offset
            if x < self.min_x:
                x = self.min_x
            if y > self.max_y:
                y = self.max_y
            if z < self.min_z:
                z = self.min_z
            if z > self.max_z:
                z = self.max_z
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
            grip_msg = pose_data['grip']
            trigger_msg = pose_data['triggerValue']
            # zero_sw = pose_data['buttonB']
            # if grip_msg == 1:
            self.publisher_B.publish(pose_msg)
            # Only publish if pose is within allowed range
            
            
            self.trigger_pose_B.publish(Bool(data=grip_msg))
            self.trigger_value_B.publish(Float32(data=trigger_msg))
            # self.zerosw_B_pub_.publish(Bool(data=zero_sw))
            # self.get_logger().info(f'Received and published pose: {pose_msg}')
        except BlockingIOError:
            # 没有数据就跳过
            pass
    def listen_udp_C(self):
        try:
            data, addr = self.sockc.recvfrom(1024)
            message = data.decode('utf-8')
            pose_data = json.loads(message)
            # print(pose_data)
            # x, y, z = pose_data['px'], pose_data['py'], pose_data['pz'] + self.height_offset
            elbow_L = pose_data['left_elbow']
            elbow_L['pz'] += self.height_offset
            elbow_R = pose_data['right_elbow']
            elbow_R['pz'] += self.height_offset
            pose_msg = PoseStamped()
            pose_msg.header.stamp = self.get_clock().now().to_msg()
            pose_msg.header.frame_id = "tracking_base_link"  # 根据实际情况修改
            pose_msg.pose.position.x = elbow_L['px'] * self.pos_scale
            pose_msg.pose.position.y = elbow_L['py'] * self.pos_scale
            pose_msg.pose.position.z = elbow_L['pz'] * self.pos_scale
            pose_msg.pose.orientation.x = elbow_L['qx']
            pose_msg.pose.orientation.y = elbow_L['qy']
            pose_msg.pose.orientation.z = elbow_L['qz']
            pose_msg.pose.orientation.w = elbow_L['qw']
            self.publisher_EL.publish(pose_msg)

            pose_msg = PoseStamped()
            pose_msg.header.stamp = self.get_clock().now().to_msg()
            pose_msg.header.frame_id = "tracking_base_link"  # 根据实际情况修改
            pose_msg.pose.position.x = elbow_R['px'] * self.pos_scale
            pose_msg.pose.position.y = elbow_R['py'] * self.pos_scale
            pose_msg.pose.position.z = elbow_R['pz'] * self.pos_scale
            pose_msg.pose.orientation.x = elbow_R['qx']
            pose_msg.pose.orientation.y = elbow_R['qy']
            pose_msg.pose.orientation.z = elbow_R['qz']
            pose_msg.pose.orientation.w = elbow_R['qw']

            self.user_height = pose_data.get('user_height')
            self.torso_height = 0.66*self.user_height
            self.height_offset = -self.torso_height + self.base_height
            # print("user_height:", self.height_offset)
            self.publisher_ER.publish(pose_msg)
        except BlockingIOError:
            # no data
            pass
    def listen_discovery(self):
        """Listen for headset discovery/broadcast packets and update self.vr_ip.

        Accepts either JSON payload with an 'ip' field or uses the sender address.
        This runs periodically and is non-blocking.
        """
        try:
            data, addr = self.sock_discovery.recvfrom(4096)
            # Only treat the packet as a discovery if it's JSON and name == 'ApexHeadset'
            try:
                text = data.decode('utf-8')
            except Exception:
                text = data.decode('utf-8', errors='replace')
            # print(text)
            try:
                obj = json.loads(text)
            except Exception:
                # not JSON -> ignore
                return

            # Only update vr_ip when the payload explicitly identifies the headset
            if obj.get('name') == 'ApexHeadset':
                new_ip = addr[0]
                if new_ip != self.vr_ip:
                    old = self.vr_ip
                    self.vr_ip = new_ip
                    self.get_logger().info(
                        f"Updated vr_ip from {old} to {self.vr_ip} (discovered from {addr[0]}:{addr[1]}) - payload name=ApexHeadset"
                    )
                print("IP",self.vr_ip)
        except BlockingIOError:
            # no data
            pass

    def send_broadcast(self):
        """Broadcast a small JSON payload so headsets can discover this node.

        Payload looks like: {"name":"Apex_host","model":"Apex_node","app_version":"251223"}
        Sent to the discovery port using UDP broadcast.
        """
        payload = {
            'name': self.broadcast_name,
            'model': self.broadcast_model,
            'app_version': self.broadcast_app_version,
        }
        try:
            text = json.dumps(payload)

            # Determine local outbound IPv4 address (no packet sent)
            local_ip = self.subnet + '255'
            bcast_addr = local_ip
            # try:
            #     s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            #     # connect to a public IP; no packets are actually sent for UDP connect
            #     s.connect(('8.8.8.8', 80))
            #     local_ip = s.getsockname()[0]
            #     s.close()
            # except Exception:
            #     local_ip = None

            # # Compute broadcast address as first three octets + .255
            # bcast_addr = '<broadcast>'
            # if local_ip:
            #     parts = local_ip.split('.')
            #     if len(parts) >= 4:
            #         bcast_addr = '.'.join(parts[:3] + ['255'])

            # Send to computed broadcast address
            # self.get_logger().info(bcast_addr)
            # self.get_logger().info(text.encode('utf-8'))
            self.sock_bcast.sendto(text.encode('utf-8'), (bcast_addr, self.discovery_port))
        except Exception as e:
            # Log but don't raise — broadcasting is best-effort
            self.get_logger().debug(f'Broadcast failed: {e}')
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

    # def recorder_cbk(self, msg):
    #     if msg.data == 1:
    #         # self.get_logger().info("Recorder started")
    #         self.sockrecord.sendto(b"1", (self.vr_ip, self.udP_record))
    #     elif msg.data == 0:
    #         # self.get_logger().info("Recorder stopped")
    #         self.sockrecord.sendto(b"0", (self.vr_ip, self.udP_record))
    #     else:
    #         self.get_logger().warn(f"Unknown recorder status: {msg.data}")

    # def send_request(self):
    #     # Non-blocking call
    #     future = self.cli.call_async(Trigger.Request())
    #     # Do NOT spin_until_future_complete
    #     # Optionally, you can add a callback later:
    #     future.add_done_callback(self.response_callback)

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