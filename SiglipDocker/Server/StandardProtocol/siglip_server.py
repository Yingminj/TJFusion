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
import torch.nn as nn
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


# =====================================================================
# Multi-view model (inlined; previously imported from siglip2_trainer).
#
# Param names / shapes are an EXACT match to the trained multi-view
# checkpoints (verified by a strict state_dict load: base_model.* +
# pooler.* + view_pos_embed, no missing/unexpected keys).  The pooler is
# the same CrossViewAttentionPooler used by the single-view server
# (SiglipDocker/ZeroMQServerema.py); the multi-view wrapper adds a
# per-view positional embedding and fuses the three views' patch tokens.
# =====================================================================

class CrossViewAttentionPooler(nn.Module):
    """Learnable query tokens cross-attend over (multi-view) patch tokens.

    Input:  [B, N_tokens, D]   Output: [B, D]
    """

    def __init__(self, embed_dim=1152, num_queries=8, num_heads=8,
                 num_layers=2, dropout=0.0):
        super().__init__()
        self.embed_dim = embed_dim
        self.num_queries = num_queries

        self.query_tokens = nn.Parameter(torch.zeros(1, num_queries, embed_dim))

        self.layers = nn.ModuleList()
        for _ in range(num_layers):
            self.layers.append(nn.ModuleDict({
                'cross_attn': nn.MultiheadAttention(
                    embed_dim=embed_dim, num_heads=num_heads,
                    dropout=dropout, batch_first=True,
                ),
                'norm1': nn.LayerNorm(embed_dim),
                'norm2': nn.LayerNorm(embed_dim),
                'ffn': nn.Sequential(
                    nn.Linear(embed_dim, embed_dim * 4),
                    nn.GELU(),
                    nn.Dropout(dropout),
                    nn.Linear(embed_dim * 4, embed_dim),
                    nn.Dropout(dropout),
                ),
            }))

        self.output_ln = nn.LayerNorm(embed_dim)

    def forward(self, x):
        queries = self.query_tokens.expand(x.shape[0], -1, -1)
        for layer in self.layers:
            residual = queries
            queries = layer['norm1'](queries)
            queries = layer['cross_attn'](query=queries, key=x, value=x)[0] + residual

            residual = queries
            queries = layer['norm2'](queries)
            queries = layer['ffn'](queries) + residual

        return self.output_ln(queries.mean(dim=1))


class MultiViewSigLIPModel(nn.Module):
    """Frozen SigLIP2 base + per-view positional embedding + CrossViewAttentionPooler.

    ``encode_views`` takes the V real-camera views of one sample stacked as a
    natural batch ([V, C, H, W], or [B*V, ...] for B samples), runs each view
    through the vision tower, tags each view's patch tokens with a learned
    positional embedding, concatenates them into one token sequence and pools
    them into a single L2-normalized feature ([B, D]).
    """

    def __init__(self, base_model, pooler, num_views=3, embed_dim=1152):
        super().__init__()
        self.base_model = base_model
        self.pooler = pooler
        self.num_views = num_views
        self.embed_dim = embed_dim
        self.config = base_model.config

        # Per-view positional embedding, broadcast over the patch-token axis.
        self.view_pos_embed = nn.Parameter(torch.zeros(num_views, 1, embed_dim))

    def encode_views(self, pixel_values: torch.Tensor) -> torch.Tensor:
        """[N=B*V, C, H, W] -> [B, D] (L2-normalized)."""
        with torch.no_grad():
            vision_outputs = self.base_model.vision_model(pixel_values=pixel_values)
            patch_tokens = vision_outputs.last_hidden_state  # [N, P, D]

        n, p, d = patch_tokens.shape
        if n % self.num_views != 0:
            raise ValueError(
                f"view count {n} is not a multiple of num_views={self.num_views}")
        b = n // self.num_views

        patch_tokens = patch_tokens.view(b, self.num_views, p, d)
        patch_tokens = patch_tokens + self.view_pos_embed.unsqueeze(0)  # [1,V,1,D]
        tokens = patch_tokens.reshape(b, self.num_views * p, d)

        fused = self.pooler(tokens)
        fused = fused / (fused.norm(dim=-1, keepdim=True) + 1e-12)
        return fused


