#!/usr/bin/env bash
set -euo pipefail

if [[ -t 1 ]]; then
  CYAN=$'\033[1;36m'
  GREEN=$'\033[1;32m'
  YELLOW=$'\033[1;33m'
  RESET=$'\033[0m'
else
  CYAN=''
  GREEN=''
  YELLOW=''
  RESET=''
fi

printf "%s\n" "${CYAN}====================================================================${RESET}"
printf "%s\n" "${CYAN}  ____       _           _      ____            _                  ${RESET}"
printf "%s\n" "${CYAN} |  _ \\ ___ | |__   ___ | |_   / ___| _   _ ___| |_ ___ _ __ ___   ${RESET}"
printf "%s\n" "${CYAN} | |_) / _ \\| '_ \\ / _ \\| __|  \\___ \\| | | / __| __/ _ \\ '_ \` _ \\  ${RESET}"
printf "%s\n" "${CYAN} |  _ < (_) | |_) | (_) | |_    ___) | |_| \\__ \\ ||  __/ | | | | | ${RESET}"
printf "%s\n" "${CYAN} |_| \\_\\___/|_.__/ \\___/ \\__|  |____/ \\__, |___/\\__\\___|_| |_| |_| ${RESET}"
printf "%s\n" "${CYAN}                                      |___/                        ${RESET}"
printf "%s\n" "${YELLOW}                      MARVIN ROBOT SYSTEM${RESET}"
printf "%s\n" "${CYAN}====================================================================${RESET}"

printf "%s\n" "${GREEN}[START]${RESET} Launching FusionDocker container with docker compose..."
docker compose up --build -d
printf "%s\n" "${GREEN}[OK]${RESET} FusionDocker is running."
