# RealSenseDocker — camera source server (`rgb` / `depth`)

The standalone camera source, split out of Fast-Foundation. It is the **only**
component that imports `pyrealsense2`, so callers can freely request RGB, the
stereo IR pair, or hardware depth without dragging in a stereo-depth model.

The server (`Server/realsense_server.py`) exposes two ZMQ interfaces and speaks
the standard protocol (`tjfusion_protocol`, NumPy multipart).

## Two interfaces

### REP (on demand) — bind `:5550`
The caller names the streams it wants; the server returns the latest frame(s):

```jsonc
// request (standard envelope, data_type "rgb" or "depth")
{ "fields": { "streams": ["color", "ir_left", "ir_right", "hw_depth"] } }
```

Response `arrays` carry the requested `color` / `ir_left` / `ir_right` /
`hw_depth`; response `fields` carry the camera parameters: `intrinsics` (left-IR
K), `color_intrinsics`, `baseline_m`, `ir_to_color_rotation`,
`ir_to_color_translation`.

### PUB (continuous) — bind `:5551`
Each frame is published as a standard `rgb` message (color + ir_left + ir_right,
optionally hw_depth) for the bridge / Fast-Foundation to SUB at high rate. This
is the source the `bridge.realsense_split.yaml` pipeline subscribes to.

## Exposed streams

- `color`   — color `[H,W,3]` uint8
- `ir_left` / `ir_right` — stereo IR pair (3-channel, fed to Fast-Foundation)
- `hw_depth` — RealSense **hardware** depth, metric float32 `[H,W]`

So downstream "depth" has two sources: RealSense hardware depth, or
Fast-Foundation stereo estimation — the consumer chooses.

## Build & run

```bash
cd RealSenseDocker
./build.sh                 # -> realsense:latest  (repo root as build context)
./run.sh                   # uses the image CMD defaults below
```

The image `CMD` launches with sensible defaults; override by passing args to
`run.sh` (forwarded to `realsense_server.py`):

```bash
./run.sh python3 Server/realsense_server.py \
  --rep-bind tcp://0.0.0.0:5550 \
  --pub-bind tcp://0.0.0.0:5551 \
  --pub-streams color,ir_left,ir_right
# REP only: --no-pub   PUB only: --no-rep   disable hardware depth: --no-hw-depth
```

`run.sh` uses `--privileged -v /dev:/dev` (USB enumeration) and `--net=host`
(ports 5550/5551 reachable by the bridge and Fast-Foundation). The Dockerfile
already `COPY`s + installs the shared `protocol/` package.