class MultiViewSiglipStatusServer(BaseModelServer):
    """Multi-view ``status`` server: classifies a 3-camera fused feature.

    Identical wire contract to :class:`SiglipStatusServer` (protocol/schemas/
    status.json) -- transparent to the bridge.  The difference is the model: a
    ``MultiViewSigLIPModel`` (frozen SigLIP2 base + a ``CrossViewAttentionPooler``)
    that fuses the three real camera views into a single feature, which is then
    compared against the same per-category centers.

    Request carries three color arrays (one per real camera); they are sent to
    the processor as a natural 3-view batch -- we do NOT call
    ``split_image_to_views`` (that is for splitting a single stitched image).
    """

    data_type = "status"

    #: array keys for the three real camera views, in the order the pooler expects
    VIEW_KEYS = ("color", "color_left", "color_right")

    def __init__(self, *, bind_addr: str, config_path: str = CONFIG_PATH) -> None:
        super().__init__(bind_addr=bind_addr)
        self.config_path = config_path
        self.model = None
        self.processor = None
        self.centers: dict[str, np.ndarray] = {}
        self.state_list: list[dict] = []
        # Similarity EMA smoothing (ported from ZeroMQServerema.py). The REP loop
        # is single-threaded, so this state safely accumulates across requests.
        self.use_sim_ema = True
        self.ema_beta = 0.7
        self._ema_state: np.ndarray | None = None

    def load_model(self) -> None:
        cfg = _load_config(self.config_path)
        model_cfg = cfg["model"]
        multi_cfg = model_cfg.get("multi", {}) or {}

        ema_cfg = cfg.get("ema", {}) or {}
        self.use_sim_ema = bool(ema_cfg.get("enabled", True))
        self.ema_beta = float(ema_cfg.get("beta", 0.7))

        base_model_path = model_cfg["path"]
        checkpoint_path = multi_cfg.get("checkpoint", model_cfg.get("checkpoint"))
        graph_info_path = multi_cfg.get(
            "graph_info_file",
            model_cfg.get("graph_info_file", model_cfg.get("cache_file", "")),
        )

        # Pooler hyper-params MUST match training (see test_video_siglip2_multiview_*).
        num_views = int(multi_cfg.get("num_views", 3))
        num_query_tokens = int(multi_cfg.get("num_query_tokens", 8))
        pooler_num_layers = int(multi_cfg.get("pooler_num_layers", 2))
        pooler_num_heads = int(multi_cfg.get("pooler_num_heads", 8))

        print(f"[status-multi] loading base model: {base_model_path}")
        base_model = AutoModel.from_pretrained(base_model_path)
        self.processor = AutoProcessor.from_pretrained(base_model_path)
        embed_dim = base_model.config.vision_config.hidden_size

        pooler = CrossViewAttentionPooler(
            embed_dim=embed_dim,
            num_queries=num_query_tokens,
            num_heads=pooler_num_heads,
            num_layers=pooler_num_layers,
            dropout=0.0,
        )
        model = MultiViewSigLIPModel(
            base_model, pooler, num_views=num_views, embed_dim=embed_dim,
        )

        if checkpoint_path and os.path.exists(checkpoint_path):
            print(f"[status-multi] loading checkpoint: {checkpoint_path}")
            checkpoint = torch.load(checkpoint_path, map_location="cpu", weights_only=False)
            model.load_state_dict(checkpoint.get("model_state_dict", checkpoint))
        else:
            print(f"[status-multi] WARNING: checkpoint not found ({checkpoint_path}); using base pooler.")

        self.model = model.to(DEVICE).eval()
        self.centers, self.state_list = _load_centers(graph_info_path)
        if self.use_sim_ema:
            print(f"[status-multi] similarity EMA smoothing on, beta={self.ema_beta}")
        else:
            print("[status-multi] similarity EMA smoothing off")
        print(f"[status-multi] multi-view SigLIP ready on {DEVICE}.")

    def _similarity_with_ema(self, feat: np.ndarray):
        """Cosine similarity to each category center, with optional EMA smoothing
        across frames. Returns (best, topk) -- mirrors ZeroMQServerema.py."""
        keys = list(self.centers.keys())
        sim_vals = np.array(
            [float(np.dot(feat, self.centers[k])) for k in keys], dtype=np.float32
        )

        if self.use_sim_ema:
            if self._ema_state is None or self._ema_state.shape != sim_vals.shape:
                self._ema_state = sim_vals.copy()
            else:
                self._ema_state = (
                    self.ema_beta * self._ema_state + (1.0 - self.ema_beta) * sim_vals
                )
            smoothed = self._ema_state
        else:
            smoothed = sim_vals

        sims = {k: float(smoothed[i]) for i, k in enumerate(keys)}
        best = max(sims.items(), key=lambda x: x[1])
        topk = sorted(sims.items(), key=lambda x: x[1], reverse=True)[:TOPK]
        return best, topk

    @torch.inference_mode()
    def _encode_views(self, images: list[Image.Image]) -> np.ndarray:
        inputs = self.processor(images=images, return_tensors="pt")
        pixel_values = inputs["pixel_values"].to(DEVICE)   # [V, C, H, W]
        fused = self.model.encode_views(pixel_values)       # [1, D]
        fused = fused / (fused.norm(dim=-1, keepdim=True) + 1e-12)
        return fused[0].detach().cpu().numpy().astype(np.float32)

    def infer(self, request: Message) -> Message:
        images: list[Image.Image] = []
        for key in self.VIEW_KEYS:
            arr = request.arrays.get(key)
            if arr is None:
                raise ValueError(f"multi-view status requires array '{key}'")
            images.append(Image.fromarray(np.ascontiguousarray(arr)).convert("RGB"))

        feat = self._encode_views(images)
        best, topk = self._similarity_with_ema(feat)

        return self.ok(
            request,
            fields={
                "best_category": best[0],
                "best_similarity": best[1],
                "topk": [{"category": k, "similarity": v} for k, v in topk],
                "state_list": self.state_list,
            },
        )


def _resolve_mode(server_cfg: dict) -> str:
    """$TJFUSION_MODE overrides config `server.mode`; default 'single'."""
    mode = (os.environ.get("TJFUSION_MODE") or server_cfg.get("mode") or "single")
    mode = str(mode).strip().lower()
    return mode if mode in ("single", "multi") else "single"


def main() -> None:
    cfg = _load_config()
    server_cfg = cfg.get("server", {})
    host = server_cfg.get("host", "0.0.0.0")
    port = int(server_cfg.get("port", 7777))
    bind_addr = f"tcp://{host}:{port}"

    mode = _resolve_mode(server_cfg)
    server_cls = MultiViewSiglipStatusServer if mode == "multi" else SiglipStatusServer
    print(f"[status] mode={mode} -> {server_cls.__name__}")
    server_cls(bind_addr=bind_addr).serve_forever()


if __name__ == "__main__":
    main()
