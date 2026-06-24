#!/usr/bin/env bash
# Run the YOLO standard-protocol `mask` server (GPU, REP on config server.port).
set -e

IMAGE="yolo:latest"
CONTAINER_NAME="yolo_tmp"

DATA_PATH="$(pwd)"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

docker rm -f "${CONTAINER_NAME}" >/dev/null 2>&1 || true

USE_NVIDIA=false
if [ -e /dev/nvidia0 ] || [ -e /dev/nvidiactl ]; then
    if command -v nvidia-smi >/dev/null 2>&1 && nvidia-smi -L >/dev/null 2>&1; then
        USE_NVIDIA=true
    fi
fi
if $USE_NVIDIA; then GPU_FLAGS="--gpus all"; else
    echo "Warning: NVIDIA runtime not detected; running without GPU flags."
    GPU_FLAGS=""
fi

# Live-mount the working dir (config + server) and the shared protocol package
# so edits take effect without an image rebuild.
docker run --rm -it \
  --name "${CONTAINER_NAME}" \
  ${GPU_FLAGS} \
  --network host \
  -v "${DATA_PATH}:/workspace" \
  -v "${REPO_ROOT}/protocol":/opt/tjfusion_protocol_src:ro \
  -w /workspace \
  "${IMAGE}" \
  bash -lc 'PYTHONPATH=/opt/tjfusion_protocol_src:${PYTHONPATH} python Server/ZeroMQ/ZeroMQServer.py'
