#!/bin/bash
set -euo pipefail

TAG="${1:-marvinfabric:latest}"
NO_CACHE="${NO_CACHE:-0}"

BUILD_ARGS=()
if [ "${NO_CACHE}" = "1" ]; then
	BUILD_ARGS+=("--no-cache")
fi

docker build "${BUILD_ARGS[@]}" -t "${TAG}" .