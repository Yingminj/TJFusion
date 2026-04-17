from __future__ import annotations

import base64
import json
from typing import Any
from urllib import request


def post_video_stream_frame(
    dashboard_url: str,
    *,
    title: str,
    frame_base64: str,
    mime_type: str = "image/jpeg",
    source: str = "",
    timeout_sec: float = 2.0,
) -> dict[str, Any]:
    payload = {
        "title": str(title),
        "frame_base64": str(frame_base64),
        "mime_type": str(mime_type),
        "source": str(source),
    }
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    endpoint = dashboard_url.rstrip("/") + "/api/video-stream"
    req = request.Request(
        endpoint,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    opener = request.build_opener(request.ProxyHandler({}))
    with opener.open(req, timeout=timeout_sec) as response:
        return json.loads(response.read().decode("utf-8"))


def encode_image_bytes_to_base64(image_bytes: bytes) -> str:
    return base64.b64encode(image_bytes).decode("utf-8")
