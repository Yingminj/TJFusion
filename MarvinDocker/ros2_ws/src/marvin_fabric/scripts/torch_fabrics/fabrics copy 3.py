from functools import partial
import time
import torch
from functorch import jacfwd, jvp
import pinocchio as pin
from torch_fabrics.envs.robot_env_marvin import RobotEnv
import numpy as np

from torch_fabrics.test_mul import J_T
class FabricHandler:
    def __init__(self, env: RobotEnv):
        self.env = env
    
    def fabric_solve(self, pos: torch.Tensor, vel: torch.Tensor):
        """
        Batched fabric solver.
        Calls fabric_eval() at most twice:
        - once for all joint-space tasks
        - once for all Cartesian-space tasks
        """
        pos = pos.detach().clone()
        pos.requires_grad_()
        vel = vel.detach().clone()
        vel.requires_grad_()

        link_p, link_v, link_a, link_j = self.env.get_fk()
        sphere_vels, sphere_cs, sphere_js = self.env.get_sphere_vel()

        # === 1️⃣ Collect joint-space tasks ===
        joint_x, joint_v = [], []
        joint_J, joint_c = [], []
        joint_task_names = []

        # === 2️⃣ Collect Cartesian-space tasks ===
        cart_x, cart_v = [], []
        cart_J, cart_c = [], []
        cart_task_names = []

        # === 3️⃣ Collect Cartesian-space group tasks ===
        carts_x, carts_v = [], []
        carts_J, carts_c = [], []
        carts_task_names = []

        # === 3️⃣ Batched evaluate fabrics ===
        all_metric, all_accel, all_J, all_c = [], [], [], []

        for task_name in self.env.task_names:
            task_map = self.env.task_maps[task_name]
            task_space = self.env.task_spaces.get(task_name, "cartesian")

            if task_space == "joint":
                # ---- Joint-space task ----
                x = task_map(pos)
                v = vel
                J = torch.func.jacfwd(task_map)(pos)
                c = torch.zeros_like(vel)
                
                metric, accel = self.fabric_eval(x, v, task_name)
                metric = metric.to(dtype=torch.float64)
                accel = accel.to(dtype=torch.float64)

                all_metric.append(metric)
                all_accel.append(accel)
                all_c.append(c)
                all_J.append(J)
            elif task_space == "cartesian":
                # ---- Cartesian-space task ----
                frames = self.env.task_frames[task_name]
                frames = frames if isinstance(frames, list) else [frames]  # 统一为 list
                # frame_id = self.env.model.getFrameId(self.env.task_frames[task_name])

                for frame_id_str in frames:
                   
                    frame_id = self.env.model.getFrameId(frame_id_str)
                    x = torch.tensor(link_p[frame_id].translation, dtype=torch.float64).requires_grad_()
                    f = task_map(x)
                    vx = torch.tensor(link_v[frame_id][:3], dtype=torch.float64)
                    c = torch.tensor(link_a[frame_id][:3], dtype=torch.float64)

                    J_x = torch.func.jacfwd(task_map)(x)
                    J_q = link_j[frame_id][:3, :]
                    J = J_x @ J_q
                    v = J_x @ vx

                    # cart_task_names.append(task_name)  
                    metric, accel = self.fabric_eval(f, v, task_name)
                    all_c.append(J_x @ c)
                    all_J.append(J)

                    all_metric.append(metric)
                    all_accel.append(accel)
            elif task_space == "carts":
                # ---- Cartesian-space task ----

                results = []
                # carts_task_names.append(task_name)
                for link_id, (link_sphere_ids, obs_sphere_ids) in self.env.link_sphere_map.items():
                    if len(link_sphere_ids) == 0 or len(obs_sphere_ids) == 0:
                        continue  # Skip empty links

                    # Jacobian of each link sphere wrt q (n_link, nq, 3)
                    J_q = torch.stack([torch.tensor(sphere_js[i], dtype=torch.float64) for i in link_sphere_ids])

                    # Positions
                    link_positions = torch.stack([
                        torch.from_numpy(self.env.data.oMf[self.env.sphere_to_frame_indices[i]].translation).to(dtype=torch.float64)
                        for i in link_sphere_ids
                    ])  # (n_link, 3)
                    obs_positions = torch.stack([
                        torch.from_numpy(self.env.data.oMf[self.env.sphere_to_frame_indices[k]].translation).to(dtype=torch.float64)
                        for k in obs_sphere_ids
                    ])  # (n_obs, 3)

                    # Radii
                    link_radii = torch.tensor([
                        self.env.geom_model.geometryObjects[i].geometry.radius for i in link_sphere_ids
                    ], dtype=torch.float64)
                    obs_radii = torch.tensor([
                        self.env.geom_model.geometryObjects[k].geometry.radius for k in obs_sphere_ids
                    ], dtype=torch.float64)

                    # Linear velocities
                    vi_all = torch.tensor([sphere_vels[i][:3] for i in link_sphere_ids], dtype=torch.float64)
                    vj_all = torch.tensor([sphere_vels[k][:3] for k in obs_sphere_ids], dtype=torch.float64)

                    # Curvature (centripetal) accelerations
                    ci_all = torch.tensor([sphere_cs[i][:3] for i in link_sphere_ids], dtype=torch.float64)
                    cj_all = torch.tensor([sphere_cs[k][:3] for k in obs_sphere_ids], dtype=torch.float64)

                    # Differences (broadcasted)
                    diff = link_positions[:, None, :] - obs_positions[None, :, :]  # (n_link, n_obs, 3)
                    norms = torch.linalg.norm(diff, dim=-1, keepdim=True).clamp_min(1e-8)  # (n_link, n_obs, 1)

                    # Radii sums
                    radii_sum = (link_radii[:, None] + obs_radii[None, :]).unsqueeze(-1)/2  # (n_link, n_obs, 1)

                    # Task map f = ||d|| / (r_i + r_j) - 1
                    f = (norms / radii_sum - 1.0).squeeze(-1)  # (n_link, n_obs)

                    # Jacobian wrt x: df/dx = diff / (||diff|| * (r_i + r_j))
                    J_x = diff / (norms * radii_sum)  # (n_link, n_obs, 3)

                    # desired: (n_link, n_obs, nq)
                    J = torch.einsum('loj,ljk->lok', J_x, J_q)

                    # Relative velocity between spheres
                    vx = vi_all[:, None, :] - vj_all[None, :, :]  # (n_link, n_obs, 3)

                    # Task-space velocity
                    v = torch.sum(J_x * vx, dim=-1)  # (n_link, n_obs)

                    # Curvature difference
                    cx = ci_all[:, None, :] - cj_all[None, :, :]  # (n_link, n_obs, 3)
                    c_linear = torch.sum(J_x * cx, dim=-1)  # (n_link, n_obs)
                    
                    c = c_linear #* 0.0
    
                    results.append({
                        "link": link_id,
                        "f": f,
                        "v": v,
                        "J": J,
                        "c": c,
                    })



                f_list = [res["f"] for res in results]  # list of (n_link, n_obs)
                v_list = [res["v"] for res in results]  # list of (n_link, n_obs)
                J_list = [res["J"] for res in results]  # list of (n_link, n_obs, nq)
                c_list = [res["c"] for res in results]  # list of (n_link, n_obs)

                M_r_c = 0
                f_r_c = 0
                for i in range(len(f_list)):
                    f = f_list[i]
                    v = v_list[i]
                    J = J_list[i]
                    c = c_list[i]
                    f_flat = f.reshape(-1, 1, 1)  # (n_link*n_obs,1,1)
                    v_flat = v.reshape(-1, 1, 1)  # (n_link*n_obs,1,1)
                    J_flat = J.reshape(-1, 1, self.env.model.nv)  #
                    c_flat = c.reshape(-1, 1, 1)  # (n_link*n_obs,1,1)
                    # n_link, n_obs = f.shape


                    metrics, accels = self.fabric_eval(f_flat, v_flat, task_name)

                    J_T = J_flat.transpose(1, 2)
                    M_r_batch = torch.bmm(J_T, torch.bmm(metrics, J_flat))
                    M_r_c += M_r_batch.sum(dim=0)  # (nv, nv)
                    # Subtract curvature term from desired acceleration
                    accels = accels #- c_flat  # (n_link*n_obs,1,1)
                    f_r_c += torch.bmm(J_T, torch.bmm(metrics, accels)).squeeze(-1).sum(dim=0)
               
        # === 4️⃣ Combine results ===
        # accel_c = [acc - c for acc, c in zip(all_accel, all_c)]
        # f_r_c= f_r_c.unsqueeze(0)
        # f_r_c=sum(f_r_c)
        accel_c = [acc  -c for acc, c in zip(all_accel, all_c)]
        M_r = sum(J.T @ M @ J for J, M in zip(all_J, all_metric))
        f_r = sum(J.T @ M @ acc_c for J, M, acc_c in zip(all_J, all_metric, accel_c))

        # Combine collision avoidance and task forces/metrics
        M_r_total = M_r# + M_r_c
        f_r_total = f_r# + f_r_c

        # Solve for joint-space acceleration in one step
        accel = torch.linalg.pinv(M_r_total) @ f_r_total
        accel_c = torch.linalg.pinv(M_r_c) @ f_r_c  # Damping term  (ignore singularity issues for now)
        return accel + accel_c


    def fabric_eval(self, pos: torch.Tensor, vel: torch.Tensor, task_name: str):
        fabric_handle = self.env.fabrics[task_name]
        fabric_type = self.env.task_spaces[task_name]
        metric, accel = fabric_handle(pos, vel)
        return metric, accel

    def fabric_eval_batch(self, pos_batch: torch.Tensor, vel_batch: torch.Tensor, task_names: list[str]):
        """
        批量计算多个任务的 metric, accel。
        pos_batch: (N, d)
        vel_batch: (N, d)
        """
        metrics, accels = [], []
        for i, task_name in enumerate(task_names):
            fabric_handle = self.env.fabrics[task_name]
            m, a = fabric_handle(pos_batch[i], vel_batch[i])
            metrics.append(m)
            accels.append(a)

        return torch.stack(metrics), torch.stack(accels)