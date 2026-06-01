"""``ModelClient`` -- a thin ZMQ REQ helper for calling a standard server.

Used by the bridge (and by demos/tests) to call any model uniformly::

    client = ModelClient("tcp://127.0.0.1:6667", data_type="pose")
    response = client.call(make_request("pose", arrays={...}, fields={...}))
    if response.ok:
        objects = response.fields["objects"]

The bridge's generic adapter can build on this so every node, regardless of
model, is invoked through one code path.
"""

from __future__ import annotations

from tjfusion_protocol.codec import pack_message, unpack_message
from tjfusion_protocol.envelope import Message
from tjfusion_protocol.validate import validate_message


class ModelClient:
    def __init__(
        self,
        endpoint: str,
        *,
        data_type: str = "",
        timeout_ms: int = 5000,
        validate: bool = False,
    ) -> None:
        self.endpoint = endpoint
        self.data_type = data_type
        self.timeout_ms = timeout_ms
        self.validate = validate
        self._zmq = None
        self._context = None

    def _require_zmq(self):
        if self._zmq is None:
            import zmq

            self._zmq = zmq
            self._context = zmq.Context.instance()
        return self._zmq

    def call(self, request: Message) -> Message:
        zmq = self._require_zmq()
        if self.validate:
            validate_message(request, direction="request", strict=True)

        socket = self._context.socket(zmq.REQ)
        socket.setsockopt(zmq.RCVTIMEO, self.timeout_ms)
        socket.setsockopt(zmq.SNDTIMEO, self.timeout_ms)
        socket.setsockopt(zmq.LINGER, 0)
        socket.connect(self.endpoint)
        try:
            socket.send_multipart(pack_message(request))
            frames = socket.recv_multipart()
        finally:
            socket.close(0)

        response = unpack_message(frames)
        if self.validate and response.ok:
            validate_message(response, direction="response", strict=True)
        return response
