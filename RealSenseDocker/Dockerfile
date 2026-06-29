# RealSenseDocker — camera source server (REP + PUB).
# Uses the shared CPU-only tjfusion-base image (common system libs + protocol +
# numpy/pyzmq/pyyaml/opencv-python already installed).
FROM tjfusion-base:latest

WORKDIR /workspace

# RealSense-specific deps only (everything else comes from the base image).
COPY RealSenseDocker/requirements.txt /workspace/requirements.txt
RUN python3 -m pip install --no-cache-dir -r /workspace/requirements.txt

COPY RealSenseDocker/Server /workspace/Server
COPY RealSenseDocker/config.yaml /workspace/config.yaml

EXPOSE 5550 5551

# Streams/binds/mode are read from /workspace/config.yaml (+ $TJFUSION_MODE).
CMD ["python3", "Server/realsense_server.py", "--config", "/workspace/config.yaml"]
