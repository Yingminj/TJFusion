#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import base64
import time
import traceback
from argparse import Namespace
import argparse
import sys
from types import SimpleNamespace
import json
import os

import cv2
import numpy as np
import torch
import zmq
import yaml

# ==================== 辅助工具函数 ====================
def save_latest_response(response: dict, save_path: str = "latest_response.json"):
    with open(save_path, "w", encoding="utf-8") as f:
        json.dump(response, f, indent=2, ensure_ascii=False)


def load_yaml_config(config_path: str) -> dict:
    if not os.path.exists(config_path):
        raise FileNotFoundError(f"配置文件未找到: {config_path}")
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def decode_image_b64(image_b64: str, flags: int) -> np.ndarray:
    raw = base64.b64decode(image_b64)
    arr = np.frombuffer(raw, dtype=np.uint8)
    img = cv2.imdecode(arr, flags)
    if img is None:
        raise ValueError("Failed to decode image from base64.")
    return img


def to_jsonable(obj):
    if isinstance(obj, torch.Tensor):
        return obj.detach().cpu().tolist()
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    if isinstance(obj, (list, tuple)):
        return [to_jsonable(x) for x in obj]
    if isinstance(obj, dict):
        return {k: to_jsonable(v) for k, v in obj.items()}
    if isinstance(obj, np.integer):
        return int(obj)
    if isinstance(obj, np.floating):
        return float(obj)
    return obj


def unpack_infer_output(pose_out, length_out):
    if pose_out is None or length_out is None:
        return None, None

    if isinstance(pose_out, (list, tuple)):
        if len(pose_out) == 0 or pose_out[0] is None:
            return None, None
        pose_all = pose_out[0]
    else:
        pose_all = pose_out

    if isinstance(length_out, (list, tuple)):
        if len(length_out) == 0 or length_out[0] is None:
            return None, None
        length_all = length_out[0]
    else:
        length_all = length_out

    pose_all = to_jsonable(pose_all)
    length_all = to_jsonable(length_all)

    if pose_all is None or length_all is None:
        return None, None

    return pose_all, length_all


def build_objects(pose_all, length_all, obj_ids, class_names=None, instance_names=None):
    if pose_all is None or length_all is None or obj_ids is None:
        return []

    if class_names is None:
        class_names = []
    if instance_names is None:
        instance_names = []

    n = min(len(pose_all), len(length_all), len(obj_ids))
    objects = []

    for i in range(n):
        obj_id = obj_ids[i]

        box_id = None
        if isinstance(obj_id, (list, tuple)) and len(obj_id) >= 2:
            try:
                box_id = int(obj_id[1])
            except Exception:
                box_id = None

        # 优先使用 instance_names，其次 class_names
        if i < len(instance_names) and instance_names[i]:
            name = str(instance_names[i])
        elif i < len(class_names) and class_names[i]:
            name = str(class_names[i])
        elif box_id is not None:
            name = f"obj_{box_id}"
        else:
            name = f"obj_{i + 1}"

        objects.append({
            "name": name,
            "pose": pose_all[i],
            "length": length_all[i],
            "obj_id": obj_id,
            "box_id": box_id,
        })

    return objects

