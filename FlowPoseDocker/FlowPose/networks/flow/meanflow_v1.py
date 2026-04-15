from networks.pts_encoder.pointnet2 import Pointnet2ClsMSGFus
import torch
import torch.nn as nn
import sys
import os
import gc
import torch.optim as optim
import numpy as np
import networks.flow.rng as rng

sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from tensorboardX import SummaryWriter
from utils.networks_utils import zero_module, get_ckpt_and_writer_path, GaussianFourierProjection
from utils.transforms.rotation import matrix_to_quaternion, get_rot_matrix, normalize_rotation
from utils.misc import get_pose_dim
from utils.clock import TrainClock
from networks.flow.time_sampler import sample_two_timesteps
from networks.flow.ema import ExponentialMovingAverage

# also add dino
# shit mountain starts from here
class MeanFlow(nn.Module):
    dino_name = 'dinov2_vits14'
    dino_dim = 384
    embedding_dim = 60

    def __init__(self, arch, args, net_configs):
        super(MeanFlow, self).__init__()
        self.args = args
        self.clock = TrainClock()

        # get checkpoint and writer path
        self.model_dir, writer_path = get_ckpt_and_writer_path(self.args)

        if self.args.is_train:
            self.writer = SummaryWriter(writer_path)  

        # dino
        self.dino : nn.Module = torch.hub.load('facebookresearch/dinov2', MeanFlow.dino_name).to(args.device)
        self.dino.requires_grad_(False)
        self.dino.eval()
        self.dino_dim = MeanFlow.dino_dim
        self.embedding_dim = MeanFlow.embedding_dim
        # for name, param in self.dino.named_parameters():
        #     print(name, param.shape)
        # quit()
        
        # point cloud encoder: 3 (xyz) + dino_dim (384) = 387 channels
        self.pts_encoder = Pointnet2ClsMSGFus(self.dino_dim)
        state_dict = torch.load("results/ckpts/pts_encoder_stripped.pth")
        self.pts_encoder.load_state_dict(state_dict, strict=True)
        self.pts_encoder.requires_grad_(False)
        self.pts_encoder.eval()
        
        ###
        self.pose_act = nn.ReLU(True)
        pose_dim = get_pose_dim(self.args.pose_mode)

        # self.pts_mlp = nn.Linear(1024, 256)

        # self.feat_map = nn.Linear(128+256+1024, 256)

        # pose encoder
        self.pose_encoder = nn.Sequential(
            nn.Linear(pose_dim, 256),
            nn.ReLU(),
            nn.Linear(256, 128),
            nn.ReLU(),
        )
        
        # time encoder
        self.t_encoder = nn.Sequential(
            GaussianFourierProjection(embed_dim=128),
            # self.act, # M4D26 update
            nn.Linear(128, 128),
            nn.ReLU(),
        )

        # fusion tail - rotation x and y regress head 
        # xxxx
        self.fusion_tail_rot_x = nn.Sequential(
            nn.Linear(128+128+1024, 256),
            # zero_module(nn.Linear(128+256+1024, 256)),
            # nn.ReLU(True),
            # zero_module(nn.Linear(256, 3)),
            nn.Linear(256, 3),
            nn.Tanh(),
        )
        # yyyy
        self.fusion_tail_rot_y = nn.Sequential(
            nn.Linear(128+128+1024, 256),
            # zero_module(nn.Linear(128+256+1024, 256)),
            # nn.ReLU(True),
            # zero_module(nn.Linear(256, 3)),
            nn.Linear(256, 3),
            nn.Tanh(),
        )
            
        # translation regress head 
        self.fusion_tail_trans = nn.Sequential(
            nn.Linear(128+128+1024, 256),
            # zero_module(nn.Linear(128+256+1024, 256)),
            # nn.ReLU(True),
            # zero_module(nn.Linear(256, 3)),
            nn.Linear(256, 3),
            nn.Tanh(),
        )


        self.to(args.device)
        self.optimizer = self.set_optimizer()
        self.scheduler = self.set_scheduler()
        self.ema = ExponentialMovingAverage(self.parameters(), 
                                            decay=0.999, 
                                            use_num_updates=True,
                                            period=1,  # periodic update
                                            use_double_precision=True # MeanFlow's numerical stability
                                            )  

    def extract_pts_feature(self, data):
        pts = data['pts']  # [bs, N, 3]

        roi_rgb = data['roi_rgb']
        # Only freeze DINO gradients
        with torch.no_grad():
            feat = self.dino.get_intermediate_layers(roi_rgb)[0]
            xs = data['roi_xs'] // 14
            ys = data['roi_ys'] // 14
            pos = xs * 16 + ys
            pos = torch.unsqueeze(pos, -1).expand(-1, -1, self.dino_dim)
            rgb_feat = torch.gather(feat, 1, pos)

            # freeze dino weights
            rgb_feat.requires_grad_(False)
            data['dino_feat'] = feat.mean(dim=1, keepdim=True).squeeze(1)  # [bs, dino_dim]

        
        if not self.training:
            with torch.no_grad():
                pts_feat = self.pts_encoder(torch.concatenate([pts, rgb_feat], dim=-1))  # [bs, 1024]
        else:
            pts_feat = self.pts_encoder(torch.concatenate([pts, rgb_feat], dim=-1))  # [bs, 1024]

        return pts_feat  # Keep gradients attached

    
    def train_flow_one_step(self, data, compiled_train_step=None, teacher=None):
        gc.collect()
        self.optimizer.zero_grad()

        loss = rng.train_step_with_rng_control(compiled_train_step, self, self.clock.step, self.args.seed, data=data)
        # loss = compiled_train_step(self, data)
        # torch.nn.utils.clip_grad_norm_(self.parameters(), max_norm=1.0)
        self.optimizer.step()
        self.ema.update(self.parameters())
        return loss
    

    def forward(self, data, time_cond, aug_cond=None):
        
        # TIME feat
        t, r = time_cond
        time_feat = self.t_encoder(t.view(-1, 1))  # [bs, 128]


        # PRE-EXTRACTED feat
        pts_feat = data['pts_feat']  # [bs, 1024]
        sampled_pose = data['sampled_pose']  # [bs, pose_dim]
        pose_feat = self.pose_encoder(sampled_pose)  # [bs, 256]
        # rgb_feat = data['dino_feat']  # [bs, dino_dim]
        # pts_feat = self.pts_mlp(pts_feat)  # [bs, 256]

        # # Concatenate all features [bs, 256+256+1024=1536]
        total_feat = torch.cat([time_feat, pose_feat, pts_feat], dim=-1)
        # total_feat = self.feat_map(total_feat)  # [bs, 256]
        rot_x = self.fusion_tail_rot_x(total_feat)   # 通过X轴旋转回归头输出X轴旋转向量 [bs, 3]
        rot_y = self.fusion_tail_rot_y(total_feat)   # 通过Y轴旋转回归头输出Y轴旋转向量 [bs, 3]
        trans = self.fusion_tail_trans(total_feat)   # [bs, 3]

        return torch.cat([rot_x, rot_y, trans], dim=-1)  # [bs, 9]

    def forward_with_loss(self, data, aug_cond=None):
        """
        Standard Flow Matching training (no JVP, no ODE)
        """


        gt_pose = data['zero_mean_gt_pose']        # x1  [B, D]
        pts_feat = data['pts_feat']
        dino_feat = data['dino_feat']
        device = gt_pose.device
        B = gt_pose.shape[0]

        # ------------------------------------------------
        # 1. sample x0 ~ p0 (noise)
        # ------------------------------------------------
        x0 = torch.randn_like(gt_pose)
        x0[:, 6:] *= 0.15   # translation noise smaller if you want

        # ------------------------------------------------
        # 2. sample t ~ U(0, 1)
        # ------------------------------------------------
        eps = 1e-3
        t = eps + (1 - 2 * eps) * torch.rand(B, device=device)
        # 保留三位小数
        t = torch.round(t * 1000) / 1000
        t_view = t.view(B, 1)

        # ------------------------------------------------
        # 3. linear interpolation path: x_t
        # ------------------------------------------------
        xt = (1.0 - t_view) * x0 + t_view * gt_pose

        # ------------------------------------------------
        # 4. ground-truth velocity
        # ------------------------------------------------
        v_gt = gt_pose - x0                          # constant velocity

        # ------------------------------------------------
        # 5. predict velocity field
        # ------------------------------------------------
        temp_data = {
            'sampled_pose': xt,
            'pts_feat': pts_feat,
            'dino_feat': dino_feat,
        }

        v_pred = self.forward(
            temp_data,
            (t,t),
            aug_cond
        )                                           # [B, D]

        # ------------------------------------------------
        # 6. Flow Matching loss
        # ------------------------------------------------
        loss_r = 1*nn.SmoothL1Loss(reduction='none', beta=0.1)(v_pred[:,:6], v_gt[:,:6])
        loss_t = 5*nn.SmoothL1Loss(reduction='none', beta=0.1)(v_pred[:,6:], v_gt[:,6:])
        loss = (loss_r.sum(dim=1) + loss_t.sum(dim=1)).mean()
        # loss = torch.mean((v_pred - v_gt) ** 2)

        if self.clock.step % 100 == 0:
            print(f"Step {self.clock.step}: rot: {loss_r.sum().item():.6f} trans: {loss_t.sum().item():.6f} mean: {loss.mean().item():.6f}")

        return loss

    @torch.no_grad()
    def sample(self, data, num_samples=1, device=None, init_pose=None):

        device = self.args.device if device is None else device
        num_steps=20
        # ------------------------------------------------
        # 1. extract point features
        # ------------------------------------------------
        if 'pts_feat' not in data:
            data['pts_feat'] = self.extract_pts_feature(data)

        pts_feat = data['pts_feat']
        bs = pts_feat.shape[0]

        # ------------------------------------------------
        # 2. initial noise x0
        # ------------------------------------------------
        if init_pose is None:
            x = 0.0*torch.randn(bs, 9, device=device)
            # x[:, 6:] *= 0.15
        else:
            x = init_pose.clone()

        # ------------------------------------------------
        # 3. time discretization: t ∈ [0, 1]
        # ------------------------------------------------
        eps = 1e-3
        t_seq = torch.linspace(eps, 1.0, num_steps + 1, device=device)

        # ------------------------------------------------
        # 4. Heun (RK2) integration
        # ------------------------------------------------
        for i in range(num_steps):
            t = t_seq[i]
            t_next = t_seq[i + 1]
            dt = t_next - t

            # ---- k1 ----
            data['sampled_pose'] = x
            u1 = self.forward(
                data,
                (t.expand(bs), t.expand(bs)),
                aug_cond=None
            )

            # ---- predictor ----
            x_pred = x + dt * u1

            # ---- k2 ----
            data['sampled_pose'] = x_pred
            u2 = self.forward(
                data,
                (t_next.expand(bs), t_next.expand(bs)),
                aug_cond=None
            )

            # ---- corrector ----
            x = x +  0.5*dt * (u1 + u2)

        # ------------------------------------------------
        # 5. post-process pose
        # ------------------------------------------------
        x[:, -3:] = 1.2*x[:, -3:]+data['pts_center']
        x[:, :-3] = normalize_rotation(x[:, :-3], 'rot_matrix')

        return x.detach()

    def pred_func(self, data, device=None, init_pose=None, valid_prev_label=None):

        device = self.args.device if device is None else device

        # ------------------------------------------------
        # 1. extract point features
        # ------------------------------------------------
        if 'pts_feat' not in data:
            data['pts_feat'] = self.extract_pts_feature(data)

        pts_feat = data['pts_feat']
        dino_feat = data['dino_feat']
        bs = pts_feat.shape[0]

        # ------------------------------------------------
        # 2. Handle previous pose logic
        # ------------------------------------------------
        if valid_prev_label and init_pose is not None:
            # compute indices of items that have previous poses
            prev_indices = [i for i, lbl in enumerate(data.get('labels', [])) if lbl in init_pose]
            non_prev_indices = [i for i in range(bs) if i not in prev_indices]

            # build repeated_data for entire batch
            repeated_data = {}
            for key, val in data.items():
                if val is None:
                    continue
                if not isinstance(val, torch.Tensor):
                    repeated_data[key] = val
                    continue
                repeated_data[key] = val.repeat_interleave(self.args.repeat_num, dim=0)

            # prepare init_x tensors for previous items
            if len(prev_indices) > 0:
                init_x_tensors = torch.stack([init_pose[data['labels'][i]] for i in prev_indices], dim=0)
                repeated_init_x = init_x_tensors.repeat_interleave(self.args.repeat_num, dim=0)
            else:
                repeated_init_x = None

            # helper to build repeated index ranges
            def ranges_for_indices(indices):
                if len(indices) == 0:
                    return torch.empty((0,), device=device, dtype=torch.long)
                ranges = [torch.arange(i * self.args.repeat_num, (i + 1) * self.args.repeat_num, device=device) for i in indices]
                return torch.cat(ranges, dim=0)

            prev_repeat_idxs = ranges_for_indices(prev_indices)
            wo_repeat_idxs = ranges_for_indices(non_prev_indices)

            # run inference separately for prev and non-prev groups
            res_prev = None
            res_wo_prev = None
            if prev_repeat_idxs.numel() > 0:
                sub_prev = {k: (v.index_select(0, prev_repeat_idxs) if isinstance(v, torch.Tensor) else v) for k, v in repeated_data.items()}
                res_prev = self.sample(sub_prev, num_samples=1, device=device, init_pose=repeated_init_x)
            if wo_repeat_idxs.numel() > 0:
                sub_wo = {k: (v.index_select(0, wo_repeat_idxs) if isinstance(v, torch.Tensor) else v) for k, v in repeated_data.items()}
                res_wo_prev = self.sample(sub_wo, num_samples=1, device=device, init_pose=None)

            # reconstruct results into original repeated ordering
            pose_dim = (res_prev.shape[-1] if res_prev is not None else res_wo_prev.shape[-1])
            res = torch.empty((bs * self.args.repeat_num, pose_dim), device=device, dtype=(res_prev.dtype if res_prev is not None else res_wo_prev.dtype))

            # Fill blocks
            if res_prev is not None:
                for j, orig_i in enumerate(prev_indices):
                    src_start = j * self.args.repeat_num
                    src_end = (j + 1) * self.args.repeat_num
                    dst_start = orig_i * self.args.repeat_num
                    dst_end = (orig_i + 1) * self.args.repeat_num
                    res[dst_start:dst_end] = res_prev[src_start:src_end]
            if res_wo_prev is not None:
                for j, orig_i in enumerate(non_prev_indices):
                    src_start = j * self.args.repeat_num
                    src_end = (j + 1) * self.args.repeat_num
                    dst_start = orig_i * self.args.repeat_num
                    dst_end = (orig_i + 1) * self.args.repeat_num
                    res[dst_start:dst_end] = res_wo_prev[src_start:src_end]

        else:
            # ------------------------------------------------
            # 3. No previous pose - standard path
            # ------------------------------------------------
            repeated_data = {}
            for key, val in data.items():
                if val is None:
                    continue
                if not isinstance(val, torch.Tensor):
                    repeated_data[key] = val
                    continue
                repeated_data[key] = val.repeat_interleave(self.args.repeat_num, dim=0)

            res = self.sample(repeated_data, num_samples=1, device=device, init_pose=None)

        # ------------------------------------------------
        # 4. Reshape and convert to quaternion
        # ------------------------------------------------
        pred_pose = res.reshape(bs, self.args.repeat_num, -1)

        rot_matrix = get_rot_matrix(res[:, :-3], self.args.pose_mode)
        quat_wxyz = matrix_to_quaternion(rot_matrix)
        res_q_wxyz = torch.cat((quat_wxyz, res[:, -3:]), dim=-1)
        pred_pose_q_wxyz = res_q_wxyz.reshape(bs, self.args.repeat_num, -1)
        
        return pred_pose, pred_pose_q_wxyz

    def save_ckpt(self, name=None):
        if name is None:
            save_path = os.path.join(
                self.model_dir,
                f"ckpt_epoch{self.clock.epoch}.pth"
            )
            print(f"Saving checkpoint epoch {self.clock.epoch}...")
        else:
            save_path = os.path.join(self.model_dir, f"{name}.pth")

        ckpt = {
            "clock": self.clock.make_checkpoint(),
            "model_state_dict": self.state_dict(),          # 原模型
            "ema_state_dict": self.ema.state_dict(),        # ✅ EMA
            "optimizer_state_dict": self.optimizer.state_dict(),
            "scheduler_state_dict": self.scheduler.state_dict(),
        }

        torch.save(ckpt, save_path)
    

    def load_ckpt(self, model_dir, load_model_only=False):
        if not os.path.exists(model_dir):
            raise ValueError("Checkpoint {} not exists.".format(model_dir))
        
        ckpt = torch.load(model_dir)
        print("Loading checkpoint from {} ...".format(model_dir))

        # Load model state
        self.load_state_dict(ckpt['model_state_dict'])

        # if not load_model_only:
        #     self.optimizer.load_state_dict(ckpt['optimizer_state_dict'])
        #     self.scheduler.load_state_dict(ckpt['scheduler_state_dict'])
        #     self.clock.restore_checkpoint(ckpt['clock'])
            
        # Restore EMA state if available
        if 'ema_state_dict' in ckpt:
            self.ema.load_state_dict(ckpt['ema_state_dict'])
            self.ema.store(self.parameters())     # 备份普通权重
            self.ema.copy_to(self.parameters())   # 切到 EMA 权重

    # called from trainer
    def encode_func(self, data):
        data['pts_feat'] = self.extract_pts_feature(data)

    def set_optimizer(self):
        if self.args.optimizer == 'Adam':
            return optim.Adam(self.parameters(), lr=self.args.lr, betas=(0.9, 0.999))
        # Add other optimizer types as needed
        
    def set_scheduler(self):
        return optim.lr_scheduler.ExponentialLR(self.optimizer, self.args.lr_decay)
    
    def update_learning_rate(self):
        self.base_lr = self.args.lr
        if self.clock.step <= self.args.warmup:
            self.optimizer.param_groups[-1]['lr'] = self.base_lr / self.args.warmup * self.clock.step
        elif not self.optimizer.param_groups[-1]['lr'] < 1e-4:
            self.scheduler.step()
 
    def record_lr(self):
        self.writer.add_scalar('learning_rate', self.optimizer.param_groups[0]['lr'], self.clock.step)

