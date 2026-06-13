#!/usr/bin/env bash
# Canonical entrypoint for the FusionDocker one-click launcher (it discovers
# services by `run.sh`). In the new split architecture Fast-Foundation is a
# pure depth estimator, so this delegates to the depth-only runner.
#
#   run.sh           → depth-only server   (ffs-depth:latest, this shim)
#   run.combined.sh  → legacy camera+depth (ffs:latest, retired)
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec "${SCRIPT_DIR}/run.depth.sh" "$@"
