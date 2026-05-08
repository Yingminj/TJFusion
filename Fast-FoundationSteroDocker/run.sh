#!/usr/bin/env bash

set -e

IMAGE="fast-foundation-stereo:jetson"
CONTAINER_NAME="ffs_tmp"

xhost +local:root >/dev/null 2>&1 || true

docker rm -f "${CONTAINER_NAME}" >/dev/null 2>&1 || true

docker run -it --rm \
    --runtime nvidia \
    --name "${CONTAINER_NAME}" \
    --gpus all \
    --net=host \
    --ipc=host \
    --privileged \
    --device /dev:/dev \
    -e DISPLAY="${DISPLAY}" \
    -e QT_X11_NO_MITSHM=1 \
    -e NVIDIA_DRIVER_CAPABILITIES=all \
    -v /tmp/.X11-unix:/tmp/.X11-unix:rw \
    -v /dev:/dev \
    -v "$(pwd)":/workspace \
    -w /workspace \
    "${IMAGE}" \
    bash -lc "cd /workspace/Server/ZeroMQ_base64/ && python3 ZeroMQServer.py"
