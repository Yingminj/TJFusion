# Copyright (c) 2025, NVIDIA CORPORATION.  All rights reserved.

import time
import os
import sys
import argparse

sys.path.append("/workspace/Fast-FoundationStereo-master")
import json
import logging
import base64
import zmq
from pathlib import Path

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


def center_crop(img: np.ndarray, target_w: int, target_h: int) -> np.ndarray:
    h, w = img.shape[:2]
    if w < target_w or h < target_h:
        raise ValueError(
            f"View size {w}x{h} is smaller than crop size {target_w}x{target_h}."
        )
    x0 = (w - target_w) // 2
    y0 = (h - target_h) // 2
    return img[y0:y0 + target_h, x0:x0 + target_w]


def split_and_crop_quad_views(
    frame: np.ndarray,
    *,
    expected_width: int,
    expected_height: int,
    crop_width: int,
    crop_height: int,
    top_extra_rows: int,
) -> dict[str, np.ndarray]:
    h, w = frame.shape[:2]
    if w != expected_width or h != expected_height:
        raise ValueError(
            f"Expected ZMQ frame size {expected_width}x{expected_height}, got {w}x{h}."
        )

    half_w = w // 2
    half_h = h // 2

    left_eye = frame[0:half_h + top_extra_rows, 0:half_w]
    right_eye = frame[0:half_h + top_extra_rows, half_w:w]
    right_hand = frame[half_h:h, 0:half_w]
    left_hand = frame[half_h:h, half_w:w]

    return {
        "left_eye": center_crop(left_eye, crop_width, crop_height),
        "right_eye": center_crop(right_eye, crop_width, crop_height),
        "right_hand": center_crop(right_hand, crop_width, crop_height),
        "left_hand": center_crop(left_hand, crop_width, crop_height),
    }


def ensure_bgr(frame: np.ndarray) -> np.ndarray:
    if frame.ndim == 2:
        return cv2.cvtColor(frame, cv2.COLOR_GRAY2BGR)
    if frame.ndim == 3 and frame.shape[2] == 4:
        return cv2.cvtColor(frame, cv2.COLOR_BGRA2BGR)
    return frame


def recv_latest_webrtc_frame_from_zmq(sub_socket: zmq.Socket, timeout_ms: int = 3000):
    poller = zmq.Poller()
    poller.register(sub_socket, zmq.POLLIN)

    events = dict(poller.poll(timeout_ms))
    if sub_socket not in events:
        raise TimeoutError(f"Timeout waiting for WebRTC ZMQ frame ({timeout_ms} ms)")

    latest_raw = sub_socket.recv_string()
    while True:
        try:
            latest_raw = sub_socket.recv_string(flags=zmq.NOBLOCK)
        except zmq.Again:
            break

    payload = json.loads(latest_raw)
    if not isinstance(payload, dict):
        raise RuntimeError("WebRTC payload must be a JSON object.")

    image_b64 = payload.get("image") or payload.get("rgb_image")
    if not image_b64:
        raise RuntimeError("WebRTC payload missing 'image' or 'rgb_image'.")

    raw = base64.b64decode(image_b64)
    arr = np.frombuffer(raw, dtype=np.uint8)
    frame = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if frame is None:
        raise RuntimeError("Failed to decode WebRTC ZMQ image.")

    return ensure_bgr(frame), payload


def load_quad_calibration(calibration_yaml: str) -> dict[str, dict[str, np.ndarray]]:
    yaml_path = Path(calibration_yaml).expanduser()
    if not yaml_path.exists():
        raise FileNotFoundError(f"Calibration yaml not found: {yaml_path}")

    fs = cv2.FileStorage(str(yaml_path), cv2.FILE_STORAGE_READ)
    if not fs.isOpened():
        raise RuntimeError(f"Failed to open calibration yaml: {yaml_path}")

    try:
        result: dict[str, dict[str, np.ndarray]] = {}
        for view_name in ("left_eye", "right_eye", "right_hand", "left_hand"):
            k = fs.getNode(f"{view_name}_K").mat()
            d = fs.getNode(f"{view_name}_D").mat()
            if k is None or d is None:
                raise ValueError(
                    f"Calibration yaml missing {view_name}_K or {view_name}_D: {yaml_path}"
                )

            d_flat = d.reshape(-1)
            if d_flat.size < 5:
                raise ValueError(
                    f"{view_name}_D requires at least 5 coeffs, got {d_flat.size}"
                )

            result[view_name] = {
                "K": k.astype(np.float64),
                "D5": d_flat[:5].astype(np.float64),
            }
        return result
    finally:
        fs.release()


