# YOLODocker — object detector (auxiliary)

An Ultralytics **YOLO** detector served over ZMQ REQ/REP. Used as an
alternative / auxiliary perception source.

> **Protocol status:** legacy. This server
> (`Server/ZeroMQ/ZeroMQServer.py`, `SERVER_VERSION = "v2"`) still speaks the
> **older base64-JSON** wire format, not the `tjfusion_protocol` NumPy-multipart
> standard. Migrate it to `BaseModelServer` (as Sam3/SigLIP were) before wiring
> it into a `data_type:` pipeline node.

## Layout

```
YOLODocker/
  Dockerfile  build.sh  run.sh
  config.yaml             # server host/port, model_path, score_threshold
  model/                  # best.pt weights (never committed)
  Server/ZeroMQ/ZeroMQServer.py   # base64-JSON detector server
  Server/ZeroMQ/ZeroMQClient.py   # reference client / smoke test
```

`config.yaml`:
```yaml
server:  { host: 0.0.0.0, port: 5562 }
yolo:    { model_path: /workspace/model/best.pt, score_threshold: 0.4 }
```

> Note: port 5562 collides with Sam3Docker's default. Pick distinct ports when
> running both at once.

## Build & run

```bash
cd YOLODocker
./build.sh                 # -> yolo  (current dir as build context)
./run.sh                   # detector on tcp://0.0.0.0:5562 (uses --gpus all)
```
