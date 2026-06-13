#!/usr/bin/env bash
set -euo pipefail

if [[ -t 1 ]]; then
  C_RESET='\033[0m'
  C_GREEN='\033[32m'
  C_YELLOW='\033[33m'
  C_RED='\033[31m'
  C_CYAN='\033[36m'
else
  C_RESET=''
  C_GREEN=''
  C_YELLOW=''
  C_RED=''
  C_CYAN=''
fi

log_info() { echo -e "${C_CYAN}$*${C_RESET}"; }
log_ok() { echo -e "${C_GREEN}$*${C_RESET}"; }
log_warn() { echo -e "${C_YELLOW}$*${C_RESET}"; }
log_err() { echo -e "${C_RED}$*${C_RESET}"; }

usage() {
  cat <<'USAGE'
Usage: ./setup_fusion_env.sh [options]

Only prepares Fusion local Python environment in current repository.
It will NOT clone/pull code, and will NOT install system packages.

Options:
  --venv-path=<path>      Virtualenv path (default: ./.venv-tjfusion)
  --python=<bin>          Python executable to use (default: auto detect >=3.11)
  --launcher-path=<path>  Launcher path (default: ./tjfusion-local)
  --sync                  Reinstall/sync python deps into venv
  -h, --help              Show this help
USAGE
}

has_cmd() {
  command -v "$1" >/dev/null 2>&1
}

python_ge_311() {
  local py_bin="$1"
  "$py_bin" - <<'PY' >/dev/null 2>&1
import sys
raise SystemExit(0 if sys.version_info >= (3, 11) else 1)
PY
}

select_python_bin() {
  local candidate
  for candidate in python3.12 python3.11 python3; do
    if ! has_cmd "$candidate"; then
      continue
    fi
    if python_ge_311 "$candidate"; then
      echo "$candidate"
      return 0
    fi
  done
  return 1
}

VENV_PATH="${PWD}/.venv-tjfusion"
PYTHON_BIN=""
LAUNCHER_PATH="${PWD}/tjfusion-local"
SYNC_DEPS="0"

for arg in "$@"; do
  case "$arg" in
    --venv-path=*) VENV_PATH="${arg#*=}" ;;
    --python=*) PYTHON_BIN="${arg#*=}" ;;
    --launcher-path=*) LAUNCHER_PATH="${arg#*=}" ;;
    --sync) SYNC_DEPS="1" ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      log_err "Unknown option: $arg"
      usage
      exit 1
      ;;
  esac
done

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FUSION_DIR="${REPO_ROOT}/FusionDocker"

if [[ ! -d "${FUSION_DIR}" ]]; then
  log_err "FusionDocker directory not found at: ${FUSION_DIR}"
  exit 1
fi

if [[ -n "${PYTHON_BIN}" ]]; then
  if ! has_cmd "${PYTHON_BIN}"; then
    log_err "Python binary not found: ${PYTHON_BIN}"
    exit 1
  fi
  if ! python_ge_311 "${PYTHON_BIN}"; then
    log_err "Python >= 3.11 is required, got: ${PYTHON_BIN}"
    exit 1
  fi
else
  PYTHON_BIN="$(select_python_bin || true)"
  if [[ -z "${PYTHON_BIN}" ]]; then
    log_err "Cannot find Python >= 3.11."
    log_warn "Please install python3.11+ and re-run."
    exit 1
  fi
fi

if [[ ! -d "${VENV_PATH}" ]]; then
  log_info "[setup] Creating virtualenv: ${VENV_PATH}"
  "${PYTHON_BIN}" -m venv "${VENV_PATH}"
  SYNC_DEPS="1"
else
  log_info "[setup] Reusing existing virtualenv: ${VENV_PATH}"
fi

if [[ "${SYNC_DEPS}" == "1" ]]; then
  log_info "[setup] Syncing Fusion dependencies in venv"
  "${VENV_PATH}/bin/python" -m pip install --upgrade pip setuptools wheel
  if [[ -f "${FUSION_DIR}/requirements.txt" ]]; then
    "${VENV_PATH}/bin/pip" install -r "${FUSION_DIR}/requirements.txt"
  fi
  # Shared protocol package: the bridge imports tjfusion_protocol for any
  # pipeline node that declares a data_type.
  if [[ -d "${REPO_ROOT}/protocol" ]]; then
    "${VENV_PATH}/bin/pip" install -e "${REPO_ROOT}/protocol"
  fi
  "${VENV_PATH}/bin/pip" install -e "${FUSION_DIR}"
else
  log_info "[setup] Skip dependency sync (use --sync to force update)"
fi

mkdir -p "$(dirname "${LAUNCHER_PATH}")"
cat > "${LAUNCHER_PATH}" <<EOF
#!/usr/bin/env bash
set -euo pipefail
exec "${VENV_PATH}/bin/python" -m fusion_docker "\$@"
EOF
chmod +x "${LAUNCHER_PATH}"

log_ok "[setup] Done"
log_info "[setup] Venv: ${VENV_PATH}"
log_info "[setup] Launcher: ${LAUNCHER_PATH}"
log_info "[setup] Try: ${LAUNCHER_PATH} --help"
