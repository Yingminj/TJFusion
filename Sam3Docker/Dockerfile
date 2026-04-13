FROM nvidia/cuda:12.8.0-cudnn-runtime-ubuntu22.04

ENV DEBIAN_FRONTEND=noninteractive
WORKDIR /workspace

# Use Tsinghua mirror for apt
RUN sed -i 's@http://archive.ubuntu.com/ubuntu/@https://mirrors.tuna.tsinghua.edu.cn/ubuntu/@g' /etc/apt/sources.list && \
    sed -i 's@http://security.ubuntu.com/ubuntu/@https://mirrors.tuna.tsinghua.edu.cn/ubuntu/@g' /etc/apt/sources.list

# Use Tsinghua mirror for pip
RUN mkdir -p /root/.pip && \
    printf "[global]\nindex-url = https://pypi.tuna.tsinghua.edu.cn/simple\ntrusted-host = pypi.tuna.tsinghua.edu.cn\n" > /root/.pip/pip.conf

# Install system dependencies
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
    libgtk2.0-dev \
    pkg-config \
    tmux \
    python3-tk \
    && rm -rf /var/lib/apt/lists/*

ENV CUDA_HOME=/usr/local/cuda
ENV PATH=${CUDA_HOME}/bin:${PATH}
ENV LD_LIBRARY_PATH=${CUDA_HOME}/lib64:${LD_LIBRARY_PATH}

RUN python3 --version

RUN python3 -m pip install --no-cache-dir -U pip setuptools wheel

RUN python3 -m pip install --no-cache-dir \
    torch==2.9.0 \
    torchvision==0.24.0 \
    torchaudio==2.9.0 \
    --index-url https://download.pytorch.org/whl/cu128 \
    -i https://pypi.tuna.tsinghua.edu.cn/simple
    
RUN python3 -m pip install --no-cache-dir \
    decord \
    psutil \
    flask

COPY ./sam3-main /workspace/sam3-main

WORKDIR /workspace/sam3-main
RUN python3 -m pip install --no-cache-dir -e .
RUN python3 -m pip install --no-cache-dir -e ".[notebooks]"
RUN python3 -m pip install --no-cache-dir -e ".[train,dev]"

WORKDIR /workspace
CMD ["/bin/bash"]
