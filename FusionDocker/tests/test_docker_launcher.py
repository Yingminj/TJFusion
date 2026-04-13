from __future__ import annotations

import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from fusion_docker.docker_launcher import (
    DockerContainerInfo,
    DockerLaunchResult,
    DockerMatch,
    DockerRunTarget,
    build_runtime_results,
    cleanup_launched_dockers,
    collect_runtime_statuses,
    describe_targets,
    launch_matched_dockers,
    launch_single_match,
    match_requested_dockers,
    monitor_tmux_sessions,
    read_result_logs,
    stop_launch_result,
)


class DockerLauncherTest(unittest.TestCase):
    def test_describe_targets_lists_run_script_folders(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            (root / "SAM3Docker").mkdir()
            (root / "SAM3Docker" / "run.sh").write_text("#!/usr/bin/env bash\n", encoding="utf-8")
            (root / "FlowPoseDocker").mkdir()
            (root / "FlowPoseDocker" / "run.sh").write_text("#!/usr/bin/env bash\n", encoding="utf-8")

            targets = describe_targets(root)

        self.assertEqual(sorted(targets), ["FlowPoseDocker", "SAM3Docker"])

    def test_match_requested_dockers_uses_folder_names(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            (root / "SAM3Docker").mkdir()
            (root / "SAM3Docker" / "run.sh").write_text("#!/usr/bin/env bash\n", encoding="utf-8")
            (root / "FlowPoseDocker").mkdir()
            (root / "FlowPoseDocker" / "run.sh").write_text("#!/usr/bin/env bash\n", encoding="utf-8")

            matches = match_requested_dockers(root, ["sam3", "flowpose"])

        self.assertEqual(matches[0].target.folder_name, "SAM3Docker")
        self.assertEqual(matches[0].strategy, "exact")
        self.assertEqual(matches[1].target.folder_name, "FlowPoseDocker")
        self.assertEqual(matches[1].strategy, "exact")

    def test_match_requested_dockers_preserves_group_name(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            (root / "SAM3Docker").mkdir()
            (root / "SAM3Docker" / "run.sh").write_text("#!/usr/bin/env bash\n", encoding="utf-8")

            matches = match_requested_dockers(
                root,
                ["SAM3Docker"],
                group_lookup={"SAM3Docker": "vision"},
            )

        self.assertEqual(matches[0].group_name, "vision")

    def test_build_runtime_results_uses_folder_name_for_tmux_session(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            (root / "SAM3Docker").mkdir()
            (root / "SAM3Docker" / "run.sh").write_text("#!/usr/bin/env bash\n", encoding="utf-8")

            matches = match_requested_dockers(root, ["SAM3Docker"])
            results = build_runtime_results(matches)

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].tmux_session, "SAM3Docker")
        self.assertTrue(results[0].reused_existing)

    def test_launch_matched_dockers_detached_creates_log_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            docker_dir = root / "SAM3Docker"
            docker_dir.mkdir()
            (docker_dir / "run.sh").write_text(
                "#!/usr/bin/env bash\nprintf 'sam3 booted\\n'\n",
                encoding="utf-8",
            )

            matches = match_requested_dockers(root, ["sam3"])
            results = launch_matched_dockers(matches, detached=True, log_dir=root / "logs")

            self.assertEqual(len(results), 1)
            self.assertTrue(results[0].succeeded)
            self.assertTrue(results[0].detached)
            self.assertIsNotNone(results[0].log_path)
            time.sleep(0.2)
            self.assertTrue(results[0].log_path.exists())
            self.assertIn("Launching SAM3Docker", results[0].log_path.read_text(encoding="utf-8"))

    @mock.patch("fusion_docker.docker_launcher.subprocess.run")
    @mock.patch("fusion_docker.docker_launcher.shutil.which")
    def test_launch_matched_dockers_tmux_uses_docker_name_as_session(
        self,
        which_mock: mock.Mock,
        run_mock: mock.Mock,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            docker_dir = root / "Fast-FoundationSteroDocker"
            docker_dir.mkdir()
            (docker_dir / "run.sh").write_text("#!/usr/bin/env bash\n", encoding="utf-8")

            def fake_which(command: str) -> str | None:
                if command == "tmux":
                    return "/usr/bin/tmux"
                if command == "bash":
                    return "/bin/bash"
                return None

            which_mock.side_effect = fake_which
            run_mock.side_effect = [
                subprocess.CompletedProcess(
                    ["/usr/bin/tmux", "has-session", "-t", "Fast-FoundationSteroDocker"],
                    1,
                    "",
                    "",
                ),
                subprocess.CompletedProcess(
                    ["/usr/bin/tmux", "new-session"],
                    0,
                    "",
                    "",
                ),
            ]

            matches = match_requested_dockers(root, ["Fast-FoundationSteroDocker"])
            results = launch_matched_dockers(matches, use_tmux=True)

        self.assertEqual(len(results), 1)
        self.assertTrue(results[0].succeeded)
        self.assertEqual(results[0].tmux_session, "Fast-FoundationSteroDocker")
        new_session_call = run_mock.call_args_list[1].args[0]
        self.assertEqual(new_session_call[0], "/usr/bin/tmux")
        self.assertEqual(new_session_call[1], "new-session")
        self.assertIn("Fast-FoundationSteroDocker", new_session_call)

    @mock.patch("fusion_docker.docker_launcher.cleanup_launched_dockers")
    @mock.patch("fusion_docker.docker_launcher._collect_runtime_statuses")
    @mock.patch("fusion_docker.docker_launcher._require_command")
    def test_monitor_tmux_sessions_cleans_up_when_sessions_finish(
        self,
        require_command_mock: mock.Mock,
        collect_statuses_mock: mock.Mock,
        cleanup_mock: mock.Mock,
    ) -> None:
        require_command_mock.return_value = "/usr/bin/tmux"
        result = DockerLaunchResult(
            match=DockerMatch(
                requested_name="sam3",
                target=DockerRunTarget(
                    folder_name="Sam3Docker",
                    folder_path=Path("/tmp/Sam3Docker"),
                    run_script_path=Path("/tmp/Sam3Docker/run.sh"),
                    relative_folder="Sam3Docker",
                ),
                strategy="exact",
                score=1.0,
            ),
            return_code=0,
            tmux_session="Sam3Docker",
        )
        collect_statuses_mock.side_effect = [
            [
                mock.Mock(
                    result=result,
                    overall_status="running",
                    session_state="running",
                    container_summary="sam3 [running]",
                )
            ],
            [
                mock.Mock(
                    result=result,
                    overall_status="ended",
                    session_state="ended",
                    container_summary="sam3 [ended]",
                )
            ],
        ]

        monitor_tmux_sessions([result], poll_interval_s=0.0, interactive=False)

        cleanup_mock.assert_called_once()

    @mock.patch("fusion_docker.docker_launcher._list_docker_containers")
    @mock.patch("fusion_docker.docker_launcher.subprocess.run")
    @mock.patch("fusion_docker.docker_launcher.shutil.which")
    def test_cleanup_launched_dockers_kills_tmux_and_removes_containers(
        self,
        which_mock: mock.Mock,
        run_mock: mock.Mock,
        list_containers_mock: mock.Mock,
    ) -> None:
        def fake_which(command: str) -> str | None:
            if command == "tmux":
                return "/usr/bin/tmux"
            if command == "docker":
                return "/usr/bin/docker"
            return None

        which_mock.side_effect = fake_which
        list_containers_mock.return_value = {
            "abc123": DockerContainerInfo("abc123", "sam3", "Up 5 seconds"),
        }
        run_mock.side_effect = [
            subprocess.CompletedProcess(["tmux", "has-session"], 0, "", ""),
            subprocess.CompletedProcess(["tmux", "kill-session"], 0, "", ""),
            subprocess.CompletedProcess(["docker", "rm", "-f", "abc123"], 0, "", ""),
        ]

        result = DockerLaunchResult(
            match=DockerMatch(
                requested_name="sam3",
                target=DockerRunTarget(
                    folder_name="Sam3Docker",
                    folder_path=Path("/tmp/Sam3Docker"),
                    run_script_path=Path("/tmp/Sam3Docker/run.sh"),
                    relative_folder="Sam3Docker",
                ),
                strategy="exact",
                score=1.0,
            ),
            return_code=0,
            tmux_session="Sam3Docker",
            container_ids=["abc123"],
        )

        cleanup_launched_dockers([result])

        invoked_commands = [call.args[0][:2] for call in run_mock.call_args_list]
        self.assertIn(["/usr/bin/tmux", "has-session"], invoked_commands)
        self.assertIn(["/usr/bin/tmux", "kill-session"], invoked_commands)
        self.assertIn(["/usr/bin/docker", "rm"], invoked_commands)

    @mock.patch("fusion_docker.docker_launcher.subprocess.run")
    @mock.patch("fusion_docker.docker_launcher.shutil.which")
    def test_collect_runtime_statuses_marks_dead_nonzero_tmux_as_error(
        self,
        which_mock: mock.Mock,
        run_mock: mock.Mock,
    ) -> None:
        def fake_which(command: str) -> str | None:
            if command == "tmux":
                return "/usr/bin/tmux"
            return None

        which_mock.side_effect = fake_which
        run_mock.return_value = subprocess.CompletedProcess(
            ["/usr/bin/tmux", "list-panes"],
            0,
            "1\t1\n",
            "",
        )

        result = DockerLaunchResult(
            match=DockerMatch(
                requested_name="sam3",
                target=DockerRunTarget(
                    folder_name="Sam3Docker",
                    folder_path=Path("/tmp/Sam3Docker"),
                    run_script_path=Path("/tmp/Sam3Docker/run.sh"),
                    relative_folder="Sam3Docker",
                ),
                strategy="exact",
                score=1.0,
            ),
            return_code=0,
            tmux_session="Sam3Docker",
        )

        statuses = collect_runtime_statuses([result])

        self.assertEqual(len(statuses), 1)
        self.assertEqual(statuses[0].overall_status, "error")
        self.assertEqual(statuses[0].container_summary, "startup error (exit code 1)")

    @mock.patch("fusion_docker.docker_launcher.subprocess.run")
    @mock.patch("fusion_docker.docker_launcher.shutil.which")
    def test_collect_runtime_statuses_treats_missing_tmux_window_as_ended(
        self,
        which_mock: mock.Mock,
        run_mock: mock.Mock,
    ) -> None:
        def fake_which(command: str) -> str | None:
            if command == "tmux":
                return "/usr/bin/tmux"
            return None

        which_mock.side_effect = fake_which
        run_mock.return_value = subprocess.CompletedProcess(
            ["/usr/bin/tmux", "list-panes"],
            1,
            "",
            "can't find window: Fast-FoundationSteroDocker",
        )

        result = DockerLaunchResult(
            match=DockerMatch(
                requested_name="fast-foundationstero",
                target=DockerRunTarget(
                    folder_name="Fast-FoundationSteroDocker",
                    folder_path=Path("/tmp/Fast-FoundationSteroDocker"),
                    run_script_path=Path("/tmp/Fast-FoundationSteroDocker/run.sh"),
                    relative_folder="Fast-FoundationSteroDocker",
                ),
                strategy="exact",
                score=1.0,
            ),
            return_code=0,
            tmux_session="Fast-FoundationSteroDocker",
            reused_existing=True,
        )

        statuses = collect_runtime_statuses([result])

        self.assertEqual(len(statuses), 1)
        self.assertEqual(statuses[0].session_state, "missing")
        self.assertEqual(statuses[0].overall_status, "ended")

    @mock.patch("fusion_docker.docker_launcher._list_docker_containers")
    @mock.patch("fusion_docker.docker_launcher.subprocess.run")
    @mock.patch("fusion_docker.docker_launcher.shutil.which")
    def test_collect_runtime_statuses_includes_ports_summary(
        self,
        which_mock: mock.Mock,
        run_mock: mock.Mock,
        list_containers_mock: mock.Mock,
    ) -> None:
        def fake_which(command: str) -> str | None:
            if command == "tmux":
                return "/usr/bin/tmux"
            return None

        which_mock.side_effect = fake_which
        run_mock.return_value = subprocess.CompletedProcess(
            ["/usr/bin/tmux", "list-panes"],
            0,
            "0\t0\n",
            "",
        )
        list_containers_mock.return_value = {
            "abc123": DockerContainerInfo(
                container_id="abc123",
                name="sam3_container",
                status="Up 12 seconds",
                ports="0.0.0.0:5555->5555/tcp",
            )
        }

        result = DockerLaunchResult(
            match=DockerMatch(
                requested_name="sam3",
                target=DockerRunTarget(
                    folder_name="Sam3Docker",
                    folder_path=Path("/tmp/Sam3Docker"),
                    run_script_path=Path("/tmp/Sam3Docker/run.sh"),
                    relative_folder="Sam3Docker",
                ),
                strategy="exact",
                score=1.0,
            ),
            return_code=0,
            tmux_session="Sam3Docker",
            container_ids=["abc123"],
        )

        statuses = collect_runtime_statuses([result])

        self.assertEqual(len(statuses), 1)
        self.assertEqual(statuses[0].ports_summary, "0.0.0.0:5555->5555/tcp")

    @mock.patch("fusion_docker.docker_launcher.subprocess.run")
    @mock.patch("fusion_docker.docker_launcher.shutil.which")
    def test_read_result_logs_prefers_tmux_capture(
        self,
        which_mock: mock.Mock,
        run_mock: mock.Mock,
    ) -> None:
        def fake_which(command: str) -> str | None:
            if command == "tmux":
                return "/usr/bin/tmux"
            return None

        which_mock.side_effect = fake_which
        run_mock.return_value = subprocess.CompletedProcess(
            ["/usr/bin/tmux", "capture-pane"],
            0,
            "live tmux output\n",
            "",
        )

        result = DockerLaunchResult(
            match=DockerMatch(
                requested_name="sam3",
                target=DockerRunTarget(
                    folder_name="Sam3Docker",
                    folder_path=Path("/tmp/Sam3Docker"),
                    run_script_path=Path("/tmp/Sam3Docker/run.sh"),
                    relative_folder="Sam3Docker",
                ),
                strategy="exact",
                score=1.0,
            ),
            return_code=0,
            tmux_session="Sam3Docker",
        )

        source, content = read_result_logs(result, tail_lines=120)

        self.assertEqual(source, "tmux")
        self.assertEqual(content, "live tmux output")
        capture_command = run_mock.call_args.args[0]
        self.assertEqual(capture_command[:3], ["/usr/bin/tmux", "capture-pane", "-p"])

    @mock.patch("fusion_docker.docker_launcher.subprocess.run")
    @mock.patch("fusion_docker.docker_launcher.shutil.which")
    def test_read_result_logs_can_preserve_ansi_from_tmux(
        self,
        which_mock: mock.Mock,
        run_mock: mock.Mock,
    ) -> None:
        def fake_which(command: str) -> str | None:
            if command == "tmux":
                return "/usr/bin/tmux"
            return None

        which_mock.side_effect = fake_which
        run_mock.return_value = subprocess.CompletedProcess(
            ["/usr/bin/tmux", "capture-pane"],
            0,
            "\x1b[31mred\x1b[0m",
            "",
        )

        result = DockerLaunchResult(
            match=DockerMatch(
                requested_name="sam3",
                target=DockerRunTarget(
                    folder_name="Sam3Docker",
                    folder_path=Path("/tmp/Sam3Docker"),
                    run_script_path=Path("/tmp/Sam3Docker/run.sh"),
                    relative_folder="Sam3Docker",
                ),
                strategy="exact",
                score=1.0,
            ),
            return_code=0,
            tmux_session="Sam3Docker",
        )

        source, content = read_result_logs(result, tail_lines=120, preserve_ansi=True)

        self.assertEqual(source, "tmux")
        self.assertEqual(content, "\x1b[31mred\x1b[0m")
        capture_command = run_mock.call_args.args[0]
        self.assertEqual(capture_command[:4], ["/usr/bin/tmux", "capture-pane", "-e", "-p"])

    @mock.patch("fusion_docker.docker_launcher.subprocess.run")
    @mock.patch("fusion_docker.docker_launcher.shutil.which")
    def test_read_result_logs_ignores_missing_tmux_pane(
        self,
        which_mock: mock.Mock,
        run_mock: mock.Mock,
    ) -> None:
        def fake_which(command: str) -> str | None:
            if command == "tmux":
                return "/usr/bin/tmux"
            return None

        which_mock.side_effect = fake_which
        run_mock.return_value = subprocess.CompletedProcess(
            ["/usr/bin/tmux", "capture-pane"],
            1,
            "",
            "can't find pane: FlowPoseDocker",
        )

        result = DockerLaunchResult(
            match=DockerMatch(
                requested_name="flowpose",
                target=DockerRunTarget(
                    folder_name="FlowPoseDocker",
                    folder_path=Path("/tmp/FlowPoseDocker"),
                    run_script_path=Path("/tmp/FlowPoseDocker/run.sh"),
                    relative_folder="FlowPoseDocker",
                ),
                strategy="exact",
                score=1.0,
            ),
            return_code=0,
            tmux_session="FlowPoseDocker",
        )

        source, content = read_result_logs(result, tail_lines=120, preserve_ansi=True)

        self.assertEqual(source, "none")
        self.assertIn("No logs are available", content)

    @mock.patch("fusion_docker.docker_launcher._list_docker_containers")
    @mock.patch("fusion_docker.docker_launcher.subprocess.run")
    @mock.patch("fusion_docker.docker_launcher.shutil.which")
    def test_stop_launch_result_stops_tmux_and_inferred_container(
        self,
        which_mock: mock.Mock,
        run_mock: mock.Mock,
        list_containers_mock: mock.Mock,
    ) -> None:
        def fake_which(command: str) -> str | None:
            if command == "tmux":
                return "/usr/bin/tmux"
            if command == "docker":
                return "/usr/bin/docker"
            return None

        which_mock.side_effect = fake_which
        list_containers_mock.return_value = {
            "abc123": DockerContainerInfo("abc123", "Sam3Docker-main", "Up 3 seconds"),
        }
        run_mock.side_effect = [
            subprocess.CompletedProcess(["tmux", "has-session"], 0, "", ""),
            subprocess.CompletedProcess(["tmux", "kill-session"], 0, "", ""),
            subprocess.CompletedProcess(["docker", "rm", "-f", "abc123"], 0, "", ""),
        ]

        result = DockerLaunchResult(
            match=DockerMatch(
                requested_name="sam3",
                target=DockerRunTarget(
                    folder_name="Sam3Docker",
                    folder_path=Path("/tmp/Sam3Docker"),
                    run_script_path=Path("/tmp/Sam3Docker/run.sh"),
                    relative_folder="Sam3Docker",
                ),
                strategy="exact",
                score=1.0,
            ),
            return_code=0,
            tmux_session="Sam3Docker",
            reused_existing=True,
        )

        ok, message = stop_launch_result(result)

        self.assertTrue(ok)
        self.assertIn("tmux session 'Sam3Docker'", message)
        self.assertIn("containers abc123", message)

    @mock.patch("fusion_docker.docker_launcher._collect_new_container_ids")
    @mock.patch("fusion_docker.docker_launcher._launch_once")
    @mock.patch("fusion_docker.docker_launcher._attempt_auto_build")
    @mock.patch("fusion_docker.docker_launcher._detect_missing_images")
    def test_launch_matched_dockers_auto_builds_before_launch_when_image_missing(
        self,
        detect_missing_images_mock: mock.Mock,
        attempt_auto_build_mock: mock.Mock,
        launch_once_mock: mock.Mock,
        collect_new_ids_mock: mock.Mock,
    ) -> None:
        detect_missing_images_mock.return_value = ["sam3:latest"]
        attempt_auto_build_mock.return_value = (True, "Auto build completed.")
        collect_new_ids_mock.return_value = ["cid123"]

        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            docker_dir = root / "Sam3Docker"
            docker_dir.mkdir()
            (docker_dir / "run.sh").write_text("#!/usr/bin/env bash\n", encoding="utf-8")
            match = match_requested_dockers(root, ["Sam3Docker"])[0]

            launch_once_mock.return_value = DockerLaunchResult(
                match=match,
                return_code=0,
                detached=True,
                pid=1001,
            )

            results = launch_matched_dockers([match], detached=True, log_dir=root / "logs")

        self.assertEqual(len(results), 1)
        self.assertTrue(results[0].succeeded)
        self.assertEqual(results[0].container_ids, ["cid123"])
        attempt_auto_build_mock.assert_called_once()
        reason = attempt_auto_build_mock.call_args.kwargs.get("reason", "")
        self.assertIn("sam3:latest", reason)
        launch_once_mock.assert_called_once()

    @mock.patch("fusion_docker.docker_launcher._collect_new_container_ids")
    @mock.patch("fusion_docker.docker_launcher._launch_once")
    @mock.patch("fusion_docker.docker_launcher._attempt_auto_build")
    @mock.patch("fusion_docker.docker_launcher._detect_missing_images")
    def test_launch_matched_dockers_retries_after_missing_image_error(
        self,
        detect_missing_images_mock: mock.Mock,
        attempt_auto_build_mock: mock.Mock,
        launch_once_mock: mock.Mock,
        collect_new_ids_mock: mock.Mock,
    ) -> None:
        detect_missing_images_mock.return_value = []
        attempt_auto_build_mock.return_value = (True, "Auto build completed.")
        collect_new_ids_mock.return_value = ["cid789"]

        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            docker_dir = root / "FlowPoseDocker"
            docker_dir.mkdir()
            (docker_dir / "run.sh").write_text("#!/usr/bin/env bash\n", encoding="utf-8")
            match = match_requested_dockers(root, ["FlowPoseDocker"])[0]

            launch_once_mock.side_effect = [
                DockerLaunchResult(
                    match=match,
                    return_code=1,
                    detached=True,
                    pid=2001,
                    startup_output="docker: Error response from daemon: No such image.",
                ),
                DockerLaunchResult(
                    match=match,
                    return_code=0,
                    detached=True,
                    pid=2002,
                ),
            ]

            results = launch_matched_dockers([match], detached=True, log_dir=root / "logs")

        self.assertEqual(len(results), 1)
        self.assertTrue(results[0].succeeded)
        self.assertEqual(results[0].container_ids, ["cid789"])
        self.assertEqual(launch_once_mock.call_count, 2)
        attempt_auto_build_mock.assert_called_once()

    @mock.patch("fusion_docker.docker_launcher._launch_once")
    @mock.patch("fusion_docker.docker_launcher._attempt_auto_build")
    @mock.patch("fusion_docker.docker_launcher._detect_missing_images")
    def test_launch_matched_dockers_fails_when_auto_build_fails(
        self,
        detect_missing_images_mock: mock.Mock,
        attempt_auto_build_mock: mock.Mock,
        launch_once_mock: mock.Mock,
    ) -> None:
        detect_missing_images_mock.return_value = ["fast-foundation:latest"]
        attempt_auto_build_mock.return_value = (False, "No build.sh found under folder.")

        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            docker_dir = root / "Fast-FoundationSteroDocker"
            docker_dir.mkdir()
            (docker_dir / "run.sh").write_text("#!/usr/bin/env bash\n", encoding="utf-8")
            match = match_requested_dockers(root, ["Fast-FoundationSteroDocker"])[0]

            results = launch_matched_dockers([match], detached=True, log_dir=root / "logs")

        self.assertEqual(len(results), 1)
        self.assertFalse(results[0].succeeded)
        self.assertIn("No build.sh found", results[0].startup_output or "")
        launch_once_mock.assert_not_called()

    @mock.patch("fusion_docker.docker_launcher.subprocess.run")
    @mock.patch("fusion_docker.docker_launcher._require_command")
    def test_match_requested_dockers_can_scan_remote_host(
        self,
        require_command_mock: mock.Mock,
        run_mock: mock.Mock,
    ) -> None:
        require_command_mock.return_value = "/usr/bin/ssh"
        run_mock.side_effect = [
            subprocess.CompletedProcess(
                ["/usr/bin/ssh"],
                0,
                "",
                "",
            ),
            subprocess.CompletedProcess(
                ["/usr/bin/ssh"],
                0,
                "/home/robot/DockerModel/Sam3Docker/run.sh\n",
                "",
            ),
        ]

        matches = match_requested_dockers(
            "/home/robot/DockerModel",
            ["Sam3Docker"],
            remote_host="192.168.1.88",
            remote_user="robot",
            remote_ssh_port=2222,
        )

        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0].target.folder_name, "Sam3Docker")
        self.assertEqual(matches[0].target.relative_folder, "Sam3Docker")
        self.assertTrue(matches[0].target.is_remote)
        self.assertEqual(run_mock.call_count, 2)
        verify_ssh_command = run_mock.call_args_list[0].args[0]
        self.assertEqual(verify_ssh_command[0], "/usr/bin/ssh")
        self.assertIn("robot@192.168.1.88", verify_ssh_command)
        self.assertIn("bash", verify_ssh_command)
        self.assertIn("test -d", verify_ssh_command[-1])
        ssh_command = run_mock.call_args_list[1].args[0]
        self.assertEqual(ssh_command[0], "/usr/bin/ssh")
        self.assertIn("robot@192.168.1.88", ssh_command)
        self.assertIn("2222", ssh_command)
        self.assertIn("find /home/robot/DockerModel -type f -name run.sh | sort", ssh_command[-1])

    @mock.patch("fusion_docker.docker_launcher.subprocess.run")
    @mock.patch("fusion_docker.docker_launcher._require_command")
    def test_match_requested_dockers_remote_missing_root_raises(
        self,
        require_command_mock: mock.Mock,
        run_mock: mock.Mock,
    ) -> None:
        require_command_mock.return_value = "/usr/bin/ssh"
        run_mock.return_value = subprocess.CompletedProcess(
            ["/usr/bin/ssh"],
            1,
            "",
            "No such file or directory",
        )

        with self.assertRaisesRegex(FileNotFoundError, "Remote DockerModel path does not exist"):
            match_requested_dockers(
                "/home/robot/DockerModel",
                ["Sam3Docker"],
                remote_host="192.168.1.88",
                remote_user="robot",
            )

        self.assertEqual(run_mock.call_count, 1)

    @mock.patch("fusion_docker.docker_launcher.subprocess.run")
    @mock.patch("fusion_docker.docker_launcher._require_command")
    def test_match_requested_dockers_remote_missing_run_sh_raises(
        self,
        require_command_mock: mock.Mock,
        run_mock: mock.Mock,
    ) -> None:
        require_command_mock.return_value = "/usr/bin/ssh"
        run_mock.side_effect = [
            subprocess.CompletedProcess(
                ["/usr/bin/ssh"],
                0,
                "",
                "",
            ),
            subprocess.CompletedProcess(
                ["/usr/bin/ssh"],
                0,
                "",
                "",
            ),
        ]

        with self.assertRaisesRegex(FileNotFoundError, "No run.sh files found under remote DockerModel path"):
            match_requested_dockers(
                "/home/robot/DockerModel",
                ["Sam3Docker"],
                remote_host="192.168.1.88",
                remote_user="robot",
            )

    @mock.patch("fusion_docker.docker_launcher.subprocess.run")
    @mock.patch("fusion_docker.docker_launcher._require_command")
    def test_launch_matched_dockers_remote_uses_ssh_background_when_detached(
        self,
        require_command_mock: mock.Mock,
        run_mock: mock.Mock,
    ) -> None:
        require_command_mock.return_value = "/usr/bin/ssh"
        run_mock.return_value = subprocess.CompletedProcess(
            ["/usr/bin/ssh"],
            0,
            "3456\n",
            "",
        )

        match = DockerMatch(
            requested_name="Sam3Docker",
            target=DockerRunTarget(
                folder_name="Sam3Docker",
                folder_path=Path("/home/robot/DockerModel/Sam3Docker"),
                run_script_path=Path("/home/robot/DockerModel/Sam3Docker/run.sh"),
                relative_folder="Sam3Docker",
                remote_host="192.168.1.88",
                remote_user="robot",
                remote_ssh_port=2222,
            ),
            strategy="exact",
            score=1.0,
        )

        results = launch_matched_dockers(
            [match],
            detached=True,
            use_tmux=False,
            log_dir=Path(tempfile.gettempdir()) / "fusion_test_logs",
        )

        self.assertEqual(len(results), 1)
        self.assertTrue(results[0].succeeded)
        self.assertTrue(results[0].detached)
        self.assertEqual(results[0].pid, 3456)
        self.assertIn("remote_pid=3456", results[0].startup_output or "")
        ssh_command = run_mock.call_args.args[0]
        self.assertEqual(ssh_command[0], "/usr/bin/ssh")
        self.assertIn("robot@192.168.1.88", ssh_command)
        self.assertIn("2222", ssh_command)

    @mock.patch("fusion_docker.docker_launcher.subprocess.run")
    @mock.patch("fusion_docker.docker_launcher._require_command")
    def test_launch_matched_dockers_remote_uses_tmux_when_requested(
        self,
        require_command_mock: mock.Mock,
        run_mock: mock.Mock,
    ) -> None:
        require_command_mock.return_value = "/usr/bin/ssh"
        run_mock.return_value = subprocess.CompletedProcess(
            ["/usr/bin/ssh"],
            0,
            "__FUSION_REMOTE_TMUX_STARTED__\n",
            "",
        )

        match = DockerMatch(
            requested_name="Sam3Docker",
            target=DockerRunTarget(
                folder_name="Sam3Docker",
                folder_path=Path("/home/robot/DockerModel/Sam3Docker"),
                run_script_path=Path("/home/robot/DockerModel/Sam3Docker/run.sh"),
                relative_folder="Sam3Docker",
                remote_host="192.168.1.88",
                remote_user="robot",
                remote_ssh_port=2222,
            ),
            strategy="exact",
            score=1.0,
        )

        results = launch_matched_dockers([match], detached=True, use_tmux=True)

        self.assertEqual(len(results), 1)
        self.assertTrue(results[0].succeeded)
        self.assertTrue(results[0].detached)
        self.assertIsNone(results[0].pid)
        self.assertIn("remote_tmux_session=Sam3Docker", results[0].startup_output or "")
        ssh_command = run_mock.call_args.args[0]
        self.assertEqual(ssh_command[0], "/usr/bin/ssh")
        self.assertIn("robot@192.168.1.88", ssh_command)
        self.assertIn("tmux new-session -d -s Sam3Docker", ssh_command[-1])

    @mock.patch("fusion_docker.docker_launcher.subprocess.run")
    @mock.patch("fusion_docker.docker_launcher._require_command")
    def test_stop_launch_result_remote_kills_tmux_session(
        self,
        require_command_mock: mock.Mock,
        run_mock: mock.Mock,
    ) -> None:
        require_command_mock.return_value = "/usr/bin/ssh"
        run_mock.return_value = subprocess.CompletedProcess(
            ["/usr/bin/ssh"],
            0,
            "__FUSION_REMOTE_TMUX_STOPPED__\n",
            "",
        )

        result = DockerLaunchResult(
            match=DockerMatch(
                requested_name="Sam3Docker",
                target=DockerRunTarget(
                    folder_name="Sam3Docker",
                    folder_path=Path("/home/robot/DockerModel/Sam3Docker"),
                    run_script_path=Path("/home/robot/DockerModel/Sam3Docker/run.sh"),
                    relative_folder="Sam3Docker",
                    remote_host="192.168.1.88",
                    remote_user="robot",
                    remote_ssh_port=2222,
                ),
                strategy="exact",
                score=1.0,
            ),
            return_code=0,
            detached=True,
        )

        ok, message = stop_launch_result(result)

        self.assertTrue(ok)
        self.assertIn("Stopped remote docker 'Sam3Docker'", message)
        ssh_command = run_mock.call_args.args[0]
        self.assertEqual(ssh_command[0], "/usr/bin/ssh")
        self.assertIn("bash", ssh_command)
        self.assertIn("tmux kill-session -t Sam3Docker", ssh_command[-1])

    @mock.patch("fusion_docker.docker_launcher.subprocess.run")
    @mock.patch("fusion_docker.docker_launcher._require_command")
    def test_match_requested_dockers_remote_validation_surfaces_shell_error(
        self,
        require_command_mock: mock.Mock,
        run_mock: mock.Mock,
    ) -> None:
        require_command_mock.return_value = "/usr/bin/ssh"
        run_mock.return_value = subprocess.CompletedProcess(
            ["/usr/bin/ssh"],
            2,
            "",
            "sh: 0: Illegal option -l",
        )

        with self.assertRaisesRegex(RuntimeError, "Illegal option -l"):
            match_requested_dockers(
                "/home/robot/DockerModel",
                ["Sam3Docker"],
                remote_host="192.168.1.88",
                remote_user="robot",
            )


if __name__ == "__main__":
    unittest.main()
