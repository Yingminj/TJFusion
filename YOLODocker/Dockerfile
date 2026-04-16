FROM python:3.10-slim

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /workspace

# Switch Debian apt source to Aliyun
RUN sed -i 's|deb.debian.org|mirrors.aliyun.com|g; s|security.debian.org|mirrors.aliyun.com|g' /etc/apt/sources.list.d/debian.sources || true

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
    python -m pip install --upgrade pip setuptools wheel -i https://mirrors.aliyun.com/pypi/simple/ --trusted-host mirrors.aliyun.com; \
    if [ -f requirements.txt ]; then \
        pip install -r requirements.txt -i https://mirrors.aliyun.com/pypi/simple/ --trusted-host mirrors.aliyun.com; \
    else \
        pip install ultralytics opencv-python-headless -i https://mirrors.aliyun.com/pypi/simple/ --trusted-host mirrors.aliyun.com; \
    fi

# Copy source code
COPY . .

# Default server entrypoint
CMD ["python", "Server/ZeroMQ/ZeroMQServer.py"]
