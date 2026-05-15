#!/usr/bin/env bash
set -e

IMAGE_NAME="siglip2:latest"
CONTAINER_NAME="siglip2_container"

DATA_PATH="$(pwd)"

USE_NVIDIA=false
if [ -e /dev/nvidia0 ] || [ -e /dev/nvidiactl ]; then
    if command -v nvidia-smi >/dev/null 2>&1 && nvidia-smi -L >/dev/null 2>&1; then
        USE_NVIDIA=true
    fi
fi

if $USE_NVIDIA; then
    GPU_FLAGS="--runtime nvidia"
    NVIDIA_ENV="-e NVIDIA_VISIBLE_DEVICES=all -e NVIDIA_DRIVER_CAPABILITIES=all"
else
    echo "Warning: NVIDIA runtime not detected; running without GPU flags."
    GPU_FLAGS=""
    NVIDIA_ENV=""
fi

# 允许 docker 使用本机显示
xhost +local:docker

echo "Starting container..."

docker rm -f ${CONTAINER_NAME} 2>/dev/null || true

docker run -it --rm \
  --name ${CONTAINER_NAME} \
  ${GPU_FLAGS} \
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
  bash -lc 'cd /workspace/Server/ZeroMQ && 
        python3 ZeroMQServer.py --show'
