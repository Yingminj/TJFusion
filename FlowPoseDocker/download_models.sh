#!/usr/bin/env bash

# 入口脚本：调用 Python 下载器，将模型保存到 FlowPoseDocker/model

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SAVE_DIR="${SCRIPT_DIR}/model"

echo "[INFO] 模型保存目录: ${SAVE_DIR}"
echo "[INFO] 开始从 ModelScope 下载模型..."

python3 "${SCRIPT_DIR}/download_models.py" --save-dir "${SAVE_DIR}"
