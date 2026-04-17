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

# One-shot installer for tjfusion.
# Features:
# 1) Install base environment (git/python3/pip/venv when possible)
# 2) Clone/pull repository from git (optional)
# 3) Create venv + install FusionDocker dependencies
# 4) Install tjfusion launcher + bash/zsh completions
#
# Usage examples:
#   ./install.sh
#   ./install.sh --repo-url https://github.com/<you>/<repo>.git --clone-dir "$HOME/Downloads/DockerModel"
#   ./install.sh --system
#   ./install.sh --local --skip-clone

MODE="local"               # cwd | local | system
REPO_URL="https://github.com/yangzhaofeng496/TJFusion.git"
CLONE_DIR="$PWD"
SKIP_CLONE="0"
SKIP_ENV_INSTALL="0"
VERBOSE="0"
LOG_FILE="/tmp/tjfusion-install-$(date +%Y%m%d-%H%M%S).log"

_strip_conda_from_path() {
  local src_path="$1"
  local cleaned=""
  local seg
  local path_parts=()
  IFS=':' read -r -a path_parts <<< "$src_path"
  for seg in "${path_parts[@]}"; do
    case "$seg" in
      *conda*|*anaconda*|*miniconda*) continue ;;
    esac
    [[ -z "$seg" ]] && continue
    if [[ -z "$cleaned" ]]; then
      cleaned="$seg"
    else
      cleaned="${cleaned}:$seg"
    fi
  done
  echo "$cleaned"
}

reexec_without_conda_if_needed() {
  [[ "${TJ_NO_CONDA_REEXEC:-0}" == "1" ]] && return 0
  if [[ -z "${CONDA_PREFIX:-}" && "${CONDA_SHLVL:-0}" == "0" ]]; then
    return 0
  fi

  local conda_name="${CONDA_DEFAULT_ENV:-${CONDA_PREFIX:-unknown}}"
  local cleaned_path
  cleaned_path="$(_strip_conda_from_path "${PATH:-}")"

  log_warn "[install] Detected active Conda env before install: ${conda_name}"
  log_warn "[install] Restarting installer outside Conda now..."

  exec env \
    -u CONDA_PREFIX \
    -u CONDA_DEFAULT_ENV \
    -u CONDA_PROMPT_MODIFIER \
    -u CONDA_SHLVL \
    -u _CE_CONDA \
    -u _CE_M \
    -u CONDA_EXE \
    -u CONDA_PYTHON_EXE \
    TJ_NO_CONDA_REEXEC=1 \
    PATH="${cleaned_path}" \
    bash "$0" "$@"
}

for arg in "$@"; do
  case "$arg" in
    --cwd) MODE="cwd" ;;
    --local) MODE="local" ;;
    --system) MODE="system" ;;
    --verbose) VERBOSE="1" ;;
    --skip-clone) SKIP_CLONE="1" ;;
    --skip-env-install) SKIP_ENV_INSTALL="1" ;;
    --repo-url=*) REPO_URL="${arg#*=}" ;;
    --clone-dir=*) CLONE_DIR="${arg#*=}" ;;
    -h|--help)
      cat <<'USAGE'
Usage: ./install.sh [options]

Options:
  --cwd                   Install launcher to current directory
  --local                 Install launcher to ~/.local/bin (default)
  --system                Install launcher to /usr/local/bin
  --verbose               Show full command output instead of concise logs
  --repo-url=<git_url>    Git repository URL for clone/pull (default: https://github.com/yangzhaofeng496/TJFusion.git)
  --clone-dir=<path>      Where to clone repository (default: current directory)
  --skip-clone            Skip git clone/pull step
  --skip-env-install      Skip system package auto-install step
  -h, --help              Show this help
USAGE
      exit 0
      ;;
    *)
      echo "Unknown option: $arg" >&2
      exit 1
      ;;
  esac
done

reexec_without_conda_if_needed "$@"

