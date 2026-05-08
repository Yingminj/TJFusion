#!/bin/bash
set -e
IP="${1:-192.168.13.190}"

# 允许容器访问本机 X11（只对本次会话生效）
xhost +local:docker >/dev/null
docker run -it --rm \
  --network host \
  --privileged \
  -e DISPLAY=$DISPLAY \
  -e ROS_DOMAIN_ID=13 \
  -e QT_X11_NO_MITSHM=1 \
  -e TERM=xterm-256color \
  -v /tmp/.X11-unix:/tmp/.X11-unix:rw \
  -v "$PWD/ros2_ws/src":/ros2_ws/src \
  -v "$PWD/scripts":/scripts \
  -v "./robotaction:/robotaction" \
  -w /ros2_ws \
  --name marvin_dev \
  marvinfabric:latest \
  bash -lc '
cat > /root/.tmux.conf <<EOF
set -g mouse on
set -g history-limit 100000
setw -g mode-keys vi
EOF
cat >> ~/.bashrc <<'EOF'
[ -f /opt/ros/humble/setup.bash ] && source /opt/ros/humble/setup.bash
[ -f /ros2_ws/install/setup.bash ] && source /ros2_ws/install/setup.bash
EOF
/scripts/StartAll.sh '"${IP}"'
'