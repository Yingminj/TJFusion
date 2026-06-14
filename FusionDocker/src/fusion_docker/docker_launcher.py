from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from pathlib import Path, PurePosixPath
import os
import re
import select
import shlex
import shutil
import subprocess
import sys
import time

from fusion_docker.console import print_banner, print_status, print_success, print_warning

COMPOSE_FILENAMES = (
    "docker-compose.yml",
    "docker-compose.yaml",
    "compose.yml",
    "compose.yaml",
)
NEW_CONTAINER_DISCOVERY_TIMEOUT_S = 4.0
NEW_CONTAINER_DISCOVERY_POLL_S = 0.4
DEFAULT_MONITOR_POLL_INTERVAL_S = 0.5
# Upper bound for the read-only status probes (docker ps / tmux list-panes) so a
# hung daemon can never block the dashboard's background status refresher.
RUNTIME_STATUS_PROBE_TIMEOUT_S = 8.0
STATUS_COLOR = {
    "running": "green",
    "error": "red",
    "ended": "yellow",
    "missing": "red",
    "unknown": "magenta",
}
MISSING_IMAGE_HINTS = (
    "unable to find image",
    "no such image",
    "pull access denied",
    "repository does not exist",
    "manifest unknown",
    "not found: manifest unknown",
)
DOCKER_RUN_OPTION_WITH_VALUE = {
    "-a",
    "-c",
    "-e",
    "-h",
    "-l",
    "-m",
    "-p",
    "-u",
    "-v",
    "-w",
    "--add-host",
    "--annotation",
    "--blkio-weight",
    "--cap-add",
    "--cap-drop",
    "--cgroup-parent",
    "--cgroupns",
    "--cidfile",
    "--cpu-period",
    "--cpu-quota",
    "--cpu-rt-period",
    "--cpu-rt-runtime",
    "--cpu-shares",
    "--cpus",
    "--cpuset-cpus",
    "--cpuset-mems",
    "--device",
    "--device-cgroup-rule",
    "--device-read-bps",
    "--device-read-iops",
    "--device-write-bps",
    "--device-write-iops",
    "--dns",
    "--dns-option",
    "--dns-search",
    "--entrypoint",
    "--env",
    "--env-file",
    "--expose",
    "--gpus",
    "--group-add",
    "--health-cmd",
    "--health-interval",
    "--health-retries",
    "--health-start-interval",
    "--health-start-period",
    "--health-timeout",
    "--hostname",
    "--init-path",
    "--ip",
    "--ip6",
    "--ipc",
    "--isolation",
    "--label",
    "--label-file",
    "--link",
    "--link-local-ip",
    "--log-driver",
    "--log-opt",
    "--mac-address",
    "--memory",
    "--memory-reservation",
    "--memory-swap",
    "--memory-swappiness",
    "--mount",
    "--name",
    "--network",
    "--network-alias",
    "--oom-kill-disable",
    "--oom-score-adj",
    "--pid",
    "--platform",
    "--pids-limit",
    "--publish",
    "--publish-all",
    "--pull",
    "--restart",
    "--runtime",
    "--security-opt",
    "--shm-size",
    "--stop-signal",
    "--stop-timeout",
    "--sysctl",
    "--tmpfs",
    "--ulimit",
    "--user",
    "--userns",
    "--uts",
    "--volume",
    "--volumes-from",
    "--workdir",
}


@dataclass(slots=True)
class DockerRunTarget:
    folder_name: str
    folder_path: Path
    run_script_path: Path
    relative_folder: str
    remote_host: str | None = None
    remote_user: str | None = None
    remote_ssh_port: int = 22
    remote_password: str | None = None

    @property
    def is_remote(self) -> bool:
        return bool(self.remote_host)


@dataclass(slots=True)
class DockerMatch:
    requested_name: str
    target: DockerRunTarget
    strategy: str
    score: float
    group_name: str | None = None


@dataclass(slots=True)
class DockerContainerInfo:
    container_id: str
    name: str
    status: str
    image: str = ""
    ports: str = ""


@dataclass(slots=True)
class DockerLaunchResult:
    match: DockerMatch
    return_code: int
    log_path: Path | None = None
    pid: int | None = None
    detached: bool = False
    tmux_session: str | None = None
    reused_existing: bool = False
    container_ids: list[str] = field(default_factory=list)
    dry_run: bool = False
    startup_output: str | None = None

    @property
    def succeeded(self) -> bool:
        return self.return_code == 0


@dataclass(slots=True)
class DockerRuntimeStatus:
    result: DockerLaunchResult
    session_state: str
    session_exit_status: int | None
    container_infos: list[DockerContainerInfo]
    overall_status: str
    container_summary: str
    image_summary: str
    ports_summary: str


def discover_docker_targets(
    root: str | Path,
    *,
    remote_host: str | None = None,
    remote_user: str | None = None,
    remote_ssh_port: int = 22,
    remote_password: str | None = None,
) -> list[DockerRunTarget]:
    if remote_host:
        return _discover_remote_docker_targets(
            root,
            remote_host=remote_host,
            remote_user=remote_user,
            remote_ssh_port=remote_ssh_port,
            remote_password=remote_password,
        )

    resolved_root = Path(os.path.expanduser(os.path.expandvars(str(root)))).resolve()
    if not resolved_root.exists():
        raise FileNotFoundError(f"DockerModel path does not exist: {resolved_root}")
    if not resolved_root.is_dir():
        raise NotADirectoryError(f"DockerModel path is not a directory: {resolved_root}")

    targets: list[DockerRunTarget] = []
    for run_script in sorted(resolved_root.rglob("run.sh")):
        if not run_script.is_file():
            continue
        folder = run_script.parent
        targets.append(
            DockerRunTarget(
                folder_name=folder.name,
                folder_path=folder,
                run_script_path=run_script,
                relative_folder=str(folder.relative_to(resolved_root)),
            )
        )
    return targets


def match_requested_dockers(
    root: str | Path,
    requested_names: list[str],
    group_lookup: dict[str, str] | None = None,
    *,
    remote_host: str | None = None,
    remote_user: str | None = None,
    remote_ssh_port: int = 22,
    remote_password: str | None = None,
) -> list[DockerMatch]:
    targets = discover_docker_targets(
        root,
        remote_host=remote_host,
        remote_user=remote_user,
        remote_ssh_port=remote_ssh_port,
        remote_password=remote_password,
    )
    if not targets:
        raise FileNotFoundError(f"No run.sh files found under DockerModel path: {Path(root)}")

    matches: list[DockerMatch] = []
    used_scripts: set[Path] = set()

    for requested_name in requested_names:
        best_match = _find_best_match(requested_name, targets)
        if group_lookup is not None:
            best_match.group_name = group_lookup.get(requested_name)
        if best_match.target.run_script_path in used_scripts:
            print_warning(
                f"Docker '{requested_name}' matched an already selected folder, skipping duplicate launch."
            )
            continue
        used_scripts.add(best_match.target.run_script_path)
        matches.append(best_match)

    return matches


def _remote_target_label(target: DockerRunTarget) -> str:
    if not target.remote_host:
        return "local"
    if target.remote_user:
        return f"{target.remote_user}@{target.remote_host}:{target.remote_ssh_port}"
    return f"{target.remote_host}:{target.remote_ssh_port}"


def _remote_path_text(path: Path) -> str:
    return PurePosixPath(str(path)).as_posix()


def _resolve_sshpass_path() -> str | None:
    for env_key in ("FUSION_SSHPASS_PATH", "SSHPASS_PATH"):
        raw = str(os.environ.get(env_key, "")).strip()
        if not raw:
            continue
        explicit_path = Path(raw).expanduser()
        if explicit_path.is_file() and os.access(explicit_path, os.X_OK):
            return str(explicit_path)

    search_path = os.environ.get("PATH", "")
    discovered = shutil.which("sshpass", path=search_path)
    if discovered:
        return discovered

    for candidate in (
        "/usr/bin/sshpass",
        "/usr/local/bin/sshpass",
        "/opt/homebrew/bin/sshpass",
        "/snap/bin/sshpass",
    ):
        candidate_path = Path(candidate)
        if candidate_path.is_file() and os.access(candidate_path, os.X_OK):
            return str(candidate_path)
    return None