run_with_privilege() {
  if [[ "$(id -u)" -eq 0 ]]; then
    "$@"
  elif command -v sudo >/dev/null 2>&1; then
    sudo "$@"
  else
    return 1
  fi
}

has_cmd() {
  command -v "$1" >/dev/null 2>&1
}

force_deactivate_conda() {
  local had_conda=0
  local conda_name="${CONDA_DEFAULT_ENV:-${CONDA_PREFIX:-unknown}}"
  if [[ -n "${CONDA_PREFIX:-}" || "${CONDA_SHLVL:-0}" != "0" ]]; then
    had_conda=1
  fi
  [[ "$had_conda" -eq 0 ]] && return 0

  log_warn "[install] Detected active Conda env: ${conda_name}"
  log_warn "[install] Conda will be disabled for this installer process."

  if declare -F conda >/dev/null 2>&1; then
    while [[ "${CONDA_SHLVL:-0}" -gt 0 ]]; do
      conda deactivate >/dev/null 2>&1 || break
    done
  fi

  local cleaned_path=""
  local seg
  local path_parts=()
  IFS=':' read -r -a path_parts <<< "${PATH:-}"
  for seg in "${path_parts[@]}"; do
    case "$seg" in
      *conda*|*anaconda*|*miniconda*) continue ;;
    esac
    [[ -z "$seg" ]] && continue
    if [[ -z "$cleaned_path" ]]; then
      cleaned_path="$seg"
    else
      cleaned_path="${cleaned_path}:$seg"
    fi
  done
  if [[ -n "$cleaned_path" ]]; then
    PATH="$cleaned_path"
    export PATH
  fi

  unset CONDA_PREFIX CONDA_DEFAULT_ENV CONDA_PROMPT_MODIFIER CONDA_SHLVL
  unset _CE_CONDA _CE_M CONDA_EXE CONDA_PYTHON_EXE

  log_warn "[install] Conda disabled. Installer now uses non-Conda Python lookup."
  log_info "[install] Tip: run 'conda deactivate' in your current shell after install."
}

run_step() {
  local step="$1"
  shift
  if [[ "$VERBOSE" == "1" ]]; then
    log_info "[install] ${step}"
    "$@"
    return $?
  fi
  log_info "[install] ${step} (简洁模式，详细日志: ${LOG_FILE})"
  if "$@" >>"$LOG_FILE" 2>&1; then
    return 0
  fi
  log_err "[install] ${step} failed. Last 80 log lines:"
  tail -n 80 "$LOG_FILE" || true
  return 1
}

install_base_env_if_needed() {
  [[ "$SKIP_ENV_INSTALL" == "1" ]] && return 0

  local need_git=0 need_py=0 need_pip=0 need_venv=0
  has_cmd git || need_git=1
  has_cmd python3 || need_py=1
  has_cmd pip3 || need_pip=1
  if has_cmd python3; then
    python3 -m venv --help >/dev/null 2>&1 || need_venv=1
  else
    need_venv=1
  fi

  if [[ "$need_git" -eq 0 && "$need_py" -eq 0 && "$need_pip" -eq 0 && "$need_venv" -eq 0 ]]; then
    return 0
  fi

  log_info "[install] Missing dependencies detected. Trying to install via package manager..."

  if has_cmd apt-get; then
    run_step "apt update" run_with_privilege apt-get -o Acquire::ForceIPv4=true -qq update
    run_step "apt install base dependencies" run_with_privilege env DEBIAN_FRONTEND=noninteractive apt-get install -y -qq git python3 python3-pip python3-venv
  elif has_cmd dnf; then
    run_step "dnf install base dependencies" run_with_privilege dnf install -y git python3 python3-pip python3-virtualenv
  elif has_cmd yum; then
    run_step "yum install base dependencies" run_with_privilege yum install -y git python3 python3-pip
  elif has_cmd pacman; then
    run_step "pacman install base dependencies" run_with_privilege pacman -Sy --noconfirm git python python-pip
  elif has_cmd zypper; then
    run_step "zypper install base dependencies" run_with_privilege zypper --non-interactive install git python3 python3-pip python3-virtualenv
  elif has_cmd brew; then
    run_step "brew install base dependencies" brew install git python
  else
    log_err "[install] No supported package manager found."
    log_warn "Please install manually: git, python3, pip3, python3-venv"
    exit 1
  fi
}

