# SiglipDocker — open-vocabulary state classification (`status`)

SigLIP2 served as a standard-protocol **`status`** model server. It classifies
the state/category of a color image (optionally narrowed by a mask) against the
category centers loaded from a graph-info file, and returns the best category
plus a top-k list.

It is interchangeable with **VlmDocker** — both speak the same `status`
contract, so the pipeline can use either as its status node.

## Protocol contract (`protocol/schemas/status.json`)

| | content |
|---|---|
| `request.arrays`  | `color` `[H,W,3]` uint8, `mask?` `[H,W]` uint8 |
| `request.fields`  | `prompts?` (ignored; categories come from the graph-info file) |
| `response.fields` | `best_category` (str), `best_similarity` (number), `topk` (list) |

The server (`Server/StandardProtocol/siglip_server.py`) subclasses
`BaseModelServer`; the image encoding and similarity math are lifted verbatim
from the old base64-JSON server, only the I/O layer changed (NumPy multipart,
no cv2 window / dashboard upload). Default port: **7777**
(`config.yaml → server.port`).

## Layout

```
SiglipDocker/
  Dockerfile  build.sh  run.sh  tips.sh
  config.yaml             # image/container, server host/port, model + checkpoint + graph_info paths
  model/                  # siglip2 weights, fine-tuned checkpoint, graph_info json (download.sh)
  Server/StandardProtocol/siglip_server.py   # ← current server
  Server/ZeroMQServer_lastvit.py             # legacy server (pre-protocol)
```

`config.yaml → model`:
- `path` — base SigLIP2 weights (`siglip2-so400m-patch14-224`)
- `checkpoint` — fine-tuned state classifier
- `graph_info_file` — category centers / label graph

## Build & run

```bash
cd SiglipDocker
./build.sh                 # -> siglip2:latest  (repo root as build context)
./run.sh                   # status server on tcp://0.0.0.0:7777 (needs GPU)
```
