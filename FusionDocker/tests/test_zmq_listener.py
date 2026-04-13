from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from fusion_docker.zmq_listener import _render_message, _render_part


class ZmqListenerTest(unittest.TestCase):
    def test_render_part_formats_json_text(self) -> None:
        rendered = _render_part(b'{"status":"ok","value":1}')

        self.assertEqual(rendered, '{"status": "ok", "value": 1}')

    def test_render_part_keeps_plain_text(self) -> None:
        rendered = _render_part(b"plain text")

        self.assertEqual(rendered, "plain text")

    def test_render_part_marks_binary_data(self) -> None:
        rendered = _render_part(b"\xff\x00\x01")

        self.assertEqual(rendered, "<binary 3 bytes>")

    def test_render_message_formats_multipart_payload(self) -> None:
        rendered = _render_message([b"topic", b'{"status":"ok"}'])

        self.assertIn('"part_count": 2', rendered)
        self.assertIn('"topic"', rendered)
        self.assertIn('\\"status\\": \\"ok\\"', rendered)


if __name__ == "__main__":
    unittest.main()
