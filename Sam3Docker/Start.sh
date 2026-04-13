#!/usr/bin/env bash

set -e

SESSION_NAME="zmq_demo"

SERVER_DIR="/home/yang/Desktop/DockerModel/Sam3Docker/Server/ZeroMQ"
CLIENT_DIR="/home/yang/Desktop/DockerModel/Sam3Docker/Server/ZeroMQ"

SERVER_SCRIPT="ZeroMQServer.py"
CLIENT_SCRIPT="ZeroMQClient.py"

CONDA_ENV="sam3"

# =========================
# 固定配置（按需修改）
# =========================
PERIODIC_SEND=true

# =========================
# 外部参数（只保留这两个）
# =========================
USE_REALSENSE=false
USE_ZMQ_SOURCE=false

show_help() {
    echo "Usage: $0 [-r] [--zmq-source]"
    echo
    echo "Options:"
    echo "  -r             Use RealSense input for client"
    echo "  --zmq-source   Use ZMQ source input for client"
    echo
    echo "Notes:"
    echo "  - Only one of -r or --zmq-source can be used."
    echo "  - If neither is given, client uses local image mode."
}

for arg in "$@"; do
    case "$arg" in
        -r)
            USE_REALSENSE=true
            ;;
        --zmq-source)
            USE_ZMQ_SOURCE=true
            ;;
        -h|--help)
            show_help
            exit 0
            ;;
        *)
            echo "[ERROR] Unknown argument: $arg"
            echo
            show_help
            exit 1
            ;;
    esac
done

if [[ "$USE_REALSENSE" == true && "$USE_ZMQ_SOURCE" == true ]]; then
    echo "[ERROR] -r and --zmq-source cannot be used at the same time."
    exit 1
fi

echo "=============================================="
echo " SAM3 ZeroMQ tmux launcher"
echo "=============================================="
echo "Session name : ${SESSION_NAME}"
echo "Server dir   : ${SERVER_DIR}"
echo "Client dir   : ${CLIENT_DIR}"
echo "Conda env    : ${CONDA_ENV}"

if [[ "${USE_REALSENSE}" == true ]]; then
    echo "Input mode   : RealSense"
elif [[ "${USE_ZMQ_SOURCE}" == true ]]; then
    echo "Input mode   : ZMQ source"
else
    echo "Input mode   : local image"
fi

if [[ "${PERIODIC_SEND}" == true ]]; then
    echo "Mode         : periodic processing"
else
    echo "Mode         : send once"
fi

echo "=============================================="

tmux kill-session -t "${SESSION_NAME}" 2>/dev/null || true
echo "[INFO] Old tmux session killed (if existed)."

tmux new-session -d -s "${SESSION_NAME}" -n main
echo "[INFO] New tmux session created: ${SESSION_NAME}"

# Pane 0: Server
tmux send-keys -t "${SESSION_NAME}:main.0" \
    "cd ${SERVER_DIR}" C-m \
    "source ~/miniconda3/etc/profile.d/conda.sh" C-m \
    "conda activate ${CONDA_ENV}" C-m \
    "echo '[SERVER] Starting ${SERVER_SCRIPT} ...'" C-m \
    "python3 ${SERVER_SCRIPT}" C-m

tmux split-window -v -t "${SESSION_NAME}:main"

CLIENT_CMD="python3 ${CLIENT_SCRIPT}"

if [[ "${USE_REALSENSE}" == true ]]; then
    CLIENT_CMD="${CLIENT_CMD} -r"
fi

if [[ "${USE_ZMQ_SOURCE}" == true ]]; then
    CLIENT_CMD="${CLIENT_CMD} --zmq-source"
fi

if [[ "${PERIODIC_SEND}" == true ]]; then
    CLIENT_CMD="${CLIENT_CMD} -t"
    CLIENT_MSG="[CLIENT] Starting ${CLIENT_SCRIPT} in periodic mode"
else
    CLIENT_MSG="[CLIENT] Starting ${CLIENT_SCRIPT} in single-shot mode"
fi

if [[ "${USE_REALSENSE}" == true ]]; then
    CLIENT_MSG="${CLIENT_MSG}, RealSense enabled ..."
elif [[ "${USE_ZMQ_SOURCE}" == true ]]; then
    CLIENT_MSG="${CLIENT_MSG}, ZMQ source enabled ..."
else
    CLIENT_MSG="${CLIENT_MSG}, local image mode ..."
fi

# Pane 1: Client
tmux send-keys -t "${SESSION_NAME}:main.1" \
    "cd ${CLIENT_DIR}" C-m \
    "source ~/miniconda3/etc/profile.d/conda.sh" C-m \
    "conda activate ${CONDA_ENV}" C-m \
    "echo '${CLIENT_MSG}'" C-m \
    "${CLIENT_CMD}" C-m

tmux select-layout -t "${SESSION_NAME}:main" even-vertical

echo "[INFO] tmux layout configured."
echo "[INFO] Attaching to session: ${SESSION_NAME}"
echo "=============================================="

exec tmux attach -t "${SESSION_NAME}"