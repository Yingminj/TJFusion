from __future__ import annotations

import argparse
import json
import os
import re
import select
import shutil
import signal
from pathlib import Path
import subprocess
import sys
import termios
import time
import tty
from typing import Any

import yaml

from fusion_docker.bridge_scaffold import create_bridge_scaffold
from fusion_docker.bridge_runtime import run_bridge_from_config
from fusion_docker.bridges.registry import list_bridges as list_registered_bridges
from fusion_docker import __version__
from fusion_docker.config import load_docker_launch_config
from fusion_docker.launch_config_bridge_editor import add_bridge_to_launch_config
from fusion_docker.console import (
    colorize,
    print_banner,
    print_error,
    print_status,
    print_success,
    supports_color,
    print_warning,
)
from fusion_docker.docker_launcher import (
    describe_targets,
    launch_matched_dockers,
    match_requested_dockers,
    monitor_tmux_sessions,
    normalize_docker_name,
)
from fusion_docker.docker_port_config import read_docker_configured_port
from fusion_docker.models import DockerTargetEntry
from fusion_docker.port_inspector import (
    inspect_port_connections,
    list_listening_ports,
    watch_port_activity,
)
from fusion_docker.system_scaffold import create_system_scaffold
from fusion_docker.zmq_listener import listen_zmq_messages


def _release_help(text: str) -> str:
    if supports_color():
        return f"{colorize('[RELEASE]', color='green', bold=True)} {text}"
    return f"[RELEASE] {text}"


def _debug_help(text: str) -> str:
    if supports_color():
        return f"{colorize('[DEBUG]', color='yellow', bold=True)} {text}"
    return f"[DEBUG] {text}"


def _release_debug_help_footer() -> str:
    if supports_color():
        return (
            f"{colorize('Legend:', bold=True)} "
            f"{colorize('[RELEASE]', color='green', bold=True)} stable runtime command, "
            f"{colorize('[DEBUG]', color='yellow', bold=True)} development/debug command."
        )
    return "Legend: [RELEASE] stable runtime command, [DEBUG] development/debug command."


def _default_docker_config_launch_path() -> str:
    docker_model_root = str(os.getenv("DOCKER_MODEL_ROOT", "")).strip()
    if docker_model_root:
        return str(
            Path(docker_model_root).expanduser()
            / "FusionDocker"
            / "configs"
            / "docker_launch.yaml"
        )
    return "configs/docker_launch.yaml"


