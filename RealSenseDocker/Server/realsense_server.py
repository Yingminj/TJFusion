#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""RealSense source server -- the ONLY component that imports pyrealsense2.

It splits the camera out of Fast-Foundation so callers can freely pull RGB, the
stereo IR pair, or the hardware depth, without dragging in the stereo depth
model.

Two view modes (see ``config.yaml`` / ``$TJFUSION_MODE``):

* ``single`` -- one camera (the *head*).  Publishes ``color`` + the stereo IR
  pair (``ir_left``/``ir_right``) + optional ``hw_depth`` plus camera params.
* ``multi``  -- three cameras.  Head emits the same streams as single mode; two
  side cameras (color-only) add ``color_left`` / ``color_right``.  The three
  views are soft-synchronised (one head frame drives the rate; the side frames
  are the freshest grabbed alongside it).

Two interfaces (per design decision):

* REP (on-demand)  -- a caller asks for specific streams + camera params and
  gets the latest frame back.  Request envelope::

        data_type = "rgb"
        fields = {"streams": ["color", "ir_left", "ir_right", "hw_depth"]}

* PUB (streaming)  -- every captured frame is published as a standard ``rgb``
  message so downstream services can subscribe and run continuously.

Wire format is the shared NumPy-multipart protocol (no base64).

