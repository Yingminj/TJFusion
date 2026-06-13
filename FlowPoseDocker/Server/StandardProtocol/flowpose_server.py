#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""FlowPose as a standard-protocol ``pose`` server.

Estimates 6-DoF object poses from color + metric depth + a combined mask.
Contract: protocol/schemas/pose.json.

  request.arrays  : color [H,W,3] uint8, depth [H,W] float32, combined_mask [H,W] uint8
  request.fields  : intrinsics?, obj_ids?, class_names?, instance_names?
  response.fields : objects (list of {name, pose, length, obj_id, box_id})

The pose inference and object-building math are lifted verbatim from the old
base64-JSON ``Server/ZeroMQ/ZeroMQServer.py``; only the I/O layer changed (no
base64, no cv2 visualization) and it now subclasses ``BaseModelServer``.
"""

from __future__ import annotations

import os
import sys
from argparse import Namespace

import numpy as np
import torch
import yaml

from tjfusion_protocol.envelope import Message
from tjfusion_protocol.server import BaseModelServer

CONFIG_PATH = os.environ.get("FLOWPOSE_CONFIG", "/workspace/config.yaml")


def _load_config(path: str = CONFIG_PATH) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def _to_jsonable(obj):
    if isinstance(obj, torch.Tensor):
        return obj.detach().cpu().tolist()
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    if isinstance(obj, (list, tuple)):
        return [_to_jsonable(x) for x in obj]
    if isinstance(obj, dict):
        return {k: _to_jsonable(v) for k, v in obj.items()}
    if isinstance(obj, np.integer):
        return int(obj)
    if isinstance(obj, np.floating):
        return float(obj)
    return obj


def _unpack_infer_output(pose_out, length_out):
    if pose_out is None or length_out is None:
        return None, None
    pose_all = pose_out[0] if isinstance(pose_out, (list, tuple)) else pose_out
    length_all = length_out[0] if isinstance(length_out, (list, tuple)) else length_out
    if pose_all is None or length_all is None:
        return None, None
    pose_all = _to_jsonable(pose_all)
    length_all = _to_jsonable(length_all)
    if pose_all is None or length_all is None:
        return None, None
    return pose_all, length_all


def _build_objects(pose_all, length_all, obj_ids, class_names=None, instance_names=None):
    if pose_all is None or length_all is None or obj_ids is None:
        return []
    class_names = class_names or []
    instance_names = instance_names or []

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


class FlowPosePoseServer(BaseModelServer):
    data_type = "pose"

    def __init__(self, *, bind_addr: str, config_path: str = CONFIG_PATH) -> None:
        super().__init__(bind_addr=bind_addr)
        self.config_path = config_path
        self.inferencer = None

    def load_model(self) -> None:
        cfg = _load_config(self.config_path)
        paths_cfg = cfg.get("paths", {})
        py_runner_path = paths_cfg.get("py_runner_path", "/workspace/FlowPose/py_runners")
        if py_runner_path not in sys.path:
            sys.path.append(py_runner_path)

        # The internal modules parse sys.argv on import; shield them from ours.
        safe_argv = sys.argv[:]
        sys.argv = [sys.argv[0]]
        try:
            from api_runner import PoseInferenceSession
            from inference.inference_helper import Flow
        finally:
            sys.argv = safe_argv

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

        print("[pose] loading Flow ...")
        flow = Flow(args)
        print("[pose] creating PoseInferenceSession ...")
        self.inferencer = PoseInferenceSession(flow, args)
        print("[pose] FlowPose ready.")

    def infer(self, request: Message) -> Message:
        rgb = np.ascontiguousarray(request.arrays["color"]).astype(np.uint8)
        depth = np.ascontiguousarray(request.arrays["depth"]).astype(np.float32)
        combined_mask = np.ascontiguousarray(request.arrays["combined_mask"]).astype(np.uint8)

        obj_ids = request.fields.get("obj_ids", []) or []
        class_names = request.fields.get("class_names", []) or []
        instance_names = request.fields.get("instance_names", []) or []

        pose_out, length_out = self.inferencer.infer(rgb, depth, combined_mask, obj_ids)
        pose_all, length_all = _unpack_infer_output(pose_out, length_out)

        objects = _build_objects(
            pose_all=pose_all,
            length_all=length_all,
            obj_ids=obj_ids,
            class_names=class_names,
            instance_names=instance_names,
        )
        return self.ok(request, fields={"objects": objects})


def main() -> None:
    cfg = _load_config()
    server_cfg = cfg.get("server", {})
    host = server_cfg.get("host", "0.0.0.0")
    port = int(server_cfg.get("port", 6667))
    bind_addr = f"tcp://{host}:{port}"
    FlowPosePoseServer(bind_addr=bind_addr).serve_forever()


if __name__ == "__main__":
    main()