def build_undistort_maps(k: np.ndarray, d8: np.ndarray, width: int, height: int):
    new_k, _ = cv2.getOptimalNewCameraMatrix(k, d8, (width, height), 0.0)
    map1, map2 = cv2.initUndistortRectifyMap(k, d8, None, new_k, (width, height), cv2.CV_16SC2)
    return map1, map2, new_k


def undistort_quad_views(
    views: dict[str, np.ndarray],
    calib: dict[str, dict[str, np.ndarray]],
    undistort_state: dict[str, dict[str, tuple[np.ndarray, np.ndarray] | np.ndarray | tuple[int, int]]],
) -> dict[str, np.ndarray]:
    undistorted: dict[str, np.ndarray] = {}
    maps = undistort_state.setdefault("maps", {})
    shapes = undistort_state.setdefault("shapes", {})
    new_ks = undistort_state.setdefault("new_k", {})

    for name, img in views.items():
        h, w = img.shape[:2]
        rebuild = name not in maps or shapes.get(name) != (w, h)
        if rebuild:
            map1, map2, new_k = build_undistort_maps(calib[name]["K"], calib[name]["D5"], w, h)
            maps[name] = (map1, map2)
            shapes[name] = (w, h)
            new_ks[name] = new_k.astype(np.float32)

        map1, map2 = maps[name]
        undistorted[name] = cv2.remap(img, map1, map2, interpolation=cv2.INTER_LINEAR)

    return undistorted


def stitch_quad_views(views: dict[str, np.ndarray]) -> np.ndarray:
    top = cv2.hconcat([views["left_eye"], views["right_eye"]])
    bottom = cv2.hconcat([views["right_hand"], views["left_hand"]])
    return cv2.vconcat([top, bottom])


def preprocess_webrtc_frame(frame_bgr: np.ndarray) -> np.ndarray:
    # Hook for custom frame processing before crop/undistort.
    return frame_bgr


