#!/usr/bin/env bash
# Run the depth-only Fast-Foundation server (needs GPU; no camera).
set -e

IMAGE="ffs-depth:latest"
CONTAINER_NAME="ffs_depth_tmp"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

docker rm -f "${CONTAINER_NAME}" >/dev/null 2>&1 || true

GPU_ARGS=()
if command -v nvidia-container-runtime >/dev/null 2>&1; then
    GPU_ARGS+=(
        --runtime nvidia
        -e NVIDIA_DRIVER_CAPABILITIES=all
        -e NVIDIA_VISIBLE_DEVICES=all
    )
else
    echo "NVIDIA container runtime is unavailable." >&2
    echo "Install nvidia-container-toolkit before running the depth server." >&2
    exit 1
fi

# Mount model weights into /workspace/model (same layout as the original run.sh).
docker run -it --rm \
    --name "${CONTAINER_NAME}" \
    --net=host \
    --ipc=host \
    -v "${SCRIPT_DIR}/model":/workspace/model \
    "${GPU_ARGS[@]}" \
    "${IMAGE}" \
    "$@"
