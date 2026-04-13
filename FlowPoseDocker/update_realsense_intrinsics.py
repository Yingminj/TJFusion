#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import yaml
import pyrealsense2 as rs
from pathlib import Path


CONFIG_PATH = "./config.yaml"


def load_yaml(path: str):
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return data if data is not None else {}


def save_yaml(path: str, data: dict):
    with open(path, "w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, allow_unicode=True, sort_keys=False)


def get_realsense_intrinsics():
    pipeline = rs.pipeline()
    config = rs.config()

    # 这里启用 depth 和 color，分辨率可按你的实际需求调整
    config.enable_stream(rs.stream.depth, 640, 480, rs.format.z16, 30)
    config.enable_stream(rs.stream.color, 640, 480, rs.format.bgr8, 30)

    profile = pipeline.start(config)

    try:
        color_stream = profile.get_stream(rs.stream.color).as_video_stream_profile()
        intr = color_stream.get_intrinsics()

        return {
            "fx": float(intr.fx),
            "fy": float(intr.fy),
            "cx": float(intr.ppx),
            "cy": float(intr.ppy),
            "width": int(intr.width),
            "height": int(intr.height),
            "model": str(intr.model),
            "coeffs": [float(x) for x in intr.coeffs],
        }
    finally:
        pipeline.stop()


def update_config(config_path: str, intrinsics: dict):
    cfg = load_yaml(config_path)

    if "visualization" not in cfg or cfg["visualization"] is None:
        cfg["visualization"] = {}

    vis = cfg["visualization"]

    vis["fx"] = intrinsics["fx"]
    vis["fy"] = intrinsics["fy"]
    vis["cx"] = intrinsics["cx"]
    vis["cy"] = intrinsics["cy"]

    # 保留原来的 axis_len，没有就给默认值
    if "axis_len" not in vis:
        vis["axis_len"] = 0.08

    # 这两个字段不是必须，但通常有用
    vis["width"] = intrinsics["width"]
    vis["height"] = intrinsics["height"]

    save_yaml(config_path, cfg)


def main():
    config_file = Path(CONFIG_PATH)
    if not config_file.exists():
        raise FileNotFoundError(f"配置文件不存在: {CONFIG_PATH}")

    print("[INFO] 正在读取 RealSense 相机内参...")
    intr = get_realsense_intrinsics()

    print("[INFO] 读取成功:")
    print(f"  fx     = {intr['fx']}")
    print(f"  fy     = {intr['fy']}")
    print(f"  cx     = {intr['cx']}")
    print(f"  cy     = {intr['cy']}")
    print(f"  width  = {intr['width']}")
    print(f"  height = {intr['height']}")
    print(f"  model  = {intr['model']}")
    print(f"  coeffs = {intr['coeffs']}")

    print(f"[INFO] 正在写入配置文件: {CONFIG_PATH}")
    update_config(CONFIG_PATH, intr)
    print("[OK] 配置文件已更新。")


if __name__ == "__main__":
    main()