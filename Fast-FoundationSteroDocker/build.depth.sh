#!/usr/bin/env bash
# Build the depth-only Fast-Foundation image. Context = REPO ROOT so the shared
# protocol/ package is included.
set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

cd "${REPO_ROOT}"
docker build -f Fast-FoundationSteroDocker/Dockerfile.depth -t ffs-depth:latest .
