from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Callable

try:
    import zmq
except ImportError:  # pragma: no cover
    zmq = None


@dataclass(slots=True)
class ZmqMessage:
    index: int
    part_count: int
    rendered: str


def listen_zmq_messages(
    *,
    endpoint: str,
    topic: str = "",
    limit: int | None = None,
    timeout_ms: int | None = None,
    on_message: Callable[[ZmqMessage], None] | None = None,
) -> list[ZmqMessage]:
    zmq_module = _require_zmq()
    context = zmq_module.Context.instance()
    socket = context.socket(zmq_module.SUB)
    socket.setsockopt(zmq_module.LINGER, 0)
    socket.setsockopt_string(zmq_module.SUBSCRIBE, topic)
    socket.connect(endpoint)

    messages: list[ZmqMessage] = []
    try:
        while True:
            if timeout_ms is not None:
                poller = zmq_module.Poller()
                poller.register(socket, zmq_module.POLLIN)
                if socket not in dict(poller.poll(timeout_ms)):
                    break

            parts = socket.recv_multipart()
            messages.append(
                ZmqMessage(
                    index=len(messages) + 1,
                    part_count=len(parts),
                    rendered=_render_message(parts),
                )
            )
            if on_message is not None:
                on_message(messages[-1])
            if limit is not None and len(messages) >= limit:
                break
    finally:
        socket.close(0)
    return messages


def _render_message(parts: list[bytes]) -> str:
    if not parts:
        return "<empty message>"
    if len(parts) == 1:
        return _render_part(parts[0])

    payload = {
        "part_count": len(parts),
        "parts": [_render_part(part) for part in parts],
    }
    return json.dumps(payload, ensure_ascii=False)


def _render_part(part: bytes) -> str:
    try:
        text = part.decode("utf-8")
    except UnicodeDecodeError:
        return f"<binary {len(part)} bytes>"

    stripped = text.strip()
    if not stripped:
        return ""
    try:
        decoded = json.loads(stripped)
    except Exception:
        return text
    return json.dumps(decoded, ensure_ascii=False)


def _require_zmq() -> Any:
    if zmq is None:
        raise RuntimeError("ZMQ listening requires pyzmq. Please install the project requirements first.")
    return zmq
