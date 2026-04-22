FROM python:3.10-slim

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /workspace

# 切换 apt 为阿里云源，并安装基础工具
RUN set -eux; \
    sed -i 's@deb.debian.org@mirrors.aliyun.com@g' /etc/apt/sources.list.d/debian.sources; \
    apt-get update; \
    apt-get install -y --no-install-recommends ca-certificates curl; \
    rm -rf /var/lib/apt/lists/*

# 配置 pip 为阿里云源
RUN mkdir -p /root/.pip && \
    printf "[global]\nindex-url = https://mirrors.aliyun.com/pypi/simple/\ndefault-timeout = 300\ntrusted-host = mirrors.aliyun.com\n" > /root/.pip/pip.conf

# System deps commonly needed by OpenCV/YOLO
RUN apt-get update && apt-get install -y --no-install-recommends \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender1 \
    ffmpeg \
    git \
    && rm -rf /var/lib/apt/lists/*

# Install dependencies first for better layer cache
COPY requirements*.txt ./
RUN set -eux; \
    python -m pip install --upgrade pip setuptools wheel; \
    if [ -f requirements.txt ]; then \
        python -m pip install -r requirements.txt; \
    else \
        python -m pip install ultralytics opencv-python-headless; \
    fi

# Copy source code
COPY . /workspace

# Default server entrypoint
CMD ["python", "Server/ZeroMQ/ZeroMQServer.py"]