#!/usr/bin/env bash
# Build the two shared TJFusion base images.
#
#   tjfusion-base      — CPU-only base (ubuntu:22.04 + common deps + protocol)
#   tjfusion-gpu-base  — GPU base (cuda:12.8 + torch 2.9.0 cu128 + common deps + protocol)
#
# All 6 GPU model dockers (FFS, FlowPose, Sam3, Siglip, Vlm, YOLO) FROM
# tjfusion-gpu-base; RealSenseDocker FROM tjfusion-base. Building the bases once
# means torch (~2.5 GB) and the common system/pip deps are downloaded a single
# time instead of once per docker.
#
# Usage:
#   ./docker/build-base.sh              # build both if missing
#   ./docker/build-base.sh --rebuild    # force rebuild (no cache)
#   ./docker/build-base.sh --gpu-only   # only build the GPU base
#   ./docker/build-base.sh --cpu-only   # only build the CPU base
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

BUILD_CPU=1
BUILD_GPU=1
NO_CACHE=""

for arg in "$@"; do
  case "$arg" in
    --rebuild) NO_CACHE="--no-cache" ;;
    --gpu-only) BUILD_CPU=0 ;;
    --cpu-only) BUILD_GPU=0 ;;
    -h|--help)
      cat <<USAGE
Usage: $0 [options]

Options:
  --rebuild     Force rebuild without Docker cache
  --gpu-only    Only build tjfusion-gpu-base
  --cpu-only    Only build tjfusion-base
  -h, --help    Show this help
USAGE
      exit 0 ;;
    *) echo "Unknown option: $arg" >&2; exit 1 ;;
  esac
done

cd "${REPO_ROOT}"

if [[ "$BUILD_CPU" -eq 1 ]]; then
  echo ">>> Building tjfusion-base:latest ..."
  docker build ${NO_CACHE} -f docker/Dockerfile.base -t tjfusion-base:latest .
  echo ">>> tjfusion-base:latest ready."
fi

if [[ "$BUILD_GPU" -eq 1 ]]; then
  echo ">>> Building tjfusion-gpu-base:latest ..."
  docker build ${NO_CACHE} -f docker/Dockerfile.gpu-base -t tjfusion-gpu-base:latest .
  echo ">>> tjfusion-gpu-base:latest ready."
fi

echo ">>> Done. GPU dockers can now use 'FROM tjfusion-gpu-base:latest'."
