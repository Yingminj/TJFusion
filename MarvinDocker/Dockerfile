FROM ros:humble

SHELL ["/bin/bash", "-lc"]

ENV DEBIAN_FRONTEND=noninteractive

# 切换 apt 源为阿里云
RUN sed -i 's@http://archive.ubuntu.com@https://mirrors.aliyun.com@g' /etc/apt/sources.list \
 && sed -i 's@http://security.ubuntu.com@https://mirrors.aliyun.com@g' /etc/apt/sources.list

# 配置 pip 为阿里云源
RUN mkdir -p /root/.pip && \
    printf "[global]\nindex-url = https://mirrors.aliyun.com/pypi/simple/\ndefault-timeout = 300\ntrusted-host = mirrors.aliyun.com\n" > /root/.pip/pip.conf

# 安装基础依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3-pip \
    python3-colcon-common-extensions \
    python3-setuptools \
    python3-wheel \
    build-essential \
    tmux \
    git \
    curl \
    gnupg \
    lsb-release \
    ca-certificates \
    ros-humble-xacro \
    ros-humble-rviz2 \
    ros-humble-rqt \
    ros-humble-rqt-common-plugins \
    ros-dev-tools \
    ros-humble-pinocchio \
    ros-humble-urdf-launch \
    python3-zmq \
    && rm -rf /var/lib/apt/lists/*

# Python 依赖
COPY requirements.txt /tmp/requirements.txt
RUN python3 -m pip install --no-cache-dir -r /tmp/requirements.txt
RUN pip install --upgrade scipy && pip install "numpy<2"

# 工作空间目录
WORKDIR /ros2_ws
RUN mkdir -p /ros2_ws/src /ros2_ws/build /ros2_ws/install /ros2_ws/log

# 先复制源码
COPY ros2_ws/src /ros2_ws/src

# 再复制你的已有脚本
COPY scripts/build_ros.sh /ros2_ws/build_ros.sh
RUN chmod +x /ros2_ws/build_ros.sh

# build 阶段直接执行（强制在 /ros2_ws 下构建）
RUN /bin/bash -lc "set -eo pipefail; source /opt/ros/humble/setup.bash; cd /ros2_ws; /ros2_ws/build_ros.sh"

# 映射成系统命令
RUN ln -sf /ros2_ws/build_ros.sh /usr/local/bin/marvin_home

# 配置 tmux 滚动
RUN cat > /root/.tmux.conf <<'EOF_TMUX' && chmod 644 /root/.tmux.conf
set -g mouse on
set -g history-limit 100000
setw -g mode-keys vi
EOF_TMUX

# 运行时如果挂载空目录，自动补齐 ros2_ws 结构
CMD ["bash", "-lc", "mkdir -p /ros2_ws/src /ros2_ws/build /ros2_ws/install /ros2_ws/log && source /opt/ros/humble/setup.bash && bash"]
