#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Fine-tuned Qwen3.5-VL as a standard-protocol ``status`` server.

Drives the **gift_v1** adapter (Qwen3.5-VL-9B base + the LoRA at ``model/gift_v1``)
to verify the current gift-packaging state from a window of recent camera frames.
Contract: protocol/schemas/status.json -- so this is a drop-in replacement for the
SigLIP status node (same request/response shape).

Because a model server gets one ZMQ request at a time but the VLM is trained on a
short *window* of frames, the server keeps a rolling buffer: each request supplies
the CURRENT ``color`` frame, the server appends it, samples ``n_frames`` evenly over
the buffer (newest last -- the shape gift_ft trained on), runs one generation, and
parses the closed-set ``{"state","name"}`` answer.

  request.arrays  : color [H,W,3] uint8 (RGB), one frame per call
  request.fields  : reset? (bool) -- clear the rolling buffer before this frame
  response.fields : best_category (str "C<id>: <name>"), best_similarity (1.0 parsed
                    / 0.0 reject|warmup|parse-fail), topk (list), plus state_id, name,
                    raw, num_frames for downstream convenience.

Inference (prompt/ontology/parse, frame picking, even-count rule) mirrors
scripts/gift_camera.py from the training repo.
"""

from __future__ import annotations

import collections
import os
import sys
import time
from typing import Deque, List

import numpy as np
import torch
import yaml
from PIL import Image

from tjfusion_protocol.envelope import Message
from tjfusion_protocol.server import BaseModelServer

# Vendored gift_ft ontology (sits next to this file).
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ontology import CLASSES, REJECT_STATE, build_prompt, parse_answer  # noqa: E402

CONFIG_PATH = os.environ.get("VLM_CONFIG", "/workspace/config.yaml")
DEVICE = "cuda" if torch.cuda.is_available() else "cpu"


def _load_config(path: str = CONFIG_PATH) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


class VlmStatusServer(BaseModelServer):
    data_type = "status"

    def __init__(self, *, bind_addr: str, config_path: str = CONFIG_PATH) -> None:
        super().__init__(bind_addr=bind_addr)
        self.config_path = config_path
        self.model = None
        self.processor = None
        self.prompt = ""
        # inference knobs (filled in load_model from config)
        self.n_frames = 6
        self.max_new_tokens = 48
        self.max_pixels = 256 * 28 * 28
        self.max_side = 448
        self.buffer_maxlen = 16
        self.buf: Deque[Image.Image] = collections.deque(maxlen=self.buffer_maxlen)

    # -- setup ----------------------------------------------------------

    def load_model(self) -> None:
        cfg = _load_config(self.config_path)
        m = cfg.get("model", {})
        inf = cfg.get("inference", {})

        base = m.get("base", "/workspace/model/qwen3_5_9B")
        adapter = m.get("adapter", "/workspace/model/gift_v1")
        task = m.get("task", "pack the toy into the gift box")

        self.n_frames = int(inf.get("n_frames", 6))
        self.max_new_tokens = int(inf.get("max_new_tokens", 48))
        self.max_pixels = int(inf.get("max_pixels", 256 * 28 * 28))
        self.max_side = int(inf.get("max_side", 448))
        self.buffer_maxlen = int(inf.get("buffer_maxlen", 16))
        self.buf = collections.deque(maxlen=self.buffer_maxlen)

        self.prompt = build_prompt(CLASSES, task=task)

        from transformers import AutoProcessor, Qwen3_5ForConditionalGeneration
        from peft import PeftModel

        # Processor lives in the adapter dir (chat template + tokenizer saved there).
        print(f"[status] loading processor <- {adapter}")
        self.processor = AutoProcessor.from_pretrained(adapter, trust_remote_code=False)

        print(f"[status] loading base {base} (bf16) + LoRA {adapter} ...")
        t0 = time.time()
        model = Qwen3_5ForConditionalGeneration.from_pretrained(
            base, dtype=torch.bfloat16, device_map="auto")
        model = PeftModel.from_pretrained(model, adapter)
        self.model = model.eval()
        vram = torch.cuda.memory_allocated() / 1e9 if torch.cuda.is_available() else 0.0
        print(f"[status] VLM ready on {DEVICE} in {time.time()-t0:.1f}s  VRAM={vram:.1f}GB")

    # -- helpers --------------------------------------------------------

    def _to_pil(self, color: np.ndarray) -> Image.Image:
        """uint8 [H,W,3] RGB numpy -> PIL, downscaled so longest side <= max_side."""
        pil = Image.fromarray(np.ascontiguousarray(color)).convert("RGB")
        if max(pil.size) > self.max_side:
            s = self.max_side / max(pil.size)
            pil = pil.resize((int(pil.width * s), int(pil.height * s)))
        return pil

    def _pick(self, frames: List[Image.Image]) -> List[Image.Image]:
        """n_frames evenly spaced over the buffer, newest last (matches gift_ft.step).
        Returns an EVEN count >= 2 (Qwen temporal_patch_size=2) or [] if too few."""
        n = min(self.n_frames, len(frames))
        if n <= 1:
            return []
        idx = [int(round(i * (len(frames) - 1) / (n - 1))) for i in range(n)]
        picks = [frames[i] for i in idx]
        if len(picks) % 2:                      # drop oldest to keep an even count
            picks = picks[1:]
        return picks if len(picks) >= 2 else []

    @torch.inference_mode()
    def _generate(self, frames: List[Image.Image]) -> str:
        messages = [{"role": "user", "content": [
            {"type": "video", "video": frames},
            {"type": "text", "text": self.prompt}]}]
        text = self.processor.apply_chat_template(
            messages, tokenize=False, add_generation_prompt=True, enable_thinking=False)
        inputs = self.processor(text=[text], videos=[frames], return_tensors="pt",
                                max_pixels=self.max_pixels).to(self.model.device)
        gen = self.model.generate(**inputs, max_new_tokens=self.max_new_tokens,
                                  do_sample=False)
        gen = gen[:, inputs["input_ids"].shape[1]:]
        return self.processor.batch_decode(gen, skip_special_tokens=True)[0].strip()

    # -- request handler ------------------------------------------------

    def infer(self, request: Message) -> Message:
        if request.fields.get("reset"):
            self.buf.clear()

        color = request.arrays["color"]                 # uint8 [H,W,3] RGB
        self.buf.append(self._to_pil(color))

        picks = self._pick(list(self.buf))
        if not picks:                                    # warming up the window
            return self._respond(state_id=None, name="(warming up)", raw="",
                                 request=request, n=len(self.buf))

        raw = self._generate(picks)
        parsed = parse_answer(raw, CLASSES)
        if parsed:
            return self._respond(state_id=parsed["state"], name=parsed["name"],
                                 raw=raw, request=request, n=len(picks))
        return self._respond(state_id=None, name="(parse-fail)", raw=raw,
                             request=request, n=len(picks))

    def _respond(self, *, state_id, name, raw, request, n) -> Message:
        # similarity is a stand-in confidence: 1.0 for a confident parsed state,
        # 0.0 for the reject class / warmup / parse failures (so downstream can
        # threshold the same way it does SigLIP cosine similarity).
        ok = state_id is not None and state_id != REJECT_STATE
        sim = 1.0 if ok else 0.0
        category = f"C{state_id}: {name}" if state_id is not None else name
        return self.ok(
            request,
            fields={
                "best_category": category,
                "best_similarity": sim,
                "topk": [{"category": category, "similarity": sim}],
                "state_id": state_id,
                "name": name,
                "raw": raw,
                "num_frames": n,
            },
        )


def main() -> None:
    cfg = _load_config()
    server_cfg = cfg.get("server", {})
    host = server_cfg.get("host", "0.0.0.0")
    port = int(server_cfg.get("port", 7788))
    bind_addr = f"tcp://{host}:{port}"
    VlmStatusServer(bind_addr=bind_addr).serve_forever()


if __name__ == "__main__":
    main()