resolve_repo_root() {
  local script_dir
  script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

  if [[ -d "${script_dir}/FusionDocker/src" ]]; then
    echo "${script_dir}"
    return 0
  fi

  if [[ -d "${script_dir}/src/fusion_docker" ]]; then
    echo "$(cd "${script_dir}/.." && pwd)"
    return 0
  fi

  if [[ -d "${CLONE_DIR}/FusionDocker/src" ]]; then
    echo "${CLONE_DIR}"
    return 0
  fi

  echo ""
}

clone_or_update_repo() {
  [[ "$SKIP_CLONE" == "1" ]] && return 0

  local repo_root
  repo_root="$(resolve_repo_root)"
  if [[ -n "$repo_root" ]]; then
    if [[ -d "${repo_root}/.git" ]]; then
      log_info "[install] Existing git repo found: ${repo_root}. Running git pull..."
      (cd "$repo_root" && git pull --ff-only || true)
    fi
    return 0
  fi

  if [[ -z "$REPO_URL" ]]; then
    log_err "[install] Repo not found locally, and --repo-url not provided."
    log_warn "Please re-run with: --repo-url=<git_url>"
    exit 1
  fi

  local target_dir="$CLONE_DIR"
  local repo_name
  repo_name="$(basename "${REPO_URL%.git}")"

  if [[ -d "$target_dir" ]]; then
    if [[ -d "$target_dir/.git" ]]; then
      log_info "[install] Existing git repo found at ${target_dir}. Running git pull..."
      (cd "$target_dir" && git pull --ff-only || true)
      CLONE_DIR="$target_dir"
      return 0
    fi
    if [[ -n "$(ls -A "$target_dir" 2>/dev/null || true)" ]]; then
      target_dir="${target_dir}/${repo_name}"
      if [[ -d "$target_dir/.git" ]]; then
        log_info "[install] Existing git repo found at ${target_dir}. Running git pull..."
        (cd "$target_dir" && git pull --ff-only || true)
        CLONE_DIR="$target_dir"
        return 0
      fi
      if [[ -e "$target_dir" && -n "$(ls -A "$target_dir" 2>/dev/null || true)" ]]; then
        log_err "[install] Target clone path exists and is not empty: ${target_dir}"
        log_warn "Please pass an empty --clone-dir or remove that folder first."
        exit 1
      fi
    fi
  fi

  log_info "[install] Cloning repository from ${REPO_URL} to ${target_dir}"
  git clone "$REPO_URL" "$target_dir"
  CLONE_DIR="$target_dir"
}

setup_python_env() {
  local repo_root="$1"
  local fusion_dir="${repo_root}/FusionDocker"
  local venv_dir="${repo_root}/.venv-tjfusion"

  if [[ ! -d "$fusion_dir" ]]; then
    log_err "[install] FusionDocker directory not found under ${repo_root}"
    exit 1
  fi

  log_info "[install] Creating virtualenv: ${venv_dir}"
  python3 -m venv "$venv_dir"

  log_info "[install] Installing Python dependencies..."
  "$venv_dir/bin/python" -m pip install --upgrade pip setuptools wheel
  if [[ -f "${fusion_dir}/requirements.txt" ]]; then
    "$venv_dir/bin/pip" install -r "${fusion_dir}/requirements.txt"
  fi
  "$venv_dir/bin/pip" install -e "$fusion_dir"

  echo "$venv_dir"
}

append_if_missing() {
  local file="$1"
  local marker_start="$2"
  local marker_end="$3"
  local payload="$4"

  touch "$file"
  if grep -Fq "$marker_start" "$file"; then
    return 0
  fi

  {
    echo ""
    echo "$marker_start"
    echo "$payload"
    echo "$marker_end"
  } >> "$file"
}

