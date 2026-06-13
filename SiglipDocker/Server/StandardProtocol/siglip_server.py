#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""SigLIP as a standard-protocol ``status`` server.

Classifies the state/category of a color image (optionally narrowed by a mask)
against the category centers loaded from the graph-info file.  Contract:
protocol/schemas/status.json.

  request.arrays  : color [H,W,3] uint8, mask? [H,W] uint8
  request.fields  : prompts? (ignored; categories come from the graph-info file)
  response.fields : best_category (str), best_similarity (number), topk (list)

The image encoding and similarity math are lifted verbatim from the old
base64-JSON ``Server/ZeroMQ/ZeroMQServer.py``; only the I/O layer changed (no
base64, no cv2 window / dashboard upload) and it now subclasses
``BaseModelServer``.
"""

from __future__ import annotations

import ast
import json
import os

import numpy as np
import torch
import yaml
from PIL import Image
from transformers import AutoModel, AutoProcessor

from tjfusion_protocol.envelope import Message
from tjfusion_protocol.server import BaseModelServer

CONFIG_PATH = os.environ.get("SIGLIP_CONFIG", "/workspace/config.yaml")
DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
TOPK = 5


def _load_config(path: str = CONFIG_PATH) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def _parse_center_feature(value) -> np.ndarray:
    if isinstance(value, str):
        text = value.strip()
        try:
            value = json.loads(text)
        except Exception:
            value = ast.literal_eval(text)
    arr = np.array(value, dtype=np.float32)
    if arr.ndim != 1:
        raise ValueError(f"center feature must be 1D, got shape={arr.shape}")
    norm = np.linalg.norm(arr)
    if norm > 0:
        arr = arr / norm
    return arr


def _load_centers(path: str):
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    def _node_key(n):
        try:
            return int(n.get("node_id", 0))
        except Exception:
            return 10**9

    nodes = sorted(data.get("nodes", []), key=_node_key)

    centers: dict[str, np.ndarray] = {}
    state_list: list[dict] = []
    idx = 0
    for n in nodes:
        desc = str(n.get("state_description", "")).strip()
        center_raw = n.get("center_feature_siglip2", None)
        node_id = str(n.get("node_id", "")).strip()
        if not desc or center_raw is None:
            continue
        idx += 1
        cid = f"C{idx}"
        category_name = f"{cid}: {desc}"
        centers[category_name] = _parse_center_feature(center_raw)
        state_list.append({"id": cid, "node_id": node_id, "name": desc, "category": category_name})

    if not centers:
        raise RuntimeError(f"no valid category centers loaded from {path}")
    print(f"[status] loaded {len(centers)} category centers.")
    return centers, state_list


class SiglipStatusServer(BaseModelServer):
    data_type = "status"

    def __init__(self, *, bind_addr: str, config_path: str = CONFIG_PATH) -> None:
        super().__init__(bind_addr=bind_addr)
        self.config_path = config_path
        self.model = None
        self.processor = None
        self.centers: dict[str, np.ndarray] = {}
        self.state_list: list[dict] = []

    def load_model(self) -> None:
        cfg = _load_config(self.config_path)
        base_model_path = cfg["model"]["path"]
        checkpoint_path = cfg["model"]["checkpoint"]
        graph_info_path = cfg["model"].get("graph_info_file", cfg["model"].get("cache_file", ""))

        print(f"[status] loading base model: {base_model_path}")
        model = AutoModel.from_pretrained(base_model_path)
        self.processor = AutoProcessor.from_pretrained(base_model_path)

        print(f"[status] loading checkpoint: {checkpoint_path}")
        checkpoint = torch.load(checkpoint_path, map_location="cpu", weights_only=False)
        model_state = checkpoint.get("model_state_dict", checkpoint)
        incompatible = model.load_state_dict(model_state, strict=False)
        if getattr(incompatible, "missing_keys", None):
            print(f"[status] missing keys: {incompatible.missing_keys}")
        if getattr(incompatible, "unexpected_keys", None):
            print(f"[status] unexpected keys: {incompatible.unexpected_keys}")

        self.model = model.to(DEVICE).eval()
        self.centers, self.state_list = _load_centers(graph_info_path)
        print(f"[status] SigLIP ready on {DEVICE}.")

    @torch.inference_mode()
    def _encode_image(self, image: Image.Image) -> np.ndarray:
        inputs = self.processor(images=[image], return_tensors="pt")
        pixel_values = inputs["pixel_values"].to(DEVICE)
        outputs = self.model.get_image_features(pixel_values=pixel_values)
        feature = outputs.pooler_output
        feature = feature / (feature.norm(dim=-1, keepdim=True) + 1e-12)
        return feature[0].detach().cpu().numpy().astype(np.float32)

    def infer(self, request: Message) -> Message:
        color = request.arrays["color"]                 # uint8 [H,W,3] RGB
        mask = request.arrays.get("mask")                # optional [H,W] uint8

        rgb = np.ascontiguousarray(color)
        if mask is not None:
            rgb = rgb.copy()
            rgb[mask == 0] = 0
        image = Image.fromarray(rgb).convert("RGB")

        feat = self._encode_image(image)
        sims = {k: float(np.dot(feat, v)) for k, v in self.centers.items()}
        best = max(sims.items(), key=lambda x: x[1])
        topk = sorted(sims.items(), key=lambda x: x[1], reverse=True)[:TOPK]

        return self.ok(
            request,
            fields={
                "best_category": best[0],
                "best_similarity": best[1],
                "topk": [{"category": k, "similarity": v} for k, v in topk],
            },
        )


def main() -> None:
    cfg = _load_config()
    server_cfg = cfg.get("server", {})
    host = server_cfg.get("host", "0.0.0.0")
    port = int(server_cfg.get("port", 7777))
    bind_addr = f"tcp://{host}:{port}"
    SiglipStatusServer(bind_addr=bind_addr).serve_forever()


if __name__ == "__main__":
    main()
