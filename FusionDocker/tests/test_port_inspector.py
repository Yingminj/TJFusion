from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from fusion_docker.port_inspector import (
    _count_tcpdump_packets,
    inspect_port_connections,
    list_listening_ports,
    watch_port_activity,
)


class PortInspectorTest(unittest.TestCase):
    def test_list_listening_ports_parses_ss_output(self) -> None:
        ss_output = "\n".join(
            [
                'tcp LISTEN 0 128 0.0.0.0:22 0.0.0.0:* users:(("sshd",pid=1,fd=3))',
                'udp UNCONN 0 0 127.0.0.1:323 0.0.0.0:* users:(("chronyd",pid=2,fd=5))',
            ]
        )

        with patch("fusion_docker.port_inspector._run_command", return_value=ss_output):
            listeners = list_listening_ports()

        self.assertEqual(len(listeners), 2)
        self.assertEqual(listeners[0].port, 22)
        self.assertEqual(listeners[0].protocol, "tcp")
        self.assertIn("sshd", listeners[0].process)
        self.assertEqual(listeners[1].port, 323)

    def test_inspect_port_connections_filters_target_port(self) -> None:
        ss_output = "\n".join(
            [
                'tcp ESTAB 0 0 127.0.0.1:1883 127.0.0.1:43000 users:(("mosquitto",pid=3,fd=8))',
                'tcp ESTAB 0 0 127.0.0.1:5555 127.0.0.1:43001 users:(("other",pid=4,fd=9))',
            ]
        )

        with patch("fusion_docker.port_inspector._run_command", return_value=ss_output):
            connections = inspect_port_connections(1883)

        self.assertEqual(len(connections), 1)
        self.assertEqual(connections[0].local_address, "127.0.0.1:1883")

    def test_watch_port_activity_reports_permission_issue(self) -> None:
        completed = subprocess.CompletedProcess(
            args=["tcpdump"],
            returncode=1,
            stdout="",
            stderr="tcpdump: eth0: You don't have permission to perform this capture",
        )

        with (
            patch("fusion_docker.port_inspector.shutil.which", return_value="/usr/sbin/tcpdump"),
            patch("fusion_docker.port_inspector.subprocess.run", return_value=completed),
        ):
            result = watch_port_activity(1883, 5)

        self.assertTrue(result.available)
        self.assertTrue(result.requires_root)
        self.assertEqual(result.packet_count, 0)

    def test_watch_port_activity_counts_packets_from_timeout_output(self) -> None:
        exc = subprocess.TimeoutExpired(
            cmd=["tcpdump"],
            timeout=5,
            output="IP 127.0.0.1.43000 > 127.0.0.1.1883: Flags [P.]\n",
            stderr="",
        )

        with (
            patch("fusion_docker.port_inspector.shutil.which", return_value="/usr/sbin/tcpdump"),
            patch("fusion_docker.port_inspector.subprocess.run", side_effect=exc),
        ):
            result = watch_port_activity(1883, 5)

        self.assertFalse(result.requires_root)
        self.assertEqual(result.packet_count, 1)

    def test_count_tcpdump_packets_ignores_blank_lines(self) -> None:
        count = _count_tcpdump_packets("\nIP 1.1.1.1 > 2.2.2.2\n\nARP, Request who-has\n")

        self.assertEqual(count, 2)


if __name__ == "__main__":
    unittest.main()
