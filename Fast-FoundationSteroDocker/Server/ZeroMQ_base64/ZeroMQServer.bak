# Copyright (c) 2025, NVIDIA CORPORATION.  All rights reserved.

import time
import os
import sys
sys.path.append("/workspace/Fast-FoundationStereo-master")
import json
import logging
import zmq
import base64

os.environ["OPENCV_IO_ENABLE_OPENEXR"] = "1"

import cv2
import numpy as np
import pyrealsense2 as rs
import torch

code_dir = os.path.dirname(os.path.realpath(__file__))
sys.path.append(f"{code_dir}/../")

from omegaconf import OmegaConf
from core.utils.utils import InputPadder
from Utils import set_logging_format, set_seed


def load_config(config_path="config.yaml"):
    return OmegaConf.load(config_path)


def encode_color_jpg(color_bgr, jpg_quality=90):
    ok, buf = cv2.imencode(".jpg", color_bgr, [int(cv2.IMWRITE_JPEG_QUALITY), int(jpg_quality)])
    if not ok:
        raise RuntimeError("Failed to encode color image to JPG.")
    return buf.tobytes()


def depth_float_m_to_uint16_mm(depth_m: np.ndarray) -> np.ndarray:
    """
    把 float32 米制深度转换为 uint16 毫米深度，
    以便与第一个 server / client 的格式保持一致。
    """
    depth_mm = depth_m.copy()
    depth_mm[~np.isfinite(depth_mm)] = 0
    depth_mm[depth_mm < 0] = 0
    depth_mm = np.clip(depth_mm * 1000.0, 0, 65535).astype(np.uint16)
    return depth_mm


def to_base64_str(data: bytes) -> str:
    return base64.b64encode(data).decode("utf-8")

def encode_depth_png(depth_u16: np.ndarray) -> bytes:
    ok, buf = cv2.imencode(".png", depth_u16)
    if not ok:
        raise RuntimeError("Failed to encode depth image to PNG.")
    return buf.tobytes()


