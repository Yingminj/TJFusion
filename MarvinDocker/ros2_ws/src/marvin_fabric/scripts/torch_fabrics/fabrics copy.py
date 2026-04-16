import torch
from functorch import jacfwd, jvp
import pinocchio as pin
from torch_fabrics.envs.robot_env_marvin import RobotEnv
import numpy as np
class FabricHandler:
    def __init__(self, env: RobotEnv):
        self.env = env
    
    def fabric_solve(self, pos: torch.Tensor, vel: torch.Tensor):
        """
        General fabric solver supporting both Cartesian and joint-space tasks.
        """
        pos = pos.detach().clone()
        pos.requires_grad_()
        vel = vel.detach().clone()
        vel.requires_grad_()
        link_p,link_v, link_a,link_j = self.env.get_fk()
        all_metric, all_accel, all_c, all_J = [], [], [], []

        
        for task_name in self.env.task_names:
            task_map = self.env.task_maps[task_name]
            task_space = self.env.task_spaces.get(task_name, "cartesian")
            
            if task_space == "joint":
                # -------- Joint-space task --------
                x = task_map(pos)  # same as configuration
                J = jacfwd(task_map)(pos)
                v = vel
                c = torch.zeros_like(vel)
                metric, accel = self.fabric_eval(x, v, task_name)
            elif task_space == "cartesian":
                # -------- Cartesian-space task --------
                frame_id = self.env.model.getFrameId(self.env.task_frames[task_name])

                # x = task_map(pos.detach().cpu().numpy())
                x = torch.tensor(link_p[frame_id].translation, dtype=torch.float32).requires_grad_()
                f = task_map(x)
                # J = link_j[frame_id][:3, :]

                # v = link_v[frame_id][:3]

                c = link_a[frame_id][:3]

                # J_x = torch.autograd.functional.jacobian(task_map, x)[:3, :3]
                J_x = jacfwd(task_map)(f)
                vx = torch.tensor(link_v[frame_id][:3], dtype=torch.float32)
                J_q = link_j[frame_id][:3, :]
                J = J_x @ J_q
                v = J_x @ vx


                # Evaluate fabric metric & acceleration
                metric, accel = self.fabric_eval(f, v, task_name)
            # elif task_space == "orientation1":
            #                     # -------- Cartesian-space task --------
            #     frame_id = self.env.model.getFrameId(self.env.task_frames[task_name])

            #     p1 = link_p[frame_id].translation + link_p[frame_id].rotation @ np.array([0.0*self.env.tcp_length, 0.0, self.env.tcp_length])

            #     # x = torch.tensor(link_p[frame_id].translation, dtype=torch.float32).requires_grad_()
            #     # x = torch.tensor(link_p[frame_id], dtype=torch.float32).requires_grad_()
            #     x= torch.tensor(p1, dtype=torch.float32).requires_grad_()
            #     f = task_map(x)
            #     # J = link_j[frame_id][:3, :]

            #     # v = link_v[frame_id][:3]

            #     c = link_a[frame_id][3:]

            #     J_x = torch.autograd.functional.jacobian(task_map, x)

            #     vx = torch.tensor(link_v[frame_id][:3], dtype=torch.float32)
                
            #     # J_x = jacfwd(task_map)(f)
            #     J_q = link_j[frame_id][:3, :]
            #     J = J_x @ J_q
            #     # v = torch.matmul(J_blocks, vx_m)
            #     v = J_x @ vx



            #     # Evaluate fabric metric & acceleration
            #     metric, accel = self.fabric_eval(f, v, task_name)
            # elif task_space == "orientation2":
            #                     # -------- Cartesian-space task --------
            #     frame_id = self.env.model.getFrameId(self.env.task_frames[task_name])

            #     p2 = link_p[frame_id].translation + link_p[frame_id].rotation @ np.array([-0.0*self.env.tcp_length, 0.0, self.env.tcp_length])
            #     # x = torch.tensor(link_p[frame_id].translation, dtype=torch.float32).requires_grad_()
            #     # x = torch.tensor(link_p[frame_id], dtype=torch.float32).requires_grad_()
            #     x= torch.tensor(p2, dtype=torch.float32).requires_grad_()
            #     f = task_map(x)
            #     # J = link_j[frame_id][:3, :]

            #     # v = link_v[frame_id][:3]

            #     c = link_a[frame_id][3:]

            #     J_x = torch.autograd.functional.jacobian(task_map, x)

            #     vx = torch.tensor(link_v[frame_id][:3], dtype=torch.float32)
                
            #     # J_x = jacfwd(task_map)(f)
            #     J_q = link_j[frame_id][:3, :]
            #     J = J_x @ J_q
            #     # v = torch.matmul(J_blocks, vx_m)
            #     v = J_x @ vx



            #     # Evaluate fabric metric & acceleration
            #     metric, accel = self.fabric_eval(f, v, task_name)
            metric = metric.to(dtype=torch.float32)
            accel = accel.to(dtype=torch.float32)

            all_J.append(J)
            all_metric.append(metric)
            all_accel.append(accel)
            all_c.append(c)

        # Combine all task contributions
        accel_c = [acc - c for acc, c in zip(all_accel, all_c)]

        M_r = sum([J.T @ M @ J for J, M in zip(all_J, all_metric)])
        f_r = sum([J.T @ M @ acc_c for J, M, acc_c in zip(all_J, all_metric, accel_c)])
        M_r_test = [J.T @ M @ J for J, M in zip(all_J, all_metric)]
        f_r_test = [J.T @ M @ acc_c for J, M, acc_c in zip(all_J, all_metric, accel_c)]
        # Solve for joint-space acceleration
        accel = torch.linalg.pinv(M_r) @ f_r
        # accel = torch.zeros_like(vel)
        # accel_test = torch.linalg.pinv(M_r_test) @ f_r_test
        return accel

    def fabric_eval(self, pos: torch.Tensor, vel: torch.Tensor, task_name: str):
        fabric_handle = self.env.fabrics[task_name]
        fabric_type = self.env.task_spaces[task_name]
        metric, accel = fabric_handle(pos, vel)
        return metric, accel