def _build_ssh_exec_command(
    target: DockerRunTarget,
    *,
    remote_command: str,
) -> list[str]:
    if not target.remote_host:
        raise ValueError("remote_host is required for SSH command execution.")
    ssh_path = _require_command("ssh")
    remote_endpoint = (
        f"{target.remote_user}@{target.remote_host}"
        if target.remote_user
        else target.remote_host
    )
    ssh_command = [
        ssh_path,
        "-p",
        str(target.remote_ssh_port),
        remote_endpoint,
        "bash",
        "-lc",
        remote_command,
    ]
    if target.remote_password:
        sshpass_path = _resolve_sshpass_path()
        if not sshpass_path:
            path_text = os.environ.get("PATH", "")
            raise FileNotFoundError(
                "sshpass is required when remote_password is configured. "
                "Please install sshpass on this machine, or set "
                "FUSION_SSHPASS_PATH to the absolute sshpass binary path. "
                f"Current PATH={path_text}"
            )
        return [
            sshpass_path,
            "-p",
            target.remote_password,
            *ssh_command,
        ]
    return ssh_command


def _discover_remote_docker_targets(
    root: str | Path,
    *,
    remote_host: str,
    remote_user: str | None,
    remote_ssh_port: int,
    remote_password: str | None,
) -> list[DockerRunTarget]:
    root_text = str(root).strip()
    if not root_text:
        raise ValueError("Remote DockerModel path is required.")

    find_command = f"find {shlex.quote(root_text)} -type f -name run.sh | sort"
    probe_target = DockerRunTarget(
        folder_name="remote_probe",
        folder_path=Path(root_text),
        run_script_path=Path(root_text) / "run.sh",
        relative_folder="remote_probe",
        remote_host=remote_host,
        remote_user=remote_user,
        remote_ssh_port=remote_ssh_port,
        remote_password=remote_password,
    )

    verify_command = f"test -d {shlex.quote(root_text)}"
    verified = subprocess.run(
        _build_ssh_exec_command(probe_target, remote_command=verify_command),
        check=False,
        capture_output=True,
        text=True,
    )
    if verified.returncode != 0:
        verify_detail = (verified.stderr.strip() or verified.stdout.strip())
        verify_detail_lower = verify_detail.lower()
        if verified.returncode == 1 and (
            not verify_detail
            or "no such file or directory" in verify_detail_lower
            or "not a directory" in verify_detail_lower
        ):
            raise FileNotFoundError(
                f"Remote DockerModel path does not exist or is not a directory: {root_text} "
                f"on {_remote_target_label(probe_target)}"
            )
        raise RuntimeError(
            f"Failed to validate remote DockerModel path '{root_text}' on "
            f"{_remote_target_label(probe_target)}: {verify_detail or f'exit code {verified.returncode}'}"
        )

    listed = subprocess.run(
        _build_ssh_exec_command(probe_target, remote_command=find_command),
        check=False,
        capture_output=True,
        text=True,
    )
    if listed.returncode != 0:
        raise RuntimeError(
            f"Failed to scan remote DockerModel path '{root_text}' on "
            f"{_remote_target_label(probe_target)}: "
            f"{listed.stderr.strip() or listed.stdout.strip()}"
        )

    remote_root = PurePosixPath(root_text)
    targets: list[DockerRunTarget] = []
    for raw_line in listed.stdout.splitlines():
        run_script_text = raw_line.strip()
        if not run_script_text:
            continue
        run_script_posix = PurePosixPath(run_script_text)
        folder_posix = run_script_posix.parent
        try:
            relative_folder = str(folder_posix.relative_to(remote_root))
        except ValueError:
            relative_folder = folder_posix.name
        targets.append(
            DockerRunTarget(
                folder_name=folder_posix.name,
                folder_path=Path(folder_posix.as_posix()),
                run_script_path=Path(run_script_posix.as_posix()),
                relative_folder=relative_folder,
                remote_host=remote_host,
                remote_user=remote_user,
                remote_ssh_port=remote_ssh_port,
                remote_password=remote_password,
            )
        )
    if not targets:
        raise FileNotFoundError(
            f"No run.sh files found under remote DockerModel path: {root_text} "
            f"on {_remote_target_label(probe_target)}"
        )
    return targets


def launch_matched_dockers(
    matches: list[DockerMatch],
    *,
    dry_run: bool = False,
    detached: bool = True,
    log_dir: str | Path | None = None,
    use_tmux: bool = False,
    replace_session: bool = False,
) -> list[DockerLaunchResult]:
    results: list[DockerLaunchResult] = []
    resolved_log_dir = (
        _resolve_log_dir(log_dir)
        if detached and not dry_run and not use_tmux
        else None
    )

    for match in matches:
        print_status(
            "START",
            f"Launching docker '{match.target.folder_name}' from {match.target.run_script_path}",
            color="green",
        )

        launch_mode_detached = detached and not use_tmux
        if match.target.is_remote:
            if dry_run:
                print_status(
                    "DRYRUN",
                    (
                        f"Would execute remote run.sh via ssh on "
                        f"{_remote_target_label(match.target)}"
                    ),
                    color="magenta",
                )
                results.append(
                    DockerLaunchResult(
                        match=match,
                        return_code=0,
                        detached=False,
                        dry_run=True,
                    )
                )
                continue

            if use_tmux:
                result = _launch_remote_tmux(match, replace_session=replace_session)
            elif detached:
                result = _launch_remote_background(match)
            else:
                result = _launch_remote_foreground(match)
            results.append(result)
            if result.succeeded:
                if use_tmux:
                    if result.reused_existing:
                        print_warning(
                            f"Remote tmux session reused for '{match.target.folder_name}' on "
                            f"{_remote_target_label(match.target)}."
                        )
                    else:
                        print_success(
                            f"Remote docker '{match.target.folder_name}' started in tmux on "
                            f"{_remote_target_label(match.target)}."
                        )
                elif result.detached:
                    print_success(
                        f"Remote docker '{match.target.folder_name}' start command sent on "
                        f"{_remote_target_label(match.target)} (pid={result.pid or 'unknown'})."
                    )
                else:
                    print_success(
                        f"Remote docker '{match.target.folder_name}' launched on "
                        f"{_remote_target_label(match.target)}."
                    )
            else:
                print_status(
                    "ERROR",
                    (
                        f"Remote docker '{match.target.folder_name}' failed on "
                        f"{_remote_target_label(match.target)} "
                        f"(exit code {result.return_code})."
                    ),
                    color="red",
                )
            continue

        before_container_ids = set(_list_docker_containers().keys())

        if dry_run:
            launch_mode = "tmux" if use_tmux else ("background" if detached else "foreground")
            print_status(
                "DRYRUN",
                f"Would execute: bash {match.target.run_script_path.name} ({launch_mode})",
                color="magenta",
            )
            results.append(
                DockerLaunchResult(
                    match=match,
                    return_code=0,
                    detached=launch_mode_detached,
                    tmux_session=_session_name_for_target(match.target) if use_tmux else None,
                    dry_run=True,
                )
            )
            continue

        missing_images = _detect_missing_images(match)
        if missing_images:
            joined_images = ", ".join(missing_images)
            print_warning(
                f"Detected missing image(s) for '{match.target.folder_name}': {joined_images}. "
                "Trying build.sh before launch."
            )
            build_succeeded, build_message = _attempt_auto_build(match, reason=joined_images)
            if not build_succeeded:
                result = DockerLaunchResult(
                    match=match,
                    return_code=1,
                    detached=launch_mode_detached,
                    startup_output=build_message,
                )
                results.append(result)
                print_status(
                    "ERROR",
                    f"Docker '{match.target.folder_name}' failed to launch (exit code {result.return_code}).",
                    color="red",
                )
                print_warning(build_message)
                continue

        result = _launch_once(
            match,
            detached=detached,
            use_tmux=use_tmux,
            replace_session=replace_session,
            log_dir=resolved_log_dir,
        )

        if (not result.succeeded) and _looks_like_missing_image_output(result.startup_output):
            print_warning(
                f"Docker '{match.target.folder_name}' appears to be missing image(s). "
                "Trying build.sh and one retry."
            )
            build_succeeded, build_message = _attempt_auto_build(
                match,
                reason="launch output indicates missing docker image",
            )
            if build_succeeded:
                before_container_ids = set(_list_docker_containers().keys())
                result = _launch_once(
                    match,
                    detached=detached,
                    use_tmux=use_tmux,
                    replace_session=replace_session,
                    log_dir=resolved_log_dir,
                )
            else:
                result.startup_output = (
                    (result.startup_output or "").strip() + "\n" + build_message
                ).strip()
                print_warning(build_message)

        if result.succeeded and not result.reused_existing and not match.target.is_remote:
            result.container_ids = _collect_new_container_ids(before_container_ids)

        results.append(result)

        if result.succeeded:
            if result.tmux_session:
                if result.reused_existing:
                    print_warning(
                        f"tmux session '{result.tmux_session}' already exists, "
                        f"reusing it for docker '{match.target.folder_name}'."
                    )
                else:
                    print_success(
                        f"Docker '{match.target.folder_name}' started in tmux session "
                        f"'{result.tmux_session}'."
                    )
                print_status(
                    "TMUX",
                    f"Session name: {result.tmux_session}",
                    color="cyan",
                )
            elif result.detached:
                print_success(
                    f"Docker '{match.target.folder_name}' started in background "
                    f"(pid={result.pid}, log={result.log_path})."
                )
            else:
                print_success(
                    f"Docker '{match.target.folder_name}' launched successfully "
                    f"using strategy={match.strategy}."
                )
        else:
            print_status(
                "ERROR",
                f"Docker '{match.target.folder_name}' failed to launch (exit code {result.return_code}).",
                color="red",
            )
            if result.log_path is not None:
                print_warning(f"Check log file: {result.log_path}")

    return results


