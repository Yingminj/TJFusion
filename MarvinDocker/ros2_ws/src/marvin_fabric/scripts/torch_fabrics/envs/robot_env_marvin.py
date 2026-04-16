import numpy as np
from abc import abstractmethod
import pinocchio as pin
import meshcat
# from pinocchio.visualize import MeshcatVisualizer
import torch
from typing import List, Tuple
import yaml
from torch_fabrics.envs.collision_helper import approximate_geom_model

class RobotEnv():


    def __init__(
        self,
        urdf_path: str = None,
        mesh_path: str = None,
        simrate: int = None,
        q_init: np.ndarray = None,
        v_init: np.ndarray = None,
    ):

        self.model, self.collision_model, self.visual_model = pin.buildModelsFromUrdf(
            urdf_path, mesh_path
        )
        for i in range(self.model.njoints):
            print(self.model.names[i])
        self.data = self.model.createData()
        self.geom_data = self.collision_model.createData()
        self.init_collision_objects()
        self.task_names = []
        self.task_maps = {}
        self.task_spaces = {}
        self.task_frames = {}
        self.fabrics = {}
        # for cartesian tasks
        self.jac_funcs = {}
        self.vel_funcs = {}
        self.accel_funcs = {}
        
        self.min_jnt_torque_lims = -self.model.effortLimit
        self.max_jnt_torque_lims = self.model.effortLimit
        self.min_pos_limit = self.model.lowerPositionLimit
        self.max_pos_limit = self.model.upperPositionLimit
        if q_init is None:
            self.q_init = np.zeros(self.model.nq)
        else:
            self.q_init = q_init
        self.q = self.q_init
        if v_init is None:
            self.v_init = np.zeros(self.model.nv)
        else:
            self.v_init = v_init

        self.v = self.v_init
        self.a = np.ones(self.model.nv)

        # self.TCP_L_id = self.model.getFrameId("left_tool")
        # self.TCP_R_id = self.model.getFrameId("right_tool")
        self.simrate = simrate


        # self.dt_ = 0.0001
        self._set_fabrics()

        self.timestep = 0 

    def init_collision_objects(self):
        with open("/home/tianhao/fabrics/torch-fabrics/torch_fabrics/envs/robot_config.yaml", "r") as f:
            config = yaml.safe_load(f)
        srdf_path = "/home/tianhao/fabrics/torch-fabrics/Models/marvin_ccs.srdf"
        
        # 示例：获取 R_link3 的碰撞球信息
        spheres = config["geometry"]["marvin_collision"]["spheres"]
        self.sphere_num = 0
        for link_s in spheres:
            print(f"Link: {link_s}, Number of spheres: {len(spheres[link_s])}")
            self.sphere_num += len(spheres[link_s])
        active_links = config["active_links"]
        self.model,self.geom_model, link_to_sphere_indices, self.sphere_to_frame_indices = approximate_geom_model(spheres, [], self.model, self.collision_model)
        self.data = self.model.createData()
        self.link_to_sphere_indices = link_to_sphere_indices
        # self.geom_data = self.geom_model.createData()
        if srdf_path:
            pin.loadReferenceConfigurations(self.model, srdf_path)
            self.collision_model.addAllCollisionPairs()
            pin.removeCollisionPairs(self.model, self.collision_model, srdf_path)
        pairs = []
        for pair in self.collision_model.collisionPairs:
            print(f"Collision Pair: {pair.first} - {pair.second}")
            pair_IDA = self.collision_model.geometryObjects[pair.first].parentFrame
            pair_IDB = self.collision_model.geometryObjects[pair.second].parentFrame
            print(f"Pair Name: {self.model.frames[pair_IDA].name} - {self.model.frames[pair_IDB].name}")
            pairs.append((self.model.frames[pair_IDA].name, self.model.frames[pair_IDB].name))
        link_name_list = list(link_to_sphere_indices.keys())
        active_set = set(active_links)
        active_link_coll_dict = {link: [] for link in active_links}


        for a, b in pairs:
            if a in active_set and b not in active_link_coll_dict[a]:
                active_link_coll_dict[a].append(b)
            if b in active_set and a not in active_link_coll_dict[b]:
                active_link_coll_dict[b].append(a)
        self.active_link_coll_dict = active_link_coll_dict
        # self.active_link_coll_dict = {"right_link7": ["left_link7"]}
        link_sphere_map = {}
        self.link_sphere_vel_map = {}
        self.link_sphere_map = {}
        for link in self.active_link_coll_dict:
            # for coll_link in self.active_link_coll_dict[link]:
            #     print(f"  Collides with: {coll_link}")
            if link in link_to_sphere_indices:
                link_ids = link_to_sphere_indices[link]
                coll_link_ids = self.active_link_coll_dict[link]
                coll_sphere_indices = [link_to_sphere_indices[coll_link] for coll_link in coll_link_ids if coll_link in link_to_sphere_indices]
                coll_sphere_indices = [idx for sublist in coll_sphere_indices for idx in sublist]  # flatten
                link_sphere_map[link] = (link_ids, coll_sphere_indices)

            
            for link in link_sphere_map:
                idxa, idxb = link_sphere_map[link]
                if idxa == [] or idxb == []:
                    continue
                self.link_sphere_map[link] = (idxa, idxb)


    def step_sim(self, action: np.ndarray):
        # action is an acceleration!
        qpos = self.q
        qvel = self.v + action / self.simrate  # simple euler integration
        self.q = qpos + qvel / self.simrate
        self.v = qvel
    

    def reset(self):
        self.t = 0
        # self.set_state(
        #     self.init_config.detach().numpy(),
        #     self.init_vel.detach().numpy()
        # )
        self.q = self.q_init
        self.v = self.v_init
        self.cal_fk(self.q, self.v)
        return self.q, self.v
  
    def cal_fk(self, qpos: np.ndarray, qvel: np.ndarray):
        pin.computeAllTerms(self.model, self.data, qpos, qvel)
        pin.updateGeometryPlacements(self.model, self.data, self.geom_model, self.geom_data)
        pin.computeForwardKinematicsDerivatives(self.model, self.data, qpos, qvel, self.a)
        pin.computeJointJacobiansTimeVariation(self.model, self.data, qpos, qvel)
    def get_fk(self) -> Tuple[
        List[torch.Tensor],            # joint_poses: [n_joints, 3]
        List[torch.Tensor],            # joint_vels: [n_joints, 6]
        List[torch.Tensor],            # joint_accs: [n_joints, 6]
        List[torch.Tensor]       # link_js: list of Jacobian matrices (6 × nv)
    ]:

        frame_pos = []
        frame_vel = []
        frame_cs = []
        frame_js = []

        for i in range(self.model.nframes):
            oMf = self.data.oMf[i]  # world -> frame
            xyz = torch.tensor(oMf.translation.copy(), dtype=torch.float64)
            # Extract rotation as quaternion (xyzw)
            R = torch.tensor(oMf.rotation, dtype=torch.float64)

            # 李代数 log map: rotation -> so(3) vector
            rot_vec = torch.tensor(pin.log3(R.numpy()), dtype=torch.float64)
            
            # Concatenate [x, y, z, rx, ry, rz] (6D pose)
            pose = torch.cat([xyz, rot_vec])
            frame_pos.append(oMf)

            # --- 2. 获取速度（6D twist: [angular; linear]）
            v_frame = pin.getFrameVelocity(
                self.model, self.data, i, pin.ReferenceFrame.LOCAL_WORLD_ALIGNED
            ).vector
            frame_vel.append(v_frame)
            dJ = pin.getFrameJacobianTimeVariation(self.model, self.data, i, pin.ReferenceFrame.LOCAL_WORLD_ALIGNED)
            c_frame = dJ @ self.v
            # c_frame =pin.getFrameAcceleration(self.model, self.data, i, pin.ReferenceFrame.WORLD).vector
            frame_cs.append(torch.tensor(c_frame,dtype=torch.float64))
            J_i = pin.getFrameJacobian(
                self.model, self.data, i, pin.ReferenceFrame.LOCAL_WORLD_ALIGNED
            )

            frame_js.append(J_i)

       

        return frame_pos, frame_vel, frame_cs, frame_js

    def get_sphere_vel(self):
        sphere_velocities = {}
        sphere_curvatures = {}
        sphere_jacobians = {}
        for i in range(self.sphere_num):
          
            frame_id = self.sphere_to_frame_indices[i]
            v_o = pin.getFrameVelocity(
                self.model, self.data, frame_id, pin.ReferenceFrame.LOCAL_WORLD_ALIGNED
            )
            v_o_linear = v_o.linear
            
            dJ = pin.getFrameJacobianTimeVariation(self.model, self.data, frame_id, pin.ReferenceFrame.LOCAL_WORLD_ALIGNED)
            c_frame = dJ @ self.v
           
            J_frame = pin.getFrameJacobian(
                self.model, self.data, frame_id, pin.ReferenceFrame.LOCAL_WORLD_ALIGNED
            )
            J_linear = J_frame[:3, :]  # Linear velocity part (3 x nv)

            sphere_velocities[i] = v_o_linear
            sphere_curvatures[i] = c_frame
            sphere_jacobians[i] = J_linear
        return sphere_velocities, sphere_curvatures, sphere_jacobians
    @abstractmethod
    def _set_fabrics(self):
        pass