def compute_depth_from_disparity(disp: np.ndarray, fx: float, baseline_m: float, z_far: float) -> np.ndarray:
    with np.errstate(divide="ignore", invalid="ignore"):
        depth = fx * baseline_m / disp
    depth = depth.astype(np.float32, copy=False)
    depth[~np.isfinite(depth)] = 0
    depth[depth < 0] = 0
    if z_far > 0:
        depth[depth > z_far] = 0
    return depth


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=str, default="/workspace/config.yaml", help="Path to config yaml")
    args_cli = parser.parse_args()

    cfg = OmegaConf.load(args_cli.config)
    set_logging_format()
    set_seed(0)
    torch.autograd.set_grad_enabled(False)

    # ==================== 配置解析块 ====================
    # 1. Server 网络配置
    server_cfg = cfg.get("server", {})
    # 优先使用 server.host 和 port，如果不存在则退化使用 zmq.pub_addr
    if "host" in server_cfg and "port" in server_cfg:
        pub_addr = f"tcp://{server_cfg['host']}:{server_cfg['port']}"
    else:
        pub_addr = cfg.get("zmq", {}).get("pub_addr", "tcp://*:4444")
    
    jpg_quality = int(cfg.get("zmq", {}).get("jpg_quality", 90))

    # 2. Paths 路径配置
    out_dir = cfg.get("paths", {}).get("out_dir", "./output")

    # 3. Model 权重和参数
    model_cfg_block = cfg.get("model", {})
    ckpt_dir = model_cfg_block.get("ckpt_dir", "")
    valid_iters = int(model_cfg_block.get("valid_iters", 8))

    # 4. Camera 相机基础参数
    camera_cfg = cfg.get("camera", {})
    cam_width = int(camera_cfg.get("width", 640))
    cam_height = int(camera_cfg.get("height", 480))
    cam_fps = int(camera_cfg.get("fps", 30))
    disable_emitter = int(camera_cfg.get("disable_emitter", 0))

    # 5. Source 输入源参数
    source_cfg = cfg.get("source", {})
    source_mode = str(source_cfg.get("mode", "realsense")).strip().lower()
    source_zmq_addr = str(source_cfg.get("zmq_addr", "tcp://127.0.0.1:4555")).strip()
    source_timeout_ms = int(source_cfg.get("zmq_timeout_ms", 10000))
    expected_width = int(source_cfg.get("expected_width", 1920))
    expected_height = int(source_cfg.get("expected_height", 1488))
    top_extra_rows = int(source_cfg.get("top_extra_rows", 100))
    crop_width = int(source_cfg.get("crop_width", cam_width))
    crop_height = int(source_cfg.get("crop_height", cam_height))
    calibration_yaml = str(source_cfg.get("calibration_yaml", ""))
    baseline_m_config = float(source_cfg.get("baseline_m", 0.065))

    # 6. Runtime 运行时控制
    runtime_cfg = cfg.get("runtime", {})
    scale = float(runtime_cfg.get("scale", 1.0))
    z_far = float(runtime_cfg.get("z_far", 10.0))
    remove_invisible = int(runtime_cfg.get("remove_invisible", 1))

    # 7. Visualization 可视化
    show_vis = cfg.get("visualization", {}).get("show", True)
    # ====================================================

    os.makedirs(out_dir, exist_ok=True)

    if source_mode not in {"realsense", "zmq_webrtc"}:
        raise ValueError("source.mode must be 'realsense' or 'zmq_webrtc'.")

    quad_calib = None
    undistort_state: dict[str, dict[str, tuple[np.ndarray, np.ndarray] | np.ndarray | tuple[int, int]]] = {}

    # ── ZMQ PUB ────────────────────────────────────────────────────────────────
    context = zmq.Context()
    socket = context.socket(zmq.PUB)
    socket.setsockopt(zmq.SNDHWM, 1)
    socket.bind(pub_addr)
    print(f"Publisher started at {pub_addr}")

    # ── Load model ─────────────────────────────────────────────────────────────
    model_cfg = OmegaConf.load(f"{os.path.dirname(ckpt_dir)}/cfg.yaml")

    if "vit_size" not in model_cfg:
        model_cfg["vit_size"] = "vitl"

    model_cfg["ckpt_dir"] = ckpt_dir
    model_cfg["out_dir"] = out_dir
    model_cfg["width"] = cam_width
    model_cfg["height"] = cam_height
    model_cfg["fps"] = cam_fps
    model_cfg["scale"] = scale
    model_cfg["z_far"] = z_far
    model_cfg["valid_iters"] = valid_iters
    model_cfg["remove_invisible"] = remove_invisible

    args = OmegaConf.create(model_cfg)

    logging.info(f"args:\n{args}")
    logging.info(f"Using pretrained model from {ckpt_dir}")

    model = torch.load(ckpt_dir, map_location="cpu", weights_only=False)
    model.args.valid_iters = args.valid_iters
    model.args.max_disp = args.max_disp
    model.cuda()
    model.eval()

    resize = (cam_width, cam_height)

    pipeline = None
    source_socket = None

    if source_timeout_ms <= 0:
        source_timeout_ms = 3000

    baseline = None
    K = None
    color_intr = None
    R_ext = None
    T_ext = None

    if source_mode == "realsense":
        # ── RealSense pipeline ─────────────────────────────────────────────────
        pipeline = rs.pipeline()
        config = rs.config()
        config.enable_stream(rs.stream.infrared, 1, resize[0], resize[1], rs.format.y8, cam_fps)
        config.enable_stream(rs.stream.infrared, 2, resize[0], resize[1], rs.format.y8, cam_fps)
        config.enable_stream(rs.stream.color, resize[0], resize[1], rs.format.bgr8, cam_fps)
        profile = pipeline.start(config)

        depth_sensor = profile.get_device().first_depth_sensor()
        if depth_sensor.supports(rs.option.emitter_enabled):
            depth_sensor.set_option(rs.option.emitter_enabled, disable_emitter)

        # ── Intrinsics / extrinsics ────────────────────────────────────────────
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
        K[:2] *= scale

        logging.info(f"K:\n{K}\nbaseline: {baseline:.4f} m")
    else:
        if not source_zmq_addr:
            raise ValueError("source.zmq_addr is required when source.mode=zmq_webrtc")
        if not calibration_yaml:
            raise ValueError("source.calibration_yaml is required when source.mode=zmq_webrtc")
        quad_calib = load_quad_calibration(calibration_yaml)

        baseline = baseline_m_config
        if baseline <= 0:
            raise ValueError("source.baseline_m must be > 0 when source.mode=zmq_webrtc")

        source_socket = context.socket(zmq.SUB)
        source_socket.setsockopt(zmq.RCVHWM, 1)
        source_socket.setsockopt(zmq.LINGER, 0)
        source_socket.setsockopt(zmq.SUBSCRIBE, b"")
        source_socket.connect(source_zmq_addr)

        K = quad_calib["left_eye"]["K"].astype(np.float32)
        K[:2] *= scale
        logging.info(
            (
                "Using ZMQ WebRTC source: addr=%s, timeout_ms=%d, baseline=%.4f, "
                "expected=%dx%d, crop=%dx%d, calib=%s"
            ),
            source_zmq_addr,
            source_timeout_ms,
            baseline,
            expected_width,
            expected_height,
            crop_width,
            crop_height,
            calibration_yaml,
        )
        print(f"WebRTC ZMQ source subscribed: {source_zmq_addr}")

    assert baseline is not None
    assert K is not None
    frame_id = 0

    try:
        while True:
            source_meta = None

            if source_mode == "realsense":
                assert pipeline is not None
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

            else:
                assert source_socket is not None
                frame_bgr, source_meta = recv_latest_webrtc_frame_from_zmq(
                    source_socket,
                    timeout_ms=source_timeout_ms,
                )

                frame_bgr = preprocess_webrtc_frame(ensure_bgr(frame_bgr))
                quad_views = split_and_crop_quad_views(
                    frame_bgr,
                    expected_width=expected_width,
                    expected_height=expected_height,
                    crop_width=crop_width,
                    crop_height=crop_height,
                    top_extra_rows=top_extra_rows,
                )

                assert quad_calib is not None
                quad_views = undistort_quad_views(quad_views, quad_calib, undistort_state)

                color_img = stitch_quad_views(quad_views)
                img0 = quad_views["left_eye"]
                img1 = quad_views["right_eye"]

                if scale != 1.0:
                    img0 = cv2.resize(img0, dsize=None, fx=scale, fy=scale)
                    img1 = cv2.resize(img1, dsize=None, fx=scale, fy=scale)

                left_new_k = undistort_state.get("new_k", {}).get("left_eye")
                if isinstance(left_new_k, np.ndarray):
                    K = left_new_k.astype(np.float32).copy()
                else:
                    K = quad_calib["left_eye"]["K"].astype(np.float32).copy()
                K[:2] *= scale

            H, W = img0.shape[:2]

            img0_t = torch.as_tensor(img0).cuda().float()[None].permute(0, 3, 1, 2)
            img1_t = torch.as_tensor(img1).cuda().float()[None].permute(0, 3, 1, 2)

            padder = InputPadder(img0_t.shape, divis_by=32, force_square=False)
            img0_t, img1_t = padder.pad(img0_t, img1_t)

            t0 = time.time()
            with torch.cuda.amp.autocast(True):
                disp = model.forward(img0_t, img1_t, iters=valid_iters, test_mode=True)
            t1 = time.time()

            disp = padder.unpad(disp.float())
            disp = disp.data.cpu().numpy().reshape(H, W)

            if remove_invisible:
                yy, xx = np.meshgrid(np.arange(H), np.arange(W), indexing="ij")
                us_right = xx - disp
                disp[us_right < 0] = np.inf

            if source_mode == "realsense":
                assert color_intr is not None
                assert R_ext is not None
                assert T_ext is not None

                depth = compute_depth_from_disparity(
                    disp,
                    fx=float(K[0, 0]),
                    baseline_m=float(baseline),
                    z_far=z_far,
                )

                # ── Align predicted depth to color ────────────────────────────
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
            else:
                depth_aligned = compute_depth_from_disparity(
                    disp,
                    fx=float(K[0, 0]),
                    baseline_m=float(baseline),
                    z_far=z_far,
                )

                # depth 发布给后续链路时，保持单目视角尺寸（left/right crop 尺寸）
                if depth_aligned.shape[:2] != (crop_height, crop_width):
                    depth_aligned = cv2.resize(
                        depth_aligned,
                        (crop_width, crop_height),
                        interpolation=cv2.INTER_LINEAR,
                    )

            # ── 和第一个 server 格式对齐：depth 转成 uint16 ──────────────────
            depth_u16 = depth_float_m_to_uint16_mm(depth_aligned)

            # ── Publish ───────────────────────────────────────────────────────
            color_bytes = encode_color_jpg(color_img, jpg_quality=jpg_quality)

            meta = {
                "depth_shape": depth_u16.shape
            }
            if source_mode == "zmq_webrtc":
                meta["source"] = "zmq_webrtc"
                meta["color_layout"] = "quad_2x2"
                meta["quad_view_order"] = ["left_eye", "right_eye", "right_hand", "left_hand"]
                meta["single_view_shape"] = [crop_height, crop_width]
                meta["left_eye_rect"] = [0, 0, crop_width, crop_height]
                if isinstance(source_meta, dict) and "ts" in source_meta:
                    meta["source_ts"] = source_meta["ts"]

            socket.send_multipart([
                json.dumps(meta).encode("utf-8"),
                color_bytes,
                depth_u16.tobytes(),
            ])
            
            # 本地调试显示，使用配置文件中的 visualization 字段控制
            if show_vis:
                cv2.imshow("color_img", color_img)
                cv2.waitKey(1)

            if frame_id % 30 == 0:
                print(f"[PUB] frame_id={frame_id}, infer_time={t1 - t0:.4f}s")

            frame_id += 1

    finally:
        if pipeline is not None:
            pipeline.stop()
        if source_socket is not None:
            source_socket.close(0)
        socket.close(0)
        context.term()


if __name__ == "__main__":
    main()