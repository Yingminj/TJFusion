# YOLODocker — standard-protocol `mask` server (GPU).
# Built on tjfusion-gpu-base (torch 2.9.0 cu128 + common deps + protocol).
FROM tjfusion-gpu-base:latest

WORKDIR /workspace

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# YOLO-specific deps. ultralytics pulls its own deps; numpy/opencv-python/pyzmq/
# pyyaml/pillow already come from the base image.
COPY YOLODocker/requirements.txt /workspace/requirements.txt
RUN python -m pip install --no-cache-dir -r /workspace/requirements.txt

# ffmpeg for video decode support.
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

COPY YOLODocker /workspace

CMD ["python", "Server/ZeroMQ/ZeroMQServer.py"]
