# Fast-FoundationSteroDocker — stereo → depth estimator

FoundationStereo served as a standard-protocol **`depth`** model server. In the
current (camera/depth split) architecture this container is a **pure stereo
depth estimator** — it no longer opens a camera. It receives a rectified stereo
pair plus stereo geometry and returns a metric `float32` depth map. Any stereo
source can feed it (RealSenseDocker is the default one).

> Vendored upstream: `Fast-FoundationStereo-master/` (inference subset).

## Protocol contract (`protocol/schemas/depth.json`)

| | content |
|---|---|
| `request.arrays`  | `left` `[H,W,3]` uint8, `right` `[H,W,3]` uint8 |
| `request.fields`  | `ir_left_intrinsics` (3×3), `baseline_m`, `z_far?`, and — to trigger depth→color alignment — `color_intrinsics?`, `ir_to_color_rotation?`, `ir_to_color_translation?` |
| `response.arrays` | `depth` `[H,W]` float32 (meters) |
| `response.fields` | `unit="m"`, `intrinsics` |

The server (`Server/StandardProtocol/depth_server.py`) subclasses
`BaseModelServer`; the disparity→depth and depth→color alignment math is
preserved verbatim from the original rawbytes server, only the I/O layer
changed (NumPy multipart, no base64). Default bind: `tcp://*:4444`.

> The `model.forward` call is left as a TODO hook so the file imports cleanly on
> a box without weights/CUDA (returns zero depth). Wire the real
> `InputPadder + model.forward` back in per the in-file comments when running on
> hardware with weights.

## Layout

```
Fast-FoundationSteroDocker/
  Dockerfile.depth          # CUDA 12.8 + torch 2.8, NO pyrealsense2  (depth-only)
  build.sh / run.sh         # canonical shims → build.depth.sh / run.depth.sh
  build.depth.sh / run.depth.sh   # build ffs-depth:latest, run depth server (needs GPU)
  build.combined.sh / run.combined.sh   # legacy camera+depth (ffs:latest, retired)
  Dockerfile                # legacy combined image
  config.yaml               # ckpt path, valid_iters, z_far, etc.
  model/                    # weights (download.sh; never committed)
  Server/
    StandardProtocol/depth_server.py   # ← current server
    ZeroMQ_rawbytes/ ZeroMQ_base64/    # legacy servers (pre-protocol)
  Fast-FoundationStereo-master/        # vendored upstream model code
```

## Build & run

```bash
cd Fast-FoundationSteroDocker
./model/download.sh        # fetch weights into model/ (not committed)
./build.sh                 # -> ffs-depth:latest  (repo root as build context)
./run.sh                   # depth server on tcp://0.0.0.0:4444 (needs nvidia runtime)
```

Want hardware depth instead of stereo estimation? Drop this node from the
pipeline and point FlowPose at RealSense's `hw_depth` — see the root
`USER_MANUAL.md`.
