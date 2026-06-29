# FlowPoseDocker — 6-DoF pose server (standard protocol).
# Built on tjfusion-gpu-base (torch 2.9.0 cu128 + common deps + protocol).
# Adds the CUDA compiler toolkit (nvcc) needed to build the pointnet2 extension.
FROM tjfusion-gpu-base:latest

# CUDA package series suffix (12.8 -> 12-8); must match the base image CUDA version.
ARG CUDA_PKG_SERIES=12-8

ENV PYTHONUNBUFFERED=1

# Install CUDA compiler toolkit (nvcc) for pointnet2 compilation.
# Don't pin patch versions — let apt resolve a mutually-compatible set within
# the ${CUDA_PKG_SERIES} series to avoid breakage when NVIDIA bumps versions.
RUN apt-get update \
    && apt-get install -y wget gnupg2 ca-certificates \
    && wget https://developer.download.nvidia.com/compute/cuda/repos/ubuntu2204/x86_64/cuda-keyring_1.1-1_all.deb \
    && dpkg -i cuda-keyring_1.1-1_all.deb \
    && rm -f cuda-keyring_1.1-1_all.deb \
    && apt-get update \
    && apt-mark showhold | grep -E 'cuda|cublas|cufft|curand|cusolver|cusparse|npp|nvjpeg|nvjitlink|nvfatbin' | xargs -r apt-mark unhold \
    && apt-get install -y --allow-change-held-packages \
        cuda-toolkit-${CUDA_PKG_SERIES} \
    && rm -rf /var/lib/apt/lists/*

# FlowPose-specific system deps for pointnet2 / OpenEXR.
RUN apt-get update && apt-get install -y --no-install-recommends \
    ninja-build \
    openexr \
    libopenexr-dev \
    libgl1-mesa-glx \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /workspace

# FlowPose-specific pip deps (numpy / opencv-python / pyzmq come from the base).
COPY FlowPoseDocker/requirements.txt .
RUN pip3 install --no-cache-dir -r requirements.txt

# Copy project code (build context = repo root).
COPY FlowPoseDocker/FlowPose/ ./FlowPose/

# Compile pointnet2 CUDA extension.
WORKDIR /workspace/FlowPose/networks/pts_encoder/pointnet2_utils/pointnet2
ENV TORCH_CUDA_ARCH_LIST="7.5;8.0;8.6;8.9+PTX"
RUN python3 setup.py install

WORKDIR /workspace

EXPOSE 6667
CMD ["python3", "Server/StandardProtocol/flowpose_server.py"]