def build_runtime_results(matches: list[DockerMatch]) -> list[DockerLaunchResult]:
    results: list[DockerLaunchResult] = []
    for match in matches:
        results.append(
            DockerLaunchResult(
                match=match,
                return_code=0,
                tmux_session=None if match.target.is_remote else _session_name_for_target(match.target),
                reused_existing=True,
            )
        )
    return results


def launch_single_match(
    match: DockerMatch,
    *,
    use_tmux: bool = True,
    replace_session: bool = True,
    detached: bool = True,
    log_dir: str | Path | None = None,
) -> DockerLaunchResult:
    return launch_matched_dockers(
        [match],
        detached=detached,
        log_dir=log_dir,
        use_tmux=use_tmux,
        replace_session=replace_session,
    )[0]


def stop_launch_result(result: DockerLaunchResult) -> tuple[bool, str]:
    if result.match.target.is_remote:
        target = result.match.target
        session_name = _session_name_for_target(target)
        remote_command = (
            f"if tmux has-session -t {shlex.quote(session_name)} 2>/dev/null; then "
            f"tmux kill-session -t {shlex.quote(session_name)} && echo __FUSION_REMOTE_TMUX_STOPPED__; "
            "else "
            "echo __FUSION_REMOTE_TMUX_MISSING__; "
            "fi"
        )
        try:
            stopped = subprocess.run(
                _build_ssh_exec_command(target, remote_command=remote_command),
                check=False,
                capture_output=True,
                text=True,
            )
        except Exception as exc:
            return (
                False,
                (
                    f"Failed to stop remote docker '{target.folder_name}' on "
                    f"{_remote_target_label(target)}: {exc}"
                ),
            )

        output = (stopped.stdout or "").strip()
        error = (stopped.stderr or "").strip()
        if stopped.returncode != 0:
            return (
                False,
                (
                    f"Failed to stop remote docker '{target.folder_name}' on "
                    f"{_remote_target_label(target)}: {error or output or 'ssh command failed'}"
                ),
            )
        if "__FUSION_REMOTE_TMUX_STOPPED__" in output:
            return (
                True,
                (
                    f"Stopped remote docker '{target.folder_name}' on "
                    f"{_remote_target_label(target)} (tmux session '{session_name}')."
                ),
            )
        return (
            False,
            (
                f"Remote tmux session '{session_name}' was not found on "
                f"{_remote_target_label(target)}. Please stop it manually if still running."
            ),
        )

    stopped_parts: list[str] = []
    warnings: list[str] = []

    tmux_path = shutil.which("tmux")
    docker_path = shutil.which("docker")

    session_name = result.tmux_session
    if session_name and tmux_path:
        has_session = subprocess.run(
            [tmux_path, "has-session", "-t", session_name],
            check=False,
            capture_output=True,
            text=True,
        )
        if has_session.returncode == 0:
            killed = subprocess.run(
                [tmux_path, "kill-session", "-t", session_name],
                check=False,
                capture_output=True,
                text=True,
            )
            if killed.returncode == 0:
                stopped_parts.append(f"tmux session '{session_name}'")
            else:
                warnings.append(
                    killed.stderr.strip() or killed.stdout.strip() or f"failed to kill {session_name}"
                )

    compose_dir = _find_compose_dir(result.match.target.folder_path)
    if compose_dir is not None and docker_path:
        down = subprocess.run(
            [docker_path, "compose", "down", "--remove-orphans"],
            cwd=str(compose_dir),
            check=False,
            capture_output=True,
            text=True,
        )
        if down.returncode == 0:
            stopped_parts.append(f"docker compose in {compose_dir.name}")
        else:
            warnings.append(
                down.stderr.strip() or down.stdout.strip() or f"docker compose down failed in {compose_dir}"
            )

    inferred_ids = _infer_container_ids_for_result(result)
    removable_ids = sorted({*result.container_ids, *inferred_ids})
    if docker_path and removable_ids:
        existing_ids = set(_list_docker_containers().keys())
        live_ids = [container_id for container_id in removable_ids if container_id in existing_ids]
        if live_ids:
            removed = subprocess.run(
                [docker_path, "rm", "-f", *live_ids],
                check=False,
                capture_output=True,
                text=True,
            )
            if removed.returncode == 0:
                stopped_parts.append("containers " + ", ".join(live_ids))
            else:
                warnings.append(
                    removed.stderr.strip() or removed.stdout.strip() or "failed to remove containers"
                )

    if stopped_parts:
        message = "Stopped " + "; ".join(stopped_parts) + "."
        if warnings:
            message += " Warning: " + " | ".join(warnings)
        return True, message
    if warnings:
        return False, "Unable to fully stop docker. " + " | ".join(warnings)
    return True, f"No running resources were found for '{result.match.target.folder_name}'."


def collect_runtime_statuses(results: list[DockerLaunchResult]) -> list[DockerRuntimeStatus]:
    tmux_path = shutil.which("tmux")
    return _collect_runtime_statuses(results, tmux_path)


def resolve_preferred_container(result: DockerLaunchResult) -> DockerContainerInfo | None:
    containers_by_id = _list_docker_containers()
    if not containers_by_id:
        return None

    candidates = [
        containers_by_id[container_id]
        for container_id in result.container_ids
        if container_id in containers_by_id
    ]
    if not candidates:
        inferred_ids = _infer_container_ids_for_result(result)
        candidates = [
            containers_by_id[container_id]
            for container_id in inferred_ids
            if container_id in containers_by_id
        ]
    if not candidates:
        return None

    return next(
        (info for info in candidates if info.status.lower().startswith("up")),
        candidates[0],
    )


