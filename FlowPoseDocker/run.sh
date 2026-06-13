#!/usr/bin/env bash

set -e

IMAGE="flowpose:latest"
CONTAINER_NAME="flowpose_run"

DINO_CKPT_HOST="./model/dinov2_vits14_pretrain.pth"
DINO_CKPT_CONT="/root/.cache/torch/hub/checkpoints/dinov2_vits14_pretrain.pth"

# Repo root holds the shared protocol/ package; mount it so the live-mounted
# server (in /workspace) can import tjfusion_protocol without an image rebuild.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

# 允许容器访问宿主机显示
xhost +local:root >/dev/null 2>&1 || true

# 如果旧容器存在，先删掉
docker rm -f "${CONTAINER_NAME}" >/dev/null 2>&1 || true

docker run -it --rm \
    --runtime nvidia \
    --name "${CONTAINER_NAME}" \
    --net=host \
    --ipc=host \
    --privileged \
    --device /dev:/dev \
    -e DISPLAY="${DISPLAY}" \
    -e QT_X11_NO_MITSHM=1 \
    -e NVIDIA_DRIVER_CAPABILITIES=all \
    -e NVIDIA_VISIBLE_DEVICES=all \
    -v /tmp/.X11-unix:/tmp/.X11-unix:rw \
    -v /dev:/dev \
    -v "$(pwd)":/workspace \
    -v "${DINO_CKPT_HOST}:${DINO_CKPT_CONT}:ro" \
    -v "${REPO_ROOT}/protocol":/opt/tjfusion_protocol_src:ro \
    -w /workspace \
    "${IMAGE}" \
    bash -lc "cd /workspace && PYTHONPATH=/opt/tjfusion_protocol_src:\${PYTHONPATH} python3 Server/StandardProtocol/flowpose_server.py"