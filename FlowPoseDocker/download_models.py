#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""下载 FlowPose 运行所需的全部模型资产。"""

import argparse
import shutil
import sys
import tempfile
from pathlib import Path


MODEL_SCOPE_REPO = "kernelmind/FlowPose"
FLOWPOSE_FILES = ("flowpose.pth", "scalenet.pth")
DINO_FILES = ("dinov2_vits14_pretrain.pth",)
DINO_REPO_DIR = "facebookresearch_dinov2_main"


def copy_item(source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    if source.is_dir():
        if target.exists():
            shutil.rmtree(target)
        shutil.copytree(source, target)
    else:
        shutil.copy2(source, target)


def download_snapshot() -> Path:
    try:
        from modelscope.hub.snapshot_download import snapshot_download
    except ImportError as exc:
        raise RuntimeError("未安装 modelscope，请先执行 pip install modelscope") from exc

    cache_dir = Path(tempfile.mkdtemp(prefix="flowpose_modelscope_"))
    snapshot_path = snapshot_download(MODEL_SCOPE_REPO, cache_dir=str(cache_dir))
    return Path(snapshot_path)


def sync_assets(snapshot_dir: Path, target_dir: Path) -> None:
    for file_name in FLOWPOSE_FILES + DINO_FILES:
        source = snapshot_dir / file_name
        if not source.exists():
            raise FileNotFoundError(f"模型文件未找到: {source}")
        copy_item(source, target_dir / file_name)

    dino_source = snapshot_dir / DINO_REPO_DIR
    if not dino_source.exists():
        raise FileNotFoundError(f"DINO 仓库目录未找到: {dino_source}")
    copy_item(dino_source, target_dir / DINO_REPO_DIR)


def main() -> int:
    base_dir = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(description="下载 FlowPose 运行所需的全部模型资产")
    parser.add_argument(
        "--save-dir",
        type=str,
        default=str(base_dir / "model"),
        help="模型保存目录，默认是 FlowPoseDocker/model",
    )
    args = parser.parse_args()

    save_dir = Path(args.save_dir).resolve()
    save_dir.mkdir(parents=True, exist_ok=True)

    print("=" * 60)
    print("FlowPose 模型资产下载工具")
    print("=" * 60)
    print(f"[INFO] ModelScope 仓库: {MODEL_SCOPE_REPO}")
    print(f"[INFO] 保存目录: {save_dir}")
    print(f"[INFO] 下载内容: {', '.join(FLOWPOSE_FILES)}, {DINO_FILES[0]}, {DINO_REPO_DIR}/")

    try:
        snapshot_dir = download_snapshot()
        print(f"[INFO] 临时快照目录: {snapshot_dir}")
        sync_assets(snapshot_dir, save_dir)
    except Exception as exc:
        print(f"[ERROR] 下载失败: {exc}")
        print("[INFO] 请先安装 modelscope: pip install modelscope")
        return 1

    print("[SUCCESS] 下载完成")
    print(f"[INFO] FlowPose 权重: {save_dir / 'flowpose.pth'}")
    print(f"[INFO] ScaleNet 权重: {save_dir / 'scalenet.pth'}")
    print(f"[INFO] DINO 权重: {save_dir / 'dinov2_vits14_pretrain.pth'}")
    print(f"[INFO] DINO 仓库: {save_dir / DINO_REPO_DIR}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