def _default_docker_model_root() -> str | None:
    docker_model_root = str(os.getenv("DOCKER_MODEL_ROOT", "")).strip()
    return docker_model_root or None


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()

    print_banner()

    try:
        if args.command == "serve-fusion":
            from fusion_docker.main import run_fusion_service

            print_status("MODE", "Fusion event service", color="cyan")
            run_fusion_service()
            return

        if args.command == "serve-bridge":
            from fusion_docker.config import get_bridge_config_path

            config_path = Path(args.config) if args.config else get_bridge_config_path()
            run_bridge_from_config(
                config_path,
                verbose=args.verbose,
                save_json=args.save_json,
                req_timeout_ms=args.req_timeout_ms,
                rgb_jpg_quality=args.rgb_jpg_quality,
                listen_host=args.listen_host,
                listen_port=args.listen_port,
            )
            return

        if args.command == "launch-dockers":
            _handle_launch_dockers(args)
            return

        if args.command == "start":
            _handle_start(args)
            return

        if args.command == "restart":
            _handle_restart(args)
            return

        if args.command == "update":
            _handle_update(args)
            return

        if args.command == "docker-config":
            _handle_docker_config(args)
            return

        if args.command == "serve-ui":
            _handle_serve_ui(args)
            return

        if args.command == "list-dockers":
            _handle_list_dockers(args)
            return

        if args.command == "list-bridges":
            _handle_list_bridges()
            return

        if args.command == "inspect-docker-io":
            _handle_inspect_docker_io(args)
            return

        if args.command == "list-docker-ports":
            _handle_list_docker_ports(args)
            return

        if args.command == "inspect-ports":
            _handle_inspect_ports(args)
            return

        if args.command == "listen-zmq":
            _handle_listen_zmq(args)
            return

        if args.command == "test-bridge":
            from fusion_docker.bridge_test_client import send_test_bridge_request

            print_status("MODE", f"Bridge test endpoint={args.endpoint}", color="cyan")
            send_test_bridge_request(
                args.endpoint,
                timeout_ms=args.timeout_ms,
                width=args.width,
                height=args.height,
            )
            return

        if args.command == "create-system":
            _handle_create_system(args)
            return

        if args.command == "create-bridge":
            _handle_create_bridge(args)
            return

        if args.command == "add-bridge-to-ui":
            _handle_add_bridge_to_ui(args)
            return
    except Exception as exc:
        print_error(str(exc))
        raise SystemExit(1) from exc

    parser.error(f"Unsupported command: {args.command}")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="tjfusion",
        description="Marvin Robot System CLI for FusionDocker, bridge service, and docker launch flow.",
        epilog=_release_debug_help_footer(),
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.add_argument(
        "-v",
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    start_parser = subparsers.add_parser(
        "start",
        help=_release_help("Start selected dockers from docker_launch.yaml."),
    )
    start_parser.add_argument(
        "--launch-config",
        help=(
            "YAML file controlling which dockers to launch. "
            "When omitted, auto-uses $DOCKER_MODEL_ROOT/FusionDocker/configs/docker_launch.yaml if it exists."
        ),
    )
    start_parser.add_argument(
        "--docker-model-root",
        default=_default_docker_model_root(),
        help="DockerModel root path. Defaults to DOCKER_MODEL_ROOT when set.",
    )
    start_parser.add_argument("--dry-run", action="store_true", help="Show matches without executing run.sh.")
    start_parser.add_argument(
        "--tmux",
        action="store_true",
        help="Launch each docker in a dedicated tmux session named after the docker folder.",
    )
    start_parser.add_argument(
        "--foreground",
        action="store_true",
        help="Run each run.sh in the foreground. Default behavior is background launch.",
    )
    start_parser.add_argument(
        "--log-dir",
        help="Directory for background launch logs. Defaults to ./logs/docker-launches.",
    )
    start_parser.add_argument(
        "--replace-session",
        action="store_true",
        help="When --tmux is enabled, replace an existing tmux session with the same docker name.",
    )
    start_parser.add_argument(
        "--monitor",
        action="store_true",
        help="When --tmux is enabled, show docker running/ended status and cleanup on Ctrl+C.",
    )
    start_parser.add_argument(
        "--poll-interval",
        type=float,
        default=None,
        help="Status monitor poll interval in seconds. Defaults to YAML or 0.5.",
    )
    start_parser.add_argument(
        "--dashboard",
        choices=("terminal", "web"),
        help="Choose the monitor dashboard mode. Defaults to YAML or 'terminal'.",
    )

    restart_parser = subparsers.add_parser(
        "restart",
        help=_release_help(
            "Force stop all local docker containers, clear busy configured ports, then relaunch selected dockers."
        ),
    )
    restart_parser.add_argument(
        "docker_names",
        nargs="*",
        help="Optional docker names to relaunch after cleanup. Defaults to launch config selected dockers.",
    )
    restart_parser.add_argument(
        "--launch-config",
        help=(
            "YAML file controlling which dockers to relaunch. "
            "When omitted, auto-uses $DOCKER_MODEL_ROOT/FusionDocker/configs/docker_launch.yaml if it exists."
        ),
    )
    restart_parser.add_argument(
        "--docker-model-root",
        default=_default_docker_model_root(),
        help="DockerModel root path. Defaults to DOCKER_MODEL_ROOT when set.",
    )
    restart_parser.add_argument(
        "--tmux",
        action="store_true",
        help="Launch each docker in a dedicated tmux session named after the docker folder.",
    )
    restart_parser.add_argument(
        "--foreground",
        action="store_true",
        help="Run each run.sh in the foreground. Default behavior is background launch.",
    )
    restart_parser.add_argument(
        "--log-dir",
        help="Directory for background launch logs. Defaults to ./logs/docker-launches.",
    )
    restart_parser.add_argument(
        "--replace-session",
        action="store_true",
        help="When --tmux is enabled, replace an existing tmux session with the same docker name.",
    )
    restart_parser.add_argument(
        "--monitor",
        action="store_true",
        help="When --tmux is enabled, show docker running/ended status and cleanup on Ctrl+C.",
    )
    restart_parser.add_argument(
        "--poll-interval",
        type=float,
        default=None,
        help="Status monitor poll interval in seconds. Defaults to YAML or 0.5.",
    )
    restart_parser.add_argument(
        "--dashboard",
        choices=("terminal", "web"),
        help="Choose the monitor dashboard mode. Defaults to YAML or 'terminal'.",
    )
    restart_parser.add_argument(
        "--skip-port-cleanup",
        action="store_true",
        help="Only stop local docker containers, do not terminate processes occupying configured service ports.",
    )
    restart_parser.add_argument(
        "--no-start",
        action="store_true",
        help="Only perform cleanup (stop containers + clear ports), and skip relaunch.",
    )
    restart_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show relaunch matches without executing run.sh. Cleanup steps still execute.",
    )

    update_parser = subparsers.add_parser(
        "update",
        help=_release_help("Update local code via git pull and refresh the Python package."),
    )
    update_parser.add_argument(
        "--repo-root",
        help="Repository root path. Defaults to auto-detected project root.",
    )
    update_parser.add_argument(
        "--skip-pip",
        action="store_true",
        help="Skip python package refresh step after git pull.",
    )
    update_parser.add_argument(
        "--allow-dirty",
        action="store_true",
        help="Allow update even when repository has local modifications.",
    )

    docker_config_parser = subparsers.add_parser(
        "docker-config",
        help=_release_help(
            "Interactively choose dockers (Up/Down + Space) and write docker_launch.yaml."
        ),
    )
    docker_config_parser.add_argument(
        "--launch-config",
        default=_default_docker_config_launch_path(),
        help=(
            "Launch config YAML path. Defaults to "
            "$DOCKER_MODEL_ROOT/FusionDocker/configs/docker_launch.yaml "
            "(fallback: configs/docker_launch.yaml)."
        ),
    )
    docker_config_parser.add_argument(
        "--docker-model-root",
        default=_default_docker_model_root(),
        help="DockerModel root path. Defaults to DOCKER_MODEL_ROOT when set.",
    )

    subparsers.add_parser(
        "serve-fusion",
        help=_debug_help("Run the original FusionDocker event service."),
    )

    bridge_parser = subparsers.add_parser(
        "serve-bridge",
        help=_debug_help("Run the ZeroMQ RGB-D bridge service integrated from ZeroMQClient_interface.py."),
    )
    bridge_parser.add_argument(
        "--config",
        help="Bridge config YAML path. Defaults to FUSION_BRIDGE_CONFIG or /app/configs/bridge.yaml.",
    )
    bridge_parser.add_argument("-v", "--verbose", action="store_true", help="Print verbose responses.")
    bridge_parser.add_argument("--save-json", action="store_true", help="Save SAM3 response JSON to disk.")
    bridge_parser.add_argument("--req-timeout-ms", type=int, help="REQ/REP send/recv timeout in ms.")
    bridge_parser.add_argument("--rgb-jpg-quality", type=int, help="RGB jpg quality for upstream requests.")
    bridge_parser.add_argument("--listen-host", help="External request listen host override.")
    bridge_parser.add_argument("--listen-port", type=int, help="External request listen port override.")

    launch_parser = subparsers.add_parser(
        "launch-dockers",
        help=_debug_help("Scan DockerModel folders, match docker names by folder name, and execute run.sh."),
    )
    launch_parser.add_argument(
        "docker_names",
        nargs="*",
        help="Docker names to match against folder names, for example sam3 flowpose fusiondocker.",
    )
    launch_parser.add_argument(
        "--launch-config",
        help="YAML file controlling which dockers to launch. Example: configs/docker_launch.yaml",
    )
    launch_parser.add_argument(
        "--docker-model-root",
        default=_default_docker_model_root(),
        help="DockerModel root path. Defaults to DOCKER_MODEL_ROOT when set.",
    )
    launch_parser.add_argument("--dry-run", action="store_true", help="Show matches without executing run.sh.")
    launch_parser.add_argument(
        "--tmux",
        action="store_true",
        help="Launch each docker in a dedicated tmux session named after the docker folder.",
    )
    launch_parser.add_argument(
        "--foreground",
        action="store_true",
        help="Run each run.sh in the foreground. Default behavior is background launch.",
    )
    launch_parser.add_argument(
        "--log-dir",
        help="Directory for background launch logs. Defaults to ./logs/docker-launches.",
    )
    launch_parser.add_argument(
        "--replace-session",
        action="store_true",
        help="When --tmux is enabled, replace an existing tmux session with the same docker name.",
    )
    launch_parser.add_argument(
        "--monitor",
        action="store_true",
        help="When --tmux is enabled, show docker running/ended status and cleanup on Ctrl+C.",
    )
    launch_parser.add_argument(
        "--poll-interval",
        type=float,
        default=None,
        help="Status monitor poll interval in seconds. Defaults to YAML or 0.5.",
    )
    launch_parser.add_argument(
        "--dashboard",
        choices=("terminal", "web"),
        help="Choose the monitor dashboard mode. Defaults to YAML or 'terminal'.",
    )

    ui_parser = subparsers.add_parser(
        "serve-ui",
        help=_debug_help("Serve a local web dashboard for docker status and clickable log viewing."),
    )
    ui_parser.add_argument(
        "docker_names",
        nargs="*",
        help="Docker names to show in the dashboard. Defaults to YAML or all runnable folders.",
    )
    ui_parser.add_argument(
        "--launch-config",
        help="YAML file controlling docker groups and defaults. Example: configs/docker_launch.yaml",
    )
    ui_parser.add_argument(
        "--docker-model-root",
        default=_default_docker_model_root(),
        help="DockerModel root path. Defaults to DOCKER_MODEL_ROOT when set.",
    )
    ui_parser.add_argument(
        "--host",
        help="Dashboard bind host. Defaults to YAML or 127.0.0.1.",
    )
    ui_parser.add_argument(
        "--port",
        type=int,
        help="Dashboard bind port. Defaults to YAML or 8765.",
    )
    ui_parser.add_argument(
        "--log-lines",
        type=int,
        help="How many recent log lines to show per docker request. Defaults to YAML or 300.",
    )

    list_parser = subparsers.add_parser(
        "list-dockers",
        help=_debug_help("List all folders under DockerModel root that contain run.sh."),
    )
    list_parser.add_argument(
        "--docker-model-root",
        default=_default_docker_model_root(),
        help="DockerModel root path. Defaults to DOCKER_MODEL_ROOT when set.",
    )

    subparsers.add_parser(
        "list-bridges",
        help=_debug_help("List all registered bridge types and their descriptions."),
    )

    inspect_io_parser = subparsers.add_parser(
        "inspect-docker-io",
        help=_debug_help(
            "Inspect RequestFormat input/output schema fields for one or more docker folders."
        ),
    )
    inspect_io_parser.add_argument(
        "docker_names",
        nargs="*",
        help="Docker names to inspect. Defaults to YAML docker list or all runnable folders.",
    )
    inspect_io_parser.add_argument(
        "--launch-config",
        help="YAML file controlling docker defaults. Example: configs/docker_launch.yaml",
    )
    inspect_io_parser.add_argument(
        "--docker-model-root",
        default=_default_docker_model_root(),
        help="DockerModel root path. Defaults to DOCKER_MODEL_ROOT when set.",
    )
    inspect_io_parser.add_argument(
        "--json",
        action="store_true",
        help="Print full inspection result as JSON.",
    )

    docker_ports_parser = subparsers.add_parser(
        "list-docker-ports",
        help=_debug_help("Read Docker config files and list the ports each docker is configured to listen on."),
    )
    docker_ports_parser.add_argument(
        "docker_names",
        nargs="*",
        help="Docker names to inspect. Defaults to YAML docker list or all runnable folders.",
    )
    docker_ports_parser.add_argument(
        "--launch-config",
        help="YAML file controlling docker defaults. Example: configs/docker_launch.yaml",
    )
    docker_ports_parser.add_argument(
        "--docker-model-root",
        default=_default_docker_model_root(),
        help="DockerModel root path. Defaults to DOCKER_MODEL_ROOT when set.",
    )

    inspect_ports_parser = subparsers.add_parser(
        "inspect-ports",
        help=_debug_help("List listening service ports and optionally inspect one port for traffic."),
    )
    inspect_ports_parser.add_argument(
        "--port",
        type=int,
        help="Inspect one specific port, for example 1883.",
    )
    inspect_ports_parser.add_argument(
        "--watch-seconds",
        type=int,
        default=0,
        help="Watch the selected port for N seconds using tcpdump to see whether packets appear.",
    )

    listen_zmq_parser = subparsers.add_parser(
        "listen-zmq",
        help=_debug_help("Subscribe to a ZMQ PUB endpoint on a port and print received messages."),
    )
    listen_zmq_parser.add_argument(
        "--port",
        type=int,
        required=True,
        help="ZMQ port to subscribe to, for example 8899.",
    )
    listen_zmq_parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="ZMQ host to subscribe to. Defaults to 127.0.0.1.",
    )
    listen_zmq_parser.add_argument(
        "--topic",
        default="",
        help="Optional SUB topic filter. Defaults to all topics.",
    )
    listen_zmq_parser.add_argument(
        "--limit",
        type=int,
        help="Stop after receiving this many messages.",
    )
    listen_zmq_parser.add_argument(
        "--timeout-ms",
        type=int,
        help="Stop if no message arrives within this timeout.",
    )

    test_parser = subparsers.add_parser(
        "test-bridge",
        help=_debug_help("Send a synthetic RGB-D request to the bridge service."),
    )
    test_parser.add_argument(
        "--endpoint",
        default="tcp://127.0.0.1:4444",
        help="External bridge endpoint, for example tcp://127.0.0.1:4444",
    )
    test_parser.add_argument("--timeout-ms", type=int, default=4000, help="REQ/REP timeout in ms.")
    test_parser.add_argument("--width", type=int, default=640, help="Synthetic RGB image width.")
    test_parser.add_argument("--height", type=int, default=480, help="Synthetic RGB image height.")

    scaffold_parser = subparsers.add_parser(
        "create-system",
        help=_debug_help("Create a new DockerModel system scaffold (Dockerfile/run.sh/build.sh/Server)."),
    )
    scaffold_parser.add_argument(
        "name",
        help="System name, for example ros. The folder will be generated as <Name>Docker.",
    )
    scaffold_parser.add_argument(
        "--docker-model-root",
        default=_default_docker_model_root(),
        help="DockerModel root path. Defaults to DOCKER_MODEL_ROOT when set.",
    )
    scaffold_parser.add_argument(
        "--launch-config",
        help="Optional launch config used to read docker_launcher.docker_model_root.",
    )
    scaffold_parser.add_argument(
        "--server-host",
        default="0.0.0.0",
        help="Default server.host written into config.yaml.",
    )
    scaffold_parser.add_argument(
        "--server-port",
        type=int,
        default=5555,
        help="Default server.port written into config.yaml.",
    )
    scaffold_parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite scaffold files when the target folder already exists.",
    )

    bridge_scaffold_parser = subparsers.add_parser(
        "create-bridge",
        help=_debug_help("Create a new bridge module, config, and registry entry scaffold."),
    )
    bridge_scaffold_parser.add_argument(
        "name",
        help="Bridge name, for example my_bridge.",
    )
    bridge_scaffold_parser.add_argument(
        "--project-root",
        default=str(Path.cwd()),
        help="Project root containing src/fusion_docker/bridges and configs.",
    )
    bridge_scaffold_parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite generated bridge files when they already exist.",
    )

    add_bridge_ui_parser = subparsers.add_parser(
        "add-bridge-to-ui",
        help=_debug_help("Add or update a bridge entry in docker_launch.yaml for the UI dashboard."),
    )
    add_bridge_ui_parser.add_argument(
        "name",
        help="Display name for the bridge inside the UI.",
    )
    add_bridge_ui_parser.add_argument(
        "--bridge-config",
        required=True,
        help="Bridge config path, for example configs/bridge.my_bridge.yaml",
    )
    add_bridge_ui_parser.add_argument(
        "--launch-config",
        default="configs/docker_launch.yaml",
        help="Launch config YAML path. Defaults to configs/docker_launch.yaml.",
    )
    add_bridge_ui_parser.add_argument(
        "--disabled",
        action="store_true",
        help="Add the bridge entry as disabled.",
    )
    add_bridge_ui_parser.add_argument(
        "--force",
        action="store_true",
        help="Update an existing bridge entry with the same name.",
    )

    return parser


