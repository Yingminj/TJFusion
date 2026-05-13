#!/usr/bin/env bash

set -e

IMAGE="ffs:latest"
CONTAINER_NAME="ffs_tmp"

xhost +local:root >/dev/null 2>&1 || true

docker rm -f "${CONTAINER_NAME}" >/dev/null 2>&1 || true

GPU_ARGS=()
if command -v nvidia-container-runtime >/dev/null 2>&1; then
    GPU_ARGS+=(
        --runtime nvidia
        -e NVIDIA_DRIVER_CAPABILITIES=all
        -e NVIDIA_VISIBLE_DEVICES=all
    )
elif [[ -e /dev/nvidia0 && -e /lib/x86_64-linux-gnu/libcuda.so.1 && -e /lib/x86_64-linux-gnu/libnvidia-ml.so.1 ]]; then
    GPU_ARGS+=(
        --device /dev/nvidia0
        --device /dev/nvidiactl
        --device /dev/nvidia-uvm
        -v /lib/x86_64-linux-gnu/libcuda.so.1:/lib/x86_64-linux-gnu/libcuda.so.1:ro
        -v /lib/x86_64-linux-gnu/libnvidia-ml.so.1:/lib/x86_64-linux-gnu/libnvidia-ml.so.1:ro
    )
else
    echo "NVIDIA container runtime is unavailable and manual GPU passthrough could not be configured." >&2
    echo "Install nvidia-container-toolkit or expose /dev/nvidia0 and libcuda.so.1 on the host." >&2
    exit 1
fi

docker run -it --rm \
    --name "${CONTAINER_NAME}" \
    --net=host \
    --ipc=host \
    --privileged \
    --device /dev:/dev \
    -e DISPLAY="${DISPLAY}" \
    -e QT_X11_NO_MITSHM=1 \
    -v /tmp/.X11-unix:/tmp/.X11-unix:rw \
    -v /dev:/dev \
    -v "$(pwd)":/workspace \
    -w /workspace \
    "${GPU_ARGS[@]}" \
    "${IMAGE}" \
    bash -lc "cd /workspace/Server/ZeroMQ_base64/ && python3 ZeroMQServer.py"