#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${PROJECT_ROOT}"

if [[ -t 1 ]]; then
  CYAN=$'\033[1;36m'
  GREEN=$'\033[1;32m'
  YELLOW=$'\033[1;33m'
  RED=$'\033[1;31m'
  RESET=$'\033[0m'
else
  CYAN=''
  GREEN=''
  YELLOW=''
  RED=''
  RESET=''
fi

LAUNCH_CONFIG="${FUSION_LAUNCH_CONFIG:-configs/docker_launch.yaml}"
export DOCKER_MODEL_ROOT="${DOCKER_MODEL_ROOT:-/home/kewei/TJFusion}"

print_info() {
  printf "%s\n" "${CYAN}[INFO]${RESET} $1"
}

print_ok() {
  printf "%s\n" "${GREEN}[OK]${RESET} $1"
}

print_warn() {
  printf "%s\n" "${YELLOW}[WARN]${RESET} $1"
}

print_err() {
  printf "%s\n" "${RED}[ERROR]${RESET} $1"
}

collect_ports_from_configs() {
  local cfg="$1"
  python - "$cfg" <<'PY'
import sys
from pathlib import Path

try:
    import yaml
except Exception:
    sys.exit(2)

cfg_path = Path(sys.argv[1]).expanduser()
if not cfg_path.exists():
    sys.exit(0)

ports: set[int] = set()
try:
    launch_cfg = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
except Exception:
    sys.exit(0)

docker_launcher = launch_cfg.get("docker_launcher") or {}
dashboard_cfg = docker_launcher.get("dashboard") or {}
dashboard_port = dashboard_cfg.get("port")
try:
    if dashboard_port is not None:
        ports.add(int(dashboard_port))
except Exception:
    pass

for bridge_entry in docker_launcher.get("bridges") or []:
    if not isinstance(bridge_entry, dict):
        continue
    bridge_cfg_raw = bridge_entry.get("config")
    if not bridge_cfg_raw:
        continue
    bridge_cfg_path = Path(bridge_cfg_raw).expanduser()
    if not bridge_cfg_path.is_absolute():
        bridge_cfg_path = (cfg_path.parent / bridge_cfg_path).resolve()
    if not bridge_cfg_path.exists():
        continue
    try:
        bridge_data = yaml.safe_load(bridge_cfg_path.read_text(encoding="utf-8")) or {}
    except Exception:
        continue
    bridge = bridge_data.get("bridge") or {}
    listen_port = bridge.get("listen_port")
    try:
        if listen_port is not None:
            ports.add(int(listen_port))
    except Exception:
        continue

for port in sorted(ports):
    if 0 < port <= 65535:
        print(port)
PY
}

kill_port_occupants() {
  local port="$1"
  local pids=()

  if command -v lsof >/dev/null 2>&1; then
    while IFS= read -r pid; do
      [[ -n "${pid}" ]] && pids+=("${pid}")
    done < <(lsof -t -iTCP:"${port}" -sTCP:LISTEN 2>/dev/null || true)
    if [[ "${#pids[@]}" -eq 0 ]]; then
      while IFS= read -r pid; do
        [[ -n "${pid}" ]] && pids+=("${pid}")
      done < <(lsof -t -i :"${port}" 2>/dev/null || true)
    fi
  elif command -v fuser >/dev/null 2>&1; then
    while IFS= read -r pid; do
      [[ -n "${pid}" ]] && pids+=("${pid}")
    done < <(fuser -n tcp "${port}" 2>/dev/null | tr ' ' '\n' || true)
  else
    print_warn "Neither lsof nor fuser is available, skip port check for ${port}."
    return
  fi

  if [[ "${#pids[@]}" -eq 0 ]]; then
    print_ok "Port ${port} is free."
    return
  fi

  local unique_pids=()
  local seen=" "
  for pid in "${pids[@]}"; do
    if [[ "${seen}" != *" ${pid} "* ]]; then
      unique_pids+=("${pid}")
      seen+="${pid} "
    fi
  done

  local killable_pids=()
  for pid in "${unique_pids[@]}"; do
    if [[ "${pid}" == "$$" || "${pid}" == "${PPID}" ]]; then
      continue
    fi
    killable_pids+=("${pid}")
  done
  if [[ "${#killable_pids[@]}" -eq 0 ]]; then
    print_warn "Port ${port} is occupied only by current launcher process. Skip killing."
    return
  fi

  print_warn "Port ${port} is occupied by PID(s): ${killable_pids[*]}. Trying to stop them..."
  for pid in "${killable_pids[@]}"; do
    kill -TERM "${pid}" 2>/dev/null || true
  done
  sleep 0.8
  for pid in "${killable_pids[@]}"; do
    if kill -0 "${pid}" 2>/dev/null; then
      kill -KILL "${pid}" 2>/dev/null || true
    fi
  done
  print_ok "Cleaned process(es) on port ${port}."
}

ports=()
if [[ -f "${LAUNCH_CONFIG}" ]]; then
  print_info "Reading launch config: ${LAUNCH_CONFIG}"
  ports_output="$(collect_ports_from_configs "${LAUNCH_CONFIG}" 2>/dev/null || true)"
  if [[ -n "${ports_output}" ]]; then
    while IFS= read -r port; do
      [[ -n "${port}" ]] && ports+=("${port}")
    done <<< "${ports_output}"
  fi
  if [[ "${#ports[@]}" -gt 0 ]]; then
    for port in "${ports[@]}"; do
      kill_port_occupants "${port}"
    done
  else
    print_info "No managed ports found in config; skip cleanup."
  fi
else
  print_warn "Launch config not found: ${LAUNCH_CONFIG}. Skip port cleanup."
fi

# The bridge needs the shared protocol package (tjfusion_protocol) for any
# pipeline node that declares a data_type. Add repo-root protocol/ to PYTHONPATH
# so the launcher and any bridge subprocess it spawns can import it without an
# install. (setup_fusion_env.sh also pip-installs it into the venv.)
REPO_ROOT="$(cd "${PROJECT_ROOT}/.." && pwd)"
export PYTHONPATH="src:${REPO_ROOT}/protocol${PYTHONPATH:+:${PYTHONPATH}}"
print_info "Starting launcher: PYTHONPATH=src:${REPO_ROOT}/protocol python -m fusion_docker launch-dockers $*"
exec python -m fusion_docker launch-dockers "$@"