def _handle_launch_dockers(args: argparse.Namespace) -> None:
    _run_docker_launch_flow(
        args,
        docker_names_override=None,
        list_when_empty=True,
    )


def _handle_start(args: argparse.Namespace) -> None:
    if not args.launch_config:
        default_launch_config = Path(_default_docker_config_launch_path()).expanduser()
        if default_launch_config.exists():
            args.launch_config = str(default_launch_config)

    docker_names = _resolve_start_docker_names(args)
    if not docker_names:
        raise ValueError(
            "No docker selected. Run `tjfusion docker-config` first or set docker_launcher.selected_dockers."
        )
    _run_docker_launch_flow(
        args,
        docker_names_override=docker_names,
        list_when_empty=False,
    )


def _handle_restart(args: argparse.Namespace) -> None:
    if not args.launch_config:
        default_launch_config = Path(_default_docker_config_launch_path()).expanduser()
        if default_launch_config.exists():
            args.launch_config = str(default_launch_config)

    print_status("RESTART", "Stopping all local docker containers.", color="cyan")
    _force_stop_all_local_containers()

    if args.skip_port_cleanup:
        print_warning("Skip port cleanup (--skip-port-cleanup).")
    else:
        configured_ports = _collect_restart_target_ports(args)
        if not configured_ports:
            print_warning(
                "No configured docker service ports resolved for cleanup. "
                "If needed, provide --docker-model-root or --launch-config."
            )
        else:
            _release_ports(configured_ports)

    if args.no_start:
        print_success("Restart cleanup completed (no relaunch due to --no-start).")
        return

    docker_names = list(args.docker_names) if args.docker_names else _resolve_start_docker_names(args)
    if not docker_names:
        raise ValueError(
            "No docker selected for relaunch. Pass docker names or run `tjfusion docker-config` first."
        )

    _run_docker_launch_flow(
        args,
        docker_names_override=docker_names,
        list_when_empty=False,
    )


def _resolve_start_docker_names(args: argparse.Namespace) -> list[str]:
    launch_config = _load_optional_launch_config(args.launch_config)
    if launch_config and launch_config.docker_names:
        return list(launch_config.docker_names)
    return []


def _handle_update(args: argparse.Namespace) -> None:
    repo_root = _resolve_repo_root_for_update(args.repo_root)
    print_status("UPDATE", f"Repository root: {repo_root}", color="cyan")

    if not args.allow_dirty:
        dirty = _run_subprocess(
            ["git", "-C", str(repo_root), "status", "--porcelain"],
            capture_output=True,
        ).stdout.strip()
        if dirty:
            raise RuntimeError(
                "Repository has uncommitted changes. Commit/stash first, or re-run with --allow-dirty."
            )

    pull_result = _run_subprocess(
        ["git", "-C", str(repo_root), "pull", "--ff-only"],
        capture_output=True,
    )
    _print_cmd_output(pull_result.stdout)
    _print_cmd_output(pull_result.stderr)

    if args.skip_pip:
        print_warning("Skipped pip package refresh (--skip-pip).")
        return

    fusion_dir = repo_root / "FusionDocker"
    if not fusion_dir.is_dir():
        raise FileNotFoundError(f"FusionDocker directory not found under: {repo_root}")

    py_bin = Path(sys.executable).resolve()
    print_status("UPDATE", f"Refreshing package with interpreter: {py_bin}", color="cyan")
    _run_subprocess([str(py_bin), "-m", "pip", "install", "--upgrade", "pip", "setuptools", "wheel"])
    requirements_file = fusion_dir / "requirements.txt"
    if requirements_file.is_file():
        _run_subprocess([str(py_bin), "-m", "pip", "install", "-r", str(requirements_file)])
    _run_subprocess([str(py_bin), "-m", "pip", "install", "-e", str(fusion_dir)])
    print_success("Update completed.")


def _resolve_repo_root_for_update(raw_repo_root: str | None) -> Path:
    if raw_repo_root:
        repo_root = Path(raw_repo_root).expanduser().resolve()
    else:
        this_file = Path(__file__).resolve()
        # .../<repo>/FusionDocker/src/fusion_docker/cli.py
        repo_root = this_file.parents[3]
    if not (repo_root / ".git").exists():
        raise FileNotFoundError(f"Git repository not found at: {repo_root}")
    return repo_root


