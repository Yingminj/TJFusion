#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Fast-Foundation as a pure ``depth`` estimator (no camera).

Phase-1 skeleton.  RealSense has been split out into RealSenseDocker; this
server now *receives* a rectified stereo pair and stereo geometry, and returns a
metric float32 depth map.  Any stereo source can feed it.

Contract (see protocol/schemas/depth.json):

  request.arrays  : left [H,W,3] uint8, right [H,W,3] uint8
  request.fields  : intrinsics (3x3), baseline_m, z_far?,
                    color_intrinsics?, ir_to_color_rotation?,
                    ir_to_color_translation?   (the last three trigger
                    depth->color alignment, exactly like the old server)
  response.arrays : depth [H,W] float32
  response.fields : unit="m", intrinsics

The disparity->depth and depth->color alignment math is preserved verbatim from
the original rawbytes ZeroMQServer; only the I/O layer changed (the model load
and ``model.forward`` are left as TODO hooks so this file imports cleanly on a
box without the weights/CUDA).
"""

from __future__ import annotations

import os
import sys

import numpy as np

# Original server appended these to sys.path; keep the hooks for the real image.
sys.path.append("/workspace/Fast-FoundationStereo-master")
os.environ.setdefault("OPENCV_IO_ENABLE_OPENEXR", "1")

from tjfusion_protocol.envelope import Message  # noqa: E402
from tjfusion_protocol.server import BaseModelServer  # noqa: E402

try:
    import cv2
except ImportError:  # pragma: no cover
    cv2 = None

try:
    import torch
except ImportError:  # pragma: no cover
    torch = None


# -- math lifted unchanged from the original server -------------------------

def compute_depth_from_disparity(disp: np.ndarray, fx: float, baseline_m: float, z_far: float) -> np.ndarray:
    with np.errstate(divide="ignore", invalid="ignore"):
        depth = fx * baseline_m / disp
    depth = depth.astype(np.float32, copy=False)
    depth[~np.isfinite(depth)] = 0
    depth[depth < 0] = 0
    if z_far > 0:
        depth[depth > z_far] = 0
    return depth


def align_depth_to_color(
    depth: np.ndarray,
    K: np.ndarray,
    color_K: np.ndarray,
    R_ext: np.ndarray,
    T_ext: np.ndarray,
    color_w: int,
    color_h: int,
) -> np.ndarray:
    """Reproject IR-frame depth into the color frame (same as original)."""
    Z = depth
    valid = (Z > 0) & np.isfinite(Z)
    y_ir, x_ir = np.nonzero(valid)
    z_ir = Z[valid]

    X_ir = (x_ir - K[0, 2]) * z_ir / K[0, 0]
    Y_ir = (y_ir - K[1, 2]) * z_ir / K[1, 1]
    P_ir = np.stack((X_ir, Y_ir, z_ir), axis=0)

    P_color = R_ext @ P_ir + T_ext[:, None]
    X_c, Y_c, Z_c = P_color[0], P_color[1], P_color[2]

    x_c = np.round((X_c / Z_c) * color_K[0, 0] + color_K[0, 2]).astype(int)
    y_c = np.round((Y_c / Z_c) * color_K[1, 1] + color_K[1, 2]).astype(int)

    mask = (x_c >= 0) & (x_c < color_w) & (y_c >= 0) & (y_c < color_h) & (Z_c > 0)
    x_c, y_c, Z_c = x_c[mask], y_c[mask], Z_c[mask]

    depth_aligned = np.zeros((color_h, color_w), dtype=np.float32)
    order = np.argsort(Z_c)[::-1]
    depth_aligned[y_c[order], x_c[order]] = Z_c[order]
    return depth_aligned


# -- the server -------------------------------------------------------------

class FastFoundationDepthServer(BaseModelServer):
    data_type = "depth"

    def __init__(self, *, bind_addr: str = "tcp://0.0.0.0:4444",
                 ckpt_dir: str = "/workspace/model/model_best_bp2_serialize.pth",
                 valid_iters: int = 8) -> None:
        super().__init__(bind_addr=bind_addr)
        self.ckpt_dir = ckpt_dir
        self.valid_iters = valid_iters
        self.model = None

    def load_model(self) -> None:
        if torch is None:
            print("[depth] torch unavailable; running in stub mode (returns zeros).")
            return
        # TODO(real image): restore the exact load from the original server:
        #   from core.utils.utils import InputPadder
        #   model = torch.load(self.ckpt_dir, map_location="cpu", weights_only=False)
        #   model.args.valid_iters = self.valid_iters; model.cuda().eval()
        torch.autograd.set_grad_enabled(False)
        self.model = None

    def _run_stereo(self, left: np.ndarray, right: np.ndarray) -> np.ndarray:
        """Return disparity [H,W] for the stereo pair.

        Stub returns zeros so the pipeline is exercisable without weights; the
        real body mirrors the original (InputPadder -> autocast forward ->
        unpad -> reshape -> remove_invisible)."""
        H, W = left.shape[:2]
        if self.model is None or torch is None:
            return np.zeros((H, W), dtype=np.float32)
        # TODO(real image): InputPadder + model.forward(...) as in the original.
        raise NotImplementedError("Wire up model.forward in the CUDA image.")

    def infer(self, request: Message) -> Message:
        left = request.arrays["left"]
        right = request.arrays["right"]
        f = request.fields
        K = np.asarray(f["intrinsics"], dtype=np.float32)
        baseline_m = float(f["baseline_m"])
        z_far = float(f.get("z_far", 10.0))

        disp = self._run_stereo(left, right)
        depth = compute_depth_from_disparity(disp, fx=float(K[0, 0]), baseline_m=baseline_m, z_far=z_far)

        out_K = K
        color_K = f.get("color_intrinsics")
        R = f.get("ir_to_color_rotation")
        T = f.get("ir_to_color_translation")
        if color_K is not None and R is not None and T is not None:
            color_K = np.asarray(color_K, dtype=np.float32)
            depth = align_depth_to_color(
                depth, K, color_K,
                np.asarray(R, dtype=np.float32), np.asarray(T, dtype=np.float32),
                color_w=left.shape[1], color_h=left.shape[0],
            )
            out_K = color_K

        return self.ok(
            request,
            arrays={"depth": depth.astype(np.float32)},
            fields={"unit": "m", "intrinsics": out_K.tolist()},
        )


if __name__ == "__main__":
    FastFoundationDepthServer.main()
