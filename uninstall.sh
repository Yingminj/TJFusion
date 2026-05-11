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

REMOVE_REPO="0"
FORCE_YES="0"
REPO_ROOT=""

usage() {
  cat <<'USAGE'
Usage: ./uninstall.sh [options]

Options:
  --repo-root=<path>   Explicit repo root (default: auto-detect from script location)
  --remove-repo        Remove repository directory after uninstalling runtime artifacts
  --yes                Non-interactive mode; do not prompt
  -h, --help           Show this help
USAGE
}

for arg in "$@"; do
  case "$arg" in
    --repo-root=*) REPO_ROOT="${arg#*=}" ;;
    --remove-repo) REMOVE_REPO="1" ;;
    --yes) FORCE_YES="1" ;;
    -h|--help) usage; exit 0 ;;
    *)
      log_err "Unknown option: $arg"
      usage
      exit 1
      ;;
  esac
done

run_with_privilege() {
  if [[ "$(id -u)" -eq 0 ]]; then
    "$@"
  elif command -v sudo >/dev/null 2>&1; then
    sudo "$@"
  else
    return 1
  fi
}

resolve_repo_root() {
  if [[ -n "$REPO_ROOT" ]]; then
    echo "$(cd "$REPO_ROOT" && pwd)"
    return 0
  fi
  local script_dir
  script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
  echo "$script_dir"
}

remove_block_by_markers() {
  local file="$1"
  local start="$2"
  local end="$3"
  [[ -f "$file" ]] || return 0
  sed -i "/^$(printf '%s' "$start" | sed 's/[.[\*^$(){}?+|/]/\\&/g')$/,/^$(printf '%s' "$end" | sed 's/[.[\*^$(){}?+|/]/\\&/g')$/d" "$file"
}

safe_remove_file() {
  local path="$1"
  if [[ -e "$path" || -L "$path" ]]; then
    rm -f "$path"
    log_ok "[uninstall] removed: $path"
  fi
}

remove_launcher_if_matches() {
  local path="$1"
  [[ -f "$path" ]] || return 0
  if grep -q "fusion_docker" "$path" 2>/dev/null || grep -q ".venv-tjfusion" "$path" 2>/dev/null; then
    safe_remove_file "$path"
  else
    log_warn "[uninstall] skip non-tjfusion launcher: $path"
  fi
}

confirm_or_exit() {
  local prompt="$1"
  if [[ "$FORCE_YES" == "1" ]]; then
    return 0
  fi
  read -r -p "$prompt [y/N] " ans
  case "$ans" in
    y|Y|yes|YES) return 0 ;;
    *) log_warn "[uninstall] cancelled."; exit 0 ;;
  esac
}

main() {
  local root
  root="$(resolve_repo_root)"
  local venv_dir="${root}/.venv-tjfusion"

  log_info "[uninstall] repo root: $root"
  confirm_or_exit "Proceed to uninstall tjfusion runtime artifacts?"

  # Remove launchers
  remove_launcher_if_matches "$root/tjfusion"
  remove_launcher_if_matches "$HOME/.local/bin/tjfusion"
  if [[ -f "/usr/local/bin/tjfusion" ]]; then
    if grep -q "fusion_docker" "/usr/local/bin/tjfusion" 2>/dev/null || grep -q ".venv-tjfusion" "/usr/local/bin/tjfusion" 2>/dev/null; then
      if ! run_with_privilege rm -f "/usr/local/bin/tjfusion"; then
        log_warn "[uninstall] cannot remove /usr/local/bin/tjfusion (permission denied)."
      else
        log_ok "[uninstall] removed: /usr/local/bin/tjfusion"
      fi
    else
      log_warn "[uninstall] skip non-tjfusion launcher: /usr/local/bin/tjfusion"
    fi
  fi

  # Remove venv
  if [[ -d "$venv_dir" ]]; then
    rm -rf "$venv_dir"
    log_ok "[uninstall] removed venv: $venv_dir"
  fi

  # Remove completion files
  safe_remove_file "$HOME/.tjfusion.bash"
  safe_remove_file "$HOME/.zfunc/_tjfusion"

  # Remove shell config blocks installed by install.sh
  remove_block_by_markers "$HOME/.bashrc" "# >>> tjfusion bash completion >>>" "# <<< tjfusion bash completion <<<"
  remove_block_by_markers "$HOME/.bashrc" "# >>> tjfusion path >>>" "# <<< tjfusion path <<<"
  remove_block_by_markers "$HOME/.zshrc" "# >>> tjfusion zsh completion >>>" "# <<< tjfusion zsh completion <<<"
  remove_block_by_markers "$HOME/.zshrc" "# >>> tjfusion path >>>" "# <<< tjfusion path <<<"
  log_ok "[uninstall] cleaned shell rc markers."

  if [[ "$REMOVE_REPO" == "1" ]]; then
    confirm_or_exit "Also remove repository directory $root ?"
    rm -rf "$root"
    log_ok "[uninstall] removed repository: $root"
  fi

  log_ok "[uninstall] done."
  log_info "[uninstall] reload shell: source ~/.bashrc  (or source ~/.zshrc)"
}

main

