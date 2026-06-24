#!/usr/bin/env bash
# Run the RealSense source server. Needs USB device access for the camera(s).
set -e

IMAGE="realsense:latest"
CONTAINER_NAME="realsense_tmp"

DATA_PATH="$(pwd)"

# Overall single/multi switch. Falls back to config.yaml's `mode` when empty.
TJFUSION_MODE="${TJFUSION_MODE:-}"

docker rm -f "${CONTAINER_NAME}" >/dev/null 2>&1 || true

# --privileged + /dev mount: required for RealSense USB enumeration (multi mode
# enumerates three devices, so all of /dev must be visible).
# --net=host: REP(5550)/PUB(5551) reachable by the bridge and Fast-Foundation.
# Live-mount the working dir so config.yaml edits take effect without a rebuild.
docker run -it --rm \
    --name "${CONTAINER_NAME}" \
    --net=host \
    --privileged \
    -v /dev:/dev \
    -v "${DATA_PATH}:/workspace" \
    -e TJFUSION_MODE="${TJFUSION_MODE}" \
    -w /workspace \
    "${IMAGE}" \
    "$@"
