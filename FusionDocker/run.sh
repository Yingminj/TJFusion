#!/usr/bin/env bash

set -e

IMAGE="fusion"
CONTAINER_NAME="fusion_run"

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
    -v "${DINO_CKPT_HOST}:${DINO_CKPT_CONT}" \
    -w /workspace \
    "${IMAGE}" \
    bash -lc "/workspace/start.sh"