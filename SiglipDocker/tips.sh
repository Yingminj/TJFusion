#!/usr/bin/env bash
set -e

IMAGE_NAME="siglip2"
CONTAINER_NAME="siglip2_container"

DATA_PATH="$(pwd)"

# 允许 docker 使用本机显示
xhost +local:docker

echo "Starting container..."

docker rm -f ${CONTAINER_NAME} 2>/dev/null || true

docker run -it --rm \
  --name ${CONTAINER_NAME} \
  --gpus all \
  --network host \
  --ipc=host \
  --privileged \
  -e DISPLAY=$DISPLAY \
  -e QT_X11_NO_MITSHM=1 \
  -v /tmp/.X11-unix:/tmp/.X11-unix \
  -v "${DATA_PATH}:${DATA_PATH}" \
  -v "$(pwd):/workspace" \
  -w /workspace \
  ${IMAGE_NAME} \
  bash -lc '
    cd /workspace/Server/ZeroMQ && \
    python3 ZeroMQServer.py \
  '
