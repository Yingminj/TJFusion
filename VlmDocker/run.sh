#!/usr/bin/env bash
set -e

IMAGE_NAME="vlm:latest"
CONTAINER_NAME="vlm_container"

DATA_PATH="$(pwd)"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

# Weights are NOT baked into the image (base is ~19 GB). Mount them at runtime.
# Override with: WEIGHTS_DIR=/path/to/model ./run.sh
# The dir must contain the base weights + the LoRA adapter as referenced in
# config.yaml (default: qwen3_5_9B/ and gift_v1/).
WEIGHTS_DIR="${WEIGHTS_DIR:-/home/kewei/TJFusion/VlmDocker/model}"
if [ ! -d "${WEIGHTS_DIR}" ]; then
    echo "Error: WEIGHTS_DIR '${WEIGHTS_DIR}' not found." >&2
    echo "Set WEIGHTS_DIR=/path/to/model (must hold qwen3_5_9B/ and gift_v1/)." >&2
    exit 1
fi

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
    echo "Warning: NVIDIA runtime not detected; running without GPU flags (the 9B VLM needs a GPU)."
    GPU_FLAGS=""
    NVIDIA_ENV=""
fi

echo "Starting container..."

docker rm -f ${CONTAINER_NAME} 2>/dev/null || true

docker run -it --rm \
  --name ${CONTAINER_NAME} \
  ${GPU_FLAGS} \
  ${NVIDIA_ENV} \
  --network host \
  --ipc=host \
  -e TRANSFORMERS_OFFLINE=1 \
  -e HF_HUB_OFFLINE=1 \
  -e PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True \
  -v "${DATA_PATH}:${DATA_PATH}" \
  -v "$(pwd):/workspace" \
  -v "${WEIGHTS_DIR}:/workspace/model:ro" \
  -v "${REPO_ROOT}/protocol":/opt/tjfusion_protocol_src:ro \
  -w /workspace \
  ${IMAGE_NAME} \
  bash -lc 'cd /workspace && PYTHONPATH=/opt/tjfusion_protocol_src:${PYTHONPATH} python3 Server/StandardProtocol/vlm_server.py'
