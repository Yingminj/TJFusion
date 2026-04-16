import threading
import time
import meshcat
from pinocchio.visualize import MeshcatVisualizer
import pinocchio as pin
import numpy as np
import matplotlib.pyplot as plt
from torch_fabrics.envs.collision_helper import approximate_geom_model
import yaml
class MeshcatVisualizerThread(threading.Thread):
    def __init__(self, env, refresh_rate=60):
        super().__init__(daemon=True)  # 后台线程
        self.model = env.model
        self.collision_model = env.collision_model
        self.visual_model = env.visual_model
        self.data = env.data
        self.q = env.q.copy()
        self.running = True
        self.refresh_rate = refresh_rate  # Hz
        self.viz = None
        self.geom_data = self.collision_model.createData()
        self.init_collision_objects()


        # fig, ax = plt.subplots()
        # ax.set_xlim(-90, 90)
        # ax.set_ylim(-90, 90)
        # ax.set_xlabel("X")
        # ax.set_ylabel("Y")
        # ax.grid(True)
        # ax.set_title("Dynamic 2D Point")
        # self.point, = ax.plot([], [], 'ro', markersize=8)
    def init_collision_objects(self):
        with open("/home/tianhao/fabrics/torch-fabrics/torch_fabrics/envs/robot_config.yaml", "r") as f:
            config = yaml.safe_load(f)
            
        # 示例：获取 R_link3 的碰撞球信息
        spheres = config["geometry"]["marvin_collision"]["spheres"]
        _, self.collision_model, link_to_sphere_indices,_ = approximate_geom_model(spheres, [], self.model, self.collision_model)
        self.geom_data = self.collision_model.createData()

    def run(self):
        self.viz = MeshcatVisualizer(
            self.model, self.collision_model, self.visual_model,self.data
        )
        self.viz.initViewer(open=False)
        self.viz.loadViewerModel()
        self.viz.displayFrames(True)
        self.viz.displayVisuals(True)
        self.viz.displayCollisions(True)
        self.viz.display(self.q)


        while self.running:
            self.viz.display(self.q)
            # self.point.set_data([self.q[5]*180/np.pi], [self.q[6]*180/np.pi])  # Update point position
            # plt.pause(0.001)
            time.sleep(1.0 / self.refresh_rate)

    def update(self, q):
        """主线程调用，用于更新可视化姿态"""
        self.q = q.copy()

    def stop(self):
        self.running = False
