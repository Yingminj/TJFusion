FROM python:3.10-slim

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /workspace

COPY scripts/select_fastest_mirrors.sh /usr/local/bin/select_fastest_mirrors.sh
RUN set -eux; \
    chmod +x /usr/local/bin/select_fastest_mirrors.sh; \
    /usr/local/bin/select_fastest_mirrors.sh; \
    apt-get update

RUN set -eux; \
    apt-get update; \
    apt-get install -y --no-install-recommends ca-certificates curl; \
    rm -rf /var/lib/apt/lists/*

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
        pip install -r requirements.txt; \
    else \
        pip install ultralytics opencv-python-headless; \
    fi

# Copy source code
COPY ./ WORKDIR
# Default server entrypoint
CMD ["python", "Server/ZeroMQ/ZeroMQServer.py"]
