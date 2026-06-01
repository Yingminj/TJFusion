# RealSenseDocker — camera source server (REP + PUB).
# The ONLY image that needs pyrealsense2. No torch / no CUDA model.
#
# IMPORTANT: build context must be the REPO ROOT (so the shared `protocol/`
# package is reachable). Use the provided build.sh, or:
#
#   docker build -f RealSenseDocker/Dockerfile -t realsense:latest .
#
FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive
WORKDIR /workspace

# Tsinghua mirror for apt
RUN sed -i 's@http://archive.ubuntu.com/ubuntu/@https://mirrors.tuna.tsinghua.edu.cn/ubuntu/@g' /etc/apt/sources.list && \
    sed -i 's@http://security.ubuntu.com/ubuntu/@https://mirrors.tuna.tsinghua.edu.cn/ubuntu/@g' /etc/apt/sources.list

# Tsinghua mirror for pip
RUN mkdir -p /root/.pip && \
    printf "[global]\nindex-url = https://pypi.tuna.tsinghua.edu.cn/simple\ntrusted-host = pypi.tuna.tsinghua.edu.cn\n" > /root/.pip/pip.conf

# System dependencies (USB for the camera, GL/zmq for opencv/zmq)
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    python3 \
    python3-dev \
    python3-pip \
    python3-setuptools \
    python3-wheel \
    libgl1 \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender1 \
    libxcb1 \
    libusb-1.0-0 \
    libzmq3-dev \
    pkg-config \
    tmux \
    && rm -rf /var/lib/apt/lists/*

RUN python3 -m pip install --no-cache-dir -U pip setuptools wheel

# Shared protocol package (copied from repo root build context).
COPY protocol /opt/tjfusion_protocol
RUN python3 -m pip install --no-cache-dir /opt/tjfusion_protocol

# RealSense server deps
COPY RealSenseDocker/requirements.txt /workspace/requirements.txt
RUN python3 -m pip install --no-cache-dir -r /workspace/requirements.txt

# Server code
COPY RealSenseDocker/Server /workspace/Server

# REP + PUB ports
EXPOSE 5550 5551

# Override args via `docker run ... <image> python3 Server/realsense_server.py --rep-bind ...`
CMD ["python3", "Server/realsense_server.py", \
     "--rep-bind", "tcp://0.0.0.0:5550", \
     "--pub-bind", "tcp://0.0.0.0:5551", \
     "--pub-streams", "color,ir_left,ir_right"]