def read_result_logs(
    result: DockerLaunchResult,
    *,
    tail_lines: int = 300,
    preserve_ansi: bool = False,
) -> tuple[str, str]:
    if tail_lines <= 0:
        raise ValueError("tail_lines must be greater than 0.")
    if not result.succeeded:
        detail = (result.startup_output or "").strip()
        if detail:
            return (
                "status",
                "Startup status: error "
                f"(launch failed with exit code {result.return_code}).\n{detail}",
            )
        return "status", f"Startup status: error (launch failed with exit code {result.return_code})."

    tmux_path = shutil.which("tmux")
    if result.tmux_session and tmux_path:
        tmux_output = _capture_tmux_output(
            tmux_path,
            result.tmux_session,
            tail_lines,
            preserve_ansi=preserve_ansi,
        )
        if tmux_output is not None:
            return "tmux", tmux_output

    if result.log_path is not None and result.log_path.exists():
        return "file", _tail_text_file(result.log_path, tail_lines)

    docker_logs = _read_container_logs(result, tail_lines)
    if docker_logs is not None:
        return "docker", docker_logs

    return "none", "No logs are available for this docker yet."


def monitor_tmux_sessions(
    results: list[DockerLaunchResult],
    *,
    poll_interval_s: float = DEFAULT_MONITOR_POLL_INTERVAL_S,
    cleanup_on_exit: bool = True,
    interactive: bool = True,
) -> None:
    tmux_results = [result for result in results if result.tmux_session]
    if not tmux_results:
        return

    tmux_path = _require_command("tmux")
    last_signature: tuple | None = None

    try:
        while True:
            statuses = _collect_runtime_statuses(tmux_results, tmux_path)
            signature = _status_signature(statuses)
            if signature != last_signature:
                _render_status_dashboard(statuses)
                last_signature = signature

            if not any(status.overall_status == "running" for status in statuses):
                print_warning("No monitored dockers are still running.")
                break

            if not interactive or not sys.stdin.isatty():
                time.sleep(max(poll_interval_s, 0.0))
                continue

            timeout = max(poll_interval_s, 0.0)
            ready, _, _ = select.select([sys.stdin], [], [], timeout)
            if not ready:
                continue

            command = sys.stdin.readline()
            if command == "":
                break

            action = _handle_monitor_command(command.strip(), statuses, tmux_path)
            if action == "quit":
                break
            last_signature = None
    except KeyboardInterrupt:
        print_warning("Ctrl+C received. Cleaning up launched dockers...")
    finally:
        if cleanup_on_exit:
            cleanup_launched_dockers(results)


def cleanup_launched_dockers(results: list[DockerLaunchResult]) -> None:
    remote_results = [result for result in results if result.match.target.is_remote]
    if remote_results:
        remote_hosts = sorted({_remote_target_label(result.match.target) for result in remote_results})
        print_warning(
            "Skipping cleanup for remote targets managed over SSH: "
            + ", ".join(remote_hosts)
        )

    local_results = [result for result in results if not result.match.target.is_remote]
    tmux_path = shutil.which("tmux")
    docker_path = shutil.which("docker")

    print_status(
        "CLEANUP",
        "Stopping tmux sessions and removing containers started by this launcher.",
        color="yellow",
    )

    seen_sessions: set[str] = set()
    for result in local_results:
        session_name = result.tmux_session
        if not session_name or result.reused_existing or session_name in seen_sessions:
            continue
        seen_sessions.add(session_name)
        if not tmux_path:
            continue
        has_session = subprocess.run(
            [tmux_path, "has-session", "-t", session_name],
            check=False,
            capture_output=True,
            text=True,
        )
        if has_session.returncode != 0:
            continue
        killed = subprocess.run(
            [tmux_path, "kill-session", "-t", session_name],
            check=False,
            capture_output=True,
            text=True,
        )
        if killed.returncode == 0:
            print_status("STOP", f"Killed tmux session '{session_name}'.", color="yellow")
        else:
            print_warning(
                f"Failed to kill tmux session '{session_name}': "
                f"{killed.stderr.strip() or killed.stdout.strip()}"
            )

    seen_compose_dirs: set[Path] = set()
    for result in local_results:
        if result.reused_existing:
            continue
        compose_dir = _find_compose_dir(result.match.target.folder_path)
        if compose_dir is None or compose_dir in seen_compose_dirs or not docker_path:
            continue
        seen_compose_dirs.add(compose_dir)
        down = subprocess.run(
            [docker_path, "compose", "down", "--remove-orphans"],
            cwd=str(compose_dir),
            check=False,
            capture_output=True,
            text=True,
        )
        if down.returncode == 0:
            print_status("DOWN", f"docker compose down in {compose_dir}", color="yellow")
        else:
            print_warning(
                f"docker compose down failed in {compose_dir}: "
                f"{down.stderr.strip() or down.stdout.strip()}"
            )

    tracked_ids = sorted(
        {
            container_id
            for result in local_results
            if not result.reused_existing
            for container_id in result.container_ids
        }
    )
    if docker_path and tracked_ids:
        existing_ids = set(_list_docker_containers().keys())
        removable_ids = [container_id for container_id in tracked_ids if container_id in existing_ids]
        if removable_ids:
            removed = subprocess.run(
                [docker_path, "rm", "-f", *removable_ids],
                check=False,
                capture_output=True,
                text=True,
            )
            if removed.returncode == 0:
                print_status("RM", f"Removed containers: {', '.join(removable_ids)}", color="yellow")
            else:
                print_warning(
                    f"Failed to remove some containers: "
                    f"{removed.stderr.strip() or removed.stdout.strip()}"
                )


def describe_targets(
    root: str | Path,
    *,
    remote_host: str | None = None,
    remote_user: str | None = None,
    remote_ssh_port: int = 22,
    remote_password: str | None = None,
) -> list[str]:
    targets = discover_docker_targets(
        root,
        remote_host=remote_host,
        remote_user=remote_user,
        remote_ssh_port=remote_ssh_port,
        remote_password=remote_password,
    )
    return [target.relative_folder for target in targets]


def normalize_docker_name(value: str) -> str:
    return _normalize_name(value)


def _find_best_match(requested_name: str, targets: list[DockerRunTarget]) -> DockerMatch:
    ranked: list[DockerMatch] = []
    for target in targets:
        strategy, score = _score_match(requested_name, target)
        if score <= 0:
            continue
        ranked.append(
            DockerMatch(
                requested_name=requested_name,
                target=target,
                strategy=strategy,
                score=score,
            )
        )

    if not ranked:
        raise FileNotFoundError(f"Cannot find a docker folder matching '{requested_name}'.")

    ranked.sort(key=lambda item: item.score, reverse=True)
    best = ranked[0]
    ambiguous = [item for item in ranked[1:] if abs(item.score - best.score) < 1e-9]
    if ambiguous and best.score >= 0.85:
        candidates = ", ".join(
            sorted({best.target.relative_folder, *[item.target.relative_folder for item in ambiguous]})
        )
        raise ValueError(
            f"Ambiguous docker name '{requested_name}', multiple folders match: {candidates}"
        )
    return best


def _score_match(requested_name: str, target: DockerRunTarget) -> tuple[str, float]:
    requested = _normalize_name(requested_name)
    aliases = sorted(_aliases_for_target(target))
    if not requested or not aliases:
        return "none", 0.0

    if requested in aliases:
        return "exact", 1.0

    if any(alias.startswith(requested) or requested.startswith(alias) for alias in aliases):
        return "prefix", 0.93

    if any(requested in alias or alias in requested for alias in aliases):
        return "contains", 0.87

    ratio = max(SequenceMatcher(None, requested, alias).ratio() for alias in aliases)
    if ratio >= 0.62:
        return "fuzzy", ratio

    return "none", 0.0


def _aliases_for_target(target: DockerRunTarget) -> set[str]:
    aliases = {
        _normalize_name(target.folder_name),
        _normalize_name(target.relative_folder),
    }

    folder_token = _normalize_name(target.folder_name)
    for suffix in ("_docker", "docker", "_model", "model"):
        if folder_token.endswith(suffix):
            aliases.add(folder_token[: -len(suffix)].strip("_"))

    return {alias for alias in aliases if alias}