def main():
    cfg = load_config("/workspace/config.yaml")

    set_logging_format()
    set_seed(0)
    torch.autograd.set_grad_enabled(False)

    os.makedirs(cfg.paths.out_dir, exist_ok=True)

    # ── ZMQ PUB ────────────────────────────────────────────────────────────────
    context = zmq.Context()
    socket = context.socket(zmq.PUB)
    socket.setsockopt(zmq.SNDHWM, 1)
    socket.bind(cfg.zmq.pub_addr)
    print(f"Publisher started at {cfg.zmq.pub_addr}")

    # ── Load model ─────────────────────────────────────────────────────────────
    ckpt_dir = cfg.model.ckpt_dir
    model_cfg = OmegaConf.load(f"{os.path.dirname(ckpt_dir)}/cfg.yaml")

    if "vit_size" not in model_cfg:
        model_cfg["vit_size"] = "vitl"

    model_cfg["ckpt_dir"] = cfg.model.ckpt_dir
    model_cfg["out_dir"] = cfg.paths.out_dir
    model_cfg["width"] = cfg.camera.width
    model_cfg["height"] = cfg.camera.height
    model_cfg["fps"] = cfg.camera.fps
    model_cfg["scale"] = cfg.runtime.scale
    model_cfg["z_far"] = cfg.runtime.z_far
    model_cfg["valid_iters"] = cfg.model.valid_iters
    model_cfg["remove_invisible"] = cfg.runtime.remove_invisible

    args = OmegaConf.create(model_cfg)

    logging.info(f"args:\n{args}")
    logging.info(f"Using pretrained model from {ckpt_dir}")

    model = torch.load(ckpt_dir, map_location="cpu", weights_only=False)
    model.args.valid_iters = args.valid_iters
    model.args.max_disp = args.max_disp
    model.cuda()
    model.eval()

    # ── RealSense pipeline ─────────────────────────────────────────────────────
    resize = (int(cfg.camera.width), int(cfg.camera.height))

    pipeline = rs.pipeline()
    config = rs.config()
    config.enable_stream(rs.stream.infrared, 1, resize[0], resize[1], rs.format.y8, int(cfg.camera.fps))
    config.enable_stream(rs.stream.infrared, 2, resize[0], resize[1], rs.format.y8, int(cfg.camera.fps))
    config.enable_stream(rs.stream.color, resize[0], resize[1], rs.format.bgr8, int(cfg.camera.fps))
    profile = pipeline.start(config)

    depth_sensor = profile.get_device().first_depth_sensor()
    if depth_sensor.supports(rs.option.emitter_enabled):
        depth_sensor.set_option(rs.option.emitter_enabled, int(cfg.camera.disable_emitter))

    # ── Intrinsics / extrinsics ────────────────────────────────────────────────
    left_stream = profile.get_stream(rs.stream.infrared, 1).as_video_stream_profile()
    right_stream = profile.get_stream(rs.stream.infrared, 2).as_video_stream_profile()
    color_stream = profile.get_stream(rs.stream.color).as_video_stream_profile()

    left_intr = left_stream.get_intrinsics()
    color_intr = color_stream.get_intrinsics()
    extr = left_stream.get_extrinsics_to(right_stream)
    ir_to_color_extr = left_stream.get_extrinsics_to(color_stream)

    baseline = abs(extr.translation[0])
    print(f"Stereo baseline: {baseline:.6f} m")

    R_ext = np.array(ir_to_color_extr.rotation).reshape(3, 3).T
    T_ext = np.array(ir_to_color_extr.translation)

    K = np.array([
        [left_intr.fx, 0, left_intr.ppx],
        [0, left_intr.fy, left_intr.ppy],
        [0, 0, 1],
    ], dtype=np.float32)
    K[:2] *= float(cfg.runtime.scale)

    logging.info(f"K:\n{K}\nbaseline: {baseline:.4f} m")

    scale = float(cfg.runtime.scale)
    frame_id = 0

    try:
        while True:
            frames = pipeline.wait_for_frames()
            left_frame_rs = frames.get_infrared_frame(1)
            right_frame_rs = frames.get_infrared_frame(2)
            color_frame_rs = frames.get_color_frame()

            if not left_frame_rs or not right_frame_rs or not color_frame_rs:
                continue

            color_img = np.asanyarray(color_frame_rs.get_data())

            img0_gray = np.asanyarray(left_frame_rs.get_data())
            img1_gray = np.asanyarray(right_frame_rs.get_data())

            img0 = cv2.cvtColor(img0_gray, cv2.COLOR_GRAY2BGR)
            img1 = cv2.cvtColor(img1_gray, cv2.COLOR_GRAY2BGR)

            if scale != 1.0:
                img0 = cv2.resize(img0, dsize=None, fx=scale, fy=scale)
                img1 = cv2.resize(img1, dsize=None, fx=scale, fy=scale)

            H, W = img0.shape[:2]

            img0_t = torch.as_tensor(img0).cuda().float()[None].permute(0, 3, 1, 2)
            img1_t = torch.as_tensor(img1).cuda().float()[None].permute(0, 3, 1, 2)

            padder = InputPadder(img0_t.shape, divis_by=32, force_square=False)
            img0_t, img1_t = padder.pad(img0_t, img1_t)

            t0 = time.time()
            with torch.cuda.amp.autocast(True):
                disp = model.forward(img0_t, img1_t, iters=int(cfg.model.valid_iters), test_mode=True)
            t1 = time.time()

            disp = padder.unpad(disp.float())
            disp = disp.data.cpu().numpy().reshape(H, W)

            if int(cfg.runtime.remove_invisible):
                yy, xx = np.meshgrid(np.arange(H), np.arange(W), indexing="ij")
                us_right = xx - disp
                disp[us_right < 0] = np.inf

            depth = K[0, 0] * baseline / disp   # meters, float32

            # ── Align predicted depth to color ────────────────────────────────
            Z = depth
            valid = (Z > 0) & np.isfinite(Z)
            y_ir, x_ir = np.nonzero(valid)
            z_ir = Z[valid]

            X_ir = (x_ir - K[0, 2]) * z_ir / K[0, 0]
            Y_ir = (y_ir - K[1, 2]) * z_ir / K[1, 1]
            P_ir = np.stack((X_ir, Y_ir, z_ir), axis=0)

            P_color = R_ext @ P_ir + T_ext[:, None]
            X_c, Y_c, Z_c = P_color[0], P_color[1], P_color[2]

            x_c = (X_c / Z_c) * color_intr.fx + color_intr.ppx
            y_c = (Y_c / Z_c) * color_intr.fy + color_intr.ppy

            x_c = np.round(x_c).astype(int)
            y_c = np.round(y_c).astype(int)

            mask = (
                (x_c >= 0) & (x_c < color_intr.width) &
                (y_c >= 0) & (y_c < color_intr.height) &
                (Z_c > 0)
            )
            x_c, y_c, Z_c = x_c[mask], y_c[mask], Z_c[mask]

            depth_aligned = np.zeros((color_intr.height, color_intr.width), dtype=np.float32)
            order = np.argsort(Z_c)[::-1]
            depth_aligned[y_c[order], x_c[order]] = Z_c[order]

            # ── depth 转成 uint16 mm ───────────────────────────────────────────
            depth_u16 = depth_float_m_to_uint16_mm(depth_aligned)

            # ── RGB JPG -> base64 ──────────────────────────────────────────────
            color_bytes = encode_color_jpg(color_img, jpg_quality=cfg.zmq.jpg_quality)
            color_b64 = to_base64_str(color_bytes)

            # Depth PNG -> base64
            depth_bytes = encode_depth_png(depth_u16)
            depth_b64 = to_base64_str(depth_bytes)

            # ── 单 JSON 发送 ───────────────────────────────────────────────────
            payload = {
                "frame_id": frame_id,
                "rgb_format": "jpg_base64",
                "depth_format": "png_base64",
                "depth_dtype": "uint16",
                "depth_shape": list(depth_u16.shape),
                "rgb": color_b64,
                "depth": depth_b64,
            }

            socket.send_string(json.dumps(payload))

            if frame_id % 30 == 0:
                print(f"[PUB] frame_id={frame_id}, infer_time={t1 - t0:.4f}s")

            frame_id += 1

    finally:
        pipeline.stop()
        socket.close(0)
        context.term()


if __name__ == "__main__":
    main()