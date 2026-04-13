#!/usr/bin/env bash

set -e

IMAGE="flowpose"
CONTAINER_NAME="flowpose_run"

DINO_CKPT_HOST="./dinov2_vits14_pretrain.pth"
DINO_CKPT_CONT="/root/.cache/torch/hub/checkpoints/dinov2_vits14_pretrain.pth"

# 允许容器访问宿主机显示
xhost +local:root >/dev/null 2>&1 || true

# 如果旧容器存在，先删掉
docker rm -f "${CONTAINER_NAME}" >/dev/null 2>&1 || true

docker run -it --rm \
    --name "${CONTAINER_NAME}" \
    --gpus all \
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
    -w /workspace \
    "${IMAGE}" \
    bash -lc "cd /workspace/Server/ZeroMQ/ && python3 ZeroMQServer.py --vis"