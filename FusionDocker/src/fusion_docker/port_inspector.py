from __future__ import annotations

from dataclasses import dataclass
import shutil
import subprocess


@dataclass(slots=True)
class PortListener:
    protocol: str
    state: str
    local_address: str
    peer_address: str
    process: str

    @property
    def port(self) -> int | None:
        return _extract_port(self.local_address)


@dataclass(slots=True)
class PortConnection:
    protocol: str
    state: str
    local_address: str
    peer_address: str
    process: str


@dataclass(slots=True)
class PortWatchResult:
    port: int
    seconds: int
    packet_count: int
    available: bool
    requires_root: bool
    command: list[str]
    output: str
    error: str


def list_listening_ports() -> list[PortListener]:
    output = _run_command(["ss", "-lntupH"])
    listeners: list[PortListener] = []
    for line in output.splitlines():
        entry = _parse_ss_line(line)
        if entry is None:
            continue
        listeners.append(
            PortListener(
                protocol=entry["protocol"],
                state=entry["state"],
                local_address=entry["local_address"],
                peer_address=entry["peer_address"],
                process=entry["process"],
            )
        )
    listeners.sort(key=lambda item: (item.port is None, item.port or 0, item.protocol, item.local_address))
    return listeners


def inspect_port_connections(port: int) -> list[PortConnection]:
    output = _run_command(["ss", "-ntupH"])
    connections: list[PortConnection] = []
    for line in output.splitlines():
        entry = _parse_ss_line(line)
        if entry is None:
            continue
        if not _line_mentions_port(entry["local_address"], port) and not _line_mentions_port(
            entry["peer_address"], port
        ):
            continue
        connections.append(
            PortConnection(
                protocol=entry["protocol"],
                state=entry["state"],
                local_address=entry["local_address"],
                peer_address=entry["peer_address"],
                process=entry["process"],
            )
        )
    return connections


def watch_port_activity(port: int, seconds: int) -> PortWatchResult:
    tcpdump = shutil.which("tcpdump")
    if tcpdump is None:
        return PortWatchResult(
            port=port,
            seconds=seconds,
            packet_count=0,
            available=False,
            requires_root=False,
            command=[],
            output="",
            error="tcpdump is not installed.",
        )

    command = [tcpdump, "-i", "any", "-nn", "-l", f"port {port}"]
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=seconds,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        stdout_text = exc.stdout or ""
        stderr_text = exc.stderr or ""
        packet_count = _count_tcpdump_packets(stdout_text)
        return PortWatchResult(
            port=port,
            seconds=seconds,
            packet_count=packet_count,
            available=True,
            requires_root=False,
            command=command,
            output=stdout_text.strip(),
            error=stderr_text.strip(),
        )
    except PermissionError:
        return PortWatchResult(
            port=port,
            seconds=seconds,
            packet_count=0,
            available=True,
            requires_root=True,
            command=command,
            output="",
            error="Permission denied while starting tcpdump.",
        )

    stderr_text = completed.stderr.strip()
    lowered_error = stderr_text.lower()
    requires_root = completed.returncode != 0 and any(
        token in lowered_error
        for token in (
            "permission denied",
            "operation not permitted",
            "don't have permission",
        )
    )
    return PortWatchResult(
        port=port,
        seconds=seconds,
        packet_count=_count_tcpdump_packets(completed.stdout),
        available=True,
        requires_root=requires_root,
        command=command,
        output=completed.stdout.strip(),
        error=stderr_text,
    )


def _run_command(command: list[str]) -> str:
    completed = subprocess.run(
        command,
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        message = completed.stderr.strip() or f"Command failed: {' '.join(command)}"
        raise RuntimeError(message)
    return completed.stdout


def _parse_ss_line(line: str) -> dict[str, str] | None:
    text = line.strip()
    if not text:
        return None
    parts = text.split(maxsplit=6)
    if len(parts) < 5:
        return None
    process = parts[6] if len(parts) > 6 else ""
    return {
        "protocol": parts[0],
        "state": parts[1],
        "local_address": parts[4],
        "peer_address": parts[5] if len(parts) > 5 else "",
        "process": process,
    }


def _extract_port(address: str) -> int | None:
    if ":" not in address:
        return None
    tail = address.rsplit(":", 1)[-1]
    if tail == "*" or not tail.isdigit():
        return None
    return int(tail)


def _line_mentions_port(address: str, port: int) -> bool:
    parsed = _extract_port(address)
    return parsed == port


def _count_tcpdump_packets(output: str) -> int:
    count = 0
    for line in output.splitlines():
        text = line.strip()
        if not text:
            continue
        if "IP " in text or "IP6 " in text or "ARP," in text:
            count += 1
    return count