def _run_subprocess(cmd: list[str], *, capture_output: bool = False) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        cmd,
        text=True,
        capture_output=capture_output,
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()
        raise RuntimeError(f"Command failed ({' '.join(cmd)}): {detail or 'unknown error'}")
    return result


def _print_cmd_output(text: str) -> None:
    content = text.strip()
    if not content:
        return
    for line in content.splitlines():
        print_status("GIT", line, color="blue")


def _run_docker_launch_flow(
    args: argparse.Namespace,
    *,
    docker_names_override: list[str] | None,
    list_when_empty: bool,
) -> None:
    launch_config = _load_optional_launch_config(args.launch_config)
    launch_config_path = _resolve_launch_config_path(args.launch_config)
    docker_model_root_value = args.docker_model_root or (
        launch_config.docker_model_root if launch_config else None
    )
    docker_model_root = (
        _require_docker_model_root(docker_model_root_value)
        if docker_model_root_value
        else None
    )
    has_target_entries = bool(launch_config and launch_config.docker_targets)
    if docker_model_root is None and not has_target_entries:
        raise ValueError(
            "Please provide --docker-model-root (or docker_launcher.docker_model_root), "
            "or define docker_launcher.docker_targets in launch config."
        )

    use_tmux = args.tmux or (launch_config.use_tmux if launch_config else False)
    monitor = args.monitor or (launch_config.monitor if launch_config else False)
    replace_session = args.replace_session or (
        launch_config.replace_session if launch_config else False
    )
    poll_interval = (
        args.poll_interval
        if args.poll_interval is not None
        else (launch_config.poll_interval if launch_config else 0.5)
    )
    dashboard_mode = args.dashboard or (
        launch_config.dashboard_mode if launch_config else "terminal"
    )

    if use_tmux and args.foreground:
        raise ValueError("--tmux and --foreground cannot be used together.")
    if replace_session and not use_tmux:
        raise ValueError("--replace-session can only be used together with --tmux.")
    if monitor and not use_tmux:
        raise ValueError("--monitor can only be used together with --tmux.")
    if poll_interval <= 0:
        raise ValueError("--poll-interval must be greater than 0.")

    if has_target_entries:
        available = [entry.name for entry in launch_config.docker_targets]
        print_status(
            "SCAN",
            f"Loaded {len(available)} docker target(s) from launch config (supports local + remote).",
            color="cyan",
        )
    else:
        assert docker_model_root is not None
        available = describe_targets(docker_model_root)
        print_status(
            "SCAN",
            f"Found {len(available)} runnable folders under {docker_model_root}",
            color="cyan",
        )

    docker_names: list[str] = []
    requested_names = list(getattr(args, "docker_names", []) or [])
    if docker_names_override is not None:
        docker_names = list(docker_names_override)
    elif requested_names:
        docker_names = requested_names
    elif launch_config:
        docker_names = list(launch_config.docker_names)

    if not docker_names:
        if list_when_empty:
            print_warning("No docker names were provided. Listing all runnable folders instead.")
            for target in available:
                print_status("DOCKER", target, color="blue")
        else:
            print_warning("No docker names selected to launch.")
        return

    group_lookup = _build_group_lookup(launch_config)
    matches = _match_dockers_for_runtime(
        docker_names,
        launch_config=launch_config,
        docker_model_root=docker_model_root,
        group_lookup=group_lookup,
    )
    if not matches:
        print_warning("No docker tasks to launch. Remote failures were skipped.")
        return
    for match in matches:
        print_status(
            "MATCH",
            (
                f"{match.requested_name} -> {match.target.relative_folder} "
                f"(strategy={match.strategy}, score={match.score:.2f})"
            ),
            color="magenta",
        )

    results = launch_matched_dockers(
        matches,
        dry_run=args.dry_run,
        detached=not args.foreground,
        log_dir=args.log_dir,
        use_tmux=use_tmux,
        replace_session=replace_session,
    )
    failures = [result for result in results if not result.succeeded]
    remote_failures = [result for result in failures if result.match.target.is_remote]
    local_failures = [result for result in failures if not result.match.target.is_remote]
    if remote_failures:
        remote_names = ", ".join(sorted({result.match.target.folder_name for result in remote_failures}))
        print_warning(
            "Skipped failed remote docker launch/restart for: "
            f"{remote_names}. Local tasks continue."
        )
    if monitor and not args.dry_run:
        if failures:
            print_warning(
                f"{len(failures)} docker launch task(s) entered error state. "
                "They will be shown as status=error in the dashboard."
            )
        if dashboard_mode == "web":
            from fusion_docker.ui_server import serve_dashboard_ui

            ui_host, ui_port, ui_log_lines = _resolve_ui_settings(args, launch_config)
            serve_dashboard_ui(
                results=results,
                host=ui_host,
                port=ui_port,
                log_lines=ui_log_lines,
                project_root=Path.cwd().resolve(),
                launch_config_path=launch_config_path,
                docker_model_root_hint=docker_model_root,
                docker_model_root_override=(
                    Path(args.docker_model_root).expanduser().resolve()
                    if args.docker_model_root
                    else None
                ),
                docker_names_override=requested_names if requested_names else None,
                bridge_entries=launch_config.bridge_entries if launch_config else None,
                cleanup_on_exit=True,
            )
        else:
            monitor_tmux_sessions(results, poll_interval_s=poll_interval)
        return
    if local_failures:
        raise RuntimeError(f"{len(local_failures)} local docker launch task(s) failed.")


def _handle_docker_config(args: argparse.Namespace) -> None:
    launch_config_path = Path(args.launch_config).expanduser().resolve()
    launch_config = _load_optional_launch_config(str(launch_config_path)) if launch_config_path.exists() else None
    docker_model_root_value = args.docker_model_root or (
        launch_config.docker_model_root if launch_config else None
    )
    docker_model_root = _require_docker_model_root(docker_model_root_value)
    docker_names = describe_targets(docker_model_root)
    if not docker_names:
        raise FileNotFoundError(f"No run.sh files found under DockerModel path: {docker_model_root}")

    default_selected = _read_selected_dockers(launch_config_path)
    if not default_selected and launch_config:
        default_selected = list(launch_config.docker_names)
    selected = _interactive_select_dockers(
        docker_names,
        default_selected,
        title=f"Select dockers to run from {docker_model_root}",
    )
    if selected is None:
        print_warning("Selection canceled. docker_launch.yaml not changed.")
        return
    _write_selected_dockers(
        launch_config_path=launch_config_path,
        docker_model_root=docker_model_root,
        selected_dockers=selected,
    )
    print_success(f"Saved {len(selected)} docker selection(s) into {launch_config_path}")
    if selected:
        print_status("SELECT", ", ".join(selected), color="green")
    else:
        print_warning("No docker selected.")


def _read_selected_dockers(launch_config_path: Path) -> list[str]:
    if not launch_config_path.exists():
        return []
    with launch_config_path.open("r", encoding="utf-8") as handle:
        raw = yaml.safe_load(handle) or {}
    if not isinstance(raw, dict):
        return []
    launch_raw = raw.get("docker_launcher")
    if launch_raw is None:
        launch_raw = raw.get("launcher", raw)
    if not isinstance(launch_raw, dict):
        return []
    return _coerce_docker_name_list(launch_raw.get("selected_dockers", []))


def _write_selected_dockers(
    *,
    launch_config_path: Path,
    docker_model_root: Path,
    selected_dockers: list[str],
) -> None:
    raw: dict[str, Any] = {}
    if launch_config_path.exists():
        with launch_config_path.open("r", encoding="utf-8") as handle:
            loaded = yaml.safe_load(handle) or {}
        if isinstance(loaded, dict):
            raw = loaded
    launcher_key = "docker_launcher"
    launch_raw = raw.get(launcher_key)
    if launch_raw is None:
        if isinstance(raw.get("launcher"), dict):
            launcher_key = "launcher"
            launch_raw = raw.get("launcher")
        else:
            launch_raw = {}
            raw[launcher_key] = launch_raw
    if not isinstance(launch_raw, dict):
        launch_raw = {}
        raw[launcher_key] = launch_raw

    if not launch_raw.get("docker_model_root"):
        launch_raw["docker_model_root"] = str(docker_model_root)
    launch_raw["selected_dockers"] = selected_dockers

    launch_config_path.parent.mkdir(parents=True, exist_ok=True)
    with launch_config_path.open("w", encoding="utf-8") as handle:
        yaml.safe_dump(raw, handle, sort_keys=False, allow_unicode=True)


