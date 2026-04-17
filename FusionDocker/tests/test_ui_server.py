from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from fusion_docker.docker_launcher import (
    DockerContainerInfo,
    DockerLaunchResult,
    DockerMatch,
    DockerRunTarget,
    match_requested_dockers,
)
from fusion_docker.ui_server import BridgeManager, DashboardController, ansi_to_html


class DashboardControllerTest(unittest.TestCase):
    def _build_controller(
        self,
        *,
        bridge_manager: object | None = None,
        launch_config_path: Path | None = None,
        docker_model_root_hint: Path | None = None,
        extra_docker_names: list[str] | None = None,
    ) -> DashboardController:
        tmp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(tmp_dir.cleanup)

        root = Path(tmp_dir.name)
        docker_dir = root / "Sam3Docker"
        docker_dir.mkdir()
        (docker_dir / "run.sh").write_text("#!/usr/bin/env bash\n", encoding="utf-8")
        for docker_name in extra_docker_names or []:
            extra_dir = root / docker_name
            extra_dir.mkdir()
            (extra_dir / "run.sh").write_text("#!/usr/bin/env bash\n", encoding="utf-8")

        matches = match_requested_dockers(
            root,
            ["Sam3Docker"],
            group_lookup={"Sam3Docker": "vision"},
        )
        return DashboardController(
            matches=matches,
            log_lines=150,
            project_root=root,
            launch_config_path=launch_config_path,
            docker_model_root_hint=docker_model_root_hint or root,
            bridge_manager=bridge_manager,
        )

    @mock.patch("fusion_docker.ui_server.collect_runtime_statuses")
    def test_status_payload_includes_group_and_session_state(
        self,
        collect_statuses_mock: mock.Mock,
    ) -> None:
        bridge_manager = mock.Mock()
        bridge_manager.payload.return_value = {
            "enabled": True,
            "status": "running",
            "message": "Bridge process is running.",
            "config_path": "/tmp/bridge.local.yaml",
            "log_path": "/tmp/bridge.log",
            "endpoint": "tcp://127.0.0.1:5556",
            "managed": True,
            "pid": 4321,
        }
        controller = self._build_controller(bridge_manager=bridge_manager)

        def fake_collect(results):
            return [
                mock.Mock(
                    result=results[0],
                    overall_status="running",
                    session_state="running",
                    container_summary="untracked",
                    ports_summary="127.0.0.1:5555->5555/tcp",
                )
            ]

        collect_statuses_mock.side_effect = fake_collect

        payload = controller.status_payload()

        self.assertEqual(payload["title"], "Marvin Robot System")
        self.assertEqual(len(payload["dockers"]), 1)
        self.assertEqual(payload["summary"]["running"], 1)
        self.assertEqual(payload["dockers"][0]["name"], "Sam3Docker")
        self.assertEqual(payload["dockers"][0]["group"], "vision")
        self.assertEqual(payload["dockers"][0]["status"], "running")
        self.assertEqual(payload["dockers"][0]["ports"], "127.0.0.1:5555->5555/tcp")
        self.assertEqual(payload["dockers"][0]["session_name"], "Sam3Docker")
        self.assertEqual(payload["bridge"]["status"], "running")
        self.assertEqual(payload["bridge"]["pid"], 4321)
        self.assertEqual(payload["bridges"][0]["name"], "Bridge 1")

    @mock.patch("fusion_docker.ui_server.read_result_logs")
    def test_log_payload_reads_selected_docker_logs(
        self,
        read_logs_mock: mock.Mock,
    ) -> None:
        controller = self._build_controller()
        read_logs_mock.return_value = ("tmux", "sam3 log output")

        payload = controller.log_payload("Sam3Docker")

        self.assertEqual(payload["name"], "Sam3Docker")
        self.assertEqual(payload["group"], "vision")
        self.assertEqual(payload["source"], "tmux")
        self.assertEqual(payload["lines"], 150)
        self.assertEqual(payload["content"], "sam3 log output")
        self.assertEqual(payload["html"], "sam3 log output")

    def test_publish_video_stream_exposes_latest_frame_payload(self) -> None:
        controller = self._build_controller()

        response = controller.publish_video_stream(
            title="Siglip Preview",
            frame_base64="YWJj",
            mime_type="image/jpeg",
            source="SiglipDocker",
        )
        payload = controller.video_streams_payload()

        self.assertTrue(response["ok"])
        self.assertEqual(response["title"], "Siglip Preview")
        self.assertEqual(len(payload["streams"]), 1)
        self.assertEqual(payload["streams"][0]["title"], "Siglip Preview")
        self.assertEqual(payload["streams"][0]["frame_base64"], "YWJj")
        self.assertEqual(payload["streams"][0]["mime_type"], "image/jpeg")
        self.assertEqual(payload["streams"][0]["source"], "SiglipDocker")

    def test_publish_video_stream_rejects_missing_title(self) -> None:
        controller = self._build_controller()

        with self.assertRaises(ValueError):
            controller.publish_video_stream(title="", frame_base64="YWJj")

    @mock.patch("fusion_docker.ui_server.read_result_logs")
    def test_log_payload_keeps_startup_error_details_for_error_docker(
        self,
        read_logs_mock: mock.Mock,
    ) -> None:
        controller = self._build_controller()
        read_logs_mock.return_value = (
            "status",
            "Startup status: error (launch failed with exit code 1).\nTraceback...",
        )

        payload = controller.log_payload("Sam3Docker")

        self.assertEqual(payload["source"], "status")
        self.assertTrue(payload["is_error"])
        self.assertIn("Traceback", payload["content"])
        read_logs_mock.assert_called_once()

    def test_log_payload_rejects_unknown_docker_name(self) -> None:
        controller = self._build_controller()

        with self.assertRaises(KeyError):
            controller.log_payload("UnknownDocker")

    def test_docker_service_config_payload_reads_yaml_fields(self) -> None:
        controller = self._build_controller()
        config_path = controller.results[0].match.target.folder_path / "service.yaml"
        config_path.write_text(
            "\n".join(
                [
                    "docker:",
                    "  container_name: sam3_container",
                    "server:",
                    "  host: 0.0.0.0",
                    "  port: 5555",
                ]
            ),
            encoding="utf-8",
        )

        payload = controller.docker_service_config_payload("Sam3Docker")

        self.assertTrue(payload["ok"])
        self.assertEqual(payload["name"], "Sam3Docker")
        self.assertEqual(payload["container_name"], "sam3_container")
        self.assertEqual(payload["host"], "0.0.0.0")
        self.assertEqual(payload["port"], 5555)
        self.assertEqual(Path(payload["config_path"]).resolve(), config_path.resolve())

    @mock.patch("fusion_docker.ui_server.collect_runtime_statuses")
    def test_save_docker_service_config_updates_yaml(
        self,
        collect_statuses_mock: mock.Mock,
    ) -> None:
        controller = self._build_controller()
        config_path = controller.results[0].match.target.folder_path / "service.yaml"
        config_path.write_text(
            "\n".join(
                [
                    "docker:",
                    "  container_name: sam3_container",
                    "server:",
                    "  host: 0.0.0.0",
                    "  port: 5555",
                ]
            ),
            encoding="utf-8",
        )

        def fake_collect(results):
            return [
                mock.Mock(
                    result=results[0],
                    overall_status="ended",
                    session_state="missing",
                    container_summary="untracked",
                    ports_summary="untracked",
                )
            ]

        collect_statuses_mock.side_effect = fake_collect

        payload = controller.save_docker_service_config(
            "Sam3Docker",
            host="127.0.0.1",
            port=5566,
            container_name="sam3_tmp",
            restart=False,
        )

        self.assertTrue(payload["ok"])
        self.assertEqual(payload["config"]["container_name"], "sam3_tmp")
        self.assertEqual(payload["config"]["host"], "127.0.0.1")
        self.assertEqual(payload["config"]["port"], 5566)
        saved_text = config_path.read_text(encoding="utf-8")
        self.assertIn("container_name: sam3_tmp", saved_text)
        self.assertIn("host: 127.0.0.1", saved_text)
        self.assertIn("port: 5566", saved_text)

    @mock.patch("fusion_docker.ui_server.DashboardController._spawn_terminal_process")
    @mock.patch("fusion_docker.ui_server._list_docker_containers")
    def test_open_docker_terminal_prefers_docker_name_from_service_yaml(
        self,
        list_containers_mock: mock.Mock,
        spawn_terminal_mock: mock.Mock,
    ) -> None:
        controller = self._build_controller()
        config_path = controller.results[0].match.target.folder_path / "service.yaml"
        config_path.write_text(
            "\n".join(
                [
                    "docker:",
                    "  name: sam3_container",
                    "server:",
                    "  host: 0.0.0.0",
                    "  port: 5555",
                ]
            ),
            encoding="utf-8",
        )
        list_containers_mock.return_value = {
            "abc123": DockerContainerInfo(
                container_id="abc123",
                name="sam3_container",
                status="Up 1 minute",
                ports="0.0.0.0:5555->5555/tcp",
            )
        }
        spawn_terminal_mock.return_value = "Opened terminal window and attached into docker shell."

        payload = controller.open_docker_terminal("Sam3Docker")

        self.assertTrue(payload["ok"])
        self.assertEqual(payload["container_name"], "sam3_container")
        self.assertIn("docker exec -it abc123", payload["shell_hint"])
        spawn_terminal_mock.assert_called_once()

    @mock.patch("fusion_docker.ui_server.DashboardController._spawn_terminal_process")
    @mock.patch("fusion_docker.ui_server._list_docker_containers")
    def test_open_docker_terminal_resolves_container_name_template_from_yaml(
        self,
        list_containers_mock: mock.Mock,
        spawn_terminal_mock: mock.Mock,
    ) -> None:
        controller = self._build_controller()
        config_path = controller.results[0].match.target.folder_path / "workspace" / "config.yaml"
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(
            "\n".join(
                [
                    "docker:",
                    "  image: sam3",
                    "  container_name: ${image}_tmp",
                    "server:",
                    "  host: 0.0.0.0",
                    "  port: 5561",
                ]
            ),
            encoding="utf-8",
        )
        list_containers_mock.return_value = {
            "abc123": DockerContainerInfo(
                container_id="abc123",
                name="sam3_tmp",
                status="Up 2 minutes",
                ports="0.0.0.0:5561->5561/tcp",
            )
        }
        spawn_terminal_mock.return_value = "Opened terminal window and attached into docker shell."

        payload = controller.open_docker_terminal("Sam3Docker")

        self.assertTrue(payload["ok"])
        self.assertEqual(payload["container_name"], "sam3_tmp")
        self.assertIn("docker exec -it abc123", payload["shell_hint"])

    @mock.patch("fusion_docker.ui_server.subprocess.run")
    @mock.patch("fusion_docker.ui_server.resolve_preferred_container")
    @mock.patch("fusion_docker.ui_server.shutil.which")
    def test_docker_console_exec_runs_local_command(
        self,
        which_mock: mock.Mock,
        resolve_preferred_mock: mock.Mock,
        run_mock: mock.Mock,
    ) -> None:
        controller = self._build_controller()
        which_mock.return_value = "/usr/bin/docker"
        resolve_preferred_mock.return_value = DockerContainerInfo(
            container_id="abc123",
            name="sam3_container",
            status="Up 2 minutes",
            ports="0.0.0.0:5555->5555/tcp",
        )
        run_mock.return_value = subprocess.CompletedProcess(
            ["/usr/bin/docker", "exec"],
            0,
            "/workspace\n",
            "",
        )

        payload = controller.docker_console_exec("Sam3Docker", "pwd", timeout_ms=3000)

        self.assertTrue(payload["ok"])
        self.assertEqual(payload["exit_code"], 0)
        self.assertIn("/workspace", payload["output"])
        command = run_mock.call_args.args[0]
        self.assertEqual(command[:4], ["/usr/bin/docker", "exec", "-i", "abc123"])

    @mock.patch("fusion_docker.ui_server.launch_single_match")
    @mock.patch("fusion_docker.ui_server.collect_runtime_statuses")
    def test_start_docker_launches_selected_match(
        self,
        collect_statuses_mock: mock.Mock,
        launch_single_mock: mock.Mock,
    ) -> None:
        controller = self._build_controller()
        initial_result = controller.results[0]
        launched_result = DockerLaunchResult(
            match=initial_result.match,
            return_code=0,
            tmux_session="Sam3Docker",
        )
        launch_single_mock.return_value = launched_result

        def fake_collect(results):
            current_result = results[0]
            if current_result is launched_result:
                status = "running"
                session = "running"
                summary = "sam3 [running]"
            else:
                status = "ended"
                session = "ended"
                summary = "untracked"
            return [
                mock.Mock(
                    result=current_result,
                    overall_status=status,
                    session_state=session,
                    container_summary=summary,
                    ports_summary="untracked",
                )
            ]

        collect_statuses_mock.side_effect = fake_collect

        payload = controller.start_docker("Sam3Docker")

        self.assertTrue(payload["ok"])
        self.assertIn("Start command sent", payload["message"])
        launch_single_mock.assert_called_once()
        self.assertEqual(payload["status"]["dockers"][0]["status"], "running")

    @mock.patch("fusion_docker.ui_server.stop_launch_result")
    @mock.patch("fusion_docker.ui_server.collect_runtime_statuses")
    def test_stop_docker_stops_selected_result(
        self,
        collect_statuses_mock: mock.Mock,
        stop_launch_mock: mock.Mock,
    ) -> None:
        controller = self._build_controller()
        stop_launch_mock.return_value = (True, "Stopped Sam3Docker.")

        def fake_collect(results):
            return [
                mock.Mock(
                    result=results[0],
                    overall_status="ended",
                    session_state="missing",
                    container_summary="untracked",
                    ports_summary="untracked",
                )
            ]

        collect_statuses_mock.side_effect = fake_collect

        payload = controller.stop_docker("Sam3Docker")

        self.assertTrue(payload["ok"])
        self.assertEqual(payload["message"], "Stopped Sam3Docker.")
        stop_launch_mock.assert_called_once()
        self.assertEqual(payload["status"]["dockers"][0]["status"], "ended")

    @mock.patch("fusion_docker.ui_server.launch_single_match")
    @mock.patch("fusion_docker.ui_server.stop_launch_result")
    @mock.patch("fusion_docker.ui_server.collect_runtime_statuses")
    def test_restart_docker_stops_then_starts_selected_result(
        self,
        collect_statuses_mock: mock.Mock,
        stop_launch_mock: mock.Mock,
        launch_single_mock: mock.Mock,
    ) -> None:
        controller = self._build_controller()
        initial_result = controller.results[0]
        restarted_result = DockerLaunchResult(
            match=initial_result.match,
            return_code=0,
            tmux_session="Sam3Docker",
        )
        stop_launch_mock.return_value = (True, "Stopped Sam3Docker.")
        launch_single_mock.return_value = restarted_result

        def fake_collect(results):
            current_result = results[0]
            if current_result is restarted_result:
                status = "running"
                session = "running"
                summary = "sam3 [running]"
            else:
                status = "ended"
                session = "missing"
                summary = "untracked"
            return [
                mock.Mock(
                    result=current_result,
                    overall_status=status,
                    session_state=session,
                    container_summary=summary,
                    ports_summary="untracked",
                )
            ]

        collect_statuses_mock.side_effect = fake_collect

        payload = controller.restart_docker("Sam3Docker")

        self.assertTrue(payload["ok"])
        self.assertIn("Restarted 'Sam3Docker'.", payload["message"])
        stop_launch_mock.assert_called_once()
        launch_single_mock.assert_called_once()
        self.assertEqual(payload["status"]["dockers"][0]["status"], "running")

    @mock.patch("fusion_docker.ui_server.collect_runtime_statuses")
    def test_start_bridge_returns_updated_status_payload(
        self,
        collect_statuses_mock: mock.Mock,
    ) -> None:
        bridge_manager = mock.Mock()
        bridge_manager.start.return_value = {
            "ok": True,
            "message": "Bridge start command sent (pid=999).",
            "bridge": {
                "enabled": True,
                "status": "running",
                "message": "Bridge start command sent (pid=999).",
                "config_path": "/tmp/bridge.local.yaml",
                "log_path": "/tmp/bridge.log",
                "endpoint": "tcp://127.0.0.1:5556",
                "managed": True,
                "pid": 999,
            },
        }
        bridge_manager.payload.return_value = bridge_manager.start.return_value["bridge"]
        controller = self._build_controller(bridge_manager=bridge_manager)

        def fake_collect(results):
            return [
                mock.Mock(
                    result=results[0],
                    overall_status="ended",
                    session_state="missing",
                    container_summary="untracked",
                    ports_summary="untracked",
                )
            ]

        collect_statuses_mock.side_effect = fake_collect

        payload = controller.start_bridge()

        self.assertTrue(payload["ok"])
        self.assertIn("Bridge start command sent", payload["message"])
        bridge_manager.start.assert_called_once()
        self.assertEqual(payload["status"]["bridge"]["status"], "running")

    def test_shutdown_stops_managed_bridge(self) -> None:
        bridge_manager = mock.Mock()
        controller = self._build_controller(bridge_manager=bridge_manager)

        controller.shutdown()

        bridge_manager.shutdown.assert_called_once()

    def test_bridge_log_payload_reads_bridge_logs(self) -> None:
        bridge_manager = mock.Mock()
        bridge_manager.payload.return_value = {
            "enabled": True,
            "status": "running",
            "message": "Bridge process is running.",
            "config_path": "/tmp/bridge.local.yaml",
            "log_path": "/tmp/bridge.log",
            "endpoint": "tcp://127.0.0.1:5556",
            "managed": True,
            "pid": 9876,
        }
        bridge_manager.read_logs.return_value = "bridge log output"
        controller = self._build_controller(bridge_manager=bridge_manager)

        payload = controller.bridge_log_payload(lines=40)

        self.assertEqual(payload["name"], "Bridge 1")
        self.assertEqual(payload["source"], "file")
        self.assertEqual(payload["lines"], 40)
        self.assertEqual(payload["content"], "bridge log output")
        self.assertEqual(payload["status"], "running")
        self.assertEqual(payload["log_path"], "/tmp/bridge.log")
        bridge_manager.read_logs.assert_called_once_with(40)

    def test_bridge_config_payload_reads_bridge_config(self) -> None:
        bridge_manager = mock.Mock()
        bridge_manager.payload.return_value = {
            "enabled": True,
            "status": "running",
            "message": "Bridge process is running.",
            "config_path": "/tmp/bridge.local.yaml",
            "log_path": "/tmp/bridge.log",
            "endpoint": "tcp://127.0.0.1:5556",
            "managed": True,
            "pid": 9876,
        }
        bridge_manager.read_config_text.return_value = "bridge:\n  listen_port: 5556\n"
        controller = self._build_controller(bridge_manager=bridge_manager)

        payload = controller.bridge_config_payload()

        self.assertEqual(payload["name"], "Bridge 1")
        self.assertEqual(payload["config_path"], "/tmp/bridge.local.yaml")
        self.assertEqual(payload["content"], "bridge:\n  listen_port: 5556\n")
        self.assertEqual(payload["status"], "running")
        self.assertEqual(payload["message"], "Bridge process is running.")
        bridge_manager.read_config_text.assert_called_once_with()

    def test_launcher_config_payload_reads_launcher_yaml(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            configs_dir = root / "configs"
            configs_dir.mkdir()
            config_path = configs_dir / "docker_launch.yaml"
            config_path.write_text(
                "\n".join(
                    [
                        "docker_launcher:",
                        f"  docker_model_root: {root}",
                        "  tmux: true",
                        "  groups:",
                        "    vision:",
                        "      - Sam3Docker",
                    ]
                ),
                encoding="utf-8",
            )
            docker_dir = root / "Sam3Docker"
            docker_dir.mkdir()
            (docker_dir / "run.sh").write_text("#!/usr/bin/env bash\n", encoding="utf-8")
            matches = match_requested_dockers(
                root,
                ["Sam3Docker"],
                group_lookup={"Sam3Docker": "vision"},
            )
            controller = DashboardController(
                matches=matches,
                log_lines=150,
                project_root=root,
                launch_config_path=config_path,
                docker_model_root_hint=root,
            )

            payload = controller.launcher_config_payload()

        self.assertEqual(payload["status"], "ready")
        self.assertEqual(payload["docker_count"], 1)
        self.assertIn("docker_launcher:", payload["content"])
        self.assertEqual(Path(payload["config_path"]).resolve(), config_path.resolve())

    @mock.patch("fusion_docker.ui_server.collect_runtime_statuses")
    def test_save_bridge_config_can_restart_bridge(
        self,
        collect_statuses_mock: mock.Mock,
    ) -> None:
        bridge_manager = mock.Mock()
        bridge_manager.payload.return_value = {
            "enabled": True,
            "status": "running",
            "message": "Bridge process is running.",
            "config_path": "/tmp/bridge.local.yaml",
            "log_path": "/tmp/bridge.log",
            "endpoint": "tcp://127.0.0.1:5556",
            "managed": True,
            "pid": 1111,
        }
        bridge_manager.read_config_text.return_value = "bridge:\n  listen_port: 5557\n"
        bridge_manager.restart.return_value = {
            "ok": True,
            "message": "Bridge stopped (exit code 0). Bridge start command sent (pid=1111).",
            "bridge": bridge_manager.payload.return_value,
        }
        controller = self._build_controller(bridge_manager=bridge_manager)

        def fake_collect(results):
            return [
                mock.Mock(
                    result=results[0],
                    overall_status="ended",
                    session_state="missing",
                    container_summary="untracked",
                    ports_summary="untracked",
                )
            ]

        collect_statuses_mock.side_effect = fake_collect

        payload = controller.save_bridge_config(
            None,
            "bridge:\n  listen_port: 5557\n",
            restart=True,
        )

        bridge_manager.save_config_text.assert_called_once_with("bridge:\n  listen_port: 5557\n")
        bridge_manager.restart.assert_called_once_with()
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["bridge_name"], "Bridge 1")
        self.assertEqual(payload["config"]["content"], "bridge:\n  listen_port: 5557\n")
        self.assertEqual(payload["bridge"]["status"], "running")
        self.assertEqual(payload["status"]["bridge"]["status"], "running")

    @mock.patch("fusion_docker.ui_server.collect_runtime_statuses")
    def test_save_launcher_config_can_reload_dashboard_targets(
        self,
        collect_statuses_mock: mock.Mock,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            configs_dir = root / "configs"
            configs_dir.mkdir()
            config_path = configs_dir / "docker_launch.yaml"
            config_path.write_text(
                "\n".join(
                    [
                        "docker_launcher:",
                        f"  docker_model_root: {root}",
                        "  groups:",
                        "    vision:",
                        "      - Sam3Docker",
                    ]
                ),
                encoding="utf-8",
            )
            for docker_name in ("Sam3Docker", "FlowPoseDocker"):
                docker_dir = root / docker_name
                docker_dir.mkdir()
                (docker_dir / "run.sh").write_text("#!/usr/bin/env bash\n", encoding="utf-8")
            matches = match_requested_dockers(
                root,
                ["Sam3Docker"],
                group_lookup={"Sam3Docker": "vision"},
            )
            controller = DashboardController(
                matches=matches,
                log_lines=150,
                project_root=root,
                launch_config_path=config_path,
                docker_model_root_hint=root,
            )

            def fake_collect(results):
                return [
                    mock.Mock(
                        result=result,
                        overall_status="ended",
                        session_state="missing",
                        container_summary="untracked",
                        ports_summary="untracked",
                    )
                    for result in results
                ]

            collect_statuses_mock.side_effect = fake_collect

            payload = controller.save_launcher_config(
                "\n".join(
                    [
                        "docker_launcher:",
                        f"  docker_model_root: {root}",
                        "  groups:",
                        "    inference:",
                        "      - FlowPoseDocker",
                    ]
                ),
                restart=True,
            )

        self.assertTrue(payload["ok"])
        self.assertIn("Launcher config reloaded", payload["message"])
        self.assertEqual(payload["config"]["docker_count"], 1)
        self.assertEqual(
            [docker["name"] for docker in payload["status"]["dockers"]],
            ["FlowPoseDocker"],
        )
        self.assertEqual(payload["status"]["dockers"][0]["group"], "inference")

    @mock.patch("fusion_docker.ui_server.match_requested_dockers")
    @mock.patch("fusion_docker.ui_server.collect_runtime_statuses")
    def test_update_docker_connection_can_switch_target_to_remote(
        self,
        collect_statuses_mock: mock.Mock,
        match_requested_mock: mock.Mock,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            configs_dir = root / "configs"
            configs_dir.mkdir()
            config_path = configs_dir / "docker_launch.yaml"
            config_path.write_text(
                "\n".join(
                    [
                        "docker_launcher:",
                        f"  docker_model_root: {root}",
                        "  groups:",
                        "    vision:",
                        "      - Sam3Docker",
                    ]
                ),
                encoding="utf-8",
            )
            docker_dir = root / "Sam3Docker"
            docker_dir.mkdir()
            (docker_dir / "run.sh").write_text("#!/usr/bin/env bash\n", encoding="utf-8")

            initial_match = match_requested_dockers(
                root,
                ["Sam3Docker"],
                group_lookup={"Sam3Docker": "vision"},
            )[0]

            remote_match = DockerMatch(
                requested_name="Sam3Docker",
                target=DockerRunTarget(
                    folder_name="Sam3Docker",
                    folder_path=Path("/home/robot/DockerModel/Sam3Docker"),
                    run_script_path=Path("/home/robot/DockerModel/Sam3Docker/run.sh"),
                    relative_folder="Sam3Docker",
                    remote_host="192.168.1.88",
                    remote_user="robot",
                    remote_ssh_port=2222,
                    remote_password="robotpass",
                ),
                strategy="exact",
                score=1.0,
                group_name="vision",
            )
            match_requested_mock.return_value = [remote_match]

            controller = DashboardController(
                matches=[initial_match],
                log_lines=150,
                project_root=root,
                launch_config_path=config_path,
                docker_model_root_hint=root,
            )

            def fake_collect(results):
                return [
                    mock.Mock(
                        result=result,
                        overall_status="ended" if result.reused_existing else "running",
                        session_state="missing",
                        container_summary="untracked",
                        ports_summary="untracked",
                    )
                    for result in results
                ]

            collect_statuses_mock.side_effect = fake_collect

            payload = controller.update_docker_connection(
                name="Sam3Docker",
                location="remote",
                docker_model_root=None,
                remote_host="192.168.1.88",
                remote_user="robot",
                remote_docker_model_root="/home/robot/DockerModel",
                remote_ssh_port=2222,
                remote_password="robotpass",
            )

            saved_text = config_path.read_text(encoding="utf-8")

        self.assertTrue(payload["ok"])
        self.assertIn("Saved connection for 'Sam3Docker'", payload["message"])
        self.assertIn("docker_targets:", saved_text)
        self.assertIn("location: remote", saved_text)
        self.assertIn("host: 192.168.1.88", saved_text)
        self.assertIn("password: robotpass", saved_text)
        self.assertEqual(payload["status"]["dockers"][0]["location"], "remote")
        self.assertEqual(payload["status"]["dockers"][0]["remote_host"], "192.168.1.88")
        self.assertEqual(payload["status"]["dockers"][0]["remote_user"], "robot")
        self.assertEqual(payload["status"]["dockers"][0]["remote_ssh_port"], 2222)
        self.assertTrue(payload["status"]["dockers"][0]["remote_password_set"])

    def test_ansi_to_html_renders_colored_spans(self) -> None:
        rendered = ansi_to_html("prefix \x1b[31mred\x1b[0m suffix")

        self.assertIn("prefix ", rendered)
        self.assertIn("suffix", rendered)
        self.assertIn("<span", rendered)
        self.assertIn("color: #ff6f7d", rendered)
        self.assertIn("red", rendered)

    @mock.patch("fusion_docker.ui_server.collect_runtime_statuses")
    @mock.patch("fusion_docker.ui_server.launch_single_match")
    def test_start_docker_returns_error_when_launch_failed(
        self,
        launch_single_mock: mock.Mock,
        collect_statuses_mock: mock.Mock,
    ) -> None:
        controller = self._build_controller()
        failed_result = DockerLaunchResult(
            match=controller.results[0].match,
            return_code=1,
            detached=True,
            startup_output="permission denied",
        )
        launch_single_mock.return_value = failed_result

        def fake_collect(results):
            return [
                mock.Mock(
                    result=result,
                    overall_status=(
                        "error"
                        if not result.succeeded
                        else ("ended" if result.reused_existing else "running")
                    ),
                    session_state="ended",
                    container_summary="launch failed",
                    ports_summary="untracked",
                )
                for result in results
            ]

        collect_statuses_mock.side_effect = fake_collect

        payload = controller.start_docker("Sam3Docker")

        self.assertFalse(payload["ok"])
        self.assertIn("Failed to start", payload["message"])
        self.assertIn("permission denied", payload["message"])

    @mock.patch("fusion_docker.ui_server._execute_zmq_json_request")
    def test_run_zmq_test_records_request_response_mapping(
        self,
        execute_zmq_mock: mock.Mock,
    ) -> None:
        controller = self._build_controller()
        execute_zmq_mock.return_value = ({"status": "ok", "model": "sam3"}, '{"status":"ok"}', 18.25)

        payload = controller.run_zmq_test(
            name="Sam3Docker",
            endpoint="tcp://127.0.0.1:5555",
            timeout_ms=1200,
            request_payload={"task": "ping"},
        )

        self.assertTrue(payload["ok"])
        self.assertIn("ZMQ test succeeded", payload["message"])
        self.assertTrue(payload["history"])
        record = payload["record"]
        self.assertEqual(record["docker_name"], "Sam3Docker")
        self.assertEqual(record["endpoint"], "tcp://127.0.0.1:5555")
        self.assertEqual(record["status"], "ok")
        self.assertIn("request_id", record["request_json"])
        self.assertEqual(record["response_json"]["status"], "ok")

    @mock.patch("fusion_docker.ui_server._execute_zmq_json_request")
    def test_run_zmq_test_returns_error_record_on_exception(
        self,
        execute_zmq_mock: mock.Mock,
    ) -> None:
        controller = self._build_controller()
        execute_zmq_mock.side_effect = RuntimeError("resource temporarily unavailable")

        payload = controller.run_zmq_test(
            name="Sam3Docker",
            endpoint="tcp://127.0.0.1:5555",
            timeout_ms=1000,
            request_payload={"task": "ping"},
        )

        self.assertFalse(payload["ok"])
        self.assertIn("failed", payload["message"].lower())
        self.assertEqual(payload["record"]["status"], "error")
        self.assertIn("resource temporarily unavailable", payload["record"]["error"])
        self.assertGreaterEqual(len(payload["history"]), 1)

    def test_zmq_test_schema_reads_endpoint_mapping_from_launcher_config(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            configs_dir = root / "configs"
            configs_dir.mkdir()
            config_path = configs_dir / "docker_launch.yaml"
            config_path.write_text(
                "\n".join(
                    [
                        "docker_launcher:",
                        f"  docker_model_root: {root}",
                        "  groups:",
                        "    vision:",
                        "      - Sam3Docker",
                        "  zmq_test:",
                        "    timeout_ms: 2200",
                        "    history_limit: 22",
                        "    endpoints:",
                        "      Sam3Docker: tcp://127.0.0.1:5555",
                    ]
                ),
                encoding="utf-8",
            )
            docker_dir = root / "Sam3Docker"
            docker_dir.mkdir()
            (docker_dir / "run.sh").write_text("#!/usr/bin/env bash\n", encoding="utf-8")
            request_format_dir = docker_dir / "RequestFormat"
            request_format_dir.mkdir()
            (request_format_dir / "input.json").write_text(
                '{"request_id":"rf-001","rgb_image":"<rgb>","depth_image":"<depth>"}',
                encoding="utf-8",
            )
            (request_format_dir / "output.json").write_text(
                '{"status":"ok","objects":[]}',
                encoding="utf-8",
            )

            matches = match_requested_dockers(
                root,
                ["Sam3Docker"],
                group_lookup={"Sam3Docker": "vision"},
            )
            controller = DashboardController(
                matches=matches,
                log_lines=150,
                project_root=root,
                launch_config_path=config_path,
                docker_model_root_hint=root,
            )

            payload = controller.zmq_test_schema_payload()

        self.assertEqual(payload["timeout_ms"], 2200)
        self.assertEqual(payload["history_limit"], 22)
        self.assertEqual(payload["endpoints"]["Sam3Docker"], "tcp://127.0.0.1:5555")
        self.assertEqual(payload["dockers"][0]["endpoint"], "tcp://127.0.0.1:5555")
        self.assertEqual(payload["dockers"][0]["request_template"]["request_id"], "rf-001")
        self.assertEqual(payload["dockers"][0]["expected_output_template"]["status"], "ok")
        self.assertTrue(payload["dockers"][0]["request_input_path"].endswith("RequestFormat/input.json"))
        self.assertTrue(payload["dockers"][0]["request_output_path"].endswith("RequestFormat/output.json"))

    def test_zmq_test_schema_autogenerates_template_when_input_is_json_schema(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            docker_dir = root / "Sam3Docker"
            docker_dir.mkdir()
            (docker_dir / "run.sh").write_text("#!/usr/bin/env bash\n", encoding="utf-8")

            request_format_dir = docker_dir / "RequestFormat"
            request_format_dir.mkdir()
            (request_format_dir / "input.json").write_text(
                json.dumps(
                    {
                        "$schema": "https://json-schema.org/draft/2020-12/schema",
                        "type": "object",
                        "required": ["request_id", "rgb_image", "depth_image"],
                        "properties": {
                            "request_id": {"type": "string", "format": "uuid"},
                            "rgb_image": {"type": "string", "contentEncoding": "base64"},
                            "depth_image": {"type": "string", "contentEncoding": "base64"},
                            "threshold": {"type": "number", "minimum": 0, "maximum": 1},
                        },
                    }
                ),
                encoding="utf-8",
            )
            (request_format_dir / "output.json").write_text(
                '{"type":"object","properties":{"status":{"type":"string"}}}',
                encoding="utf-8",
            )

            matches = match_requested_dockers(
                root,
                ["Sam3Docker"],
                group_lookup={"Sam3Docker": "vision"},
            )
            controller = DashboardController(
                matches=matches,
                log_lines=100,
                project_root=root,
                docker_model_root_hint=root,
            )

            payload = controller.zmq_test_schema_payload()

        request_template = payload["dockers"][0]["request_template"]
        self.assertIsInstance(request_template, dict)
        self.assertIn("request_id", request_template)
        self.assertIn("rgb_image", request_template)
        self.assertIn("depth_image", request_template)
        self.assertNotIn("properties", request_template)
        self.assertIn("json schema", str(payload["dockers"][0]["request_format_note"]).lower())

    def test_generate_zmq_request_template_returns_randomized_request(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            docker_dir = root / "Sam3Docker"
            docker_dir.mkdir()
            (docker_dir / "run.sh").write_text("#!/usr/bin/env bash\n", encoding="utf-8")

            request_format_dir = docker_dir / "RequestFormat"
            request_format_dir.mkdir()
            (request_format_dir / "input.json").write_text(
                json.dumps(
                    {
                        "$schema": "https://json-schema.org/draft/2020-12/schema",
                        "type": "object",
                        "required": ["request_id", "rgb_image", "depth_image"],
                        "properties": {
                            "request_id": {"type": "string", "format": "uuid"},
                            "rgb_image": {"type": "string", "contentEncoding": "base64"},
                            "depth_image": {"type": "string", "contentEncoding": "base64"},
                        },
                    }
                ),
                encoding="utf-8",
            )
            (request_format_dir / "output.json").write_text(
                '{"status":"ok"}',
                encoding="utf-8",
            )

            matches = match_requested_dockers(
                root,
                ["Sam3Docker"],
                group_lookup={"Sam3Docker": "vision"},
            )
            controller = DashboardController(
                matches=matches,
                log_lines=100,
                project_root=root,
                docker_model_root_hint=root,
            )

            payload = controller.generate_zmq_request_template(name="Sam3Docker")

        self.assertTrue(payload["ok"])
        request_template = payload["request_template"]
        self.assertIsInstance(request_template, dict)
        self.assertIn("request_id", request_template)
        self.assertIn("timestamp", request_template)
        self.assertIn("rgb_image", request_template)
        self.assertIn("depth_image", request_template)
        self.assertIn("random request", str(payload["message"]).lower())


class BridgeManagerTest(unittest.TestCase):
    def test_resolves_relative_config_path_from_launch_config_directory(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            fusion_root = root / "FusionDocker"
            config_dir = fusion_root / "configs"
            config_dir.mkdir(parents=True)
            config_path = config_dir / "bridge.sam3_flowpose.yaml"
            config_path.write_text(
                "\n".join(
                    [
                        "bridge:",
                        "  sam3_server_addr: tcp://127.0.0.1:5555",
                        "  flowpose_server_addr: tcp://127.0.0.1:6666",
                    ]
                ),
                encoding="utf-8",
            )

            manager = BridgeManager(
                name="MainBridge",
                project_root=root,
                config_base_dir=config_dir,
                enabled=True,
                config_path="bridge.sam3_flowpose.yaml",
            )
            manager._is_endpoint_open = mock.Mock(return_value=False)
            payload = manager.payload()

        self.assertEqual(payload["status"], "stopped")
        self.assertEqual(Path(payload["config_path"]).resolve(), config_path.resolve())

    def test_payload_uses_zmq_source_endpoint_label_for_zmq_source_bridge(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            config_dir = root / "configs"
            config_dir.mkdir()
            config_path = config_dir / "bridge.sam3_flowpose.yaml"
            config_path.write_text(
                "\n".join(
                    [
                        "bridge:",
                        "  source_mode: zmq_source",
                        "  sam3_server_addr: tcp://127.0.0.1:5555",
                        "  flowpose_server_addr: tcp://127.0.0.1:6666",
                        "  zmq_source_addr: tcp://127.0.0.1:6000",
                    ]
                ),
                encoding="utf-8",
            )

            manager = BridgeManager(
                name="ZMQ Source To FlowPose",
                project_root=root,
                enabled=True,
                config_path="configs/bridge.sam3_flowpose.yaml",
            )

            payload = manager.payload()

        self.assertEqual(payload["endpoint"], "zmq-source: tcp://127.0.0.1:6000")

    @mock.patch("fusion_docker.ui_server.subprocess.Popen")
    def test_start_releases_occupied_port_before_launch(self, popen_mock: mock.Mock) -> None:
        class FakeProcess:
            def __init__(self) -> None:
                self.pid = 5678

            def poll(self):
                return None

            def wait(self, timeout: float | None = None) -> int:
                raise subprocess.TimeoutExpired("bridge", timeout or 0.25)

        popen_mock.return_value = FakeProcess()

        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            config_dir = root / "configs"
            config_dir.mkdir()
            config_path = config_dir / "bridge.sam3_flowpose.yaml"
            config_path.write_text(
                "\n".join(
                    [
                        "bridge:",
                        "  sam3_server_addr: tcp://127.0.0.1:5555",
                        "  flowpose_server_addr: tcp://127.0.0.1:6666",
                        "  listen_host: 127.0.0.1",
                        "  listen_port: 5556",
                    ]
                ),
                encoding="utf-8",
            )
            manager = BridgeManager(
                name="MainBridge",
                project_root=root,
                enabled=True,
                config_path="configs/bridge.sam3_flowpose.yaml",
            )
            manager._release_listen_port_if_busy = mock.Mock(
                return_value=(True, "Released port 5556 by stopping PID(s) 1234.")
            )

            response = manager.start()

        manager._release_listen_port_if_busy.assert_called_once_with()
        self.assertTrue(response["ok"])
        self.assertIn("Released port 5556", response["message"])
        self.assertIn("Bridge start command sent", response["message"])

    def test_stop_clears_visible_logs_but_keeps_new_logs_afterward(self) -> None:
        class FakeProcess:
            def __init__(self) -> None:
                self.pid = 4321
                self.return_code = None

            def poll(self):
                return self.return_code

            def terminate(self) -> None:
                self.return_code = 0

            def wait(self, timeout: float | None = None) -> int:
                self.return_code = 0
                return 0

        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            config_dir = root / "configs"
            config_dir.mkdir()
            config_path = config_dir / "bridge.sam3_flowpose.yaml"
            config_path.write_text(
                "\n".join(
                    [
                        "bridge:",
                        "  sam3_server_addr: tcp://127.0.0.1:5554",
                        "  flowpose_server_addr: tcp://127.0.0.1:5555",
                    ]
                ),
                encoding="utf-8",
            )

            manager = BridgeManager(
                name="MainBridge",
                project_root=root,
                enabled=True,
                config_path="configs/bridge.sam3_flowpose.yaml",
            )
            manager._log_path.parent.mkdir(parents=True, exist_ok=True)
            manager._log_path.write_text("old line\n", encoding="utf-8")
            manager._process = FakeProcess()

            response = manager.stop()

            self.assertTrue(response["ok"])
            self.assertEqual(manager.read_logs(20), "")

            with manager._log_path.open("a", encoding="utf-8") as handle:
                handle.write("new line\n")

            self.assertEqual(manager.read_logs(20), "new line")


if __name__ == "__main__":
    unittest.main()
