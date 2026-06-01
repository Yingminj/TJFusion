"""``BaseModelServer`` -- a ZMQ REP loop that speaks the standard protocol.

A new model becomes pluggable by subclassing this and implementing two methods::

    class MyDepthServer(BaseModelServer):
        data_type = "depth"

        def load_model(self):
            self.model = ...                      # one-time setup

        def infer(self, request: Message) -> Message:
            left = request.arrays["left"]         # numpy, already decoded
            depth = self._run(left, request.arrays["right"])
            return self.ok(request, arrays={"depth": depth}, fields={"unit": "m"})

The base class owns everything generic: the REP socket, multipart pack/unpack,
request/response schema validation, timing (``elapsed_ms``), uniform error
envelopes, and the ``--port`` CLI.  Models never touch the wire format.

This module imports :mod:`zmq` lazily so the rest of the protocol package stays
dependency-light.
"""

from __future__ import annotations

import argparse
import time
import traceback
from typing import Any

from tjfusion_protocol.codec import pack_message, unpack_message
from tjfusion_protocol.envelope import (
    Message,
    make_error_response,
    make_ok_response,
)
from tjfusion_protocol.validate import ValidationError, validate_message


class BaseModelServer:
    """Base class for a standard-protocol model server (ZMQ REP)."""

    #: Subclasses must set this to one of the six canonical data types.
    data_type: str = ""

    #: Validate inbound requests / outbound responses against the schema.
    validate_requests: bool = True
    validate_responses: bool = True

    def __init__(self, *, bind_addr: str = "tcp://0.0.0.0:5560") -> None:
        if not self.data_type:
            raise ValueError(
                f"{type(self).__name__} must set a class-level 'data_type'."
            )
        self.bind_addr = bind_addr
        self._zmq = None
        self._context = None
        self._socket = None

    # -- lifecycle hooks for subclasses ---------------------------------

    def load_model(self) -> None:
        """Override to load weights / open resources once before serving."""

    def infer(self, request: Message) -> Message:  # pragma: no cover - abstract
        """Override: take a validated request Message, return a response Message.

        Use :meth:`ok` to build the success response so the envelope stays
        consistent.
        """
        raise NotImplementedError

    # -- response helpers -----------------------------------------------

    def ok(
        self,
        request: Message,
        *,
        fields: dict[str, Any] | None = None,
        arrays: dict[str, Any] | None = None,
        elapsed_ms: float | None = None,
    ) -> Message:
        return make_ok_response(
            self.data_type,
            request.request_id,
            fields=fields,
            arrays=arrays,
            elapsed_ms=elapsed_ms,
        )

    # -- main loop ------------------------------------------------------

    def _require_zmq(self):
        if self._zmq is None:
            import zmq  # local import keeps base package import-light

            self._zmq = zmq
        return self._zmq

    def serve_forever(self) -> None:
        zmq = self._require_zmq()
        self.load_model()

        self._context = zmq.Context.instance()
        self._socket = self._context.socket(zmq.REP)
        self._socket.bind(self.bind_addr)
        print(f"[{self.data_type}] server listening on {self.bind_addr}")

        try:
            while True:
                frames = self._socket.recv_multipart()
                response = self._handle(frames)
                self._socket.send_multipart(pack_message(response))
        except KeyboardInterrupt:
            print(f"[{self.data_type}] server stopped.")
        finally:
            self._socket.close(0)

    def _handle(self, frames: list[bytes]) -> Message:
        """Decode -> validate -> infer -> validate, all wrapped in a uniform
        error envelope so a model exception never crashes the loop."""
        request_id = ""
        t0 = time.perf_counter()
        try:
            request = unpack_message(frames)
            request_id = request.request_id

            if request.data_type != self.data_type:
                raise ValidationError(
                    f"request data_type {request.data_type!r} does not match "
                    f"server data_type {self.data_type!r}"
                )
            if self.validate_requests:
                validate_message(request, direction="request", strict=True)

            response = self.infer(request)

            if response.elapsed_ms is None:
                response.elapsed_ms = round((time.perf_counter() - t0) * 1000.0, 3)
            if self.validate_responses:
                validate_message(response, direction="response", strict=True)
            return response
        except Exception as exc:  # noqa: BLE001 - report everything uniformly
            elapsed_ms = round((time.perf_counter() - t0) * 1000.0, 3)
            traceback.print_exc()
            return make_error_response(
                self.data_type,
                request_id,
                f"{type(exc).__name__}: {exc}",
                elapsed_ms=elapsed_ms,
            )

    # -- CLI ------------------------------------------------------------

    @classmethod
    def main(cls, argv: list[str] | None = None) -> None:
        parser = argparse.ArgumentParser(description=f"{cls.data_type} model server")
        parser.add_argument("--host", default="0.0.0.0")
        parser.add_argument("--port", type=int, default=5560)
        parser.add_argument("--bind", default="", help="Full bind addr; overrides host/port.")
        args = parser.parse_args(argv)
        bind_addr = args.bind or f"tcp://{args.host}:{args.port}"
        cls(bind_addr=bind_addr).serve_forever()
