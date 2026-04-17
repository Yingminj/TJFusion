from __future__ import annotations

import json
from typing import Any

import zmq

from fusion_docker.models import ZmqEndpointConfig


class ZmqSubscriberBus:
    def __init__(self, channels: dict[str, ZmqEndpointConfig]) -> None:
        self._context = zmq.Context.instance()
        self._poller = zmq.Poller()
        self._socket_map: dict[zmq.Socket, tuple[str, str]] = {}

        for name, config in channels.items():
            socket = self._context.socket(zmq.SUB)
            socket.setsockopt_string(zmq.SUBSCRIBE, config.topic)
            if config.mode == "bind":
                socket.bind(config.endpoint)
            else:
                socket.connect(config.endpoint)
            self._poller.register(socket, zmq.POLLIN)
            self._socket_map[socket] = (name, config.topic)

    def poll(self, timeout_ms: int) -> list[tuple[str, str, dict[str, Any]]]:
        events = self._poller.poll(timeout_ms)
        messages: list[tuple[str, str, dict[str, Any]]] = []
        for socket, _ in events:
            raw_message = socket.recv_string()
            topic, _, payload = raw_message.partition(" ")
            messages.append((self._socket_map[socket][0], topic, _decode_payload(payload)))
        return messages

    def close(self) -> None:
        for socket in self._socket_map:
            socket.close(0)
        self._socket_map.clear()


class ZmqPublisher:
    def __init__(self, config: ZmqEndpointConfig) -> None:
        self._context = zmq.Context.instance()
        self._config = config
        self._socket = self._context.socket(zmq.PUB)
        if config.mode == "bind":
            self._socket.bind(config.endpoint)
        else:
            self._socket.connect(config.endpoint)

    def send_json(self, payload: dict[str, Any]) -> None:
        message = json.dumps(payload, ensure_ascii=False)
        self._socket.send_string(f"{self._config.topic} {message}")

    def close(self) -> None:
        self._socket.close(0)


def _decode_payload(payload: str) -> dict[str, Any]:
    if not payload.strip():
        return {}
    decoded = json.loads(payload)
    if isinstance(decoded, dict):
        return decoded
    return {"data": decoded}