# ==================== 核心服务类 ====================
class FlowPoseServer:
    def __init__(
        self,
        config_path: str = "config.yaml",  # 默认值改为当前目录下的 config.yaml
        visualize: bool = False,
        vis_wait: int = 1,
    ):
        print(f"[INIT] 加载配置文件: {config_path}")
        self.cfg = load_yaml_config(config_path)
        self.visualize = visualize
        self.vis_wait = vis_wait

        # 1. 解析 Server 配置
        server_cfg = self.cfg.get("server", {})
        host = server_cfg.get("host", "0.0.0.0")
        port = server_cfg.get("port", 5555)

        # 2. 解析 Paths 配置
        paths_cfg = self.cfg.get("paths", {})
        py_runner_path = paths_cfg.get("py_runner_path", "/workspace/FlowPose/py_runners")
        if py_runner_path not in sys.path:
            sys.path.append(py_runner_path)

        # 3. 解析 Visualization 配置
        vis_cfg = self.cfg.get("visualization", {})
        self.fx = float(vis_cfg.get("fx", 912.0))
        self.fy = float(vis_cfg.get("fy", 912.0))
        self.cx = float(vis_cfg.get("cx", 640.0))
        self.cy = float(vis_cfg.get("cy", 360.0))
        # yaml中没有提供 width 和 height，这里做安全的默认值处理
        self.width = int(vis_cfg.get("width", 640))
        self.height = int(vis_cfg.get("height", 480))
        # 适配 yaml 中的 axis_len
        self.axis_len = float(vis_cfg.get("axis_len", 0.08))

        # 导入内部模块 (需确保路径已正确加入 sys.path)
        safe_argv = sys.argv[:]
        sys.argv = [sys.argv[0]]

        from api_runner import PoseInferenceSession
        from inference.inference_helper import Flow
        from utils.yomni_vis import visualize_detections

        sys.argv = safe_argv
        self.visualize_detections = visualize_detections

        # 初始化参数配置
        args = Namespace(
            pretrained_flow_model_path=paths_cfg.get("pretrained_flow_model_path", ""),
            pretrained_scale_model_path=paths_cfg.get("pretrained_scale_model_path", ""),
            device="cuda",
            img_size=224,
            n_pts=1024,
            frame_gap_threshold=10,
            eval_repeat_num=25,
            retain_ratio=0.4,
            enable_tracking=True,
            seed=0,
            dropout=0,
            use_edm_aug=False,
            log_dir="debug",
            use_pretrain=False,
            is_train=False,
            pose_mode="rot_matrix",
            optimizer="Adam",
            lr=1e-2,
            lr_decay=0.98,
            num_points=1024,
            scale_embedding=180,
            ema_rate=0.999,
            repeat_num=20,
            clustering=1,
            clustering_eps=0.05,
            clustering_minpts=0.1667,
        )

        print("[INIT] Loading Flow...")
        self.flow = Flow(args)

        print("[INIT] Creating PoseInferenceSession...")
        self.inferencer = PoseInferenceSession(self.flow, args)

        # 启动 ZeroMQ Server
        self.context = zmq.Context()
        self.socket = self.context.socket(zmq.REP)
        zmq_addr = f"tcp://{host}:{port}"
        self.socket.bind(zmq_addr)

        print(f"[ZMQ] FlowPose server listening at {zmq_addr}")
        print(f"[INIT] Visualization: {'ON' if self.visualize else 'OFF'}")

    def build_cam_intrinsics(self):
        data = SimpleNamespace()
        data.fx = self.fx
        data.fy = self.fy
        data.cx = self.cx
        data.cy = self.cy
        data.width = self.width
        data.height = self.height

        K = np.array([
            [self.fx, 0.0, self.cx],
            [0.0, self.fy, self.cy],
            [0.0, 0.0, 1.0]
        ], dtype=np.float32)

        data.intrinsic_matrix = K
        data.K = K
        return data

    def process(self, req: dict) -> dict:
        t0 = time.time()

        request_id = req.get("request_id", "")

        rgb = decode_image_b64(req["rgb_image"], cv2.IMREAD_COLOR).astype(np.uint8)
        depth = decode_image_b64(req["depth_image"], cv2.IMREAD_ANYDEPTH).astype(np.float32)
        combined_mask = decode_image_b64(req["combined_mask"], cv2.IMREAD_GRAYSCALE).astype(np.uint8)

        obj_ids = req.get("obj_ids", [])
        class_names = req.get("class_names", [])
        instance_names = req.get("instance_names", [])

        pose_out, length_out = self.inferencer.infer(rgb, depth, combined_mask, obj_ids)
        pose_all, length_all = unpack_infer_output(pose_out, length_out)

        if self.visualize:
            try:
                vis = rgb.copy()

                valid_output = (
                    pose_all is not None
                    and length_all is not None
                    and len(pose_all) > 0
                    and len(length_all) > 0
                )

                if valid_output:
                    all_final_pose = np.asarray(pose_all, dtype=np.float32)
                    all_final_length = np.asarray(length_all, dtype=np.float32)

                    data = SimpleNamespace()
                    data.cam_intrinsics = self.build_cam_intrinsics()

                    # 如果你底层的 visualize_detections 支持传入 axis_len，你可以加进去
                    vis = self.visualize_detections(
                        vis,
                        all_final_pose,
                        all_final_length,
                        data.cam_intrinsics,
                        color=(0, 255, 0),
                        thickness=2,
                        alpha=0.1,
                        # axis_len=self.axis_len # 如果底层函数支持，可以取消注释
                    )

                if request_id:
                    cv2.putText(
                        vis,
                        f"request_id: {request_id}",
                        (10, 30),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.8,
                        (255, 255, 255),
                        2,
                        cv2.LINE_AA,
                    )
                
                cv2.putText(
                        vis,
                        f"Elapsed: {time.time() - t0:.2f}s",
                        (10, 30),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.8,
                        (255, 255, 255),
                        2,
                        cv2.LINE_AA,
                    )

                cv2.imshow("FlowPose Visualization", vis)
                cv2.waitKey(self.vis_wait)

            except Exception as e:
                print(f"[WARN] Visualization failed: {e}")

        if pose_all is None or length_all is None:
            response = {
                "status": "ok",
                "request_id": request_id,
                "objects": [],
                "elapsed_sec": round(time.time() - t0, 4),
            }
            save_latest_response(response)
            return response

        objects = build_objects(
            pose_all=pose_all,
            length_all=length_all,
            obj_ids=obj_ids,
            class_names=class_names,
            instance_names=instance_names,
        )

        response = {
            "status": "ok",
            "request_id": request_id,
            "objects": objects,
            "elapsed_sec": round(time.time() - t0, 4),
        }
        save_latest_response(response)
        return response

    def serve_forever(self):
        try:
            while True:
                req = None
                try:
                    req = self.socket.recv_json()
                    resp = self.process(req)
                    self.socket.send_json(resp)
                except Exception as e:
                    err = {
                        "status": "error",
                        "request_id": req.get("request_id", "") if isinstance(req, dict) else "",
                        "message": str(e),
                        "traceback": traceback.format_exc(),
                    }
                    save_latest_response(err)
                    try:
                        self.socket.send_json(err)
                    except Exception:
                        pass
                    print(traceback.format_exc())
        finally:
            if self.visualize:
                cv2.destroyAllWindows()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=str, default="/workspace/config.yaml", help="Path to config yaml")
    parser.add_argument("--vis", action="store_true", help="Enable FlowPose visualization")
    parser.add_argument("--vis-wait", type=int, default=1, help="cv2.waitKey delay in ms")

    args, unknown = parser.parse_known_args()
    # 修复：防止内部模块解析 sys.argv 报错
    sys.argv = [sys.argv[0]]

    server = FlowPoseServer(
        config_path=args.config,
        visualize=args.vis,
        vis_wait=args.vis_wait,
    )
    server.serve_forever()