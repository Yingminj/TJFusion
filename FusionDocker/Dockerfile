FROM ros:humble-ros-base-jammy

WORKDIR /app

SHELL ["/bin/bash", "-lc"]

ENV DEBIAN_FRONTEND=noninteractive
ENV ROS_DISTRO=humble
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app/src

RUN sed -i 's|http://archive.ubuntu.com/ubuntu/|https://mirrors.aliyun.com/ubuntu/|g' /etc/apt/sources.list && \
    sed -i 's|http://security.ubuntu.com/ubuntu/|https://mirrors.aliyun.com/ubuntu/|g' /etc/apt/sources.list && \
    apt-get update && apt-get install -y --no-install-recommends \
    python3-pip \
    python-is-python3 \
    python3-numpy \
    python3-opencv \
    ros-humble-tf2-msgs \
    ros-humble-geometry-msgs \
    ros-humble-std-msgs && \
    python -m pip config set global.index-url https://mirrors.aliyun.com/pypi/simple/ && \
    python -m pip config set install.trusted-host mirrors.aliyun.com && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
RUN python -m pip install --no-cache-dir --upgrade pip && \
    python -m pip install --no-cache-dir -r requirements.txt

COPY src ./src
COPY configs ./configs
COPY scripts ./scripts

CMD ["bash", "-lc", "source /opt/ros/humble/setup.bash && python -m fusion_docker serve-fusion"]