def _normalize_name(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.strip().lower()).strip("_")


def _session_name_for_target(target: DockerRunTarget) -> str:
    session_name = re.sub(r"[^A-Za-z0-9_.-]+", "_", target.folder_name).strip("_.-")
    return session_name or "docker_session"


def _launch_once(
    match: DockerMatch,
    *,
    detached: bool,
    use_tmux: bool,
    replace_session: bool,
    log_dir: Path | None,
) -> DockerLaunchResult:
    if use_tmux:
        return _launch_tmux(match, replace_session=replace_session)
    if detached:
        if log_dir is None:
            raise ValueError("log_dir is required for detached launch mode.")
        return _launch_detached(match, log_dir)
    return _launch_foreground(match)


def _launch_remote_foreground(match: DockerMatch) -> DockerLaunchResult:
    target = match.target
    if not target.is_remote:
        raise ValueError("Remote launch requires target.remote_host to be set.")

    remote_folder = _remote_path_text(target.folder_path)
    remote_script = _remote_path_text(target.run_script_path)
    remote_command = f"cd {shlex.quote(remote_folder)} && bash {shlex.quote(remote_script)}"
    ssh_command = _build_ssh_exec_command(target, remote_command=remote_command)

    process = subprocess.Popen(
        ssh_command,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    output_lines: list[str] = []
    log_prefix = f"{target.folder_name}@{target.remote_host}"
    if process.stdout is not None:
        for raw_line in process.stdout:
            output_lines.append(raw_line)
            line = raw_line.rstrip()
            if line:
                print_status(log_prefix, line, color="blue")

    return DockerLaunchResult(
        match=match,
        return_code=process.wait(),
        detached=False,
        pid=process.pid,
        startup_output="".join(output_lines).strip() or None,
    )


def _launch_remote_background(match: DockerMatch) -> DockerLaunchResult:
    target = match.target
    if not target.is_remote:
        raise ValueError("Remote launch requires target.remote_host to be set.")

    remote_folder = _remote_path_text(target.folder_path)
    remote_script = _remote_path_text(target.run_script_path)
    remote_log = f"{remote_folder}/.fusion_remote_launcher.log"
    remote_command = (
        f"cd {shlex.quote(remote_folder)} && "
        f"nohup bash {shlex.quote(remote_script)} > {shlex.quote(remote_log)} 2>&1 < /dev/null & "
        "echo $!"
    )
    ssh_command = _build_ssh_exec_command(target, remote_command=remote_command)
    launched = subprocess.run(
        ssh_command,
        check=False,
        capture_output=True,
        text=True,
    )

    output = (launched.stdout or "").strip()
    error = (launched.stderr or "").strip()
    if launched.returncode != 0:
        return DockerLaunchResult(
            match=match,
            return_code=launched.returncode,
            detached=True,
            startup_output=(error or output or "remote launch command failed"),
        )

    remote_pid: int | None = None
    if output:
        first_line = output.splitlines()[0].strip()
        if first_line.isdigit():
            remote_pid = int(first_line)
    startup_detail = (
        f"remote_pid={remote_pid}, remote_log={remote_log}"
        if remote_pid is not None
        else f"remote launch command accepted, remote_log={remote_log}"
    )
    return DockerLaunchResult(
        match=match,
        return_code=0,
        detached=True,
        pid=remote_pid,
        startup_output=startup_detail,
    )


def _launch_remote_tmux(
    match: DockerMatch,
    *,
    replace_session: bool,
) -> DockerLaunchResult:
    target = match.target
    if not target.is_remote:
        raise ValueError("Remote launch requires target.remote_host to be set.")

    remote_folder = _remote_path_text(target.folder_path)
    remote_script = _remote_path_text(target.run_script_path)
    session_name = _session_name_for_target(target)
    # Keep shell single-quoted for tmux, and escape any embedded single quote safely.
    run_command = (
        f"cd {shlex.quote(remote_folder)} && bash {shlex.quote(remote_script)}"
    ).replace("'", "'\"'\"'")

    if replace_session:
        remote_command = (
            f"tmux kill-session -t {shlex.quote(session_name)} >/dev/null 2>&1 || true; "
            f"tmux new-session -d -s {shlex.quote(session_name)} '{run_command}'; "
            "echo __FUSION_REMOTE_TMUX_STARTED__"
        )
        reused_existing = False
    else:
        remote_command = (
            f"if tmux has-session -t {shlex.quote(session_name)} 2>/dev/null; then "
            "echo __FUSION_REMOTE_TMUX_REUSED__; "
            "else "
            f"tmux new-session -d -s {shlex.quote(session_name)} '{run_command}'; "
            "echo __FUSION_REMOTE_TMUX_STARTED__; "
            "fi"
        )
        reused_existing = False

    ssh_command = _build_ssh_exec_command(target, remote_command=remote_command)
    launched = subprocess.run(
        ssh_command,
        check=False,
        capture_output=True,
        text=True,
    )

    output = (launched.stdout or "").strip()
    error = (launched.stderr or "").strip()
    if launched.returncode != 0:
        return DockerLaunchResult(
            match=match,
            return_code=launched.returncode,
            detached=True,
            startup_output=(
                error
                or output
                or "remote tmux launch failed (ensure remote host has tmux installed)"
            ),
        )

    if "__FUSION_REMOTE_TMUX_REUSED__" in output:
        reused_existing = True
    startup_detail = (
        f"remote_tmux_session={session_name} "
        f"(host={_remote_target_label(target)}, reused={str(reused_existing).lower()})"
    )
    return DockerLaunchResult(
        match=match,
        return_code=0,
        detached=True,
        reused_existing=reused_existing,
        startup_output=startup_detail,
    )


def _attempt_auto_build(
    match: DockerMatch,
    *,
    reason: str,
) -> tuple[bool, str]:
    build_script = _find_build_script(match.target.folder_path)
    if build_script is None:
        return False, f"No build.sh found under {match.target.folder_path}."

    print_status(
        "BUILD",
        (
            f"Auto build '{match.target.folder_name}' because {reason}. "
            f"Using script: {build_script}"
        ),
        color="magenta",
    )
    return_code, output = _run_build_script(match, build_script)
    if return_code == 0:
        print_success(f"Auto build finished for '{match.target.folder_name}'.")
        return True, "Auto build completed."

    tail = ""
    if output:
        tail_lines = output.splitlines()[-8:]
        tail = " | ".join(line.strip() for line in tail_lines if line.strip())
    message = (
        f"Auto build failed for '{match.target.folder_name}' with exit code {return_code}."
        + (f" Tail: {tail}" if tail else "")
    )
    return False, message


def _find_build_script(folder_path: Path) -> Path | None:
    direct = folder_path / "build.sh"
    if direct.is_file():
        return direct.resolve()

    candidates = sorted(path for path in folder_path.rglob("build.sh") if path.is_file())
    if not candidates:
        return None
    return candidates[0].resolve()


def _run_build_script(match: DockerMatch, build_script: Path) -> tuple[int, str]:
    command = [_require_command("bash"), str(build_script)]
    process = subprocess.Popen(
        command,
        cwd=str(build_script.parent.resolve()),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )

    output_lines: list[str] = []
    if process.stdout is not None:
        for raw_line in process.stdout:
            output_lines.append(raw_line)
            line = raw_line.rstrip()
            if line:
                print_status(
                    "BUILD",
                    f"[{match.target.folder_name}] {line}",
                    color="magenta",
                )

    return process.wait(), "".join(output_lines).strip()


def _looks_like_missing_image_output(output: str | None) -> bool:
    if not output:
        return False
    lowered = output.lower()
    return any(hint in lowered for hint in MISSING_IMAGE_HINTS)


def _detect_missing_images(match: DockerMatch) -> list[str]:
    docker_path = shutil.which("docker")
    if not docker_path:
        return []

    required_images = _extract_docker_run_images(match.target.run_script_path)
    if not required_images:
        return []

    missing_images: list[str] = []
    for image in required_images:
        inspected = subprocess.run(
            [docker_path, "image", "inspect", image],
            check=False,
            capture_output=True,
            text=True,
        )
        if inspected.returncode != 0:
            missing_images.append(image)
    return sorted(set(missing_images))


def _extract_docker_run_images(run_script_path: Path) -> list[str]:
    try:
        script_text = run_script_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []

    images: list[str] = []
    env_vars: dict[str, str] = {}
    for logical_line in _to_logical_shell_lines(script_text):
        stripped = logical_line.strip()
        if not stripped or stripped.startswith("#"):
            continue

        try:
            tokens = shlex.split(logical_line, comments=True, posix=True)
        except ValueError:
            continue
        if not tokens:
            continue

        if tokens[0] == "export":
            for token in tokens[1:]:
                name, sep, value = token.partition("=")
                if sep and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name):
                    env_vars[name] = value
            continue
        if len(tokens) == 1:
            name, sep, value = tokens[0].partition("=")
            if sep and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name):
                env_vars[name] = value
            continue

        for index in range(len(tokens) - 1):
            command_token = tokens[index]
            if command_token != "docker" and not command_token.endswith("/docker"):
                continue
            if tokens[index + 1] != "run":
                continue

            image = _extract_image_token_from_docker_run(tokens[index + 2 :], env_vars)
            if image:
                images.append(image)

    return sorted(set(images))


