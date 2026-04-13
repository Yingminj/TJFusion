#!/usr/bin/env bash
set -e

IMAGE_NAME="senyun:latest"
CONTAINER_NAME="senyun_tmp"

docker rm -f "${CONTAINER_NAME}" 2>/dev/null || true

docker run --rm -it \
    --name "${CONTAINER_NAME}" \
    --network host \
    -v "$(pwd)":/workspace \
    -w /workspace \
    -e GST_PLUGIN_SCANNER=/usr/lib/x86_64-linux-gnu/gstreamer1.0/gstreamer-1.0/gst-plugin-scanner \
    -e GST_DEBUG=2 \
    "${IMAGE_NAME}" \
    python3 /workspace/Server/ZeroMQ/ZeroMQServer.py