from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from fusion_docker.bridge_service import (
    _extract_prompts_from_source_meta,
    _request_siglip2_once,
    _external_request_format_hint,
    _normalize_sidecar_result,
    _summarize_external_request_payload,
    _summarize_zmq_meta,
    _truncate_text,
    _zmq_source_format_hint,
    build_instance_names,
)


class BridgeServiceTest(unittest.TestCase):
    def test_request_siglip2_once_sends_image_b64_json_payload(self) -> None:
        class _FakeSocket:
            def __init__(self) -> None:
                self.sent_payload = None

            def send_json(self, payload):
                self.sent_payload = payload

            def recv_json(self):
                return {"status": "ok"}

            def close(self, linger=0):
                return None

        fake_socket = _FakeSocket()

        class _FakeContext:
            @staticmethod
            def instance():
                return object()

        class _FakeAgain(Exception):
            pass

        class _FakeZmq:
            Context = _FakeContext

            class error:
                Again = _FakeAgain

        with (
            patch("fusion_docker.bridge_service._require_zmq", return_value=_FakeZmq),
            patch("fusion_docker.bridge_service.make_req_socket", return_value=fake_socket),
        ):
            result = _request_siglip2_once(
                "tcp://127.0.0.1:7777",
                timeout_ms=1000,
                meta={"frame_id": 7},
                rgb_jpg_bytes=b"jpeg-bytes",
            )

        self.assertEqual(result, {"status": "ok"})
        self.assertEqual(fake_socket.sent_payload["frame_id"], 7)
        self.assertEqual(fake_socket.sent_payload["image_b64"], "anBlZy1ieXRlcw==")

    def test_build_instance_names_uses_category_labels_without_suffix(self) -> None:
        instance_names = build_instance_names(["toy car", "toy car", "cup"])

        self.assertEqual(instance_names, ["toy car", "toy car", "cup"])

    def test_external_request_format_hint_mentions_required_fields(self) -> None:
        hint = _external_request_format_hint()

        self.assertIn("rgb_image", hint)
        self.assertIn("depth_image", hint)

    def test_zmq_source_format_hint_mentions_depth_shape(self) -> None:
        hint = _zmq_source_format_hint()

        self.assertIn("depth_shape", hint)
        self.assertIn("multipart", hint)

    def test_summarize_external_request_payload_reports_key_and_length_info(self) -> None:
        summary = _summarize_external_request_payload(
            {
                "request_id": "abc",
                "rgb_image": "x" * 12,
                "depth_image": "y" * 8,
                "extra": 1,
            }
        )

        self.assertIn("request_id=abc", summary)
        self.assertIn("rgb_image_len=12", summary)
        self.assertIn("depth_image_len=8", summary)

    def test_summarize_zmq_meta_reports_depth_shape(self) -> None:
        summary = _summarize_zmq_meta({"frame_id": 7, "depth_shape": [480, 640]})

        self.assertIn("frame_id=7", summary)
        self.assertIn("depth_shape=[480, 640]", summary)

    def test_truncate_text_limits_preview_length(self) -> None:
        truncated = _truncate_text("a" * 40, limit=16)

        self.assertEqual(truncated, "aaaaaaaaaaaaa...")

    def test_normalize_sidecar_result_unwraps_flowpose_response_wrapper(self) -> None:
        payload = _normalize_sidecar_result(
            {"elapsed_sec": 0.3, "response": {"status": "ok", "objects": []}},
            "flowpose",
        )

        self.assertTrue(payload["ok"])
        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["elapsed_sec"], 0.3)

    def test_extract_prompts_from_source_meta_uses_input_payload(self) -> None:
        prompts = _extract_prompts_from_source_meta(
            {"prompts": ["toy car", " cup ", ""]},
            required=True,
        )

        self.assertEqual(prompts, ["toy car", "cup"])

    def test_extract_prompts_from_source_meta_requires_prompt_list(self) -> None:
        with self.assertRaises(RuntimeError):
            _extract_prompts_from_source_meta({"request_id": "1"}, required=True)


if __name__ == "__main__":
    unittest.main()