def _to_logical_shell_lines(script_text: str) -> list[str]:
    lines: list[str] = []
    pending = ""
    for raw_line in script_text.splitlines():
        line = raw_line.rstrip()
        if pending:
            pending = pending + line.lstrip()
        else:
            pending = line

        if pending.endswith("\\"):
            pending = pending[:-1] + " "
            continue
        lines.append(pending)
        pending = ""

    if pending:
        lines.append(pending)
    return lines


def _extract_image_token_from_docker_run(
    tokens: list[str],
    env_vars: dict[str, str],
) -> str | None:
    index = 0
    while index < len(tokens):
        token = tokens[index]
        if token == "--":
            index += 1
            break
        if token.startswith("--"):
            if "=" in token:
                index += 1
                continue
            if token in DOCKER_RUN_OPTION_WITH_VALUE:
                index += 2
            else:
                index += 1
            continue
        if token.startswith("-"):
            option_prefix = token[:2]
            if option_prefix in {"-a", "-c", "-e", "-h", "-l", "-m", "-p", "-u", "-v", "-w"}:
                if len(token) > 2:
                    index += 1
                else:
                    index += 2
            elif token in DOCKER_RUN_OPTION_WITH_VALUE:
                index += 2
            else:
                index += 1
            continue
        break

    if index >= len(tokens):
        return None

    raw_token = tokens[index].strip()
    resolved = _resolve_shell_token(raw_token, env_vars)
    if resolved is None:
        return None
    image = resolved.strip()
    if not image:
        return None
    if any(char in image for char in ("$", "`")):
        return None
    if "${" in image or "$(" in image:
        return None
    return image


def _resolve_shell_token(token: str, env_vars: dict[str, str]) -> str | None:
    if token.startswith("${") and token.endswith("}"):
        var_name = token[2:-1]
        if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", var_name):
            return env_vars.get(var_name)
        return None
    if token.startswith("$"):
        var_name = token[1:]
        if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", var_name):
            return env_vars.get(var_name)
        return None
    return token


def _launch_foreground(match: DockerMatch) -> DockerLaunchResult:
    command = _build_run_command(match)
    process = subprocess.Popen(
        command,
        cwd=str(match.target.folder_path.resolve()),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )

    output_lines: list[str] = []
    if process.stdout is not None:
        for raw_line in process.stdout:
            output_lines.append(raw_line)
            line = raw_line.rstrip()
            if line:
                print_status(match.target.folder_name, line, color="blue")

    return DockerLaunchResult(
        match=match,
        return_code=process.wait(),
        detached=False,
        pid=process.pid,
        startup_output="".join(output_lines).strip() or None,
    )


def _launch_detached(match: DockerMatch, log_dir: Path) -> DockerLaunchResult:
    command = _build_run_command(match)
    log_path = log_dir / f"{_normalize_name(match.target.folder_name)}.log"
    with log_path.open("a", encoding="utf-8") as log_file:
        log_file.write(
            f"\n=== Launching {match.target.folder_name} from {match.target.run_script_path} ===\n"
        )
        log_file.flush()

        process = subprocess.Popen(
            command,
            cwd=str(match.target.folder_path.resolve()),
            stdout=log_file,
            stderr=subprocess.STDOUT,
            text=True,
            start_new_session=True,
        )

    time.sleep(0.8)
    return_code = process.poll()
    if return_code is None:
        return DockerLaunchResult(
            match=match,
            return_code=0,
            log_path=log_path,
            pid=process.pid,
            detached=True,
        )

    startup_output: str | None = None
    try:
        startup_output = _tail_text_file(log_path, 120)
    except OSError:
        startup_output = None

    return DockerLaunchResult(
        match=match,
        return_code=return_code,
        log_path=log_path,
        pid=process.pid,
        detached=True,
        startup_output=startup_output,
    )


