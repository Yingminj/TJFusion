#!/usr/bin/env bash
# Canonical build for the FusionDocker one-click launcher (auto-build uses
# `build.sh`). Builds the depth-only image with the repo root as context so the
# shared protocol/ package is included.
#
#   build.sh           → ffs-depth:latest (depth-only, this shim)
#   build.combined.sh  → ffs:latest       (legacy camera+depth, retired)
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec "${SCRIPT_DIR}/build.depth.sh" "$@"
