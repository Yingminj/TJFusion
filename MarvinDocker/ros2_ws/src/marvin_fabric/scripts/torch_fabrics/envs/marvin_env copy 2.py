import os
import numpy as np
import torch
import pinocchio as pin
from torch import cos, vmap
from torch import sin
from functorch import jacfwd, hessian, grad
from typing import List
from copy import copy, deepcopy


from torch_fabrics.envs.robot_env_marvin import RobotEnv

# def so3_exp(rot_vec: torch.Tensor):
#     """
#     Rodrigues formula: so(3) vector -> SO(3) matrix
#     rot_vec: [3]
#     returns: 3x3 rotation matrix
#     """
#     theta = torch.linalg.norm(rot_vec) + 1e-8  # avoid zero div
#     k = rot_vec / theta
#     K = torch.tensor([[0, -k[2], k[1]],
#                       [k[2], 0, -k[0]],
#                       [-k[1], k[0], 0]], dtype=torch.float64)
#     R = torch.eye(3, dtype=torch.float64) + torch.sin(theta)*K + (1-torch.cos(theta))*(K@K)
#     return R

# def so3_log(R: torch.Tensor):
#     """
#     SO(3) matrix -> rotation vector
#     """
#     cos_theta = (torch.trace(R) - 1)/2
#     cos_theta = torch.clamp(cos_theta, -1.0, 1.0)  # numerical stability
#     theta = torch.acos(cos_theta)
#     if theta < 1e-6:
#         # small angle approx
#         return 0.5 * torch.tensor([R[2,1]-R[1,2], R[0,2]-R[2,0], R[1,0]-R[0,1]], dtype=torch.float64)
#     else:
#         return theta/(2*torch.sin(theta)) * torch.tensor([R[2,1]-R[1,2], R[0,2]-R[2,0], R[1,0]-R[0,1]], dtype=torch.float64)


