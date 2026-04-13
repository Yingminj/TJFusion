# 直接使用包含完整编译环境的 devel 镜像
FROM nvidia/cuda:12.8.0-cudnn-runtime-ubuntu22.04

ENV PYTHONUNBUFFERED=1 \
    DEBIAN_FRONTEND=noninteractive

# 0. 替换 Ubuntu apt 源为清华源
RUN sed -i 's|http://archive.ubuntu.com/ubuntu/|https://mirrors.tuna.tsinghua.edu.cn/ubuntu/|g' /etc/apt/sources.list && \
    sed -i 's|http://security.ubuntu.com/ubuntu/|https://mirrors.tuna.tsinghua.edu.cn/ubuntu/|g' /etc/apt/sources.list

# 1. 安装系统依赖
RUN apt-get update && apt-get install -y \
    python3 \
    python3-pip \
    python3-dev \
    git \
    ninja-build \
    openexr \
    libopenexr-dev \
    libgl1-mesa-glx \
    libglib2.0-0 \
    libusb-1.0-0 \
    wget \
    && rm -rf /var/lib/apt/lists/*

RUN apt-get update \
    && apt-get install -y wget gnupg2 ca-certificates \
    && wget https://developer.download.nvidia.com/compute/cuda/repos/ubuntu2204/x86_64/cuda-keyring_1.1-1_all.deb \
    && dpkg -i cuda-keyring_1.1-1_all.deb \
    && rm -f cuda-keyring_1.1-1_all.deb \
    && apt-get update \
    && apt-mark showhold | grep -E 'cuda|cublas|cufft|curand|cusolver|cusparse|npp|nvjpeg|nvjitlink|nvfatbin' | xargs -r apt-mark unhold \
    && apt-get install -y --allow-change-held-packages \
        libcublas-12-8=12.8.4.1-1 \
        libcublas-dev-12-8=12.8.4.1-1 \
        cuda-toolkit-12-8=12.8.1-1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /workspace

# 2. 配置 pip 清华源
RUN mkdir -p /root/.pip && \
    printf "[global]\nindex-url = https://pypi.tuna.tsinghua.edu.cn/simple\n" > /root/.pip/pip.conf

RUN python3 -m pip install --no-cache-dir -U pip setuptools wheel

RUN python3 -m pip install --no-cache-dir \
    torch==2.9.0 \
    torchvision==0.24.0 \
    torchaudio==2.9.0 \
    --index-url https://download.pytorch.org/whl/cu128 \
    -i https://pypi.tuna.tsinghua.edu.cn/simple
# 3. 安装基础的 pip 依赖
COPY requirements.txt .
RUN pip3 install --no-cache-dir -r requirements.txt

# 4. 【修改点】不再通过 pip 安装 cutoop，而是从宿主机物理复制
# 将宿主机准备好的 cutoop_pkg 复制到容器的 python 库路径
# COPY cutoop/ /usr/local/lib/python3.10/dist-packages/

# 5. 复制项目的所有代码
COPY FlowPose/ ./FlowPose/

# 6. 编译 pointnet2
WORKDIR /workspace/FlowPose/networks/pts_encoder/pointnet2_utils/pointnet2
ENV TORCH_CUDA_ARCH_LIST="7.5;8.0;8.6;8.9+PTX"
RUN python3 setup.py install

# 7. 切回工作目录
WORKDIR /workspace/FlowPose

# 8. 暴露端口并启动
EXPOSE 6666
CMD ["uvicorn", "server:workspace", "--host", "0.0.0.0", "--port", "6666"]
