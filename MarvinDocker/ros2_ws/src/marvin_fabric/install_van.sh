#!/usr/bin/env bash
set -e

SERVICE_FILE="/etc/systemd/system/vcan.service"

# Check root permission
if [ "$EUID" -ne 0 ]; then
  echo "Please run as root: sudo bash install_vcan.sh"
  exit 1
fi

# Create the service file
cat << 'EOF' > $SERVICE_FILE
[Unit]
Description=Virtual CAN interfaces
After=network.target

[Service]
Type=oneshot
ExecStart=/sbin/modprobe vcan
ExecStart=/sbin/ip link add dev vcan0 type vcan
ExecStart=/sbin/ip link add dev vcan1 type vcan
ExecStart=/sbin/ip link set up vcan0
ExecStart=/sbin/ip link set up vcan1
RemainAfterExit=yes

[Install]
WantedBy=multi-user.target
EOF

# Enable and start the service
systemctl daemon-reload
systemctl enable vcan.service
systemctl start vcan.service

echo "✅ vcan.service installed and started successfully!"
echo "Use 'ip link show vcan*' to verify interfaces."