class MarvinEnv(RobotEnv):
    def __init__(
        self, 
        obs_pos: torch.Tensor,
        obs_radii: torch.Tensor,
        urdf_path: str = None,
        mesh_path: str = None,
    ):
        self.obs_pos = obs_pos
        self.obs_radii = obs_radii
        self.point = torch.Tensor([0,0,0,1])
        self.t = 0
        obs_shape = 18
        
        q_init = np.array([  0, -1.0, 0, -0.9, 0, 0, 0, 0, -1.0, 0, -0.9, 0, 0, 0])
        v_init = np.array([  0.0, -0.2, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0])
        self.goal_posL = None
        self.goal_posR = None
        self.tcp_length = 0.10
        
        super().__init__(urdf_path, mesh_path, simrate=100,q_init=q_init, v_init=v_init)

    def set_goalL(self, goal: pin.SE3):
        pos = goal.translation
        pos_tensor = torch.tensor(pos, dtype=torch.float64)
        offset_pos_1 = goal.translation + goal.rotation @ np.array([self.tcp_length, 0.0, 0.0])
        offset_pos_2 = goal.translation + goal.rotation @ np.array([0.0, self.tcp_length, 0.0])
        # offset_pos_z = goal.translation + goal.rotation @ np.array([0.0001, 0.0001, self.tcp_length])
        offset_pos_tensor_1 = torch.tensor(offset_pos_1, dtype=torch.float64)
        offset_pos_tensor_2 = torch.tensor(offset_pos_2, dtype=torch.float64)
        # offset_pos_tensor_z = torch.tensor(offset_pos_z, dtype=torch.float64)

        self.goal_posL = torch.stack([pos_tensor, offset_pos_tensor_1, offset_pos_tensor_2])

    def set_goalR(self, goal: pin.SE3):
        pos = goal.translation
        pos_tensor = torch.tensor(pos, dtype=torch.float64)
        offset_pos_1 = goal.translation + goal.rotation @ np.array([self.tcp_length, 0.0, 0.0])
        offset_pos_2 = goal.translation + goal.rotation @ np.array([0.0, self.tcp_length, 0.0])
        # offset_pos_z = goal.translation + goal.rotation @ np.array([0.0001, 0.0001, self.tcp_length])
        offset_pos_tensor_1 = torch.tensor(offset_pos_1, dtype=torch.float64)
        offset_pos_tensor_2 = torch.tensor(offset_pos_2, dtype=torch.float64)
        # offset_pos_tensor_z = torch.tensor(offset_pos_z, dtype=torch.float64)

        self.goal_posR = torch.stack([pos_tensor, offset_pos_tensor_1, offset_pos_tensor_2])

    def step(self, action: np.ndarray):
        self.t += 1
        self.step_sim(action)
        obs = (self.q, self.v)
        reward = self.get_reward()
        qpos = torch.Tensor(self.q)

        # print(f"t: {self.t}")
        # done = done or self.t > 200
        done = False
        return obs, reward, done, {}

    
    def get_reward(self):
        return 0

    ############# FABRIC STUFF ####################

    # def get_fk(self):
    #     link_id = self.model.getFrameId(link_name)
    #     return self.data.oMf[link_id]
    
    def attractor_task_mapL(self, x: torch.Tensor):
        """
        x: 6D [pos(3), rot_vec(3)]
        returns 6D error: [pos_err; rot_err]
        fully differentiable in PyTorch
        """
        pos = x[:3]
        pos_err = pos - self.goal_posL[0,:3]

        return pos_err

    def attractor_task_mapR(self, x: torch.Tensor):
        """
        x: 6D [pos(3), rot_vec(3)]
        returns 6D error: [pos_err; rot_err]
        fully differentiable in PyTorch
        """
        pos = x[:3]
        pos_err = pos - self.goal_posR[0,:3]

        return pos_err
    
    def orient_task_mapL1(self, x: torch.Tensor):
        """
        x: n x 3
        returns n x 3 error: [pos_err]
        fully differentiable in PyTorch
        """
        pos = x
        pos_err = pos - self.goal_posL[1,:3]

        return pos_err
    def orient_task_mapL2(self, x: torch.Tensor):
        """
        x: n x 3
        returns n x 3 error: [pos_err]
        fully differentiable in PyTorch
        """
        pos = x
        pos_err = pos - self.goal_posL[2,:3]

        return pos_err
    def orient_task_mapR1(self, x: torch.Tensor):
        """
        x: n x 3
        returns n x 3 error: [pos_err]
        fully differentiable in PyTorch
        """
        pos = x
        pos_err = pos - self.goal_posR[1,:3]

        return pos_err
    def orient_task_mapR2(self, x: torch.Tensor):
        """
        x: n x 3
        returns n x 3 error: [pos_err]
        fully differentiable in PyTorch
        """
        pos = x
        pos_err = pos - self.goal_posR[2,:3]

        return pos_err
    
    @torch.jit.export
    def obstacle_avoidance_task_map(self, x: torch.Tensor, obs_pos: torch.Tensor) -> torch.Tensor:
        """
        x: (3,)
        obs_pos: (n,3)
        output: (n,)
        """
        # --- 向量化计算差值 ---
        diff = obs_pos - x  # 避免中间变量复制 (n,3)
        norms = torch.linalg.norm(diff, dim=-1)  # (n,)

        # --- 防止除零 ---
        norms = norms.clamp_min(1e-8)

        # --- 距离标准化 ---
        normed = norms / self.obs_radii - 1.0
        return normed
    
    def self_coll_avoidance_task_map(self, qpos: torch.Tensor):
        out = []
        pin.forwardKinematics(self.model, self.data, qpos)
        pin.updateFramePlacements(self.model, self.data)
        link_poses = self.data.oMf
        flange_pose = link_poses[self.TCP_R_id].translation
        flange_pose_torch = torch.from_numpy(flange_pose).double()
        n_pose = len([flange_pose_torch])
        n_obs = len(self.obs_pos)

        # diff = (torch.stack(flange_pose_torch)[:, None, :] - self.obs_pos[None, :, :]).view(-1, 3)
        diff = (torch.stack([flange_pose_torch]) - self.obs_pos).view(-1, 3)
        radii = (0.5 * self.obs_radii).view(1, -1)
        norms = torch.linalg.norm(diff, axis=1)
        if n_obs > 1:
            radii = radii.repeat(n_pose, n_obs).view(-1)
            norms = norms.repeat_interleave(n_obs)
            out = (norms/radii)[::n_obs] - 1
        else:
            out = norms / radii - 1

        return out.double().view(-1)

    

    def floor_repulsion_task_map(self, qpos: torch.Tensor):
        link_poses, all_Ts = self._apply_fk(qpos)
        return torch.stack(link_poses)[:,2].double()
        # add gripper pose because not in XML
        # flange_pose = link_poses[-1]
        # gripper_pose = flange_pose + torch.Tensor([0, 0, 0.0584]).double()        
        # return gripper_pose - self.goal_pos

    def upper_joint_limit_task_map(self, qpos: torch.Tensor):
        # upper_limit = self.sim.model.jnt_range[:7,0]
        upper_limit = self.max_pos_limit
        return torch.Tensor(upper_limit) - qpos

    def lower_joint_limit_task_map(self, qpos: torch.Tensor):
        # lower_limit = self.sim.model.jnt_range[:7,1]
        lower_limit = self.min_pos_limit
        return qpos - torch.Tensor(lower_limit)

    def attractor_fabric(self, pos: torch.Tensor, vel: torch.Tensor):
        """
        k = potential scaling term, increase to increase magnitude of acceleration
        upper_m = upper isotropic mass, 
        lower_m = lower isotropic mass,
        radial_basis_width = 
        transition_rate = 
        damping = velocity damping term
        """
        k = 50.0
        upper_m = 50.0
        lower_m = 1.0
        radial_basis_width = 5.0
        transition_rate = 10.0
        damping = 30.0

        potential = lambda x: k*(torch.linalg.norm(x) + (1/transition_rate)*torch.log(1+torch.exp(-2*transition_rate*torch.linalg.norm(x))))
        pos_ = pos[:3].clone()
        vel_ = vel[:3].clone()
        potential_grad = torch.func.grad(potential)(pos_)

        accel = -potential_grad - damping*vel_
        metric = (upper_m - lower_m)*torch.exp(-(radial_basis_width * torch.norm(pos_))**2)*torch.eye(3) + lower_m*torch.eye(3).double()

        # print(f"Accel attractor: {accel}")
        # print(f"Metric attractor: {metric}")
        return metric, accel
    def attractor_fabric_batch(self, pos: torch.Tensor, vel: torch.Tensor):
        """
        Batched version of attractor_fabric.
        pos: (B, 3)
        vel: (B, 3)
        Returns:
            metric: (B, 3, 3)
            accel:  (B, 3)
        """
        k = 5.0
        upper_m = 50.0
        lower_m = 10.0
        radial_basis_width = 5.0
        transition_rate = 10.0
        damping = 10.0

        # ---- Compute norms ----
        norms = torch.linalg.norm(pos, dim=1, keepdim=True)  # (B, 1)

        # ---- Potential and gradient (analytic) ----
        # potential = k*(‖x‖ + (1/τ)*log(1 + exp(-2τ‖x‖)))
        # dV/dx = k * (x / ‖x‖) * (1 - 2 / (1 + exp(2τ‖x‖)))
        safe_norm = norms + 1e-9  # avoid divide-by-zero
        exp_term = torch.exp(2 * transition_rate * norms)
        potential_grad = k * (pos / safe_norm) * (1 - 2 / (1 + exp_term))

        # ---- Acceleration ----
        accel = -potential_grad - damping * vel  # (B, 3)

        # ---- Metric ----
        exp_weight = torch.exp(-(radial_basis_width * norms)**2)  # (B, 1, 1)
        I = torch.eye(3, device=pos.device, dtype=pos.dtype).unsqueeze(0).repeat(pos.shape[0], 1, 1)
        metric = (upper_m - lower_m) * exp_weight * I + lower_m * I  # (B, 3, 3)

        return metric, accel
    # def attractor_orientation(self, rot: torch.Tensor, vel: torch.Tensor):
    #     """
    #     rot: 3D rotation vector
    #     vel: 3D angular velocity
    #     """
    #     # --- Parameters
       
        

    #     k_rot = 100.0
    #     damping_rot = 100.0
    #     upper_m_rot = 20.0
    #     lower_m_rot = 10.0
    #     radial_basis_width_rot = 5.0
    #     transition_rate_pos = 10.0

       
    #     # --- Rotation attractor
    #     rot_vec = rot

    #     potential = lambda x: k_rot*(torch.linalg.norm(x) + (1/transition_rate_pos)*torch.log(1+torch.exp(-2*transition_rate_pos*torch.linalg.norm(x))))
    #     potential_grad = grad(potential)(rot_vec)

    #     accel = -potential_grad - damping_rot*vel
    #     metric = (upper_m_rot - lower_m_rot)*torch.exp(-(radial_basis_width_rot * torch.norm(rot_vec))**2)*torch.eye(3) + lower_m_rot*torch.eye(3)

    #     return metric, accel
    
    def attractor_fabric_se3(self,pos: torch.Tensor, vel: torch.Tensor):
        """
        pos_rot: 6D [pos(3), rot_vec(3)]
        vel: 6D [v_linear(3), omega(3)]
        goal_pos: 3D
        goal_rot_vec: 3D
        """
        # --- Parameters
        k_pos = 100.0
        damping_pos = 10.0
        upper_m_pos = 50.0
        lower_m_pos = 10.0
        radial_basis_width_pos = 5.0
        transition_rate_pos = 10.0

        k_rot = 100.0
        damping_rot = 20.0
        upper_m_rot = 20.0
        lower_m_rot = 10.0
        radial_basis_width_rot = 5.0

        # --- Position attractor
        pos = pos_rot[:3]
        pos_err = pos 
        potential_pos = lambda x: k_pos*(torch.linalg.norm(x) + (1/transition_rate_pos)*torch.log(1+torch.exp(-2*transition_rate_pos*torch.linalg.norm(x))))
        potential_grad_pos = grad(potential_pos)(pos)
        accel_pos = -potential_grad_pos - damping_pos*vel[:3]
        metric_pos = (upper_m_pos - lower_m_pos)*torch.exp(-(radial_basis_width_pos * torch.norm(pos))**2)*torch.eye(3) + lower_m_pos*torch.eye(3)

        # --- Rotation attractor
        rot_vec = pos_rot[3:]
        
        rot_err = rot_vec
        accel_rot = -k_rot * rot_err - damping_rot * vel[3:]
        metric_rot = (upper_m_rot - lower_m_rot)*torch.exp(-(radial_basis_width_rot * torch.norm(rot_vec))**2)*torch.eye(3) + lower_m_rot*torch.eye(3)

        # --- Combine 6D
        accel = torch.cat([accel_pos, accel_rot])
        metric = torch.block_diag(metric_pos, metric_rot)

        return metric, accel
    def orient_fabric(self, pos: torch.Tensor, vel: torch.Tensor):
        """
        k = potential scaling term, increase to increase magnitude of acceleration
        upper_m = upper isotropic mass, 
        lower_m = lower isotropic mass,
        radial_basis_width = 
        transition_rate = 
        damping = velocity damping term
        """
        k = 50.0
        upper_m = 50.0
        lower_m = 10.0
        radial_basis_width = 5.0
        transition_rate = 10.0
        damping = 30.0

        potential = lambda x: k*(torch.linalg.norm(x) + (1/transition_rate)*torch.log(1+torch.exp(-2*transition_rate*torch.linalg.norm(x))))
        pos_ = pos[:3].clone()
        vel_ = vel[:3].clone()
        potential_grad = grad(potential)(pos_)

        accel = -potential_grad - damping*vel_
        metric = (upper_m - lower_m)*torch.exp(-(radial_basis_width * torch.norm(pos_))**2)*torch.eye(3) + lower_m*torch.eye(3)

        # print(f"Accel attractor: {accel}")
        # print(f"Metric attractor: {metric}")
        return metric.double(), accel.double()
    def obstacle_avoidance_fabric(self, pos: torch.Tensor, vel: torch.Tensor):
        """
        Batch version of obstacle avoidance fabric computation.
        Fully vectorized, uses manual gradient (no jacfwd).

        Parameters:
            pos: (n, 1, m) — distance ratios (e.g., d/r - 1)
            vel: (n, 1, m) — relative velocities
            k_b: metric scaling term
            a_b: potential scaling term

        Returns:
            metric: (n, m, m) — diagonal metric matrices for each sample
            accel: (n, 1, m) — repulsive acceleration for each sample
        """
        # Ensure correct dtype
        k_b = 1  # metric scaling
        a_b = 100# potential scaling
        upper_m = 50.0
        lower_m = 10.0
        pos = pos.to(torch.float64)
        vel = vel.to(torch.float64)

        eps = 1e-8  # prevent divide by zero

        # Step 1: velocity sign mask (only apply repulsion if moving toward obstacle)
        s = (vel < 0.0).double()  # (n, 1, m)

        # Step 2: potential φ(x) = a_b / (2 * x^8)
        # Step 3: manual gradient dφ/dx = -4 * a_b / x^9
        potential_grad = -4.0 * a_b / ((pos + eps) ** 9)  # (n, 1, m)

        # Step 4: acceleration term (repulsion)
        # accel = (s) * potential_grad  # (n, 1, m)
        accel = - s * (pos**2) @ potential_grad.double()

        # Step 5: metric G(x) = k_b / x^2 * I
        inv_sq = 1.0 / (pos** 2+eps)  # (n, 1, m)
        # metric = 
        metric = k_b * inv_sq
      
        return metric, accel
    def obstacle_avoidance_fabric1(self, pos: torch.Tensor, vel: torch.Tensor):
        """
        无视速度的障碍物排斥 fabric。
        Parameters:
            pos: 与障碍物的距离（或距离向量）
            vel: 保留参数接口，但不参与计算
        Returns:
            metric: 局部度量矩阵
            accel: 排斥加速度
        """
        k_b = 0.2   # metric scaling
        a_b = 0.2 # potential scaling
        s = (vel < 0.0).double()
        # potential = a_b / (2 * d^8)
        potential = lambda x: a_b / (2 * (x ** 8))

        pos_ = pos.clone().requires_grad_(True)
        # potential_grad = torch.autograd.functional.jacobian(potential, pos_)
        # 或使用 jacfwd：
        potential_grad = jacfwd(potential)(pos_)

        # 🚫 无速度项，直接使用 potential gradient 的反方向作为排斥加速度
        accel =  (torch.ones_like(vel)**2) @ potential_grad.double()

        # metric 与距离平方反比
        metric = torch.diag(torch.ones_like(pos)) * (k_b / (pos ** 2))

        return metric, accel
    
    def self_coll_avoidance_fabric(self, pos: torch.Tensor, vel: torch.Tensor):
        pass
    
    def floor_repulsion_fabric(self, pos: torch.Tensor, vel: torch.Tensor):
        """
        Parameters:
        k_b = metric scaling term
        a_b = potential scaling term
        """
        k_b = 150
        a_b = 150# potential scaling term

        s = (vel < 0).double()
        potential = lambda x: a_b / (2*(x**8))
        pos_ = pos.clone()
        potential_grad = jacfwd(potential)(pos_)
        
        accel = -s * (vel**2) @ potential_grad.double()
        metric = torch.diag(s) * k_b / (pos**2)

        print(f"Accel repeller: {accel}")
        print(f"Metric repeller: {metric}")

        return metric, accel
    def joint_limit_fabric_upper(self, pos: torch.Tensor, vel: torch.Tensor):
        """
        Parameters:
        l = 
        a1 = 
        a2 = 
        a3 = 
        a4 = 
        """
        # pos = pos[:7]
        # vel = vel[:7]
        # pos = torch.Tensor(self.q).double()
        # vel = torch.Tensor(self.v).double()
        # pos = torch.Tensor(self.q).double()
        # vel = torch.Tensor(self.v).double()
        x_dot = -vel
        l = 0.25
        a1, a2, a3, a4 = 0.3, 0.5, 1.0, 2.0
        s = (x_dot < 0).double()
        metric = torch.diag(s * (l / pos))
        potential = lambda q: (a1 / q**2) + a2 * torch.log(1. + torch.exp(-a3 * (q - a4)))
        pos_ = pos.clone()
        potential_grad = torch.func.jacfwd(potential)(pos_)
        # sigmoid_term = torch.sigmoid(-a3 * (pos - a4))
        # grad = -2 * a1 / (pos**3) - a2 * a3 * sigmoid_term
        accel = - s * torch.linalg.norm(x_dot)**2 @ potential_grad

        return metric, accel
    
    def joint_limit_fabric_lower(self, pos: torch.Tensor, vel: torch.Tensor):
        """
        Parameters:
        l = 
        a1 = 
        a2 = 
        a3 = 
        a4 = 
        """
        # pos = pos[:7]
        # vel = vel[:7]
        # pos = torch.Tensor(self.q).double()
        # vel = torch.Tensor(self.v).double()
        # pos = torch.Tensor(self.q).double()
        # vel = torch.Tensor(self.v).double()
        x_dot = vel
        l = 0.25
        a1, a2, a3, a4 = 0.3, 0.5, 1.0, 2.0
        s = (x_dot < 0).double()
        metric = torch.diag(s * (l / pos))
        potential = lambda q: (a1 / q**2) + a2 * torch.log(1. + torch.exp(-a3 * (q - a4)))
        pos_ = pos.clone()
        potential_grad = torch.func.jacfwd(potential)(pos_)
        accel = - s * torch.linalg.norm(x_dot)**2 @ potential_grad

        return metric, accel
    def joint_limit_fabric_old(self, pos: torch.Tensor, vel: torch.Tensor):
        """
        Parameters:
        l = 
        a1 = 
        a2 = 
        a3 = 
        a4 = 
        """
        # pos = pos[:7]
        # vel = vel[:7]
        # pos = torch.Tensor(self.q).double()
        # vel = torch.Tensor(self.v).double()
        # pos = torch.Tensor(self.q).double()
        # vel = torch.Tensor(self.v).double()
        l = 0.25
        a1, a2, a3, a4 = 0.3, 0.5, 1.0, 2.0
        s = (vel < 0).double()
        metric = torch.diag(s * (l / pos))
        potential = lambda q: (a1 / q**2) + a2 * torch.log(1. + torch.exp(-a3 * (q - a4)))
        pos_ = pos.clone()
        potential_grad = jacfwd(potential)(pos_)
        accel = -s * torch.linalg.norm(vel)**2 @ potential_grad

        return metric, accel

    # def compute_jacobianL(self):
    #     J = pin.computeFrameJacobian(self.model, self.data, self.q, self.TCP_L_id, pin.ReferenceFrame.LOCAL_WORLD_ALIGNED)
    #     J_torch = torch.from_numpy(J).double()
    #     return J_torch[:3, :]  # translation part
    
    # def compute_vL(self):
    #     v_frame = pin.getFrameVelocity(self.model, self.data, self.TCP_L_id, pin.ReferenceFrame.LOCAL_WORLD_ALIGNED)
    #     v_linear = v_frame.linear.copy() 
    #     v_frame_torch = torch.from_numpy(v_linear).double()
    #     return v_frame_torch[:3]  # translation part

    # def compute_cL(self):
    #     pin.computeJointJacobiansTimeVariation(self.model, self.data, self.q, self.v)
    #     dJ = pin.getFrameJacobianTimeVariation(self.model, self.data, self.TCP_L_id, pin.ReferenceFrame.LOCAL_WORLD_ALIGNED)
    #     c = dJ @ self.v
    #     c_linear = c[:3].copy()
    #     c_torch = torch.from_numpy(c_linear).double()
    #     return c_torch
    # def compute_jacobianR(self):
    #     J = pin.computeFrameJacobian(self.model, self.data, self.q, self.TCP_R_id, pin.ReferenceFrame.LOCAL_WORLD_ALIGNED)
    #     J_torch = torch.from_numpy(J).double()
    #     return J_torch[:3, :]  # translation part
    
    # def compute_vR(self):
    #     v_frame = pin.getFrameVelocity(self.model, self.data, self.TCP_R_id, pin.ReferenceFrame.LOCAL_WORLD_ALIGNED)
    #     v_linear = v_frame.linear.copy() 
    #     v_frame_torch = torch.from_numpy(v_linear).double()
    #     return v_frame_torch[:3]  # translation part

    # def compute_cR(self):
    #     pin.computeJointJacobiansTimeVariation(self.model, self.data, self.q, self.v)
    #     dJ = pin.getFrameJacobianTimeVariation(self.model, self.data, self.TCP_R_id, pin.ReferenceFrame.LOCAL_WORLD_ALIGNED)
    #     c = dJ @ self.v
    #     c_linear = c[:3].copy()
    #     c_torch = torch.from_numpy(c_linear).double()
    #     return c_torch
    
    def _set_fabrics(self):
        self.task_names = [
            # "attractor_L",
            "attractor_R",
            # "orient_L1",
            # "orient_L2",
            # "orient_R1",
            # "orient_R2",
            "obstacle_avoidance",
            # "floor_repulsion",
           "upper_jointlim",
           "lower_jointlim"
        ]
        self.task_spaces = {
            "attractor_L": "cartesian",
            "attractor_R": "cartesian",
            "orient_L1": "cartesian",
            "orient_L2": "cartesian",
            "orient_R1": "cartesian",
            "orient_R2": "cartesian",
            "upper_jointlim": "joint",
            "lower_jointlim": "joint",
            "obstacle_avoidance": "carts",
            # "floor_repulsion": "cartesian",
        }
        self.task_frames={
            "attractor_L": "left_oo",
            "attractor_R": "right_oo",
            "orient_L1": "left_ox",
            "orient_L2": "left_oy",
            "orient_R1": "right_ox",
            "orient_R2": "right_oy",
        }
        self.task_maps = {
            "attractor_L" : self.attractor_task_mapL,
            "attractor_R" : self.attractor_task_mapR,
            "orient_L1": self.orient_task_mapL1,
            "orient_L2": self.orient_task_mapL2,
            "orient_R1": self.orient_task_mapR1,
            "orient_R2": self.orient_task_mapR2,

            "obstacle_avoidance" : self.obstacle_avoidance_task_map,
            # "floor_repulsion": self.floor_repulsion_task_map,
            "upper_jointlim" : self.upper_joint_limit_task_map,
            "lower_jointlim" : self.lower_joint_limit_task_map
        }
        self.fabrics = {
            "attractor_L" : self.attractor_fabric,
            "attractor_R" : self.attractor_fabric,
            "orient_L1": self.orient_fabric,
            "orient_L2": self.orient_fabric,
            "orient_R1": self.orient_fabric,
            "orient_R2": self.orient_fabric,
            "obstacle_avoidance" : self.obstacle_avoidance_fabric,
            # "floor_repulsion" : self.floor_repulsion_fabric,
            # # double weighting? whatever
            "upper_jointlim" : self.joint_limit_fabric_upper,
            "lower_jointlim" : self.joint_limit_fabric_lower
        }
        # self.jac_funcs = {
        #     "attractor_L": self.compute_jacobianL,
        #     "attractor_R": self.compute_jacobianR,
        #     # "obstacle_avoidance": self.compute_jacobianL,
        #     # "floor_repulsion": self.compute_jacobian,
        # }
        # self.vel_funcs = {
        #     "attractor_L": self.compute_vL,
        #     "attractor_R": self.compute_vR,
        #     # "obstacle_avoidance": self.compute_vL,
        #     # "floor_repulsion": self.compute_v,
        # }
        # self.accel_funcs = {
        #     "attractor_L": self.compute_cL,
        #     "attractor_R": self.compute_cR,
        #     # "obstacle_avoidance": self.compute_cL,
        #     # "floor_repulsion": self.compute_c,
        # }



if __name__ == "__main__":
    env = MarvinEnv(
        urdf_path="/home/tianhao/torch-fabrics/marvin_coll_mpc/marvin_ccs.urdf",
        mesh_path="/home/tianhao/torch-fabrics/marvin_coll_mpc"
    )
    while True:
        print("xx") 