install_launcher() {
  local venv_dir="$1"
  local target=""
  local tmp
  tmp="$(mktemp)"

  cat > "$tmp" <<EOF2
#!/usr/bin/env bash
set -euo pipefail
exec "${venv_dir}/bin/python" -m fusion_docker "\$@"
EOF2
  chmod +x "$tmp"

  case "$MODE" in
    cwd)
      target="$(pwd)/tjfusion"
      install -m 0755 "$tmp" "$target"
      ;;
    system)
      target="/usr/local/bin/tjfusion"
      if [[ -w "/usr/local/bin" ]]; then
        install -m 0755 "$tmp" "$target"
      elif run_with_privilege install -m 0755 "$tmp" "$target"; then
        :
      else
        log_err "[install] Cannot write to /usr/local/bin. Try --local."
        rm -f "$tmp"
        exit 1
      fi
      ;;
    local)
      mkdir -p "$HOME/.local/bin"
      target="$HOME/.local/bin/tjfusion"
      install -m 0755 "$tmp" "$target"
      ;;
  esac

  rm -f "$tmp"
  echo "$target"
}

install_bash_completion() {
  local completion_file="$HOME/.tjfusion.bash"
  cat > "$completion_file" <<'EOF2'
_tjfusion_complete() {
  local cur
  cur="${COMP_WORDS[COMP_CWORD]}"
  local cmds="start update list-dockers serve-fusion serve-bridge launch-dockers docker-select serve-ui list-bridges inspect-docker-io list-docker-ports inspect-ports listen-zmq test-bridge create-system create-bridge add-bridge-to-ui"
  COMPREPLY=( $(compgen -W "$cmds" -- "$cur") )
}
complete -F _tjfusion_complete tjfusion
EOF2

  append_if_missing "$HOME/.bashrc" "# >>> tjfusion bash completion >>>" "# <<< tjfusion bash completion <<<" '[ -f "$HOME/.tjfusion.bash" ] && source "$HOME/.tjfusion.bash"'
}

install_zsh_completion() {
  local zfunc_dir="$HOME/.zfunc"
  local completion_file="$zfunc_dir/_tjfusion"
  mkdir -p "$zfunc_dir"

  cat > "$completion_file" <<'EOF2'
#compdef tjfusion

_tjfusion() {
  local -a cmds
  cmds=(
    'start:Start all dockers configured in docker_launch.yaml'
    'update:Pull latest code and refresh python package'
    'list-dockers:List runnable docker folders'
    'serve-fusion:Run FusionDocker event service (develop/debug)'
    'serve-bridge:Run ZeroMQ RGB-D bridge service (develop/debug)'
    'launch-dockers:Launch docker run.sh scripts (develop/debug)'
    'docker-select:Write selected dockers into docker_launch.yaml (develop/debug)'
    'serve-ui:Serve web dashboard (develop/debug)'
    'list-bridges:List bridge types (develop/debug)'
    'inspect-docker-io:Inspect docker input/output schema (develop/debug)'
    'list-docker-ports:List docker ports from config (develop/debug)'
    'inspect-ports:Inspect listening ports (develop/debug)'
    'listen-zmq:Subscribe to ZMQ PUB endpoint (develop/debug)'
    'test-bridge:Send synthetic RGB-D request (develop/debug)'
    'create-system:Create DockerModel system scaffold (develop/debug)'
    'create-bridge:Create bridge scaffold (develop/debug)'
    'add-bridge-to-ui:Add bridge entry to docker_launch.yaml (develop/debug)'
  )
  _arguments '1:command:->cmds' '*::arg:->args'
  case $state in
    cmds)
      _describe 'tjfusion command' cmds
      ;;
  esac
}

_tjfusion "$@"
EOF2

  append_if_missing "$HOME/.zshrc" "# >>> tjfusion zsh completion >>>" "# <<< tjfusion zsh completion <<<" $'fpath=("$HOME/.zfunc" $fpath)\nautoload -Uz compinit\ncompinit'
}

