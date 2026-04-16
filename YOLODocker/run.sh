#!/usr/bin/env bash
set -e

docker run --rm -it \
  --name yolo_tmp \
  --gpus all \
  --network host \
  -v $(pwd):/workspace \
  -e DISPLAY="$DISPLAY" \
  -v /tmp/.X11-unix:/tmp/.X11-unix:rw \
  yolo