def _coerce_docker_name_list(raw: Any) -> list[str]:
    if not isinstance(raw, list):
        return []
    docker_names: list[str] = []
    for item in raw:
        if isinstance(item, str):
            name = item.strip()
            if name:
                docker_names.append(name)
            continue
        if isinstance(item, dict):
            name = str(item.get("name", "")).strip()
            if name and bool(item.get("enabled", True)):
                docker_names.append(name)
    return docker_names


def _interactive_select_dockers(
    options: list[str],
    default_selected: list[str],
    *,
    title: str,
) -> list[str] | None:
    if not options:
        return []
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        raise RuntimeError("docker-config requires an interactive TTY terminal.")

    default_set = set(default_selected)
    selected = {name for name in options if name in default_set}
    cursor = 0

    fd = sys.stdin.fileno()
    original_settings = termios.tcgetattr(fd)
    try:
        tty.setcbreak(fd)
        # Use alternate screen to avoid polluting scrollback and reduce flicker.
        sys.stdout.write("\033[?1049h\033[?25l")
        sys.stdout.flush()
        needs_render = True
        while True:
            if needs_render:
                _render_docker_selection_screen(
                    title=title,
                    options=options,
                    selected=selected,
                    cursor=cursor,
                )
                needs_render = False

            key = _read_selection_key(fd, timeout_s=0.2)
            if key is None:
                continue
            if key == "UP":
                cursor = (cursor - 1) % len(options)
                needs_render = True
            elif key == "DOWN":
                cursor = (cursor + 1) % len(options)
                needs_render = True
            elif key == "SPACE":
                name = options[cursor]
                if name in selected:
                    selected.remove(name)
                else:
                    selected.add(name)
                needs_render = True
            elif key == "ENTER":
                return [name for name in options if name in selected]
            elif key == "QUIT":
                return None
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, original_settings)
        sys.stdout.write("\033[?25h\033[?1049l")
        sys.stdout.flush()


def _render_docker_selection_screen(
    *,
    title: str,
    options: list[str],
    selected: set[str],
    cursor: int,
) -> None:
    lines: list[str] = []
    lines.append(colorize(title, color="cyan", bold=True))
    lines.append(
        colorize(
            "Keys: Up/Down (or k/j) move | Space select/unselect | Enter save | q cancel",
            color="yellow",
            bold=True,
        )
    )
    lines.append("")
    for idx, name in enumerate(options):
        marker = "[x]" if name in selected else "[ ]"
        prefix = ">" if idx == cursor else " "
        if idx == cursor:
            row = colorize(f"{prefix} {marker} {name}", color="green", bold=True)
        else:
            row = f"{prefix} {marker} {name}"
        lines.append(row)
    lines.append("")
    lines.append(f"Selected: {len(selected)} / {len(options)}")
    sys.stdout.write("\033[H\033[J")
    sys.stdout.write("\n".join(lines))
    sys.stdout.flush()


def _read_selection_key(fd: int, *, timeout_s: float) -> str | None:
    while True:
        ready, _, _ = select.select([fd], [], [], timeout_s)
        if not ready:
            return None
        ch = os.read(fd, 1).decode(errors="ignore")
        if not ch:
            return None
        if ch == "\x1b":
            seq = _read_escape_sequence(fd)
            if seq in {"[A", "OA"} or seq.endswith("A"):
                return "UP"
            if seq in {"[B", "OB"} or seq.endswith("B"):
                return "DOWN"
            continue
        if ch in {"\r", "\n"}:
            return "ENTER"
        if ch == " ":
            return "SPACE"
        if ch in {"k", "K"}:
            return "UP"
        if ch in {"j", "J"}:
            return "DOWN"
        if ch in {"q", "Q"}:
            return "QUIT"


def _read_escape_sequence(fd: int) -> str:
    chars: list[str] = []
    # Collect the rest of an escape sequence with a short timeout window.
    for _ in range(16):
        ready, _, _ = select.select([fd], [], [], 0.03)
        if not ready:
            break
        c = os.read(fd, 1).decode(errors="ignore")
        if not c:
            break
        chars.append(c)
        if c.isalpha() or c == "~":
            break
    return "".join(chars)


def _handle_list_dockers(args: argparse.Namespace) -> None:
    docker_model_root = _require_docker_model_root(args.docker_model_root)
    targets = describe_targets(docker_model_root)
    print_status("SCAN", f"DockerModel root: {docker_model_root}", color="cyan")
    for target in targets:
        print_status("DOCKER", target, color="blue")


def _handle_list_bridges() -> None:
    bridge_definitions = sorted(
        list_registered_bridges(),
        key=lambda item: item.kind,
    )
    print_status("BRIDGE", f"Registered bridge types: {len(bridge_definitions)}", color="cyan")
    for definition in bridge_definitions:
        alias_text = ", ".join(definition.aliases) if definition.aliases else "-"
        print_status(
            "BRIDGE",
            f"{definition.kind} | aliases={alias_text} | {definition.description}",
            color="blue",
        )


def _handle_inspect_docker_io(args: argparse.Namespace) -> None:
    launch_config = _load_optional_launch_config(args.launch_config)
    docker_model_root_value = args.docker_model_root or (
        launch_config.docker_model_root if launch_config else None
    )
    docker_model_root = _require_docker_model_root(docker_model_root_value)

    docker_names = list(args.docker_names) if args.docker_names else []
    if not docker_names and launch_config:
        docker_names = list(launch_config.docker_names)
    if not docker_names:
        docker_names = describe_targets(docker_model_root)

    if not docker_names:
        print_warning("No docker names found to inspect.")
        return

    group_lookup = _build_group_lookup(launch_config)
    matches = match_requested_dockers(
        docker_model_root,
        docker_names,
        group_lookup=group_lookup,
    )

    report_items: list[dict[str, Any]] = []
    seen_paths: set[str] = set()
    for match in matches:
        folder_path = match.target.folder_path
        folder_key = str(folder_path)
        if folder_key in seen_paths:
            continue
        seen_paths.add(folder_key)

        request_format_dir = folder_path / "RequestFormat"
        input_path = _resolve_first_existing(
            request_format_dir,
            ("input.schema.json", "input.json"),
        )
        output_path = _resolve_first_existing(
            request_format_dir,
            ("output.schema.json", "output.json"),
        )

        item: dict[str, Any] = {
            "docker_name": match.target.folder_name,
            "group": match.group_name or "",
            "folder_path": str(folder_path),
            "request_format_dir": str(request_format_dir),
            "input_path": str(input_path) if input_path else "",
            "output_path": str(output_path) if output_path else "",
            "input_fields": [],
            "output_fields": [],
            "errors": [],
        }

        if not request_format_dir.is_dir():
            item["errors"].append(f"RequestFormat directory missing: {request_format_dir}")
            report_items.append(item)
            continue

        if input_path is None:
            item["errors"].append("Missing input schema file (input.schema.json or input.json).")
        else:
            try:
                input_doc = _read_json_file(input_path)
                item["input_fields"] = _extract_schema_fields(input_doc)
            except Exception as exc:
                item["errors"].append(f"Failed to parse input schema: {exc}")

        if output_path is None:
            item["errors"].append("Missing output schema file (output.schema.json or output.json).")
        else:
            try:
                output_doc = _read_json_file(output_path)
                item["output_fields"] = _extract_schema_fields(output_doc)
            except Exception as exc:
                item["errors"].append(f"Failed to parse output schema: {exc}")

        report_items.append(item)

    payload: dict[str, Any] = {
        "docker_model_root": str(docker_model_root),
        "count": len(report_items),
        "items": report_items,
    }

    if args.json:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return

    print_status(
        "INSPECT",
        f"DockerModel root: {docker_model_root} | target(s): {len(report_items)}",
        color="cyan",
    )
    for item in report_items:
        docker_name = str(item.get("docker_name", "unknown"))
        group_name = str(item.get("group", "") or "ungrouped")
        print_status(
            "DOCKER",
            f"{docker_name} (group={group_name})",
            color="magenta",
        )
        print_status("PATH", f"folder={item.get('folder_path', '')}", color="blue")
        print_status("PATH", f"input={item.get('input_path', 'missing')}", color="blue")
        print_status("PATH", f"output={item.get('output_path', 'missing')}", color="blue")

        input_fields = item.get("input_fields", [])
        output_fields = item.get("output_fields", [])
        errors = item.get("errors", [])
        if isinstance(errors, list) and errors:
            for err in errors:
                print_warning(str(err))

        print_status("INPUT", _format_field_summary(input_fields), color="cyan")
        for row in _iter_field_lines(input_fields):
            print_status("FIELD", row, color="green")

        print_status("OUTPUT", _format_field_summary(output_fields), color="cyan")
        for row in _iter_field_lines(output_fields):
            print_status("FIELD", row, color="green")


