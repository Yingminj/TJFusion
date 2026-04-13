#!/usr/bin/env bash

set -e

CONFIG_FILE="config.yaml"

# 1. Check if the configuration file exists
if [ ! -f "$CONFIG_FILE" ]; then
    echo "Error: Configuration file $CONFIG_FILE not found."
    exit 1
fi

# 2. Parse YAML file to read parameters (supports quoted/unquoted, case-insensitive)
# Extract the image parameter
IMAGE=$(grep -i -E '^[[:space:]]*image:' "$CONFIG_FILE" | awk -F: '{print $2}' | sed -e 's/^[[:space:]]*//' -e 's/["'\'']//g')

# Extract the container_name parameter
CONTAINER_NAME=$(grep -i -E '^[[:space:]]*container_name:' "$CONFIG_FILE" | awk -F: '{print $2}' | sed -e 's/^[[:space:]]*//' -e 's/["'\'']//g')

# 3. Perform string replacement: replace ${image} with the actual $IMAGE variable value
CONTAINER_NAME="${CONTAINER_NAME//\$\{image\}/$IMAGE}"

# 4. Verify if parameters were successfully read
if [ -z "$IMAGE" ] || [ -z "$CONTAINER_NAME" ]; then
    echo "Error: Failed to read IMAGE or CONTAINER_NAME from $CONFIG_FILE!"
    exit 1
fi

echo "Using image: ${IMAGE}"
echo "Container name: ${CONTAINER_NAME}"

# Grant X11 access
xhost +local:root >/dev/null 2>&1 || true

# Clean up any existing old container
docker rm -f "${CONTAINER_NAME}" >/dev/null 2>&1 || true

# Run the Docker container
docker run -it --rm \
    --name "${CONTAINER_NAME}" \
    --gpus all \
    --net=host \
    --ipc=host \
    --privileged \
    --device /dev:/dev \
    -e DISPLAY="${DISPLAY}" \
    -e QT_X11_NO_MITSHM=1 \
    -e NVIDIA_DRIVER_CAPABILITIES=all \
    -v /tmp/.X11-unix:/tmp/.X11-unix:rw \
    -v /dev:/dev \
    -v "$(pwd)":/workspace \
    -w /workspace \
    "${IMAGE}" \
    bash -lc "cd /workspace/Server/Sam3/ && python3 ZeroMQServer.py"