def _launch_tmux(match: DockerMatch, *, replace_session: bool) -> DockerLaunchResult:
    tmux_path = _require_command("tmux")
    command = _build_run_command(match)
    session_name = _session_name_for_target(match.target)
    folder_path = match.target.folder_path.resolve()

    has_session = subprocess.run(
        [tmux_path, "has-session", "-t", session_name],
        check=False,
        capture_output=True,
        text=True,
    )
    if has_session.returncode == 0:
        if not replace_session:
            return DockerLaunchResult(
                match=match,
                return_code=0,
                tmux_session=session_name,
                reused_existing=True,
            )

        kill_session = subprocess.run(
            [tmux_path, "kill-session", "-t", session_name],
            check=False,
            capture_output=True,
            text=True,
        )
        if kill_session.returncode != 0:
            raise RuntimeError(
                f"Failed to replace existing tmux session '{session_name}': "
                f"{kill_session.stderr.strip() or kill_session.stdout.strip()}"
            )

    shell_command = " ".join(shlex.quote(part) for part in command)
    new_session = subprocess.run(
        [
            tmux_path,
            "new-session",
            "-d",
            "-s",
            session_name,
            "-c",
            str(folder_path),
            shell_command,
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    if new_session.returncode != 0:
        raise RuntimeError(
            f"Failed to create tmux session '{session_name}': "
            f"{new_session.stderr.strip() or new_session.stdout.strip()}"
        )

    return DockerLaunchResult(
        match=match,
        return_code=0,
        tmux_session=session_name,
    )


def _build_run_command(match: DockerMatch) -> list[str]:
    if match.target.is_remote:
        raise ValueError("Use _launch_remote_foreground for remote docker targets.")

    folder_path = match.target.folder_path.resolve()
    run_script_path = match.target.run_script_path.resolve()

    if not folder_path.exists():
        raise FileNotFoundError(f"Docker folder does not exist: {folder_path}")
    if not folder_path.is_dir():
        raise NotADirectoryError(f"Docker folder is not a directory: {folder_path}")
    if not run_script_path.exists():
        raise FileNotFoundError(f"run.sh does not exist: {run_script_path}")
    if not run_script_path.is_file():
        raise FileNotFoundError(f"run.sh is not a regular file: {run_script_path}")

    return [_require_command("bash"), str(run_script_path)]


def _resolve_log_dir(log_dir: str | Path | None) -> Path:
    if log_dir is None:
        resolved = (Path.cwd() / "logs" / "docker-launches").resolve()
    else:
        resolved = Path(log_dir).expanduser().resolve()
    resolved.mkdir(parents=True, exist_ok=True)
    return resolved


def _require_command(name: str) -> str:
    command_path = shutil.which(name)
    if not command_path:
        raise FileNotFoundError(f"{name} is not installed or not available in PATH.")
    return command_path


def _list_docker_containers() -> dict[str, DockerContainerInfo]:
    docker_path = shutil.which("docker")
    if not docker_path:
        return {}

    try:
        listed = subprocess.run(
            [
                docker_path,
                "ps",
                "-a",
                "--no-trunc",
                "--format",
                "{{.ID}}\t{{.Names}}\t{{.Status}}\t{{.Image}}\t{{.Ports}}",
            ],
            check=False,
            capture_output=True,
            text=True,
            timeout=RUNTIME_STATUS_PROBE_TIMEOUT_S,
        )
    except subprocess.TimeoutExpired:
        return {}
    if listed.returncode != 0:
        return {}

    containers: dict[str, DockerContainerInfo] = {}
    for raw_line in listed.stdout.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        parts = line.split("\t")
        if len(parts) < 3:
            continue
        container_id, name, status = parts[0], parts[1], parts[2]
        image = parts[3] if len(parts) >= 4 else ""
        ports = parts[4] if len(parts) >= 5 else ""
        containers[container_id] = DockerContainerInfo(
            container_id=container_id,
            name=name,
            status=status,
            image=image,
            ports=ports,
        )
    return containers


def _collect_new_container_ids(
    before_container_ids: set[str],
    *,
    timeout_s: float = NEW_CONTAINER_DISCOVERY_TIMEOUT_S,
    poll_interval_s: float = NEW_CONTAINER_DISCOVERY_POLL_S,
) -> list[str]:
    if not shutil.which("docker"):
        return []

    discovered_ids: set[str] = set()
    deadline = time.monotonic() + timeout_s
    while True:
        current_ids = set(_list_docker_containers().keys())
        discovered_ids.update(current_ids - before_container_ids)
        if time.monotonic() >= deadline:
            break
        time.sleep(poll_interval_s)
    return sorted(discovered_ids)


def _collect_runtime_statuses(
    results: list[DockerLaunchResult],
    tmux_path: str | None,
) -> list[DockerRuntimeStatus]:
    containers_by_id = _list_docker_containers()
    statuses: list[DockerRuntimeStatus] = []
    for result in results:
        session_state, session_exit_status = _get_tmux_session_state(tmux_path, result.tmux_session)
        container_infos = [
            containers_by_id[container_id]
            for container_id in result.container_ids
            if container_id in containers_by_id
        ]
        overall_status = _summarize_status(
            result,
            session_state,
            session_exit_status,
            container_infos,
        )
        statuses.append(
            DockerRuntimeStatus(
                result=result,
                session_state=session_state,
                session_exit_status=session_exit_status,
                container_infos=container_infos,
                overall_status=overall_status,
                container_summary=_summarize_containers(
                    result,
                    container_infos,
                    overall_status=overall_status,
                    session_exit_status=session_exit_status,
                ),
                image_summary=_summarize_images(
                    result,
                    container_infos,
                ),
                ports_summary=_summarize_ports(
                    result,
                    container_infos,
                ),
            )
        )
    return statuses


def _get_tmux_session_state(
    tmux_path: str | None,
    session_name: str | None,
) -> tuple[str, int | None]:
    if not tmux_path:
        return "missing", None
    if not session_name:
        return "missing", None

    try:
        listed = subprocess.run(
            [
                tmux_path,
                "list-panes",
                "-t",
                session_name,
                "-F",
                "#{pane_dead}\t#{pane_dead_status}",
            ],
            check=False,
            capture_output=True,
            text=True,
            timeout=RUNTIME_STATUS_PROBE_TIMEOUT_S,
        )
    except subprocess.TimeoutExpired:
        return "missing", None
    if listed.returncode != 0:
        message = (listed.stderr.strip() or listed.stdout.strip()).lower()
        if (
            "can't find session" in message
            or "can't find window" in message
            or "can't find pane" in message
            or "no server running" in message
        ):
            return "missing", None
        raise RuntimeError(
            f"Failed to inspect tmux session '{session_name}': "
            f"{listed.stderr.strip() or listed.stdout.strip()}"
        )

    pane_states = [line.strip() for line in listed.stdout.splitlines() if line.strip()]
    if not pane_states:
        return "missing", None

    dead_markers: list[str] = []
    exit_codes: list[int] = []
    for line in pane_states:
        dead_marker, _, raw_exit_status = line.partition("\t")
        dead_markers.append(dead_marker.strip())
        raw_exit_status = raw_exit_status.strip()
        if raw_exit_status:
            try:
                exit_codes.append(int(raw_exit_status))
            except ValueError:
                pass

    if all(marker == "1" for marker in dead_markers):
        exit_status = max(exit_codes) if exit_codes else None
        return "ended", exit_status
    return "running", None


def _summarize_status(
    result: DockerLaunchResult,
    session_state: str,
    session_exit_status: int | None,
    container_infos: list[DockerContainerInfo],
) -> str:
    if not result.succeeded:
        return "error"
    if result.match.target.is_remote:
        return "ended" if result.reused_existing else "running"
    if session_exit_status not in {None, 0}:
        return "error"
    if any(info.status.lower().startswith("up") for info in container_infos):
        return "running"
    if session_state == "running":
        return "running"
    if session_state in {"ended", "missing"}:
        return "ended"
    if container_infos:
        return "ended"
    return "unknown"


def _summarize_containers(
    result: DockerLaunchResult,
    container_infos: list[DockerContainerInfo],
    *,
    overall_status: str,
    session_exit_status: int | None,
) -> str:
    if overall_status == "error":
        if not result.succeeded:
            return f"launch failed (exit code {result.return_code})"
        if session_exit_status not in {None, 0}:
            return f"startup error (exit code {session_exit_status})"
        return "startup error"
    if result.match.target.is_remote:
        target = result.match.target
        endpoint = _remote_target_label(target)
        if overall_status == "running":
            return f"remote target active on {endpoint}"
        return f"remote target on {endpoint}"
    if not container_infos:
        return "untracked"
    if len(container_infos) == 1:
        info = container_infos[0]
        return f"{info.name} [{_normalize_container_status(info.status)}]"

    running_count = sum(1 for info in container_infos if info.status.lower().startswith("up"))
    return f"{len(container_infos)} containers, {running_count} running"


def _summarize_ports(
    result: DockerLaunchResult,
    container_infos: list[DockerContainerInfo],
) -> str:
    if result.match.target.is_remote:
        return "remote-managed"
    if not container_infos:
        return "untracked"

    unique_ports: list[str] = []
    seen: set[str] = set()
    for info in container_infos:
        raw_ports = (info.ports or "").strip()
        if not raw_ports:
            continue
        for token in raw_ports.split(","):
            normalized = token.strip()
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            unique_ports.append(normalized)

    if unique_ports:
        return ", ".join(unique_ports)
    return "not published"


def _summarize_images(
    result: DockerLaunchResult,
    container_infos: list[DockerContainerInfo],
) -> str:
    if result.match.target.is_remote:
        return "remote-managed"
    if not container_infos:
        return "untracked"

    unique_images: list[str] = []
    seen: set[str] = set()
    for info in container_infos:
        image_name = (info.image or "").strip()
        if not image_name or image_name in seen:
            continue
        seen.add(image_name)
        unique_images.append(image_name)

    if not unique_images:
        return "untracked"
    if len(unique_images) == 1:
        return unique_images[0]
    return f"{len(unique_images)} images"


def _normalize_container_status(status: str) -> str:
    lowered = status.lower()
    if lowered.startswith("up"):
        return "running"
    if lowered.startswith("exited") or lowered.startswith("dead"):
        return "ended"
    return status


def _status_signature(statuses: list[DockerRuntimeStatus]) -> tuple:
    return tuple(
        (
            status.result.match.target.folder_name,
            status.overall_status,
            status.session_state,
            status.container_summary,
            status.ports_summary,
        )
        for status in statuses
    )


def _render_status_dashboard(statuses: list[DockerRuntimeStatus]) -> None:
    if sys.stdout.isatty():
        print("\033[2J\033[H", end="")

    print_banner()
    print_status("PANEL", "Marvin Robot System docker status", color="cyan")
    for index, status in enumerate(statuses, start=1):
        folder_name = status.result.match.target.folder_name
        group_name = status.result.match.group_name or "ungrouped"
        message = (
            f"{index}. [{group_name:<9}] {folder_name:<28} "
            f"status={status.overall_status:<7} "
            f"session={status.session_state:<7} "
            f"container={status.container_summary}"
        )
        print_status(str(index), message, color=STATUS_COLOR.get(status.overall_status, "cyan"))

    print_status(
        "CMD",
        "Input <number|name> to enter docker shell, 'attach <name>' for tmux, "
        "'status' to refresh, 'quit' to cleanup and exit.",
        color="yellow",
    )


def _handle_monitor_command(
    command: str,
    statuses: list[DockerRuntimeStatus],
    tmux_path: str,
) -> str:
    normalized = command.strip()
    if not normalized or normalized.lower() in {"status", "s", "refresh"}:
        return "refresh"
    if normalized.lower() in {"quit", "q", "exit"}:
        return "quit"
    if normalized.lower() in {"help", "h", "?"}:
        print_status(
            "HELP",
            "Use docker name or index to enter shell, 'attach <name>' to open tmux, 'quit' to exit.",
            color="yellow",
        )
        return "refresh"

    command_name, _, argument = normalized.partition(" ")
    if command_name.lower() in {"attach", "tmux"}:
        status = _resolve_runtime_status(argument.strip(), statuses)
        if status is None:
            print_warning(f"Cannot find docker '{argument.strip()}'.")
            return "refresh"
        _attach_tmux_session(tmux_path, status)
        return "refresh"

    target = _resolve_runtime_status(normalized, statuses)
    if target is None:
        print_warning(f"Cannot find docker '{normalized}'.")
        return "refresh"
    _enter_container_shell(target)
    return "refresh"


def _resolve_runtime_status(
    token: str,
    statuses: list[DockerRuntimeStatus],
) -> DockerRuntimeStatus | None:
    if not token:
        return None
    stripped = token.strip()
    if stripped.isdigit():
        index = int(stripped) - 1
        if 0 <= index < len(statuses):
            return statuses[index]
        return None

    normalized = _normalize_name(stripped)
    for status in statuses:
        folder_name = status.result.match.target.folder_name
        session_name = status.result.tmux_session or ""
        if normalized in {
            _normalize_name(folder_name),
            _normalize_name(session_name),
        }:
            return status
    return None


def _enter_container_shell(status: DockerRuntimeStatus) -> None:
    running_containers = [
        info for info in status.container_infos if info.status.lower().startswith("up")
    ]
    target_container = running_containers[0] if running_containers else (
        status.container_infos[0] if status.container_infos else None
    )
    if target_container is None:
        print_warning(
            f"No tracked running container is available for '{status.result.match.target.folder_name}'."
        )
        return

    docker_path = _require_command("docker")
    print_status(
        "ENTER",
        (
            f"Entering container '{target_container.name}'. "
            "Type 'exit' to return to Marvin Robot System."
        ),
        color="cyan",
    )
    subprocess.run(
        [
            docker_path,
            "exec",
            "-it",
            target_container.container_id,
            "sh",
            "-lc",
            "if command -v bash >/dev/null 2>&1; then exec bash; else exec sh; fi",
        ],
        check=False,
    )
    print_status("BACK", f"Returned from container '{target_container.name}'.", color="cyan")


def _attach_tmux_session(tmux_path: str, status: DockerRuntimeStatus) -> None:
    session_name = status.result.tmux_session
    if not session_name:
        print_warning(f"No tmux session is available for '{status.result.match.target.folder_name}'.")
        return
    print_status(
        "ATTACH",
        f"Attached to tmux session '{session_name}'. Detach with Ctrl+B then D.",
        color="cyan",
    )
    subprocess.run([tmux_path, "attach-session", "-t", session_name], check=False)
    print_status("BACK", f"Returned from tmux session '{session_name}'.", color="cyan")


def _find_compose_dir(folder_path: Path) -> Path | None:
    resolved_folder = folder_path.resolve()
    for filename in COMPOSE_FILENAMES:
        if (resolved_folder / filename).exists():
            return resolved_folder
    return None


def _infer_container_ids_for_result(result: DockerLaunchResult) -> list[str]:
    containers_by_id = _list_docker_containers()
    if not containers_by_id:
        return []

    aliases = {
        _normalize_name(result.match.target.folder_name),
        _normalize_name(result.match.target.relative_folder),
        _normalize_name(result.match.requested_name),
        _normalize_name(result.tmux_session or ""),
    }
    aliases = {alias for alias in aliases if alias}
    if not aliases:
        return []

    matched_ids: list[str] = []
    for container_id, info in containers_by_id.items():
        normalized_name = _normalize_name(info.name)
        if any(
            normalized_name == alias
            or normalized_name.startswith(alias)
            or alias.startswith(normalized_name)
            or alias in normalized_name
            for alias in aliases
        ):
            matched_ids.append(container_id)
    return sorted(set(matched_ids))


def _capture_tmux_output(
    tmux_path: str,
    session_name: str,
    tail_lines: int,
    *,
    preserve_ansi: bool = False,
) -> str | None:
    command = [tmux_path, "capture-pane"]
    if preserve_ansi:
        command.append("-e")
    command.extend(
        [
            "-p",
            "-S",
            f"-{tail_lines}",
            "-t",
            session_name,
        ]
    )
    captured = subprocess.run(
        command,
        check=False,
        capture_output=True,
        text=True,
    )
    if captured.returncode != 0:
        message = (captured.stderr.strip() or captured.stdout.strip()).lower()
        if (
            "can't find session" in message
            or "can't find window" in message
            or "can't find pane" in message
            or "no server running" in message
        ):
            return None
        raise RuntimeError(
            f"Failed to capture tmux output for '{session_name}': "
            f"{captured.stderr.strip() or captured.stdout.strip()}"
        )

    output = captured.stdout.rstrip()
    return output or "tmux session is active, but no log output has been captured yet."


def _tail_text_file(log_path: Path, tail_lines: int) -> str:
    with log_path.open("r", encoding="utf-8", errors="replace") as handle:
        lines = deque(handle, maxlen=tail_lines)
    output = "".join(lines).rstrip()
    return output or "The log file exists, but it is currently empty."


def _read_container_logs(
    result: DockerLaunchResult,
    tail_lines: int,
) -> str | None:
    if not result.container_ids:
        return None

    docker_path = shutil.which("docker")
    if not docker_path:
        return None

    containers_by_id = _list_docker_containers()
    container_infos = [
        containers_by_id[container_id]
        for container_id in result.container_ids
        if container_id in containers_by_id
    ]

    chosen_container = next(
        (info for info in container_infos if info.status.lower().startswith("up")),
        None,
    )
    if chosen_container is None:
        if container_infos:
            chosen_container = container_infos[0]
        else:
            chosen_container = DockerContainerInfo(
                container_id=result.container_ids[0],
                name=result.container_ids[0][:12],
                status="unknown",
            )

    logged = subprocess.run(
        [
            docker_path,
            "logs",
            "--tail",
            str(tail_lines),
            chosen_container.container_id,
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    if logged.returncode != 0:
        message = logged.stderr.strip() or logged.stdout.strip()
        return (
            f"Unable to read docker logs for '{chosen_container.name}': {message}"
            if message
            else f"Unable to read docker logs for '{chosen_container.name}'."
        )

    output = (logged.stdout or "").rstrip()
    return output or f"Docker container '{chosen_container.name}' has no log output yet."
