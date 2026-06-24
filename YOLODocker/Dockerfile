# YOLODocker — standard-protocol `mask` server (GPU).
# Build context = REPO ROOT so the shared protocol/ package is included
# (see build.sh). Mirrors the SiglipDocker layout.
FROM nvidia/cuda:12.8.0-cudnn-runtime-ubuntu22.04

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /workspace

RUN sed -i 's@http://archive.ubuntu.com/ubuntu/@https://mirrors.tuna.tsinghua.edu.cn/ubuntu/@g' /etc/apt/sources.list && \
    sed -i 's@http://security.ubuntu.com/ubuntu/@https://mirrors.tuna.tsinghua.edu.cn/ubuntu/@g' /etc/apt/sources.list || true

RUN mkdir -p /root/.pip && \
    printf "[global]\nindex-url = https://pypi.tuna.tsinghua.edu.cn/simple\n" > /root/.pip/pip.conf

RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    curl \
    git \
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
    libzmq3-dev \
    ffmpeg \
    tmux \
    && rm -rf /var/lib/apt/lists/*

RUN ln -sf /usr/bin/python3 /usr/bin/python && \
    python -m pip install --upgrade pip setuptools wheel

# YOLO deps. ultralytics pulls a CUDA torch wheel automatically.
COPY YOLODocker/requirements.txt /workspace/requirements.txt
RUN python -m pip install -r /workspace/requirements.txt

# Shared standard-protocol package (build context = repo root).
COPY protocol /opt/tjfusion_protocol
RUN python -m pip install --no-cache-dir "/opt/tjfusion_protocol[zmq]"

COPY YOLODocker /workspace

CMD ["python", "Server/ZeroMQ/ZeroMQServer.py"]
