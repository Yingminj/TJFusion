#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""RealSense source server -- the ONLY component that imports pyrealsense2.

Phase-1 skeleton.  It splits the camera out of Fast-Foundation so callers can
freely pull RGB, the stereo IR pair, or the hardware depth, without dragging in
the stereo depth model.

Two interfaces (per design decision):

* REP (on-demand)  -- a caller asks for specific streams + camera params and
  gets the latest frame back.  Request envelope::

        data_type = "rgb"            # or "depth"
        fields = {"streams": ["color", "ir_left", "ir_right", "hw_depth"]}

  Response carries the requested arrays (``color``/``ir_left``/``ir_right``/
  ``hw_depth``) plus camera params in ``fields`` (``intrinsics``,
  ``color_intrinsics``, ``baseline_m``, ``ir_to_color_rotation``,
  ``ir_to_color_translation``).

* PUB (streaming)  -- every captured frame is published as a standard ``rgb``
  message (color + ir_left + ir_right + optional hw_depth), so Fast-Foundation
  can subscribe and run continuously at high rate.

Wire format is the shared NumPy-multipart protocol (no base64).

The actual pyrealsense2 calls are lifted from the original
Fast-FoundationSteroDocker rawbytes server; they are guarded so this file can be
imported and unit-tested on a machine without the SDK or a camera.
"""

from __future__ import annotations

import argparse
import threading
import time
from typing import Any

import numpy as np

# The protocol package is COPYed into the image at build time (see Dockerfile).
from tjfusion_protocol.codec import pack_message, unpack_message
from tjfusion_protocol.envelope import (
    Message,
    make_error_response,
    make_ok_response,
)

try:  # camera + transport deps are optional at import time
    import pyrealsense2 as rs
except ImportError:  # pragma: no cover - no SDK on dev box
    rs = None

try:
    import cv2
except ImportError:  # pragma: no cover
    cv2 = None

try:
    import zmq
except ImportError:  # pragma: no cover
    zmq = None


# --------------------------------------------------------------------------
# Camera abstraction
# --------------------------------------------------------------------------

class RealSenseCamera:
    """Thin wrapper around an Intel RealSense stereo + color device.

    Captures color, the two IR images (the stereo pair Fast-Foundation needs),
    and optionally the hardware depth.  Exposes intrinsics/extrinsics/baseline
    so downstream depth alignment no longer needs the camera object.
    """

    def __init__(self, width: int = 640, height: int = 480, fps: int = 30,
                 disable_emitter: int = 0, enable_hw_depth: bool = True) -> None:
        self.width = width
        self.height = height
        self.fps = fps
        self.disable_emitter = disable_emitter
        self.enable_hw_depth = enable_hw_depth

        self._pipeline = None
        self.color_K: np.ndarray | None = None
        self.left_K: np.ndarray | None = None
        self.baseline_m: float | None = None
        self.ir_to_color_R: np.ndarray | None = None
        self.ir_to_color_T: np.ndarray | None = None

    def start(self) -> None:
        if rs is None:
            raise RuntimeError("pyrealsense2 is not available in this environment.")
        self._pipeline = rs.pipeline()
        config = rs.config()
        config.enable_stream(rs.stream.infrared, 1, self.width, self.height, rs.format.y8, self.fps)
        config.enable_stream(rs.stream.infrared, 2, self.width, self.height, rs.format.y8, self.fps)
        config.enable_stream(rs.stream.color, self.width, self.height, rs.format.bgr8, self.fps)
        if self.enable_hw_depth:
            config.enable_stream(rs.stream.depth, self.width, self.height, rs.format.z16, self.fps)

        profile = self._pipeline.start(config)

        depth_sensor = profile.get_device().first_depth_sensor()
        if depth_sensor.supports(rs.option.emitter_enabled):
            depth_sensor.set_option(rs.option.emitter_enabled, self.disable_emitter)
        self._depth_scale = float(depth_sensor.get_depth_scale()) if self.enable_hw_depth else 0.0

        left_stream = profile.get_stream(rs.stream.infrared, 1).as_video_stream_profile()
        right_stream = profile.get_stream(rs.stream.infrared, 2).as_video_stream_profile()
        color_stream = profile.get_stream(rs.stream.color).as_video_stream_profile()

        left_intr = left_stream.get_intrinsics()
        color_intr = color_stream.get_intrinsics()
        extr = left_stream.get_extrinsics_to(right_stream)
        ir_to_color_extr = left_stream.get_extrinsics_to(color_stream)

        self.baseline_m = abs(extr.translation[0])
        self.ir_to_color_R = np.array(ir_to_color_extr.rotation).reshape(3, 3).T
        self.ir_to_color_T = np.array(ir_to_color_extr.translation)
        self.left_K = np.array([
            [left_intr.fx, 0, left_intr.ppx],
            [0, left_intr.fy, left_intr.ppy],
            [0, 0, 1],
        ], dtype=np.float32)
        self.color_K = np.array([
            [color_intr.fx, 0, color_intr.ppx],
            [0, color_intr.fy, color_intr.ppy],
            [0, 0, 1],
        ], dtype=np.float32)
        print(f"[realsense] baseline={self.baseline_m:.6f} m, started.")

    def capture(self, want: set[str]) -> dict[str, np.ndarray]:
        """Return a dict with the requested arrays among
        color / ir_left / ir_right / hw_depth."""
        if self._pipeline is None:
            raise RuntimeError("Camera not started.")
        frames = self._pipeline.wait_for_frames()
        out: dict[str, np.ndarray] = {}

        if "color" in want:
            color_frame = frames.get_color_frame()
            if color_frame:
                out["color"] = np.asanyarray(color_frame.get_data())
        if "ir_left" in want:
            left = frames.get_infrared_frame(1)
            if left:
                gray = np.asanyarray(left.get_data())
                out["ir_left"] = cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR) if cv2 else gray
        if "ir_right" in want:
            right = frames.get_infrared_frame(2)
            if right:
                gray = np.asanyarray(right.get_data())
                out["ir_right"] = cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR) if cv2 else gray
        if "hw_depth" in want and self.enable_hw_depth:
            depth_frame = frames.get_depth_frame()
            if depth_frame:
                depth_mm = np.asanyarray(depth_frame.get_data())  # uint16, z16
                # expose metric float32 to match the depth schema unit "m"
                out["hw_depth"] = (depth_mm.astype(np.float32) * self._depth_scale)
        return out

    def camera_fields(self) -> dict[str, Any]:
        return {
            "intrinsics": self.left_K.tolist() if self.left_K is not None else None,
            "color_intrinsics": self.color_K.tolist() if self.color_K is not None else None,
            "baseline_m": float(self.baseline_m) if self.baseline_m is not None else None,
            "ir_to_color_rotation": (
                self.ir_to_color_R.tolist() if self.ir_to_color_R is not None else None
            ),
            "ir_to_color_translation": (
                self.ir_to_color_T.tolist() if self.ir_to_color_T is not None else None
            ),
        }

    def stop(self) -> None:
        if self._pipeline is not None:
            self._pipeline.stop()
            self._pipeline = None


# --------------------------------------------------------------------------
# Mapping arrays -> the data_type they belong to
# --------------------------------------------------------------------------

_DEFAULT_STREAMS = ("color", "ir_left", "ir_right")


def _response_for(camera: RealSenseCamera, request: Message) -> Message:
    streams = request.fields.get("streams") or list(_DEFAULT_STREAMS)
    want = {str(s) for s in streams}
    arrays = camera.capture(want)
    fields = camera.camera_fields()
    # ``rgb`` is the natural envelope for a camera source frame; hw_depth, when
    # requested, rides along in the same message arrays.
    return make_ok_response(request.data_type, request.request_id, fields=fields, arrays=arrays)


# --------------------------------------------------------------------------
# REP server + PUB streamer
# --------------------------------------------------------------------------

def run_rep_server(camera: RealSenseCamera, bind_addr: str) -> None:
    if zmq is None:
        raise RuntimeError("pyzmq is not available.")
    context = zmq.Context.instance()
    socket = context.socket(zmq.REP)
    socket.bind(bind_addr)
    print(f"[realsense] REP server on {bind_addr}")
    try:
        while True:
            request_id = ""
            try:
                request = unpack_message(socket.recv_multipart())
                request_id = request.request_id
                response = _response_for(camera, request)
            except Exception as exc:  # noqa: BLE001
                response = make_error_response("rgb", request_id, f"{type(exc).__name__}: {exc}")
            socket.send_multipart(pack_message(response))
    finally:
        socket.close(0)


def run_pub_streamer(camera: RealSenseCamera, bind_addr: str, streams: tuple[str, ...]) -> None:
    if zmq is None:
        raise RuntimeError("pyzmq is not available.")
    context = zmq.Context.instance()
    socket = context.socket(zmq.PUB)
    socket.setsockopt(zmq.SNDHWM, 1)
    socket.bind(bind_addr)
    print(f"[realsense] PUB streamer on {bind_addr}, streams={streams}")
    want = set(streams)
    fields = camera.camera_fields()
    frame_id = 0
    try:
        while True:
            arrays = camera.capture(want)
            msg = make_ok_response("rgb", "", fields={**fields, "frame_id": frame_id}, arrays=arrays)
            socket.send_multipart(pack_message(msg))
            frame_id += 1
    finally:
        socket.close(0)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="RealSense source server (REP + PUB)")
    parser.add_argument("--rep-bind", default="tcp://0.0.0.0:5550")
    parser.add_argument("--pub-bind", default="tcp://0.0.0.0:5551")
    parser.add_argument("--width", type=int, default=640)
    parser.add_argument("--height", type=int, default=480)
    parser.add_argument("--fps", type=int, default=30)
    parser.add_argument("--disable-emitter", type=int, default=0)
    parser.add_argument("--no-hw-depth", action="store_true")
    parser.add_argument("--no-pub", action="store_true", help="Disable the PUB streamer.")
    parser.add_argument("--no-rep", action="store_true", help="Disable the REP server.")
    parser.add_argument(
        "--pub-streams",
        default="color,ir_left,ir_right",
        help="Comma-separated streams to publish on PUB.",
    )
    args = parser.parse_args(argv)

    camera = RealSenseCamera(
        width=args.width,
        height=args.height,
        fps=args.fps,
        disable_emitter=args.disable_emitter,
        enable_hw_depth=not args.no_hw_depth,
    )
    camera.start()

    pub_streams = tuple(s.strip() for s in args.pub_streams.split(",") if s.strip())

    threads: list[threading.Thread] = []
    try:
        if not args.no_pub:
            t = threading.Thread(
                target=run_pub_streamer,
                args=(camera, args.pub_bind, pub_streams),
                daemon=True,
            )
            t.start()
            threads.append(t)

        if not args.no_rep:
            run_rep_server(camera, args.rep_bind)
        else:
            # No REP loop to block on; idle while the PUB thread runs.
            while True:
                time.sleep(1.0)
    except KeyboardInterrupt:
        print("[realsense] stopping.")
    finally:
        camera.stop()


if __name__ == "__main__":
    main()