ensure_local_path() {
  append_if_missing "$HOME/.bashrc" "# >>> tjfusion path >>>" "# <<< tjfusion path <<<" 'export PATH="$HOME/.local/bin:$PATH"'
  append_if_missing "$HOME/.zshrc" "# >>> tjfusion path >>>" "# <<< tjfusion path <<<" 'export PATH="$HOME/.local/bin:$PATH"'
}

check_docker_install() {
  log_info "[check] Docker installation"
  if ! has_cmd docker; then
    log_err "  - docker: NOT FOUND"
    log_warn "  - suggestion: sudo apt update && sudo apt install -y docker.io docker-compose-plugin"
    log_warn "  - suggestion: sudo systemctl enable docker && sudo systemctl start docker"
    return 0
  fi

  log_ok "  - docker: $(docker --version 2>/dev/null || echo 'installed (version query failed)')"
  if docker compose version >/dev/null 2>&1; then
    log_ok "  - docker compose: OK"
  else
    log_warn "  - docker compose: NOT AVAILABLE (install docker-compose-plugin)"
  fi

  if docker info >/dev/null 2>&1; then
    log_ok "  - docker daemon: reachable"
    local test_image="hello-world:latest"
    local existed_before=0
    local pull_ok=0
    local attempt=1
    if docker image inspect "$test_image" >/dev/null 2>&1; then
      existed_before=1
    fi
    while [[ "$attempt" -le 5 ]]; do
      if docker pull "$test_image" >/dev/null 2>&1; then
        pull_ok=1
        break
      fi
      log_warn "  - docker pull test (${test_image}) failed (attempt ${attempt}/5), retry in 1s..."
      sleep 1
      attempt=$((attempt + 1))
    done
    if [[ "$pull_ok" -eq 1 ]]; then
      log_ok "  - docker pull test (${test_image}): OK"
      if [[ "$existed_before" -eq 0 ]]; then
        if docker rmi "$test_image" >/dev/null 2>&1; then
          log_ok "  - docker cleanup (${test_image}): removed"
        else
          log_warn "  - docker cleanup (${test_image}): failed to remove (manual cleanup may be needed)"
        fi
      else
        log_info "  - docker cleanup: skipped (image existed before test)"
      fi
    else
      log_err "  - docker pull test (${test_image}): FAILED after 5 attempts"
      log_warn "  - suggestion: check proxy/registry network and docker daemon proxy settings"
    fi
  else
    log_err "  - docker daemon: not reachable by current user"
    log_warn "  - suggestion: sudo systemctl restart docker"
    log_warn "  - suggestion: sudo usermod -aG docker \$USER && newgrp docker"
  fi
}

check_docker_gpu() {
  echo "[check] Docker GPU support"
  if ! has_cmd docker; then
    echo "  - skipped (docker not installed)"
    return 0
  fi

  if has_cmd nvidia-smi && nvidia-smi >/dev/null 2>&1; then
    echo "  - host nvidia-smi: OK"
  else
    echo "  - host nvidia-smi: NOT AVAILABLE"
    echo "  - suggestion: install NVIDIA driver first"
  fi

  if docker info 2>/dev/null | grep -qiE 'Runtimes:.*nvidia|nvidia'; then
    echo "  - nvidia runtime in docker: detected"
  else
    echo "  - nvidia runtime in docker: NOT detected"
    echo "  - suggestion: install nvidia-container-toolkit and run:"
    echo "    sudo nvidia-ctk runtime configure --runtime=docker && sudo systemctl restart docker"
  fi

  local cuda_image="nvidia/cuda:12.3.1-base-ubuntu22.04"
  if docker image inspect "$cuda_image" >/dev/null 2>&1; then
    if docker run --rm --gpus all "$cuda_image" nvidia-smi >/dev/null 2>&1; then
      echo "  - container GPU test: OK"
    else
      echo "  - container GPU test: FAILED"
    fi
  else
    echo "  - container GPU test: skipped (image not local: $cuda_image)"
    echo "  - tip: docker run --rm --gpus all $cuda_image nvidia-smi"
  fi
}

