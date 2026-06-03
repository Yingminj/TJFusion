#!/usr/bin/env bash
# Build with the REPO ROOT as context so the shared protocol/ package is included.
set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

cd "${REPO_ROOT}"
docker build -f RealSenseDocker/Dockerfile -t realsense:latest .