The pyrealsense2 calls are guarded so this file can be imported and unit-tested
on a machine without the SDK or a camera.
"""

from __future__ import annotations

import argparse
import os
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

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None


# --------------------------------------------------------------------------
# Camera abstraction
# --------------------------------------------------------------------------

class RealSenseCamera:
    """Thin wrapper around a single Intel RealSense device.

    A *head* camera captures color, the two IR images (the stereo pair
    Fast-Foundation needs) and optionally the hardware depth, and exposes
    intrinsics/extrinsics/baseline.  A *side* camera (``enable_color_only``)
    captures color only -- no IR/depth, no intrinsics.
    """

    def __init__(self, width: int = 640, height: int = 480, fps: int = 30,
                 disable_emitter: int = 0, enable_hw_depth: bool = True,
                 *, serial: str = "", enable_color: bool = True,
                 enable_ir: bool = True) -> None:
        self.width = width
        self.height = height
        self.fps = fps
        self.disable_emitter = disable_emitter
        self.serial = str(serial or "").strip()
        self.enable_color = enable_color
        self.enable_ir = enable_ir
        # depth only makes sense alongside the IR stereo head
        self.enable_hw_depth = bool(enable_hw_depth and enable_ir)

        self._pipeline = None
        self._depth_scale = 0.0
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
        if self.serial:
            config.enable_device(self.serial)
        if self.enable_ir:
            config.enable_stream(rs.stream.infrared, 1, self.width, self.height, rs.format.y8, self.fps)
            config.enable_stream(rs.stream.infrared, 2, self.width, self.height, rs.format.y8, self.fps)
        if self.enable_color:
            config.enable_stream(rs.stream.color, self.width, self.height, rs.format.bgr8, self.fps)
        if self.enable_hw_depth:
            config.enable_stream(rs.stream.depth, self.width, self.height, rs.format.z16, self.fps)

        profile = self._pipeline.start(config)

        if self.enable_ir or self.enable_hw_depth:
            depth_sensor = profile.get_device().first_depth_sensor()
            if depth_sensor.supports(rs.option.emitter_enabled):
                depth_sensor.set_option(rs.option.emitter_enabled, self.disable_emitter)
            self._depth_scale = float(depth_sensor.get_depth_scale()) if self.enable_hw_depth else 0.0

        # Intrinsics/extrinsics are only computed for the IR-equipped head.
        if self.enable_ir and self.enable_color:
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
            print(f"[realsense] serial={self.serial or '(auto)'} baseline={self.baseline_m:.6f} m, started.")
        else:
            print(f"[realsense] serial={self.serial or '(auto)'} color-only, started.")

    def capture(self, want: set[str]) -> dict[str, np.ndarray]:
        """Return a dict with the requested arrays among
        color / ir_left / ir_right / hw_depth."""
        if self._pipeline is None:
            raise RuntimeError("Camera not started.")
        frames = self._pipeline.wait_for_frames()
        out: dict[str, np.ndarray] = {}

        if "color" in want and self.enable_color:
            color_frame = frames.get_color_frame()
            if color_frame:
                out["color"] = np.asanyarray(color_frame.get_data())
        if "ir_left" in want and self.enable_ir:
            left = frames.get_infrared_frame(1)
            if left:
                gray = np.asanyarray(left.get_data())
                out["ir_left"] = cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR) if cv2 else gray
        if "ir_right" in want and self.enable_ir:
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
            "ir_left_intrinsics": self.left_K.tolist() if self.left_K is not None else None,
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


class CameraGroup:
    """One head camera plus optional left/right color-only side cameras.

    In single mode only the head is present and behaves exactly like the old
    server.  In multi mode the side cameras add ``color_left`` / ``color_right``
    to every captured frame, soft-synchronised by capturing them right after the
    head frame (all three run at the same fps).
    """

    def __init__(self, head: RealSenseCamera,
                 left: RealSenseCamera | None = None,
                 right: RealSenseCamera | None = None) -> None:
        self.head = head
        self.left = left
        self.right = right

    @property
    def multi(self) -> bool:
        return self.left is not None or self.right is not None

    def start(self) -> None:
        self.head.start()
        if self.left is not None:
            self.left.start()
        if self.right is not None:
            self.right.start()

    def stop(self) -> None:
        for cam in (self.head, self.left, self.right):
            if cam is not None:
                cam.stop()

    def capture(self, want: set[str]) -> dict[str, np.ndarray]:
        # The head frame drives the cadence; side frames are grabbed alongside.
        head_want = {w for w in want if w in ("color", "ir_left", "ir_right", "hw_depth")}
        out = self.head.capture(head_want or {"color"})
        if self.left is not None and "color_left" in want:
            left = self.left.capture({"color"})
            if "color" in left:
                out["color_left"] = left["color"]
        if self.right is not None and "color_right" in want:
            right = self.right.capture({"color"})
            if "color" in right:
                out["color_right"] = right["color"]
        return out

    def camera_fields(self) -> dict[str, Any]:
        return self.head.camera_fields()


# --------------------------------------------------------------------------
# Mapping arrays -> the data_type they belong to
# --------------------------------------------------------------------------

_DEFAULT_STREAMS = ("color", "ir_left", "ir_right")


def _response_for(group: CameraGroup, request: Message) -> Message:
    streams = request.fields.get("streams") or list(_DEFAULT_STREAMS)
    want = {str(s) for s in streams}
    arrays = group.capture(want)
    fields = group.camera_fields()
    # ``rgb`` is the natural envelope for a camera source frame; hw_depth and the
    # side views, when requested, ride along in the same message arrays.
    return make_ok_response(request.data_type, request.request_id, fields=fields, arrays=arrays)


# --------------------------------------------------------------------------
# REP server + PUB streamer
# --------------------------------------------------------------------------

def run_rep_server(group: CameraGroup, bind_addr: str) -> None:
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
                response = _response_for(group, request)
            except Exception as exc:  # noqa: BLE001
                response = make_error_response("rgb", request_id, f"{type(exc).__name__}: {exc}")
            socket.send_multipart(pack_message(response))
    finally:
        socket.close(0)


def run_pub_streamer(group: CameraGroup, bind_addr: str, streams: tuple[str, ...]) -> None:
    if zmq is None:
        raise RuntimeError("pyzmq is not available.")
    context = zmq.Context.instance()
    socket = context.socket(zmq.PUB)
    socket.setsockopt(zmq.SNDHWM, 1)
    socket.bind(bind_addr)
    print(f"[realsense] PUB streamer on {bind_addr}, streams={streams}")
    want = set(streams)
    fields = group.camera_fields()
    frame_id = 0
    try:
        while True:
            arrays = group.capture(want)
            msg = make_ok_response("rgb", "", fields={**fields, "frame_id": frame_id}, arrays=arrays)
            socket.send_multipart(pack_message(msg))
            frame_id += 1
    finally:
        socket.close(0)


# --------------------------------------------------------------------------
# Config / mode resolution
# --------------------------------------------------------------------------

_DEFAULT_CONFIG_PATH = os.environ.get("REALSENSE_CONFIG", "/workspace/config.yaml")


def _load_config(path: str) -> dict:
    if yaml is None:
        print(f"[realsense] WARNING: pyyaml not installed -- ignoring config {path!r}; "
              f"all camera serials default to (auto) and may collide.")
        return {}
    if not path or not os.path.exists(path):
        print(f"[realsense] WARNING: config not found at {path!r}; using defaults.")
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _resolve_mode(cli_mode: str | None, cfg: dict) -> str:
    """CLI --mode  >  $TJFUSION_MODE  >  config `mode`  >  'single'."""
    mode = (cli_mode or os.environ.get("TJFUSION_MODE") or cfg.get("mode") or "single")
    mode = str(mode).strip().lower()
    return mode if mode in ("single", "multi") else "single"


def _camera_by_role(cfg: dict, role: str) -> dict:
    for cam in cfg.get("cameras", []) or []:
        if str(cam.get("role", "")).strip().lower() == role:
            return cam
    return {}


def build_group(cfg: dict, mode: str, *, width: int, height: int, fps: int,
                disable_emitter: int, enable_hw_depth: bool) -> CameraGroup:
    head_cfg = _camera_by_role(cfg, "head")
    head = RealSenseCamera(
        width=width, height=height, fps=fps,
        disable_emitter=disable_emitter,
        enable_hw_depth=enable_hw_depth and bool(head_cfg.get("enable_depth", True)),
        serial=head_cfg.get("serial", ""),
        enable_color=True,
        enable_ir=bool(head_cfg.get("enable_ir", True)),
    )
    if mode != "multi":
        return CameraGroup(head)

    def _side(role: str) -> RealSenseCamera:
        c = _camera_by_role(cfg, role)
        return RealSenseCamera(
            width=width, height=height, fps=fps,
            disable_emitter=disable_emitter, enable_hw_depth=False,
            serial=c.get("serial", ""), enable_color=True, enable_ir=False,
        )

    return CameraGroup(head, left=_side("left"), right=_side("right"))


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="RealSense source server (REP + PUB)")
    parser.add_argument("--config", default=_DEFAULT_CONFIG_PATH, help="Path to config.yaml")
    parser.add_argument("--mode", default=None, choices=["single", "multi"],
                        help="Override view mode (else $TJFUSION_MODE / config).")
    parser.add_argument("--rep-bind", default=None)
    parser.add_argument("--pub-bind", default=None)
    parser.add_argument("--width", type=int, default=None)
    parser.add_argument("--height", type=int, default=None)
    parser.add_argument("--fps", type=int, default=None)
    parser.add_argument("--disable-emitter", type=int, default=None)
    parser.add_argument("--no-hw-depth", action="store_true")
    parser.add_argument("--no-pub", action="store_true", help="Disable the PUB streamer.")
    parser.add_argument("--no-rep", action="store_true", help="Disable the REP server.")
    parser.add_argument(
        "--pub-streams",
        default=None,
        help="Comma-separated streams to publish on PUB (default depends on mode).",
    )
    args = parser.parse_args(argv)

    cfg = _load_config(args.config)
    mode = _resolve_mode(args.mode, cfg)
    server_cfg = cfg.get("server", {}) or {}

    width = args.width if args.width is not None else int(cfg.get("width", 640))
    height = args.height if args.height is not None else int(cfg.get("height", 480))
    fps = args.fps if args.fps is not None else int(cfg.get("fps", 30))
    disable_emitter = (
        args.disable_emitter if args.disable_emitter is not None
        else int(cfg.get("disable_emitter", 0))
    )
    enable_hw_depth = (not args.no_hw_depth) and bool(cfg.get("enable_hw_depth", True))
    rep_bind = args.rep_bind or server_cfg.get("rep_bind", "tcp://0.0.0.0:5550")
    pub_bind = args.pub_bind or server_cfg.get("pub_bind", "tcp://0.0.0.0:5551")

    group = build_group(
        cfg, mode, width=width, height=height, fps=fps,
        disable_emitter=disable_emitter, enable_hw_depth=enable_hw_depth,
    )
    print(f"[realsense] mode={mode}, multi={group.multi}")
    group.start()

    if args.pub_streams:
        pub_streams = tuple(s.strip() for s in args.pub_streams.split(",") if s.strip())
    elif mode == "multi":
        pub_streams = ("color", "ir_left", "ir_right", "color_left", "color_right")
    else:
        pub_streams = ("color", "ir_left", "ir_right")

    threads: list[threading.Thread] = []
    try:
        if not args.no_pub:
            t = threading.Thread(
                target=run_pub_streamer,
                args=(group, pub_bind, pub_streams),
                daemon=True,
            )
            t.start()
            threads.append(t)

        if not args.no_rep:
            run_rep_server(group, rep_bind)
        else:
            # No REP loop to block on; idle while the PUB thread runs.
            while True:
                time.sleep(1.0)
    except KeyboardInterrupt:
        print("[realsense] stopping.")
    finally:
        group.stop()


if __name__ == "__main__":
    main()