check_proxy_config() {
  echo "[check] Proxy configuration"
  local has_env_proxy=0
  for k in HTTP_PROXY HTTPS_PROXY ALL_PROXY http_proxy https_proxy all_proxy; do
    if [[ -n "${!k:-}" ]]; then
      echo "  - env $k=${!k}"
      has_env_proxy=1
    fi
  done
  if [[ "$has_env_proxy" -eq 0 ]]; then
    echo "  - env proxy: NOT SET"
  fi

  local docker_proxy_file="/etc/systemd/system/docker.service.d/http-proxy.conf"
  if [[ -f "$docker_proxy_file" ]]; then
    echo "  - docker daemon proxy file: $docker_proxy_file (found)"
  else
    echo "  - docker daemon proxy file: NOT FOUND"
    echo "  - suggestion: create $docker_proxy_file"
  fi

  if has_cmd systemctl; then
    local env_line
    env_line="$(systemctl show --property=Environment docker 2>/dev/null || true)"
    if [[ -n "$env_line" ]]; then
      echo "  - systemctl docker environment: ${env_line}"
    else
      echo "  - systemctl docker environment: unavailable (permission or docker service missing)"
    fi
  fi

  echo "  - recommendation: 建议安装并开启稳定梯子/代理（如 Clash/V2Ray），可显著提升 git clone / docker pull / pip install 成功率。"
}

list_docker_folders() {
  local root="$1"
  log_info "[scan] Downloaded Docker folders under: $root"
  local found=0
  while IFS= read -r line; do
    found=1
    log_info "  - $line"
  done < <(
    find "$root" -mindepth 1 -maxdepth 2 -type d \
      \( -name '*Docker' -o -name '*docker' \) \
      | sed "s#^$root/##" | sort
  )
  if [[ "$found" -eq 0 ]]; then
    log_warn "  - (none found by *Docker naming)"
  fi
}

list_git_repos() {
  local root="$1"
  log_info "[scan] Git repositories under: $root"
  local found=0
  while IFS= read -r repo_dir; do
    found=1
    log_info "  - ${repo_dir}"
  done < <(
    find "$root" -mindepth 1 -maxdepth 4 \( -type d -name .git -o -type f -name .git \) \
      | sed 's#/.git$##' \
      | sed "s#^$root/##" \
      | sort -u
  )
  if [[ "$found" -eq 0 ]]; then
    log_warn "  - (none found)"
  fi
}

main() {
  : > "$LOG_FILE"
  [[ "$VERBOSE" == "1" ]] && log_info "[install] Verbose mode enabled."
  force_deactivate_conda
  install_base_env_if_needed
  clone_or_update_repo

  local repo_root
  repo_root="$(resolve_repo_root)"
  if [[ -z "$repo_root" ]]; then
    log_err "[install] Failed to resolve repo root. Expecting <repo>/FusionDocker/src."
    exit 1
  fi

  local venv_dir="${repo_root}/.venv-tjfusion"
  setup_python_env "$repo_root" >/dev/null

  local launcher_path
  launcher_path="$(install_launcher "$venv_dir")"

  if [[ "$launcher_path" == "$HOME/.local/bin/"* ]]; then
    ensure_local_path
  fi

  install_bash_completion
  install_zsh_completion

  log_ok "[install] Done"
  log_info "[install] Repo root: $repo_root"
  log_info "[install] Venv: $venv_dir"
  log_ok "[install] Command: $launcher_path"
  log_info "[install] Reload shell: source ~/.bashrc  (or source ~/.zshrc)"
  log_info "[install] Test: tjfusion --help"
  list_docker_folders "$repo_root"
  list_git_repos "$repo_root"
  check_docker_install
  check_docker_gpu
  check_proxy_config
}

main
