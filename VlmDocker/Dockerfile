FROM nvidia/cuda:12.8.0-cudnn-runtime-ubuntu22.04

ENV DEBIAN_FRONTEND=noninteractive
WORKDIR /workspace

RUN sed -i 's@http://archive.ubuntu.com/ubuntu/@https://mirrors.tuna.tsinghua.edu.cn/ubuntu/@g' /etc/apt/sources.list && \
    sed -i 's@http://security.ubuntu.com/ubuntu/@https://mirrors.tuna.tsinghua.edu.cn/ubuntu/@g' /etc/apt/sources.list

RUN mkdir -p /root/.pip && \
    printf "[global]\nindex-url = https://pypi.tuna.tsinghua.edu.cn/simple\n" > /root/.pip/pip.conf

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    git \
    ca-certificates \
    wget \
    curl \
    python3 \
    python3-dev \
    python3-pip \
    python3-setuptools \
    python3-wheel \
    python3-pkg-resources \
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

RUN python3 -m pip install -U pip setuptools wheel

# Torch build must match the other GPU dockers (cu129).
RUN pip install torch==2.8.0 torchvision==0.23.0 torchaudio==2.8.0 --index-url https://download.pytorch.org/whl/cu129

# transformers>=5.9 is REQUIRED for the Qwen3.5-VL (qwen3_5) architecture; peft
# attaches the LoRA adapter at inference; accelerate provides device_map="auto".
RUN pip install --no-cache-dir \
    "transformers>=5.9.0" \
    "peft>=0.13.0" \
    "accelerate>=1.0.0" \
    "qwen-vl-utils>=0.0.8" \
    numpy \
    pillow \
    opencv-python \
    pyzmq \
    pyyaml

# Shared standard-protocol package (build context = repo root).
COPY protocol /opt/tjfusion_protocol
RUN python3 -m pip install --no-cache-dir "/opt/tjfusion_protocol[zmq]"

CMD ["/bin/bash"]
