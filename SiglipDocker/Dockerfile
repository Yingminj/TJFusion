# SiglipDocker — open-vocabulary state classification (`status`).
# Built on tjfusion-gpu-base (torch 2.9.0 cu128 + common deps + protocol).
# Adds the CUDA compiler (nvcc 12.9) for any JIT-compiled ops.
FROM tjfusion-gpu-base:latest

ENV DEBIAN_FRONTEND=noninteractive
WORKDIR /workspace

# Install CUDA compiler 12.9 (for any compilation needs).
RUN wget -q https://developer.download.nvidia.com/compute/cuda/repos/ubuntu2204/x86_64/cuda-keyring_1.1-1_all.deb -O /tmp/cuda-keyring.deb && \
    dpkg -i /tmp/cuda-keyring.deb && \
    rm -f /tmp/cuda-keyring.deb && \
    apt-get update && \
    apt-get install -y --no-install-recommends cuda-compiler-12-9 && \
    rm -rf /var/lib/apt/lists/*

# Siglip-specific pip deps (numpy / opencv-python / pyzmq / pyyaml / pillow come from base).
RUN python3 -m pip install --no-cache-dir \
    transformers \
    torchmetrics==1.7.3 \
    pyrealsense2

CMD ["/bin/bash"]
