# Sam3Docker — promptable segmentation (`mask`)

SAM3 served as a standard-protocol **`mask`** model server. Given a color image
and a list of text prompts, it returns a single combined label mask plus
(optionally) per-instance masks and aligned identity lists.

> Vendored upstream: `sam3-main/` (the Dockerfile imports `sam3.*` from it).

## Protocol contract (`protocol/schemas/mask.json`)

| | content |
|---|---|
| `request.arrays`  | `color` `[H,W,3]` uint8 |
| `request.fields`  | `prompts` (string list), `return_masks?`, `clear_previous?` |
| `response.arrays` | `combined_mask` `[H,W]` uint8 (label image), `masks?` `[N,H,W]` uint8 |
| `response.fields` | `obj_ids`, `class_names`, `instance_names`, `scores` |

The server (`Server/StandardProtocol/sam3_server.py`) subclasses
`BaseModelServer`; the segmentation math is lifted verbatim from the old
base64-JSON server, only the I/O layer changed (NumPy multipart, no matplotlib
visualization). Default port: **5562** (`config.yaml → server.port`).

## Layout

```
Sam3Docker/
  Dockerfile  build.sh  run.sh  Start.sh
  config.yaml             # image/container, server host/port, checkpoint paths, score_threshold
  model/                  # sam3.pt weights (download.sh; never committed)
  Server/StandardProtocol/sam3_server.py   # ← current server
  sam3-main/              # vendored upstream SAM3 model code
```

`config.yaml` supports both the full `sam3` checkpoint and an `efficient_sam3`
(MobileCLIP text encoder) variant.

## Build & run

```bash
cd Sam3Docker
./model/download.sh        # fetch sam3.pt into model/
./build.sh                 # -> sam3:latest  (repo root as build context)
./run.sh                   # mask server on tcp://0.0.0.0:5562 (needs GPU)
```

`run.sh` mounts the repo's `protocol/` read-only and live-mounts the workspace,
so editing `sam3_server.py` does not require an image rebuild.
