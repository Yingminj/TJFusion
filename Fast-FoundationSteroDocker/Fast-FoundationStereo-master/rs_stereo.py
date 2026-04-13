# Copyright (c) 2025, NVIDIA CORPORATION.  All rights reserved.
#
# NVIDIA CORPORATION and its licensors retain all intellectual property
# and proprietary rights in and to this software, related documentation
# and any modifications thereto.  Any use, reproduction, disclosure or
# distribution of this software and related documentation without an express
# license agreement from NVIDIA CORPORATION is strictly prohibited.

import time
import os, sys
import argparse
import torch
import logging
os.environ["OPENCV_IO_ENABLE_OPENEXR"] = "1"
import cv2
import numpy as np
import pyrealsense2 as rs
code_dir = os.path.dirname(os.path.realpath(__file__))
sys.path.append(f'{code_dir}/../')
from omegaconf import OmegaConf
from core.utils.utils import InputPadder
from Utils import set_logging_format, set_seed, vis_disparity


if __name__ == "__main__":
    code_dir = os.path.dirname(os.path.realpath(__file__))
    parser = argparse.ArgumentParser()
    parser.add_argument('--ckpt_dir', default='weights/20-30-48/model_best_bp2_serialize.pth', type=str, help='pretrained model path')
    parser.add_argument('--out_dir', default=f'{code_dir}/../output/', type=str, help='directory to save results')
    parser.add_argument('--width', default=640, type=int, help='IR stream width')
    parser.add_argument('--height', default=480, type=int, help='IR stream height')
    parser.add_argument('--fps', default=30, type=int, help='IR stream FPS')
    parser.add_argument('--scale', default=1.0, type=float, help='downsize the image by scale, must be <=1')
    parser.add_argument('--z_far', default=10.0, type=float, help='max depth to clip in visualization')
    parser.add_argument('--valid_iters', type=int, default=8, help='number of flow-field updates during forward pass')
    parser.add_argument('--remove_invisible', default=1, type=int, help='remove non-overlapping pixels from disparity')
    args = parser.parse_args()

    assert args.scale <= 1, "scale must be <=1"

    set_logging_format()
    set_seed(0)
    torch.autograd.set_grad_enabled(False)
    os.makedirs(args.out_dir, exist_ok=True)

    # ── Load model ─────────────────────────────────────────────────────────────
    ckpt_dir = args.ckpt_dir
    cfg = OmegaConf.load(f'{os.path.dirname(ckpt_dir)}/cfg.yaml')
    if 'vit_size' not in cfg:
        cfg['vit_size'] = 'vitl'
    for k in args.__dict__:
        cfg[k] = args.__dict__[k]
    args = OmegaConf.create(cfg)
    logging.info(f"args:\n{args}")
    logging.info(f"Using pretrained model from {ckpt_dir}")

    model = torch.load(ckpt_dir, map_location='cpu', weights_only=False)
    model.args.valid_iters = args.valid_iters
    model.args.max_disp = args.max_disp
    model.cuda()
    model.eval()

    # ── RealSense pipeline ──────────────────────────────────────────────────────
    resize = (args.width, args.height)
    pipeline = rs.pipeline()
    config = rs.config()
    config.enable_stream(rs.stream.infrared, 1, resize[0], resize[1], rs.format.y8, args.fps)  # Left IR
    config.enable_stream(rs.stream.infrared, 2, resize[0], resize[1], rs.format.y8, args.fps)  # Right IR
    config.enable_stream(rs.stream.color, resize[0], resize[1], rs.format.bgr8, args.fps)       # Color
    profile = pipeline.start(config)

    # Remove align
    # align = rs.align(rs.stream.infrared)


    # Disable IR emitter to get clean passive IR images (optional – comment out to keep emitter on)
    depth_sensor = profile.get_device().first_depth_sensor()
    if depth_sensor.supports(rs.option.emitter_enabled):
        depth_sensor.set_option(rs.option.emitter_enabled, 0)

    # Read intrinsics and baseline directly from the camera
    left_stream = profile.get_stream(rs.stream.infrared, 1).as_video_stream_profile()
    right_stream = profile.get_stream(rs.stream.infrared, 2).as_video_stream_profile()
    color_stream = profile.get_stream(rs.stream.color).as_video_stream_profile()
    
    left_intr = left_stream.get_intrinsics()
    color_intr = color_stream.get_intrinsics()
    extr = left_stream.get_extrinsics_to(right_stream)
    ir_to_color_extr = left_stream.get_extrinsics_to(color_stream)
    
    baseline = abs(extr.translation[0])  # metres
    print(baseline)

    R_ext = np.array(ir_to_color_extr.rotation).reshape(3, 3).T  # column-major → transpose to get R
    T_ext = np.array(ir_to_color_extr.translation)

    K = np.array([
        [left_intr.fx, 0,            left_intr.ppx],
        [0,            left_intr.fy, left_intr.ppy],
        [0,            0,            1             ],
    ], dtype=np.float32)
    K[:2] *= args.scale
    logging.info(f"K:\n{K}\nbaseline: {baseline:.4f} m")

    scale = args.scale

    global_state = {"depth": None}

    def on_mouse_click(event, x, y, flags, param):
        if event == cv2.EVENT_LBUTTONDOWN:
            depth = global_state["depth"]
            if depth is not None:
                H, W = depth.shape
                if x < W:
                    part = "Left IR"
                    lx = x
                elif x < 2 * W:
                    part = "Overlay"
                    lx = x - W
                else:
                    part = "Color"
                    lx = x - 2 * W
                
                if y < H and lx < W:
                    val = depth[y, lx]
                    print(f"[{part}] Clicked at ({lx}, {y}), Depth: {val:.3f} m")

    cv2.namedWindow("Left IR | RGB+Depth Overlay | Color")
    cv2.setMouseCallback("Left IR | RGB+Depth Overlay | Color", on_mouse_click)

    try:
        while True:
            frames = pipeline.wait_for_frames()
            left_frame_rs = frames.get_infrared_frame(1)
            right_frame_rs = frames.get_infrared_frame(2)
            color_frame_rs = frames.get_color_frame()
            if not left_frame_rs or not right_frame_rs or not color_frame_rs:
                continue
            color_img = np.asanyarray(color_frame_rs.get_data())  # raw BGR

            # Convert to numpy (grayscale uint8)
            img0_gray = np.asanyarray(left_frame_rs.get_data())
            img1_gray = np.asanyarray(right_frame_rs.get_data())

            # Convert grayscale → BGR so the model receives a 3-channel tensor
            img0 = cv2.cvtColor(img0_gray, cv2.COLOR_GRAY2BGR)
            img1 = cv2.cvtColor(img1_gray, cv2.COLOR_GRAY2BGR)

            if scale != 1.0:
                img0 = cv2.resize(img0, dsize=None, fx=scale, fy=scale)
                img1 = cv2.resize(img1, dsize=None, fx=scale, fy=scale)

            H, W = img0.shape[:2]
            img0_ori = img0.copy()

            img0_t = torch.as_tensor(img0).cuda().float()[None].permute(0, 3, 1, 2)
            img1_t = torch.as_tensor(img1).cuda().float()[None].permute(0, 3, 1, 2)
            padder = InputPadder(img0_t.shape, divis_by=32, force_square=False)
            img0_t, img1_t = padder.pad(img0_t, img1_t)

            t0 = time.time()
            with torch.cuda.amp.autocast(True):
                disp = model.forward(img0_t, img1_t, iters=args.valid_iters, test_mode=True)
            t1 = time.time()
            # print(f"Inference time: {t1 - t0:.3f} s")

            disp = padder.unpad(disp.float())
            disp = disp.data.cpu().numpy().reshape(H, W)

            if args.remove_invisible:
                yy, xx = np.meshgrid(np.arange(H), np.arange(W), indexing='ij')
                us_right = xx - disp
                disp[us_right < 0] = np.inf

            depth = K[0, 0] * baseline / disp
            
            # Align depth to Color
            Z = depth
            valid = (Z > 0) & np.isfinite(Z)
            y_ir, x_ir = np.nonzero(valid)
            z_ir = Z[valid]
            
            X_ir = (x_ir - K[0, 2]) * z_ir / K[0, 0]
            Y_ir = (y_ir - K[1, 2]) * z_ir / K[1, 1]
            P_ir = np.stack((X_ir, Y_ir, z_ir), axis=0) # 3 x N
            
            P_color = R_ext @ P_ir + T_ext[:, None] # 3 x N
            X_c, Y_c, Z_c = P_color[0], P_color[1], P_color[2]
            
            x_c = (X_c / Z_c) * color_intr.fx + color_intr.ppx
            y_c = (Y_c / Z_c) * color_intr.fy + color_intr.ppy
            
            x_c = np.round(x_c).astype(int)
            y_c = np.round(y_c).astype(int)
            
            mask = (x_c >= 0) & (x_c < color_intr.width) & (y_c >= 0) & (y_c < color_intr.height) & (Z_c > 0)
            x_c, y_c, Z_c = x_c[mask], y_c[mask], Z_c[mask]
            
            depth_aligned = np.zeros((color_intr.height, color_intr.width), dtype=np.float32)
            order = np.argsort(Z_c)[::-1]
            depth_aligned[y_c[order], x_c[order]] = Z_c[order]
            depth = depth_aligned
            
            # Use raw color image instead of aligned
            global_state["depth"] = depth

            # Update H, W for visualization to match the aligned depth
            H, W = depth.shape

            # ── Depth colormap visualization ────────────────────────────────────
            depth_vis = depth.copy()
            depth_vis[~np.isfinite(depth_vis)] = 0
            depth_vis = np.clip(depth_vis, 0, args.z_far)

            valid = depth_vis > 0
            if np.any(valid):
                dmin = float(depth_vis[valid].min())
                dmax = float(depth_vis[valid].max())
            else:
                dmin, dmax = 0.0, 1.0

            depth_norm = np.zeros_like(depth_vis, dtype=np.float32)
            if dmax > dmin:
                depth_norm[valid] = (depth_vis[valid] - dmin) / (dmax - dmin)
            elif np.any(valid):
                depth_norm[valid] = 1.0

            depth_u8 = (depth_norm * 255).astype(np.uint8)
            depth_color = cv2.applyColorMap(depth_u8, cv2.COLORMAP_JET)

            # ── RGB edge overlay on depth (alignment diagnostic) ───────────────
            color_scaled = cv2.resize(color_img, (W, H))
            gray_color = cv2.cvtColor(color_scaled, cv2.COLOR_BGR2GRAY)
            edges = cv2.Canny(gray_color, 50, 150)
            edges_colored = np.zeros_like(depth_color)
            edges_colored[:, :, 1] = edges  # green channel only
            check = cv2.addWeighted(depth_color, 0.8, edges_colored, 1.0, 0)

            # ── Direct RGB + Depth Blend (alignment diagnostic) ───────────────
            color_scaled = cv2.resize(color_img, (W, H))
            
            # Blend 60% RGB and 40% Depth colormap
            overlay = cv2.addWeighted(color_scaled, 0.6, depth_color, 0.4, 0)

            # Show: left IR | depth+edges overlay | aligned color
            left_bgr = cv2.cvtColor(img0_gray, cv2.COLOR_GRAY2BGR)
            left_bgr_scaled = cv2.resize(left_bgr, (W, H))
            combined = np.concatenate([left_bgr_scaled, check, color_scaled], axis=1)
            cv2.imshow("Left IR | Depth+RGB edges | Color", combined)

            # Show: left IR | RGB+Depth Overlay | aligned color
            left_bgr = cv2.cvtColor(img0_gray, cv2.COLOR_GRAY2BGR)
            left_bgr_scaled = cv2.resize(left_bgr, (W, H))
            combined = np.concatenate([left_bgr_scaled, overlay, color_scaled], axis=1)
            cv2.imshow("Left IR | RGB+Depth Overlay | Color", combined)

            if cv2.waitKey(1) & 0xFF == 27:  # ESC to quit
                break
    finally:
        pipeline.stop()
        cv2.destroyAllWindows()
