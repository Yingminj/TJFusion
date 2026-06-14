# SenyunDocker — WebRTC camera bridge (image source)

Pulls a multi-view video stream from a Senyun device over **WebRTC** (GStreamer
+ websockets signaling) and re-publishes frames on a ZMQ **PUB** socket so the
rest of the pipeline can consume them like any other image source.

> **Protocol status:** legacy. The server
> (`Server/ZeroMQ/ZeroMQServer.py`) publishes JPEG-encoded frames over a plain
> ZMQ PUB socket; it does **not** yet speak the `tjfusion_protocol` standard
> envelope. It is an upstream image feeder, not a `data_type:` model node.

## Layout

```
SenyunDocker/
  Dockerfile  build.sh  run.sh
  config.yaml             # source ws_url, frame size, jpeg quality, ports
  Server/ZeroMQ/ZeroMQServer.py    # WebRTC → ZMQ PUB bridge
  Server/ZeroMQ/ZeroMQClient.py    # reference subscriber
```

`config.yaml` highlights:
```yaml
server: { host: 0.0.0.0, port: 5559 }
source: { ws_url: "ws://192.168.11.123:8555/quad_tile",
          expected_width: 2560, expected_height: 1984 }
zmq:    { jpg_quality: 80, multi_view_jpeg: true }
```

Environment overrides (see `ZeroMQServer.py`): `SENYUN_ZMQ_BIND`,
`SENYUN_JPEG_QUALITY`, `SENYUN_MAX_WIDTH`.

## Build & run

```bash
cd SenyunDocker
./build.sh                 # -> senyun  (current dir as build context)
./run.sh                   # WebRTC→ZMQ bridge on the host network
```

Requires network reachability to the Senyun signaling server (`ws_url`) and the
GStreamer WebRTC plugins baked into the image.