def _handle_list_docker_ports(args: argparse.Namespace) -> None:
    launch_config = _load_optional_launch_config(args.launch_config)
    docker_model_root_value = args.docker_model_root or (
        launch_config.docker_model_root if launch_config else None
    )
    docker_model_root = _require_docker_model_root(docker_model_root_value)

    docker_names = list(args.docker_names) if args.docker_names else []
    if not docker_names and launch_config:
        docker_names = list(launch_config.docker_names)
    if not docker_names:
        docker_names = describe_targets(docker_model_root)

    if not docker_names:
        print_warning("No docker names found to inspect.")
        return

    group_lookup = _build_group_lookup(launch_config)
    matches = match_requested_dockers(
        docker_model_root,
        docker_names,
        group_lookup=group_lookup,
    )

    print_status("PORT", f"Configured docker services: {len(matches)}", color="cyan")
    for match in matches:
        try:
            info = read_docker_configured_port(match.target)
        except Exception as exc:
            print_warning(f"{match.target.folder_name}: {exc}")
            continue

        port_text = str(info.port) if info.port is not None else "missing"
        container_text = info.container_name or "-"
        print_status(
            "DOCKER",
            (
                f"{info.docker_name} port={port_text} host={info.host} "
                f"container={container_text} config={info.config_path}"
            ),
            color="blue",
        )


def _handle_inspect_ports(args: argparse.Namespace) -> None:
    listeners = list_listening_ports()
    print_status("PORT", f"Listening services: {len(listeners)}", color="cyan")
    for item in listeners:
        process = item.process or "-"
        print_status(
            "LISTEN",
            f"{item.protocol:<4} {item.local_address} state={item.state} peer={item.peer_address} proc={process}",
            color="blue",
        )

    if args.port is None:
        return

    port = int(args.port)
    if port <= 0 or port > 65535:
        raise ValueError("--port must be between 1 and 65535.")

    matching_listeners = [item for item in listeners if item.port == port]
    if matching_listeners:
        print_success(f"Port {port} is listening.")
    else:
        print_warning(f"Port {port} is not in the current listening-port list.")

    connections = inspect_port_connections(port)
    print_status("PORT", f"Active socket entries for {port}: {len(connections)}", color="cyan")
    for item in connections:
        process = item.process or "-"
        print_status(
            "FLOW",
            f"{item.protocol:<4} {item.state} {item.local_address} <-> {item.peer_address} proc={process}",
            color="magenta",
        )

    watch_seconds = int(args.watch_seconds or 0)
    if watch_seconds <= 0:
        return

    print_status(
        "WATCH",
        f"Watching port {port} for {watch_seconds}s via tcpdump.",
        color="cyan",
    )
    result = watch_port_activity(port, watch_seconds)
    if not result.available:
        print_warning(result.error)
        return
    if result.requires_root:
        print_warning(
            "tcpdump needs elevated privileges. Re-run with sudo, for example: "
            f"sudo PYTHONPATH=src python3 -m fusion_docker inspect-ports --port {port} --watch-seconds {watch_seconds}"
        )
        if result.error:
            print_warning(result.error)
        return

    if result.packet_count > 0:
        print_success(f"Observed {result.packet_count} packet(s) on port {port} within {watch_seconds}s.")
    else:
        print_warning(f"No packets observed on port {port} within {watch_seconds}s.")
    if result.output:
        for line in result.output.splitlines():
            print_status("PACKET", line, color="green")
    if result.error:
        print_warning(result.error)


def _force_stop_all_local_containers() -> None:
    docker_bin = shutil.which("docker")
    if docker_bin is None:
        print_warning("docker command not found. Skip stopping containers.")
        return

    listed = subprocess.run(
        [docker_bin, "ps", "-aq"],
        capture_output=True,
        text=True,
        check=False,
    )
    if listed.returncode != 0:
        detail = listed.stderr.strip() or listed.stdout.strip() or "unknown error"
        print_warning(f"Failed to list containers: {detail}")
        return

    container_ids = [line.strip() for line in listed.stdout.splitlines() if line.strip()]
    if not container_ids:
        print_status("DOCKER", "No local containers to stop.", color="blue")
        return

    removed = subprocess.run(
        [docker_bin, "rm", "-f", *container_ids],
        capture_output=True,
        text=True,
        check=False,
    )
    if removed.returncode != 0:
        detail = removed.stderr.strip() or removed.stdout.strip() or "unknown error"
        raise RuntimeError(f"Failed to stop/remove containers: {detail}")
    print_success(f"Stopped and removed {len(container_ids)} local container(s).")


def _collect_restart_target_ports(args: argparse.Namespace) -> list[int]:
    launch_config = _load_optional_launch_config(args.launch_config)
    docker_model_root_value = args.docker_model_root or (
        launch_config.docker_model_root if launch_config else None
    )
    has_target_entries = bool(launch_config and launch_config.docker_targets)
    docker_model_root = (
        _require_docker_model_root(docker_model_root_value)
        if docker_model_root_value
        else None
    )
    if docker_model_root is None and not has_target_entries:
        return []

    docker_names = list(args.docker_names) if args.docker_names else []
    if not docker_names and launch_config:
        docker_names = list(launch_config.docker_names)
    if not docker_names and docker_model_root is not None:
        docker_names = describe_targets(docker_model_root)
    if not docker_names:
        return []

    group_lookup = _build_group_lookup(launch_config)
    matches = _match_dockers_for_runtime(
        docker_names,
        launch_config=launch_config,
        docker_model_root=docker_model_root,
        group_lookup=group_lookup,
    )

    ports: set[int] = set()
    for match in matches:
        if match.target.is_remote:
            continue
        try:
            info = read_docker_configured_port(match.target)
        except Exception as exc:
            print_warning(f"{match.target.folder_name}: failed to read configured port: {exc}")
            continue
        if info.port is None:
            continue
        if 1 <= info.port <= 65535:
            ports.add(int(info.port))
    return sorted(ports)


def _release_ports(ports: list[int]) -> None:
    if not ports:
        return
    print_status("PORT", f"Cleaning owner processes on configured port(s): {', '.join(str(p) for p in ports)}", color="cyan")
    for port in ports:
        pids = _find_port_owner_pids(port)
        if not pids:
            print_status("PORT", f"{port}: no owner process found.", color="blue")
            continue
        killed_count = 0
        for pid in sorted(pids):
            if _terminate_pid(pid):
                killed_count += 1
        if killed_count > 0:
            print_success(f"Port {port}: stopped {killed_count} owner process(es).")
            continue
        print_warning(f"Port {port}: found PID(s) but unable to stop them (permission denied or already exited).")


def _find_port_owner_pids(port: int) -> set[int]:
    pids = _pids_from_lsof(port)
    if pids:
        return pids
    pids = _pids_from_fuser(port)
    if pids:
        return pids
    return _pids_from_ss(port)


