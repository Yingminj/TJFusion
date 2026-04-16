import numpy as np
import torch
from torch.utils.tensorboard import SummaryWriter

from torch_fabrics.fabrics import FabricHandler
from torch_fabrics.envs.marvin_env import MarvinEnv

from torch_fabrics.envs.robot_visualizer import MeshcatVisualizerThread 
import pinocchio as pin
import time
from tools.test_gui import TkinterGUI
import threading

import rclpy
from std_msgs.msg import Float32
NUM_ROLLOUTS = 10
SEED = 15
XML_PATH = "/home/tianhao/torch-fabrics/torch_fabrics/envs/assets/models/panda/full_panda.xml"


def ros_spin(node):
    rclpy.spin(node)

class FabricNode(rclpy.node.Node):
    def __init__(self):
        super().__init__('fabric_node')
        self.subscriber = self.create_subscription(
            Float32,
            '/test/z',
            self.listener_callback,
            10)
        self.z_value = 0.0

    def listener_callback(self, msg):

        self.z_value = msg.data
        print(f"Received z value: {self.z_value}")

            
def run(Node=None):
    env = MarvinEnv(
            urdf_path="/home/tianhao/fabrics/torch-fabrics/Models/marvin_ccs.urdf",
            mesh_path="/home/tianhao/fabrics/torch-fabrics/Models",
            obs_pos=torch.Tensor([
            [0.5, -0.0, 0.1],
            ]),
            obs_radii=torch.Tensor([0.06]),
        )
    env = env
    poseL = pin.SE3.Identity()
    poseL.translation = np.array([0.45, 0.00, 0.0])
    env.set_goalL(poseL)

    poseR = pin.SE3.Identity()
    poseR.translation = np.array([0.45, -0.05, 0.1])
    env.set_goalR(poseR)
    viz_thread = MeshcatVisualizerThread(env)
    viz_thread.start()
    time.sleep(1)  # Give some time for the visualizer to start

    fabric_handler = FabricHandler(env)

    def policy(pos: np.ndarray, vel: np.ndarray):
        pos = torch.from_numpy(pos)
        vel = torch.from_numpy(vel)
        accel = fabric_handler.fabric_solve(pos, vel)
        return accel.detach().numpy()

    state = env.reset()
    action = policy(*state)

    writer = SummaryWriter()


    i = 0
    for _ in range(NUM_ROLLOUTS):
        state = env.reset()
        while True:
            i += 1
            env.cal_fk(env.q, env.v)
            time_start = time.time()
            accel = policy(*state)
            time_end = time.time()
            # print(f"Time for fabric solve: {time_end - time_start} seconds")
            # accel = np.zeros_like(env.data.qvel)
            state, reward, done, _ = env.step(accel)
            if Node is not None:
                poseR.translation[2] = Node.z_value
            env.set_goalR(poseR)
            viz_thread.update(env.q)
            time.sleep(0.005)
            # env.render()
            # if done:
            #     break

def main():
    rclpy.init()
    node = FabricNode()

    # rclpy.spin(node)

    ros_thread = threading.Thread(target=ros_spin, args=(node,), daemon=True)
    ros_thread.start()
    run(node)

if __name__ == "__main__":
    main()
