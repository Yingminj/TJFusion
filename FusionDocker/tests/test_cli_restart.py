from __future__ import annotations

import argparse
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from fusion_docker.cli import _build_parser, _handle_restart


class CliRestartTest(unittest.TestCase):
    def test_cli_parser_supports_restart_command(self) -> None:
        parser = _build_parser()
        args = parser.parse_args(
            [
                "restart",
                "sam3",
                "--docker-model-root",
                "/tmp/DockerModel",
                "--no-start",
                "--skip-port-cleanup",
            ]
        )
        self.assertEqual(args.command, "restart")
        self.assertEqual(args.docker_names, ["sam3"])
        self.assertEqual(args.docker_model_root, "/tmp/DockerModel")
        self.assertTrue(args.no_start)
        self.assertTrue(args.skip_port_cleanup)

    def test_handle_restart_no_start_only_runs_cleanup(self) -> None:
        args = argparse.Namespace(
            command="restart",
            docker_names=[],
            launch_config="/tmp/docker_launch.yaml",
            docker_model_root="/tmp/DockerModel",
            tmux=False,
            foreground=False,
            log_dir=None,
            replace_session=False,
            monitor=False,
            poll_interval=None,
            dashboard=None,
            skip_port_cleanup=False,
            no_start=True,
            dry_run=False,
        )
        with (
            mock.patch("fusion_docker.cli._force_stop_all_local_containers") as stop_mock,
            mock.patch("fusion_docker.cli._collect_restart_target_ports", return_value=[5555, 8899]) as ports_mock,
            mock.patch("fusion_docker.cli._release_ports") as release_mock,
            mock.patch("fusion_docker.cli._run_docker_launch_flow") as launch_mock,
        ):
            _handle_restart(args)

        stop_mock.assert_called_once_with()
        ports_mock.assert_called_once_with(args)
        release_mock.assert_called_once_with([5555, 8899])
        launch_mock.assert_not_called()

    def test_handle_restart_relaunches_with_explicit_names(self) -> None:
        args = argparse.Namespace(
            command="restart",
            docker_names=["Sam3Docker"],
            launch_config="/tmp/docker_launch.yaml",
            docker_model_root="/tmp/DockerModel",
            tmux=False,
            foreground=False,
            log_dir=None,
            replace_session=False,
            monitor=False,
            poll_interval=None,
            dashboard=None,
            skip_port_cleanup=False,
            no_start=False,
            dry_run=False,
        )
        with (
            mock.patch("fusion_docker.cli._force_stop_all_local_containers") as stop_mock,
            mock.patch("fusion_docker.cli._collect_restart_target_ports", return_value=[]),
            mock.patch("fusion_docker.cli._release_ports") as release_mock,
            mock.patch("fusion_docker.cli._resolve_start_docker_names") as resolve_start_mock,
            mock.patch("fusion_docker.cli._run_docker_launch_flow") as launch_mock,
        ):
            _handle_restart(args)

        stop_mock.assert_called_once_with()
        release_mock.assert_not_called()
        resolve_start_mock.assert_not_called()
        launch_mock.assert_called_once_with(
            args,
            docker_names_override=["Sam3Docker"],
            list_when_empty=False,
        )

    def test_handle_restart_collect_ports_skips_remote_targets(self) -> None:
        args = argparse.Namespace(
            docker_names=["sam3"],
            launch_config="/tmp/docker_launch.yaml",
            docker_model_root="/tmp/DockerModel",
        )
        launch_config = SimpleNamespace(
            docker_model_root="/tmp/DockerModel",
            docker_targets=[],
            docker_names=["sam3"],
            docker_groups={},
        )
        local_target = SimpleNamespace(is_remote=False, folder_name="Sam3Docker")
        remote_target = SimpleNamespace(is_remote=True, folder_name="RemoteDocker")
        matches = [
            SimpleNamespace(target=local_target),
            SimpleNamespace(target=remote_target),
        ]
        with (
            mock.patch("fusion_docker.cli._load_optional_launch_config", return_value=launch_config),
            mock.patch("fusion_docker.cli._require_docker_model_root", return_value=Path("/tmp/DockerModel")),
            mock.patch("fusion_docker.cli._build_group_lookup", return_value={}),
            mock.patch("fusion_docker.cli._match_dockers_for_runtime", return_value=matches),
            mock.patch(
                "fusion_docker.cli.read_docker_configured_port",
                return_value=SimpleNamespace(port=5555),
            ) as read_mock,
        ):
            from fusion_docker.cli import _collect_restart_target_ports

            ports = _collect_restart_target_ports(args)

        self.assertEqual(ports, [5555])
        read_mock.assert_called_once_with(local_target)


if __name__ == "__main__":
    unittest.main()
