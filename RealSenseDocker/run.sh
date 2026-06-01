#!/usr/bin/env bash
# Run the RealSense source server. Needs USB device access for the camera.
set -e

IMAGE="realsense:latest"
CONTAINER_NAME="realsense_tmp"

docker rm -f "${CONTAINER_NAME}" >/dev/null 2>&1 || true

# --privileged + /dev mount: required for RealSense USB enumeration.
# --net=host: REP(5550)/PUB(5551) reachable by the bridge and Fast-Foundation.
docker run -it --rm \
    --name "${CONTAINER_NAME}" \
    --net=host \
    --privileged \
    -v /dev:/dev \
    "${IMAGE}" \
    "$@"
