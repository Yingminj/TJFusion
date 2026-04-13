FROM ros:humble

SHELL ["/bin/bash", "-lc"]

ENV DEBIAN_FRONTEND=noninteractive

# 切换 apt 源为清华
RUN sed -i 's@http://archive.ubuntu.com@https://mirrors.tuna.tsinghua.edu.cn@g' /etc/apt/sources.list \
 && sed -i 's@http://security.ubuntu.com@https://mirrors.tuna.tsinghua.edu.cn@g' /etc/apt/sources.list

# 配置 pip 为清华源
RUN mkdir -p /root/.pip && \
    printf "[global]\nindex-url = https://pypi.tuna.tsinghua.edu.cn/simple\ndefault-timeout = 300\ntrusted-host = pypi.tuna.tsinghua.edu.cn\n" > /root/.pip/pip.conf

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

# 先复制源码
COPY ros2_ws/src /ros2_ws/src

# 再复制你的已有脚本
COPY ros2_ws/build_ros.sh /ros2_ws/build_ros.sh
RUN chmod +x /ros2_ws/build_ros.sh

# build 阶段直接执行
RUN /bin/bash -lc "source /opt/ros/humble/setup.bash && /ros2_ws/build_ros.sh"

# 映射成系统命令
RUN ln -sf /ros2_ws/build_ros.sh /usr/local/bin/marvin_home

# 配置 tmux 滚动
RUN cat > /root/.tmux.conf <<'EOF' && chmod 644 /root/.tmux.conf
set -g mouse on
set -g history-limit 100000
setw -g mode-keys vi
EOF

CMD ["bash", "-lc", "source /opt/ros/humble/setup.bash && bash"]