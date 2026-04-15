from networks.pts_encoder.pointnet2 import Pointnet2ClsMSGFus
import torch
import torch.nn as nn
import sys
import os
import gc
import time
import torch.optim as optim
import numpy as np
import networks.flow.rng as rng

import torch.nn.functional as F

sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from tensorboardX import SummaryWriter
from utils.networks_utils import zero_module, get_ckpt_and_writer_path, GaussianFourierProjection

from utils_copy.transforms.rotation_conversions import matrix_to_quaternion
from utils_copy.metrics import get_metrics, get_rot_matrix
from utils_copy.visualize import create_grid_image
from utils.genpose_utils import TrainClock, get_pose_dim
from networks.flow.time_sampler import sample_two_timesteps
from networks.flow.ema import ExponentialMovingAverage
from utils_copy.misc import normalize_rotation

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
        self.dino : nn.Module = torch.hub.load('facebookre
        search/dinov2', MeanFlow.dino_name).to(args.device)
        self.dino.requires_grad_(False)
        # self.dino.eval()
        self.dino_dim = MeanFlow.dino_dim
        self.embedding_dim = MeanFlow.embedding_dim
        
        # point cloud encoder: 3 (xyz) + dino_dim (384) = 387 channels
        self.pts_encoder = Pointnet2ClsMSGFus(self.dino_dim)
        # state_dict = torch.load("../results/ckpts/pts_encoder_stripped.pth")
        # self.pts_encoder.load_state_dict(state_dict, strict=True)
        self.pts_encoder.requires_grad_(False)
        self.pts_encoder.eval()
    
        
        ###
        self.pose_act = nn.ReLU(True)
        pose_dim = get_pose_dim(self.args.pose_mode)

        # pose encoder
        self.pose_encoder = nn.Sequential(
            nn.Linear(pose_dim, 256),
            nn.ReLU(),
            nn.Linear(256, 256),
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
            nn.Linear(128+256+1024, 256),
            nn.ReLU(),
            zero_module(nn.Linear(256, 3)),
        )
        # yyyy
        self.fusion_tail_rot_y = nn.Sequential(
            nn.Linear(128+256+1024, 256),
            nn.ReLU(),
            zero_module(nn.Linear(256, 3)),
        )
            
        # translation regress head 
        self.fusion_tail_trans = nn.Sequential(
            nn.Linear(128+256+1024, 256),
            nn.ReLU(),
            zero_module(nn.Linear(256, 3)),
        )

        # ---- modules that participate in EMA (FlowNet part) ----
        # self.ema_modules = nn.ModuleList([
        #     self.pose_encoder,
        #     self.t_encoder,
        #     self.fusion_tail_rot_x,
        #     self.fusion_tail_rot_y,
        #     self.fusion_tail_trans,
        # ])

        self.to(args.device)
        self.optimizer = self.set_optimizer()
        self.scheduler = self.set_scheduler()
        self.ema = ExponentialMovingAverage(self.parameters(), 
                                            decay=0.999, 
                                            use_num_updates=True,
                                            period=1,  # periodic update
                                            use_double_precision=True # MeanFlow's numerical stability
                                            )  

    # def ema_parameters(self, modules):
    #         for m in modules:
    #             for p in m.parameters():
    #                 yield p

    def extract_pts_feature(self, data):
        pts = data['pts']  # [bs, N, 3]
        # pts = data['zero_mean_pts']

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
        torch.nn.utils.clip_grad_norm_(self.parameters(), max_norm=1.0)
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

        # # Concatenate all features [bs, 256+256+1024=1536]
        total_feat = torch.cat([time_feat, pose_feat, pts_feat], dim=-1)
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
        # x0 = torch.randn_like(gt_pose)
        # x0[:, 6:] *= 0.15   # translation noise smaller if you want
        # x0[:, :6] *= 0.25   # rotation noise smaller if you want

        # ------------------------------------------------
        # 2. sample t ~ U(0, 1)
        # ------------------------------------------------
        eps = 1e-3
        t_raw = torch.rand((B,)).to(device)  # 均匀分布的0-1采样
        t = eps + (1 - 2*eps) * t_raw  # 将采样结果映射到[eps, 1-eps]
        t_view = t.view(B, 1)


        # # option 2: reflected flow matching
        sigma_min = 0.1
        sigma_max = 2.0
        sigma = sigma_min * torch.exp(torch.log(torch.tensor(sigma_max / sigma_min, device=t.device)) * (1-t_view))
        # sigma = sigma_min * (sigma_max / sigma_min) ** t_view 

        z = torch.randn_like(gt_pose)
        #z[:,6:] *= 0.1 
        xt = gt_pose + z * sigma  # 添加与时间相关的噪声，得到xt
        target_score = -z * sigma / (sigma**2)
        
        
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
        )                    # [B, D]

        ##
        loss_weighting = sigma**2
        loss_r = 1.0 * loss_weighting * ((v_pred[:, :6]-target_score[:, :6])**2)
        loss_t = 1.0 * loss_weighting * ((v_pred[:, 6:]-target_score[:, 6:])**2)
        loss = (loss_r.sum(dim=1) + loss_t.sum(dim=1)).mean()
        ##
        if self.clock.step % 100 == 0:
            print(f"Step {self.clock.step}: rot: {loss_r.sum().item():.6f} trans: {loss_t.sum().item():.6f} mean: {loss.mean().item():.6f}")

        return loss


    @torch.no_grad()
    def sample(self, data, num_samples=1, device=None, init_pose=None):

        device = self.args.device if device is None else device
        num_steps = 20
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
            x = 0.00*torch.randn(bs, 9, device=device)
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
            x = x + 0.5*dt * (u1 + u2)

        # ------------------------------------------------
        # 5. post-process pose
        # ------------------------------------------------
        x[:, -3:] = 1.2*x[:, -3:]+data['pts_center']
        x[:, :-3] = normalize_rotation(x[:, :-3], 'rot_matrix')

        return x.detach()



    def pred_func(self, data, initial_data=None):
        # self.eval()
        
        # with torch.no_grad():
        data['pts_feat'] = self.extract_pts_feature(data)
        # print('pts_feat', data['pts_feat'].cpu())
        bs = data['pts'].shape[0]

        repeated_data = {}
        for key in data.keys():
            if data[key] is None:
                continue

            data_shape = [item for item in data[key].shape]
            repeat_list = np.ones(len(data_shape) + 1, dtype=np.int8).tolist()
            repeat_list[1] = self.args.repeat_num
            repeated_data[key] = data[key].unsqueeze(1).repeat(repeat_list)
            data_shape[0] = bs * self.args.repeat_num
            repeated_data[key] = repeated_data[key].view(data_shape)
        
        init_pose = None
        
        if initial_data is not None:
            if bs > initial_data.shape[0]:
                new_pose = torch.zeros((bs, initial_data.shape[1])).to(initial_data.device)
                new_pose[:initial_data.shape[0], :] = initial_data
                new_pose[initial_data.shape[0]:, :] = initial_data[-1,:]
                init_pose = new_pose
                initial_data = init_pose
        
            init_pose = initial_data.unsqueeze(1).repeat(1, self.args.repeat_num, 1)
            init_pose = init_pose.view(bs * self.args.repeat_num, -1)

        # Sample multiple predictions (repeat_num times)
        res = self.sample(repeated_data, num_samples=1, device=self.args.device, init_pose=init_pose)

        # Reshape to [bs, repeat_num, 9]
        pred_pose = res.reshape(bs, self.args.repeat_num, -1)

        # Convert rotation to quaternion
        rot_matrix = get_rot_matrix(res[:, :-3], self.args.pose_mode)
        quat_wxyz = matrix_to_quaternion(rot_matrix)
        res_q_wxyz = torch.cat((quat_wxyz, res[:, -3:]), dim=-1)
        pred_pose_q_wxyz = res_q_wxyz.reshape(bs, self.args.repeat_num, -1)  # [bs, repeat_num, 7]

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
        ##
        # self.ema.copy_to(self.ema_parameters(self.ema_modules))   
    

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
            # self.ema.store(self.parameters())     # 备份普通权重
            self.ema.copy_to(self.ema_parameters(self.ema_modules))  

    # called from trainer
    def encode_func(self, data):
        data['pts_feat'] = self.extract_pts_feature(data)

    def set_optimizer(self):
        if self.args.optimizer == 'Adam':
            return optim.Adam(self.parameters(), lr=self.args.lr, betas=(0.9, 0.999))
        # Add other optimizer types as needed
        
    def set_scheduler(self):
        return optim.lr_scheduler.ExponentialLR(self.optimizer, self.args.lr_decay)

    # eval function
    def eval_flow_func(self, data, data_mode):
        # self.is_testing = True
        self.eval()
        # self.ema.store(self.parameters())
        # self.ema.copy_to(self.parameters())
        
        with torch.no_grad():
            # Extract features once
            data['pts_feat'] = self.extract_pts_feature(data)

            # Sample predictions
            pred_pose = self.sample(data)
            
            # Get metrics
            metric = self.collect_pose_metric(pred_pose, data['gt_pose'], data['sym_info'])
            self.record_metrics(metric, 'meanflow', data_mode)
            
            # Visualize
            if hasattr(self, 'writer'):
                pts = torch.cat((data['pts'], data['pts_color']), dim=2)
                grid_image, _ = create_grid_image(pts, pred_pose, data['gt_pose'], 
                                                data.get('color'), self.args.pose_mode)
                self.writer.add_image(f'{data_mode}/vis_meanflow', grid_image, self.clock.epoch)
        
        # self.ema.restore(self.parameters())
        return [metric], ['meanflow']
    
    def update_learning_rate(self):
        self.base_lr = self.args.lr
        if self.clock.step <= self.args.warmup:
            self.optimizer.param_groups[-1]['lr'] = self.base_lr / self.args.warmup * self.clock.step
        elif not self.optimizer.param_groups[-1]['lr'] < 1e-4:
            self.scheduler.step()

    def collect_pose_metric(self, pred_pose, gt_pose, sym_info):
        rot_error, trans_error = get_metrics(
            pred_pose.type_as(gt_pose),
            gt_pose,
            sym_info,
            pose_mode = self.args.pose_mode,
        )
        rot_error = {
            'mean': np.mean(rot_error),
            'median': np.median(rot_error),
            'item': rot_error,
        }
        trans_error = {
            'mean': np.mean(trans_error),
            'median': np.median(trans_error),
            'item': trans_error,
        }
        return {'rot_error': rot_error,
                'trans_error': trans_error}
    
    def record_metrics(self, metric, sampler_mode, mode='val'):
        """record metric to tensorboard"""
        if 'rot_error' in metric:
            rot_error = metric['rot_error']
            for k, v in rot_error.items():
                if not k == 'item':
                    self.writer.add_scalar(f'{mode}/{sampler_mode}_{k}_rot_error', v, self.clock.epoch)
        
        if 'trans_error' in metric:
            trans_error = metric['trans_error']
            for k, v in trans_error.items():
                if not k == 'item':
                    self.writer.add_scalar(f'{mode}/{sampler_mode}_{k}_trans_error', v, self.clock.epoch)
        
        if 'length_error' in metric:
            length_error = metric['length_error']
            for k, v in length_error.items():
                if not k == 'item':
                    self.writer.add_scalar(f'{mode}/{sampler_mode}_{k}_length_error', v, self.clock.step)
 
    def record_lr(self):
        self.writer.add_scalar('learning_rate', self.optimizer.param_groups[0]['lr'], self.clock.step)

    def visualize_batch(self, data, res, sampler_mode, mode):
        """write visualization results to tensorboard writer"""
        for res_item, sampler_item in zip(res, sampler_mode):
            pts = torch.cat((data['pts'], data['pts_color']), dim=2)
            if 'color' in data.keys():
                grid_image, _ = create_grid_image(pts, res_item, data['gt_pose'], data['color'], self.args.pose_mode)
            else:
                grid_image, _ = create_grid_image(pts, res_item, data['gt_pose'], None, self.args.pose_mode)
            self.writer.add_image(f'{mode}/vis_{sampler_item}', grid_image, self.clock.epoch)

