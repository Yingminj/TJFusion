# VlmDocker

A fine-tuned **Qwen3.5-VL-9B + `gift_v1` LoRA** vision-language model, served as a
standard-protocol `status` model server. It reads a window of recent camera frames and
emits the current gift-packaging state (closed set of 12 classes; class 12 = `rubbish`
reject). It is a **drop-in replacement for the SigLIP status node** — same
request/response contract (`protocol/schemas/status.json`).

Adapted from the training repo's live script
`test_vlm/scripts/gift_camera.py` (prompt, ontology, frame sampling, JSON parsing).

## Layout

```
VlmDocker/
  Dockerfile                              # CUDA 12.8 + torch 2.8/cu129 + transformers>=5.9 + peft
  build.sh                                # builds with repo root as context (bundles protocol/)
  run.sh                                  # mounts weights + protocol, launches the server
  config.yaml                             # ports + weight paths + inference window knobs
  RequestFormat/{input,output}.schema.json
  Server/StandardProtocol/
    vlm_server.py                         # VlmStatusServer(BaseModelServer), data_type="status"
    ontology.py                           # vendored gift_ft ontology (prompt + parser + CLASSES)
```

## How it speaks the protocol

A model server receives one ZMQ request at a time, but the VLM is trained on a short
**window** of frames. So the server keeps a rolling buffer:

- Each request supplies the **current** `color` frame (uint8 `[H,W,3]` RGB).
- The server appends it, samples `n_frames` evenly over the buffer (newest last — the
  shape `gift_ft` trained on, even count for Qwen `temporal_patch_size=2`), runs one
  generation, and parses the `{"state","name"}` answer.
- Send `fields.reset = true` to clear the buffer at the start of a new clip/task.

Response `fields`: `best_category` (`"C<id>: <name>"`), `best_similarity` (1.0 for a
parsed non-reject state, else 0.0), `topk`, plus `state_id` / `name` / `raw` /
`num_frames`.

Until the buffer holds ≥ 2 frames the server replies with `best_category="(warming up)"`.

## Weights (mounted at runtime, ~19 GB base — never committed)

`run.sh` bind-mounts a weights directory to `/workspace/model` read-only. It must
contain the base weights and the LoRA adapter referenced in `config.yaml`:

```
<WEIGHTS_DIR>/
  qwen3_5_9B/      # base Qwen3.5-VL-9B
  gift_v1/         # LoRA adapter + processor/chat template
```

Default `WEIGHTS_DIR=/home/kewei/YING/test_vlm/model`; override per host:

```bash
WEIGHTS_DIR=/path/to/model ./run.sh
```

## Build & run

```bash
cd VlmDocker
./build.sh                      # -> vlm:latest
./run.sh                        # serves status on tcp://0.0.0.0:7788 (config.yaml)
```

Requires an NVIDIA GPU (bf16, ~19 GB VRAM). The server loads base + adapter once, then
serves the REP loop.

## Tuning (`config.yaml` → `inference`)

| key             | meaning                                                        |
|-----------------|----------------------------------------------------------------|
| `n_frames`      | frames sent to the model per check (even, ≥2; default 6)       |
| `buffer_maxlen` | rolling buffer depth (how much history the window samples from)|
| `max_new_tokens`| generation cap                                                 |
| `max_pixels`    | processor max_pixels per frame (latency/VRAM vs. detail)       |
| `max_side`      | pre-downscale longest side of each incoming frame              |

`model.task` is the task description injected into the closed-set prompt.

> The vendored `ontology.py` MUST stay in sync with whatever ontology `gift_v1` was
> trained against — the prompt, class ids, and answer regex are a single contract.
