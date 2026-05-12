#!/usr/bin/env bash
set -euo pipefail

# Use host network during build to avoid bridge iptables dependency on some Jetson hosts.
docker build --network=host -f Dockerfile.jetson -t sam3:jetson .