def _pids_from_lsof(port: int) -> set[int]:
    lsof_bin = shutil.which("lsof")
    if lsof_bin is None:
        return set()
    completed = subprocess.run(
        [lsof_bin, "-ti", f"tcp:{port}"],
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0 and not completed.stdout.strip():
        return set()
    pids: set[int] = set()
    for line in completed.stdout.splitlines():
        value = line.strip()
        if value.isdigit():
            pids.add(int(value))
    return pids


def _pids_from_fuser(port: int) -> set[int]:
    fuser_bin = shutil.which("fuser")
    if fuser_bin is None:
        return set()
    completed = subprocess.run(
        [fuser_bin, "-n", "tcp", str(port)],
        capture_output=True,
        text=True,
        check=False,
    )
    output = f"{completed.stdout} {completed.stderr}"
    pids: set[int] = set()
    for token in output.split():
        if token.isdigit():
            pids.add(int(token))
    return pids


def _pids_from_ss(port: int) -> set[int]:
    completed = subprocess.run(
        ["ss", "-lntupH"],
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        return set()
    pids: set[int] = set()
    for line in completed.stdout.splitlines():
        text = line.strip()
        if not text:
            continue
        if f":{port} " not in f"{text} ":
            continue
        for pid_text in re.findall(r"pid=(\d+)", text):
            pids.add(int(pid_text))
    return pids


def _terminate_pid(pid: int) -> bool:
    if pid <= 0 or pid == os.getpid():
        return False
    try:
        os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        return True
    except PermissionError:
        return False
    except OSError:
        return False

    for _ in range(20):
        if not _pid_exists(pid):
            return True
        time.sleep(0.1)
    try:
        os.kill(pid, signal.SIGKILL)
    except ProcessLookupError:
        return True
    except PermissionError:
        return False
    except OSError:
        return False
    return not _pid_exists(pid)


def _pid_exists(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _handle_listen_zmq(args: argparse.Namespace) -> None:
    port = int(args.port)
    if port <= 0 or port > 65535:
        raise ValueError("--port must be between 1 and 65535.")
    if args.limit is not None and int(args.limit) <= 0:
        raise ValueError("--limit must be greater than 0.")
    if args.timeout_ms is not None and int(args.timeout_ms) <= 0:
        raise ValueError("--timeout-ms must be greater than 0.")

    endpoint = f"tcp://{args.host}:{port}"
    print_status("ZMQ", f"Listening on {endpoint} topic='{args.topic}'", color="cyan")
    printed_count = 0

    def _print_message(item) -> None:
        nonlocal printed_count
        printed_count += 1
        print_status(
            "ZMQ",
            f"message={item.index} parts={item.part_count} payload={item.rendered}",
            color="green",
        )

    messages = listen_zmq_messages(
        endpoint=endpoint,
        topic=str(args.topic),
        limit=int(args.limit) if args.limit is not None else None,
        timeout_ms=int(args.timeout_ms) if args.timeout_ms is not None else None,
        on_message=_print_message,
    )
    if not messages:
        print_warning("No ZMQ messages received.")
        return
    if args.limit is not None or args.timeout_ms is not None:
        print_status("ZMQ", f"Received {printed_count} message(s).", color="cyan")


def _resolve_first_existing(base_dir: Path, names: tuple[str, ...]) -> Path | None:
    for name in names:
        candidate = base_dir / name
        if candidate.is_file():
            return candidate
    return None


def _read_json_file(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _extract_schema_fields(schema_doc: Any) -> list[dict[str, Any]]:
    if not isinstance(schema_doc, dict):
        return []

    properties = schema_doc.get("properties")
    required_set = {
        str(item).strip()
        for item in schema_doc.get("required", [])
        if str(item).strip()
    } if isinstance(schema_doc.get("required"), list) else set()

    rows: list[dict[str, Any]] = []
    if isinstance(properties, dict):
        for field_name, field_spec in properties.items():
            if not isinstance(field_spec, dict):
                field_spec = {}
            raw_type = field_spec.get("type")
            if isinstance(raw_type, list):
                field_type = "|".join(str(t).strip() for t in raw_type if str(t).strip())
            else:
                field_type = str(raw_type).strip() if raw_type is not None else "unknown"
            rows.append(
                {
                    "name": str(field_name),
                    "required": str(field_name) in required_set,
                    "type": field_type or "unknown",
                    "format": str(field_spec.get("format", "")).strip(),
                    "encoding": str(field_spec.get("contentEncoding", "")).strip(),
                    "description": str(field_spec.get("description", "")).strip(),
                }
            )
        return rows

    for key, value in schema_doc.items():
        rows.append(
            {
                "name": str(key),
                "required": True,
                "type": type(value).__name__,
                "format": "",
                "encoding": "",
                "description": "",
            }
        )
    return rows


def _format_field_summary(rows: Any) -> str:
    if not isinstance(rows, list) or not rows:
        return "no fields found"
    required_count = 0
    for row in rows:
        if isinstance(row, dict) and bool(row.get("required", False)):
            required_count += 1
    return f"fields={len(rows)}, required={required_count}"


def _iter_field_lines(rows: Any) -> list[str]:
    if not isinstance(rows, list):
        return []
    lines: list[str] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        name = str(row.get("name", "")).strip()
        if not name:
            continue
        required = bool(row.get("required", False))
        field_type = str(row.get("type", "unknown")).strip() or "unknown"
        fmt = str(row.get("format", "")).strip()
        encoding = str(row.get("encoding", "")).strip()
        description = str(row.get("description", "")).strip()
        prefix = "[required]" if required else "[optional]"
        extra_parts: list[str] = []
        if fmt:
            extra_parts.append(f"format={fmt}")
        if encoding:
            extra_parts.append(f"encoding={encoding}")
        if description:
            extra_parts.append(f"desc={description}")
        extra = f" ({', '.join(extra_parts)})" if extra_parts else ""
        lines.append(f"{prefix} {name}: {field_type}{extra}")
    return lines


def _handle_serve_ui(args: argparse.Namespace) -> None:
    from fusion_docker.ui_server import serve_dashboard_ui

    launch_config = _load_optional_launch_config(args.launch_config)
    launch_config_path = _resolve_launch_config_path(args.launch_config)
    docker_model_root_value = args.docker_model_root or (
        launch_config.docker_model_root if launch_config else None
    )
    docker_model_root = (
        _require_docker_model_root(docker_model_root_value)
        if docker_model_root_value
        else None
    )
    has_target_entries = bool(launch_config and launch_config.docker_targets)
    if docker_model_root is None and not has_target_entries:
        raise ValueError(
            "Please provide --docker-model-root (or docker_launcher.docker_model_root), "
            "or define docker_launcher.docker_targets in launch config."
        )

    docker_names = list(args.docker_names) if args.docker_names else []
    if not docker_names and launch_config:
        docker_names = list(launch_config.docker_names)
    if not docker_names:
        if has_target_entries:
            docker_names = [entry.name for entry in launch_config.docker_targets]
        else:
            assert docker_model_root is not None
            docker_names = describe_targets(docker_model_root)

    ui_host, ui_port, ui_log_lines = _resolve_ui_settings(args, launch_config)

    if ui_port <= 0 or ui_port > 65535:
        raise ValueError("--port must be between 1 and 65535.")
    if ui_log_lines <= 0:
        raise ValueError("--log-lines must be greater than 0.")

    group_lookup = _build_group_lookup(launch_config)
    matches = _match_dockers_for_runtime(
        docker_names,
        launch_config=launch_config,
        docker_model_root=docker_model_root,
        group_lookup=group_lookup,
    )
    print_status(
        "UI",
        f"Preparing dashboard for {len(matches)} docker target(s).",
        color="cyan",
    )
    serve_dashboard_ui(
        matches=matches,
        host=ui_host,
        port=ui_port,
        log_lines=ui_log_lines,
        project_root=Path.cwd().resolve(),
        launch_config_path=launch_config_path,
        docker_model_root_hint=docker_model_root,
        docker_model_root_override=(
            Path(args.docker_model_root).expanduser().resolve()
            if args.docker_model_root
            else None
        ),
        docker_names_override=list(args.docker_names) if args.docker_names else None,
        bridge_entries=launch_config.bridge_entries if launch_config else None,
    )


def _handle_create_system(args: argparse.Namespace) -> None:
    launch_config = _load_optional_launch_config(args.launch_config)
    docker_model_root_value = args.docker_model_root or (
        launch_config.docker_model_root if launch_config else None
    )
    docker_model_root = _require_docker_model_root(docker_model_root_value)

    print_status(
        "SCAFFOLD",
        f"Creating system scaffold '{args.name}' under {docker_model_root}",
        color="cyan",
    )
    result = create_system_scaffold(
        name=args.name,
        docker_model_root=docker_model_root,
        server_host=args.server_host,
        server_port=int(args.server_port),
        force=bool(args.force),
    )

    print_success(f"Scaffold ready: {result.folder_path}")
    print_status("DOCKER", f"folder={result.folder_name} image={result.image_name}", color="magenta")
    for path in result.created_dirs:
        print_status("DIR", str(path), color="blue")
    for path in result.created_files:
        print_status("FILE", str(path), color="green")
    for path in result.updated_files:
        print_status("UPDATE", str(path), color="yellow")


def _handle_create_bridge(args: argparse.Namespace) -> None:
    project_root = Path(args.project_root).expanduser().resolve()
    print_status(
        "SCAFFOLD",
        f"Creating bridge scaffold '{args.name}' under {project_root}",
        color="cyan",
    )
    result = create_bridge_scaffold(
        name=args.name,
        project_root=project_root,
        force=bool(args.force),
    )

    print_success(f"Bridge scaffold ready: {result.bridge_kind}")
    print_status("BRIDGE", f"module={result.module_name}", color="magenta")
    for path in result.created_files:
        print_status("FILE", str(path), color="green")
    for path in result.updated_files:
        print_status("UPDATE", str(path), color="yellow")


def _handle_add_bridge_to_ui(args: argparse.Namespace) -> None:
    launch_config_path = Path(args.launch_config).expanduser().resolve()
    print_status(
        "CONFIG",
        f"Updating bridge entries in {launch_config_path}",
        color="cyan",
    )
    result = add_bridge_to_launch_config(
        launch_config_path=launch_config_path,
        bridge_name=args.name,
        bridge_config_path=args.bridge_config,
        enabled=not bool(args.disabled),
        force=bool(args.force),
    )

    action = "updated" if result.updated else "created"
    print_success(
        f"Bridge '{result.bridge_name}' {action} in {result.launch_config_path}"
    )
    print_status("BRIDGE", f"config={result.config_path}", color="magenta")
    print_status("BRIDGE", f"bridge_count={result.bridge_count}", color="blue")


def _require_docker_model_root(raw_path: str | None) -> Path:
    if not raw_path:
        raise ValueError(
            "Please provide --docker-model-root or set DOCKER_MODEL_ROOT first."
        )
    return Path(raw_path).expanduser().resolve()


def _load_optional_launch_config(raw_path: str | None):
    resolved = _resolve_launch_config_path(raw_path)
    if resolved is not None:
        print_status("CONFIG", f"Using docker launch config: {resolved}", color="cyan")
        return load_docker_launch_config(resolved)
    return None


def _resolve_launch_config_path(raw_path: str | None) -> Path | None:
    candidate_paths: list[Path] = []
    if raw_path:
        candidate_paths.append(Path(raw_path))
    else:
        default_path = Path("configs/docker_launch.yaml")
        if default_path.exists():
            candidate_paths.append(default_path)

    for candidate in candidate_paths:
        resolved = candidate.expanduser().resolve()
        if resolved.exists():
            return resolved
        if raw_path:
            raise FileNotFoundError(f"Docker launch config not found: {resolved}")
    return None


def _build_group_lookup(launch_config) -> dict[str, str]:
    if launch_config is None:
        return {}

    group_lookup: dict[str, str] = {}
    for group_name, docker_names in launch_config.docker_groups.items():
        for docker_name in docker_names:
            group_lookup[docker_name] = group_name
    return group_lookup


def _match_dockers_for_runtime(
    docker_names: list[str],
    *,
    launch_config,
    docker_model_root: Path | None,
    group_lookup: dict[str, str],
):
    if launch_config is None or not launch_config.docker_targets:
        if docker_model_root is None:
            raise ValueError("docker_model_root is required for non-target launch mode.")
        return match_requested_dockers(
            docker_model_root,
            docker_names,
            group_lookup=group_lookup,
        )

    entries_by_name = {
        normalize_docker_name(entry.name): entry
        for entry in launch_config.docker_targets
    }
    selected_entries: list[DockerTargetEntry] = []
    for requested_name in docker_names:
        normalized_requested = normalize_docker_name(requested_name)
        entry = entries_by_name.get(normalized_requested)
        if entry is None:
            raise FileNotFoundError(
                f"Docker '{requested_name}' is not defined in docker_launcher.docker_targets."
            )
        selected_entries.append(entry)

    grouped_scan_requests: dict[
        tuple[str, str, str, int, str],
        dict[str, object],
    ] = {}
    for entry in selected_entries:
        (
            root_value,
            remote_host,
            remote_user,
            remote_ssh_port,
            remote_password,
        ) = _resolve_target_entry_scan_params(
            entry,
            launch_config=launch_config,
            docker_model_root=docker_model_root,
        )
        scan_key = (
            str(root_value),
            str(remote_host or ""),
            str(remote_user or ""),
            int(remote_ssh_port or 22),
            str(remote_password or ""),
        )
        request_group = grouped_scan_requests.get(scan_key)
        if request_group is None:
            request_group = {
                "root_value": str(root_value),
                "remote_host": remote_host,
                "remote_user": remote_user,
                "remote_ssh_port": int(remote_ssh_port or 22),
                "remote_password": remote_password,
                "entries": [],
            }
            grouped_scan_requests[scan_key] = request_group
        entries = request_group["entries"]
        assert isinstance(entries, list)
        entries.append(entry)

    matches = []
    seen_match_keys: set[tuple[str, str, int, str]] = set()
    for request_group in grouped_scan_requests.values():
        entries = request_group["entries"]
        assert isinstance(entries, list)
        docker_names_for_scan = [entry.name for entry in entries]
        group_lookup_for_scan = {entry.name: entry.group for entry in entries}
        try:
            matched = match_requested_dockers(
                request_group["root_value"],
                docker_names_for_scan,
                group_lookup=group_lookup_for_scan,
                remote_host=request_group["remote_host"],
                remote_user=request_group["remote_user"],
                remote_ssh_port=request_group["remote_ssh_port"],
                remote_password=request_group["remote_password"],
            )
        except Exception as exc:
            is_remote_group = bool(request_group["remote_host"])
            if is_remote_group:
                print_warning(
                    "Skip remote docker target group "
                    f"{docker_names_for_scan} on "
                    f"{request_group['remote_user'] or 'unknown'}@{request_group['remote_host']}:"
                    f"{request_group['remote_ssh_port']} due to: {exc}"
                )
                continue
            raise
        for match in matched:
            requested_normalized = normalize_docker_name(match.requested_name)
            matched_entry = next(
                (entry for entry in entries if normalize_docker_name(entry.name) == requested_normalized),
                None,
            )
            if matched_entry is not None:
                match.group_name = matched_entry.group
            target_key = (
                match.target.remote_host or "",
                match.target.remote_user or "",
                int(match.target.remote_ssh_port),
                str(match.target.run_script_path),
            )
            if target_key in seen_match_keys:
                continue
            seen_match_keys.add(target_key)
            matches.append(match)
    if not matches:
        print_warning("No runnable docker matched after skipping failed remote targets.")
    return matches


def _resolve_target_entry_scan_params(
    entry: DockerTargetEntry,
    *,
    launch_config,
    docker_model_root: Path | None,
) -> tuple[str, str | None, str | None, int, str | None]:
    if entry.location == "remote":
        remote_root = (
            entry.remote_docker_model_root
            or launch_config.remote_docker_model_root
            or launch_config.docker_model_root
        )
        if not remote_root:
            raise ValueError(
                f"Docker target '{entry.name}' is remote but remote_docker_model_root is missing."
            )
        if not entry.remote_host:
            raise ValueError(
                f"Docker target '{entry.name}' is remote but remote_host is missing."
            )
        remote_password = entry.remote_password or launch_config.remote_password
        return (
            str(remote_root),
            entry.remote_host,
            entry.remote_user,
            int(entry.remote_ssh_port or 22),
            remote_password,
        )

    local_root = (
        entry.docker_model_root
        or launch_config.docker_model_root
        or (str(docker_model_root) if docker_model_root is not None else None)
    )
    if not local_root:
        raise ValueError(
            f"Docker target '{entry.name}' is local but docker_model_root is not configured."
        )
    return str(local_root), None, None, 22, None


def _resolve_ui_settings(args: argparse.Namespace, launch_config) -> tuple[str, int, int]:
    ui_host = (
        getattr(args, "host", None)
        or (launch_config.ui_host if launch_config else None)
        or "127.0.0.1"
    )
    ui_port = (
        getattr(args, "port", None)
        if getattr(args, "port", None) is not None
        else (launch_config.ui_port if launch_config else 8765)
    )
    ui_log_lines = (
        getattr(args, "log_lines", None)
        if getattr(args, "log_lines", None) is not None
        else (launch_config.ui_log_lines if launch_config else 300)
    )
    return str(ui_host), int(ui_port), int(ui_log_lines)


if __name__ == "__main__":
    main()
