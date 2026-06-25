#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
import ast
import base64
import json
import threading
import time
from io import BytesIO
from urllib import error, request
from typing import Any
from pathlib import Path

import cv2
import numpy as np
import torch
import torch.nn as nn
import yaml
import zmq
from PIL import Image

from transformers import AutoModel, AutoProcessor


# =====================================================================
# V2 Attention Pooler & Model (inline, 不依赖训练框架)
# =====================================================================

class CrossViewAttentionPooler(nn.Module):
    """
    Cross-attention pooler: learnable queries attend to patch tokens.
    Input:  [B, N_patches, D]
    Output: [B, D]
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
        B = x.shape[0]
        queries = self.query_tokens.expand(B, -1, -1)

        for layer in self.layers:
            residual = queries
            queries = layer['norm1'](queries)
            queries = layer['cross_attn'](query=queries, key=x, value=x)[0] + residual

            residual = queries
            queries = layer['norm2'](queries)
            queries = layer['ffn'](queries) + residual

        output = queries.mean(dim=1)
        output = self.output_ln(output)
        return output


class SingleViewSigLIPModel(nn.Module):
    """
    V2 single-view: frozen SigLIP + CrossViewAttentionPooler on patch tokens.
    """

    def __init__(self, base_model, pooler, embed_dim=1152):
        super().__init__()
        self.base_model = base_model
        self.pooler = pooler
        self.config = base_model.config

    def encode(self, pixel_values):
        with torch.no_grad():
            vision_outputs = self.base_model.vision_model(pixel_values=pixel_values)
            patch_tokens = vision_outputs.last_hidden_state  # [B, 256, D]
        fused = self.pooler(patch_tokens)
        fused = fused / (fused.norm(dim=-1, keepdim=True) + 1e-12)
        return fused


def load_config(path="/workspace/config.yaml"):
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


cfg = load_config()

SERVER_HOST = cfg.get("server", {}).get("host", "0.0.0.0")
SERVER_PORT = cfg.get("server", {}).get("port", 5555)
ZMQ_ADDR = f"tcp://{SERVER_HOST}:{SERVER_PORT}"

BASE_MODEL_PATH = cfg["model"]["path"]
CHECKPOINT_PATH = cfg["model"]["checkpoint"]
GRAPH_INFO_PATH = cfg["model"].get("graph_info_file", cfg["model"].get("cache_file", ""))

DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
TOPK = 5

# ==================== 相似度 EMA 平滑配置 ====================
USE_SIM_EMA = cfg.get("ema", {}).get("enabled", True)
EMA_BETA    = cfg.get("ema", {}).get("beta", 0.7)
# =============================================================


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--show", action="store_true", help="显示推理结果窗口")
    parser.add_argument("--window_name", default="SigLIP Inference", help="可视化窗口名")
    parser.add_argument("--dashboard", default="", help="Dashboard base URL，例如 http://127.0.0.1:8765")
    parser.add_argument("--stream_title", default="SigLIP Inference", help="上传到 dashboard 的流标题")
    parser.add_argument("--stream_source", default="siglip_zmq_server", help="上传到 dashboard 的来源标识")
    parser.add_argument("--jpeg_quality", type=int, default=85, help="上传图像的 JPEG 质量")
    parser.add_argument("--upload_max_width", type=int, default=960, help="上传图像最大宽度，<=0 表示不缩放")
    parser.add_argument("--upload_max_height", type=int, default=720, help="上传图像最大高度，<=0 表示不缩放")
    parser.add_argument(
        "--dashboard_api_path",
        default="/api/video-stream",
        help="Dashboard 上传接口路径",
    )
    parser.add_argument(
        "--dashboard_api_fallbacks",
        default="/api/video_stream,/video-stream,/video_stream,/api/video-stream/frame,/api/video_stream/frame,/video-stream/frame,/video_stream/frame,/api/stream/frame,/stream/frame",
        help="逗号分隔的候选上传路径，主路径失败后依次尝试",
    )
    parser.add_argument(
        "--output_path",
        default="./outputs",
        help="推理结果输出路径",
    )
    return parser.parse_args()


def load_single_model():
    print(f"[INIT] 加载基础模型: {BASE_MODEL_PATH}")
    full_model = AutoModel.from_pretrained(BASE_MODEL_PATH)
    processor = AutoProcessor.from_pretrained(BASE_MODEL_PATH)

    print(f"[INIT] 加载训练权重: {CHECKPOINT_PATH}")
    checkpoint = torch.load(CHECKPOINT_PATH, map_location="cpu", weights_only=False)
    state_dict = checkpoint.get("model_state_dict", checkpoint)

    # 检测 V2 单视角 checkpoint: key 以 base_model. 和 pooler. 开头
    sample_key = next(iter(state_dict))
    is_v2 = sample_key.startswith('base_model.') and any(
        k.startswith('pooler.') for k in state_dict)

    if is_v2:
        embed_dim = full_model.config.vision_config.hidden_size
        # 从 checkpoint 推断 pooler 参数
        num_queries = state_dict['pooler.query_tokens'].shape[1]
        num_layers = sum(1 for k in state_dict if k.endswith('.cross_attn.in_proj_weight'))
        num_heads = 8  # 与训练配置一致

        pooler = CrossViewAttentionPooler(
            embed_dim=embed_dim, num_queries=num_queries,
            num_heads=num_heads, num_layers=num_layers, dropout=0.0)
        model = SingleViewSigLIPModel(full_model, pooler, embed_dim=embed_dim)
        model.load_state_dict(state_dict)
        model = model.to(DEVICE)
        model.eval()
        print(f"[INIT] V2 SingleView 模型加载完成 (queries={num_queries}, layers={num_layers})")
    else:
        # V1 路径: 直接加载到 full_model
        incompatible = full_model.load_state_dict(state_dict, strict=False)
        if getattr(incompatible, "missing_keys", None):
            print(f"[WARN] 缺失键: {incompatible.missing_keys}")
        if getattr(incompatible, "unexpected_keys", None):
            print(f"[WARN] 多余键: {incompatible.unexpected_keys}")
        model = full_model
        model = model.to(DEVICE)
        model.eval()
        print("[INIT] V1 模型加载完成")

    return model, processor


def _parse_center_feature(value) -> np.ndarray:
    if isinstance(value, str):
        text = value.strip()
        try:
            value = json.loads(text)
        except Exception:
            value = ast.literal_eval(text)

    arr = np.array(value, dtype=np.float32)
    if arr.ndim != 1:
        raise ValueError(f"center feature 必须为 1D，当前 shape={arr.shape}")

    norm = np.linalg.norm(arr)
    if norm > 0:
        arr = arr / norm
    return arr


def load_centers(path: str):
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    nodes = data.get("nodes", [])

    def _node_key(n):
        try:
            return int(n.get("node_id", 0))
        except Exception:
            return 10**9

    nodes = sorted(nodes, key=_node_key)

    centers = {}
    state_list = []

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
        center = _parse_center_feature(center_raw)

        centers[category_name] = center
        state_list.append({
            "id": cid,
            "node_id": node_id,
            "name": desc,
            "category": category_name
        })

    if not centers:
        raise RuntimeError(f"未从 {path} 读取到有效类别中心")

    print(f"[INIT] 加载类别数: {len(centers)}")
    return centers, state_list


def decode_image_b64_to_pil(image_b64: str) -> Image.Image:
    try:
        image_bytes = base64.b64decode(image_b64)
    except Exception as e:
        raise ValueError(f"图片 base64 解码失败: {e}") from e

    try:
        return Image.open(BytesIO(image_bytes)).convert("RGB")
    except Exception as e:
        raise ValueError(f"图片解码失败: {e}") from e


def decode_image_b64_to_bgr(image_b64: str) -> np.ndarray:
    try:
        image_bytes = base64.b64decode(image_b64)
    except Exception as e:
        raise ValueError(f"图片 base64 解码失败: {e}") from e

    img_array = np.frombuffer(image_bytes, dtype=np.uint8)
    image_bgr = cv2.imdecode(img_array, cv2.IMREAD_COLOR)
    if image_bgr is None:
        raise ValueError("OpenCV 图片解码失败")
    return image_bgr


@torch.inference_mode()
def encode_image(model, processor, image: Image.Image) -> np.ndarray:
    inputs = processor(images=[image], return_tensors="pt")
    pixel_values = inputs["pixel_values"].to(DEVICE)

    # V2: model.encode() / V1: model.vision_model()
    if hasattr(model, 'encode'):
        feature = model.encode(pixel_values)  # [1, D] already L2-normalized
    else:
        outputs = model.vision_model(pixel_values=pixel_values)
        feature = outputs.pooler_output
        feature = feature / (feature.norm(dim=-1, keepdim=True) + 1e-12)

    feat_np = feature[0].detach().cpu().numpy().astype(np.float32)
    return feat_np


def calculate_similarity(feat_np: np.ndarray, centers: dict, state_list: list,
                         ema_state: np.ndarray = None):
    """计算相似度，可选 EMA 平滑。返回 (result_dict, updated_ema_state)。"""
    sim_keys = list(centers.keys())
    sim_vals = np.array([float(np.dot(feat_np, centers[k])) for k in sim_keys],
                        dtype=np.float32)

    # EMA 平滑
    if USE_SIM_EMA:
        if ema_state is None:
            ema_state = sim_vals.copy()
        else:
            ema_state = EMA_BETA * ema_state + (1 - EMA_BETA) * sim_vals
        smoothed = ema_state
    else:
        smoothed = sim_vals

    sims = {k: float(smoothed[i]) for i, k in enumerate(sim_keys)}
    best = max(sims.items(), key=lambda x: x[1])
    topk = sorted(sims.items(), key=lambda x: x[1], reverse=True)[:TOPK]

    result = {
        "ok": True,
        "best_category": best[0],
        "best_similarity": best[1],
        "topk": [{"category": k, "similarity": v} for k, v in topk],
        "total_category": state_list
    }
    return result, ema_state


def create_state_diagram(states, current_state_id=None, width=640, height=400):
    diagram = np.ones((height, width, 3), dtype=np.uint8) * 255
    if not states:
        cv2.putText(
            diagram,
            "No states loaded",
            (20, height // 2),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.8,
            (90, 90, 90),
            2,
            cv2.LINE_AA,
        )
        return diagram

    n_states = len(states)
    split_x = int(width * 0.56)
    cv2.line(diagram, (split_x, 10), (split_x, height - 10), (220, 220, 220), 1)

    left_w = split_x
    cx, cy = left_w // 2, height // 2
    rx = int(left_w * 0.33)
    ry = int(height * 0.30)
    node_r = 20

    positions = []
    for i in range(n_states):
        angle = -90 + (360.0 * i / n_states)
        rad = np.deg2rad(angle)
        x = int(cx + rx * np.cos(rad))
        y = int(cy + ry * np.sin(rad))
        positions.append((x, y))

    for i in range(n_states):
        x1, y1 = positions[i]
        x2, y2 = positions[(i + 1) % n_states]
        cv2.line(diagram, (x1, y1), (x2, y2), (205, 205, 205), 2)

        dx, dy = x2 - x1, y2 - y1
        dist = max(np.hypot(dx, dy), 1e-6)
        ex = int(x2 - dx / dist * node_r)
        ey = int(y2 - dy / dist * node_r)
        sx = int(x2 - dx / dist * (node_r + 8))
        sy = int(y2 - dy / dist * (node_r + 8))
        px = int(-dy / dist * 6)
        py = int(dx / dist * 6)
        cv2.line(diagram, (sx - px, sy - py), (ex, ey), (165, 165, 165), 2)
        cv2.line(diagram, (sx + px, sy + py), (ex, ey), (165, 165, 165), 2)

    for st, (x, y) in zip(states, positions):
        sid = str(st.get("id", ""))
        is_cur = sid == current_state_id

        if is_cur:
            cv2.circle(diagram, (x, y), node_r + 8, (0, 200, 255), 2)
            cv2.circle(diagram, (x, y), node_r, (0, 140, 255), -1)
            txt_color = (255, 255, 255)
            txt_thick = 2
        else:
            cv2.circle(diagram, (x, y), node_r, (185, 185, 185), 2)
            cv2.circle(diagram, (x, y), node_r - 3, (245, 245, 245), -1)
            txt_color = (90, 90, 90)
            txt_thick = 1

        label = sid if sid else "?"
        (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.45, txt_thick)
        cv2.putText(
            diagram,
            label,
            (x - tw // 2, y + th // 2),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.45,
            txt_color,
            txt_thick,
            cv2.LINE_AA,
        )

    cv2.putText(
        diagram,
        "States",
        (split_x + 12, 24),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.52,
        (60, 60, 60),
        1,
        cv2.LINE_AA,
    )

    right_x = split_x + 12
    right_w = width - right_x - 8
    top_y = 46
    usable_h = height - top_y - 10
    line_h = max(16, int(usable_h / max(n_states, 1)))
    font_scale = min(0.45, max(0.30, line_h / 48.0))

    def fit_text(text, max_w, scale, thickness):
        if cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, scale, thickness)[0][0] <= max_w:
            return text
        lo, hi = 0, len(text)
        best = "..."
        while lo <= hi:
            mid = (lo + hi) // 2
            cand = text[:mid] + "..."
            w = cv2.getTextSize(cand, cv2.FONT_HERSHEY_SIMPLEX, scale, thickness)[0][0]
            if w <= max_w:
                best = cand
                lo = mid + 1
            else:
                hi = mid - 1
        return best

    for i, st in enumerate(states):
        y = top_y + i * line_h
        if y > height - 6:
            break

        sid = str(st.get("id", ""))
        name = str(st.get("name", ""))
        raw_text = f"{sid} : {name}"
        is_cur = sid == current_state_id
        color = (0, 140, 255) if is_cur else (85, 85, 85)
        thickness = 2 if is_cur else 1

        if is_cur:
            cv2.rectangle(diagram, (right_x - 4, y - 12), (width - 8, y + 5), (235, 245, 255), -1)

        cv2.putText(
            diagram,
            fit_text(raw_text, right_w, font_scale, thickness),
            (right_x, y),
            cv2.FONT_HERSHEY_SIMPLEX,
            font_scale,
            color,
            thickness,
            cv2.LINE_AA,
        )

    return diagram


def get_current_state_id(result: dict, states: list):
    if not result or not result.get("ok"):
        return None

    category = str(result.get("best_category", "")).strip()
    if not category:
        return None

    if ":" in category:
        maybe_id = category.split(":", 1)[0].strip()
        if any(str(s.get("id", "")) == maybe_id for s in states):
            return maybe_id

    for state in states:
        if str(state.get("name", "")).strip() == category:
            return str(state.get("id", ""))

    for state in states:
        if str(state.get("category", "")).strip() == category:
            return str(state.get("id", ""))

    return None


def draw_result_on_frame(frame: np.ndarray, result: dict, fps=None):
    vis = frame.copy()
    if result and result.get("ok"):
        category = str(result.get("best_category", "unknown"))
        similarity = float(result.get("best_similarity", 0.0))
        cv2.putText(vis, f"State: {category}", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)
        cv2.putText(vis, f"Confidence: {similarity:.3f}", (10, 65), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 0, 0), 2)
    else:
        err = result.get("error", "unknown") if isinstance(result, dict) else "unknown"
        cv2.putText(vis, f"Error: {err}", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)

    if fps is not None:
        cv2.putText(vis, f"FPS: {float(fps):.2f}", (10, 100), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 180, 0), 2)

    return vis


def build_visualization_frame(image_bgr: np.ndarray, result: dict, state_list: list, fps=None):
    vis = draw_result_on_frame(image_bgr, result, fps=fps)
    diagram = create_state_diagram(
        state_list,
        current_state_id=get_current_state_id(result, state_list),
        width=vis.shape[1],
        height=400,
    )
    return np.vstack([vis, diagram])


def show_inference_window(image_bgr: np.ndarray, result: dict, state_list: list, window_name: str, fps=None):
    combined = build_visualization_frame(image_bgr, result, state_list, fps=fps)
    cv2.imshow(window_name, combined)
    return (cv2.waitKey(1) & 0xFF) != ord("q")


def encode_image_bytes_to_base64(image_bytes: bytes) -> str:
    return base64.b64encode(image_bytes).decode("utf-8")


def build_dashboard_endpoint(dashboard: str, api_path: str) -> str:
    dashboard = dashboard.rstrip("/")
    if not dashboard:
        raise ValueError("dashboard 不能为空")
    if api_path.startswith(("http://", "https://")):
        return api_path
    return f"{dashboard}/{api_path.lstrip('/')}"


def parse_dashboard_paths(primary_path: str, fallback_paths: str) -> list[str]:
    paths = []
    for item in [primary_path, *fallback_paths.split(",")]:
        path = item.strip()
        if not path or path in paths:
            continue
        paths.append(path)
    return paths


def post_video_stream_frame(
    dashboard: str,
    *,
    title: str,
    frame_base64: str,
    mime_type: str,
    source: str,
    api_paths: list[str],
):
    payload = {
        "title": title,
        "frame_base64": frame_base64,
        "mime_type": mime_type,
        "source": source,
    }
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")

    last_http_error = None
    last_exception = None
    for api_path in api_paths:
        endpoint = build_dashboard_endpoint(dashboard, api_path)
        req = request.Request(
            endpoint,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with request.urlopen(req, timeout=5.0) as resp:
                body = resp.read().decode("utf-8")
                result = json.loads(body) if body else {}
                if isinstance(result, dict):
                    result["_endpoint"] = endpoint
                return result
        except error.HTTPError as e:
            body = ""
            try:
                body = e.read().decode("utf-8", errors="ignore")
            except Exception:
                pass
            if e.code != 404:
                message = f"HTTP {e.code} @ {endpoint}"
                if body:
                    message = f"{message} | {body[:500]}"
                raise RuntimeError(message) from e
            last_http_error = (endpoint, e.code, body[:500])
        except Exception as e:
            last_exception = (endpoint, e)

    if last_http_error is not None:
        endpoint, code, body = last_http_error
        message = f"HTTP {code} @ {endpoint}"
        if body:
            message = f"{message} | {body}"
        raise RuntimeError(message)

    if last_exception is not None:
        endpoint, exc = last_exception
        raise RuntimeError(f"request failed @ {endpoint}: {exc}") from exc

    raise RuntimeError("没有可用的 dashboard 上传路径")


def upload_visualization_frame(
    frame_bgr: np.ndarray,
    *,
    dashboard: str,
    title: str,
    source: str,
    api_paths: list[str],
    jpeg_quality: int,
    max_width: int,
    max_height: int,
):
    frame_to_upload = resize_for_upload(frame_bgr, max_width=max_width, max_height=max_height)
    ok, buf = cv2.imencode(
        ".jpg",
        frame_to_upload,
        [int(cv2.IMWRITE_JPEG_QUALITY), int(jpeg_quality)],
    )
    if not ok:
        raise RuntimeError("可视化图像 JPEG 编码失败")

    return post_video_stream_frame(
        dashboard,
        title=title,
        frame_base64=encode_image_bytes_to_base64(buf.tobytes()),
        mime_type="image/jpeg",
        source=source,
        api_paths=api_paths,
    )


def resize_for_upload(frame_bgr: np.ndarray, *, max_width: int, max_height: int) -> np.ndarray:
    h, w = frame_bgr.shape[:2]
    if max_width <= 0 and max_height <= 0:
        return frame_bgr

    scale_w = 1.0 if max_width <= 0 else max_width / max(w, 1)
    scale_h = 1.0 if max_height <= 0 else max_height / max(h, 1)
    scale = min(scale_w, scale_h, 1.0)
    if scale >= 1.0:
        return frame_bgr

    new_w = max(1, int(w * scale))
    new_h = max(1, int(h * scale))
    return cv2.resize(frame_bgr, (new_w, new_h), interpolation=cv2.INTER_AREA)


class VisualizationOutput:
    def __init__(
        self,
        *,
        show: bool,
        window_name: str,
        enable_upload: bool,
        dashboard: str,
        title: str,
        source: str,
        api_paths: list[str],
        jpeg_quality: int,
        upload_max_width: int,
        upload_max_height: int,
    ):
        self.show = show
        self.window_name = window_name
        self.enable_upload = enable_upload
        self.dashboard = dashboard
        self.title = title
        self.source = source
        self.api_paths = api_paths
        self.jpeg_quality = jpeg_quality
        self.upload_max_width = upload_max_width
        self.upload_max_height = upload_max_height

        self.lock = threading.Lock()
        self.stop_event = threading.Event()
        self.frame_ready = threading.Event()
        self.latest_frame = None
        self.frame_seq = 0
        self.last_uploaded_seq = -1
        self.log_counter = 0

    def submit(self, frame_bgr: np.ndarray):
        if not (self.show or self.enable_upload):
            return
        with self.lock:
            self.latest_frame = frame_bgr.copy()
            self.frame_seq += 1
        self.frame_ready.set()

    def request_stop(self):
        self.stop_event.set()
        self.frame_ready.set()

    def run(self):
        last_seen_seq = -1

        try:
            while not self.stop_event.is_set():
                self.frame_ready.wait(timeout=0.1)

                with self.lock:
                    frame = None if self.latest_frame is None else self.latest_frame.copy()
                    frame_seq = self.frame_seq
                    should_clear = frame_seq == last_seen_seq

                if should_clear:
                    self.frame_ready.clear()
                    continue

                if frame is None:
                    self.frame_ready.clear()
                    continue

                if self.show:
                    try:
                        cv2.imshow(self.window_name, frame)
                        if (cv2.waitKey(1) & 0xFF) == ord("q"):
                            print("[Server] 收到 q，关闭可视化并退出。")
                            self.request_stop()
                            break
                    except Exception as e:
                        print(f"[Server] 可视化失败: {e}")

                if self.enable_upload and frame_seq != self.last_uploaded_seq:
                    try:
                        upload_response = upload_visualization_frame(
                            frame,
                            dashboard=self.dashboard,
                            title=self.title,
                            source=self.source,
                            api_paths=self.api_paths,
                            jpeg_quality=self.jpeg_quality,
                            max_width=self.upload_max_width,
                            max_height=self.upload_max_height,
                        )
                        self.last_uploaded_seq = frame_seq
                        if self.log_counter % 30 == 0:
                            uploaded_title = upload_response.get("title", self.title)
                            updated_at = upload_response.get("updated_at", "unknown")
                            print(f"[Server] dashboard pushed {uploaded_title} at {updated_at}")
                        self.log_counter += 1
                    except Exception as e:
                        print(f"[Server] Dashboard 上传失败: {e}")

                last_seen_seq = frame_seq
                with self.lock:
                    if self.frame_seq == frame_seq:
                        self.frame_ready.clear()
        finally:
            if self.show:
                cv2.destroyAllWindows()


class PreviewRecorder:
    def __init__(self, *, show: bool, output_path: str, raw_window="Raw Image", vis_window="SigLIP Vis"):
        self.show = show
        self.output_dir = Path(output_path)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        self.raw_window = raw_window
        self.vis_window = vis_window

        self.lock = threading.Lock()
        self.frame_ready = threading.Event()
        self.stop_event = threading.Event()

        self.latest_raw = None
        self.latest_vis = None
        self.latest_best_category = None

        self.recording = False
        self.writer = None
        self.record_path = None
        self.record_log_path = None
        self.record_log_fp = None
        self.record_fps = 30.0

    def submit(self, raw_frame=None, vis_frame=None, best_category=None):
        if not self.show:
            return
        with self.lock:
            if raw_frame is not None:
                self.latest_raw = raw_frame.copy()
            if vis_frame is not None:
                self.latest_vis = vis_frame.copy()
            self.latest_best_category = None if best_category is None else str(best_category)
        self.frame_ready.set()

    def request_stop(self):
        self.stop_event.set()
        self.frame_ready.set()

    def _start_record(self, raw_frame):
        ts = time.strftime("%Y%m%d_%H%M%S")
        base_name = f"raw_{ts}"
        self.record_path = self.output_dir / f"{base_name}.mp4"
        self.record_log_path = self.output_dir / f"{base_name}.log"

        h, w = raw_frame.shape[:2]
        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        self.writer = cv2.VideoWriter(str(self.record_path), fourcc, self.record_fps, (w, h))
        self.recording = True

        # 同名日志文件
        self.record_log_fp = open(self.record_log_path, "a", encoding="utf-8")
        self.record_log_fp.write(f"# start\t{time.strftime('%Y-%m-%d %H:%M:%S')}\n")
        self.record_log_fp.flush()

        print(f"[Server] 开始录制原图: {self.record_path}")
        print(f"[Server] 开始记录状态: {self.record_log_path}")

    def _stop_record(self):
        if self.writer is not None:
            self.writer.release()
        if self.record_log_fp is not None:
            try:
                self.record_log_fp.write(f"# stop\t{time.strftime('%Y-%m-%d %H:%M:%S')}\n")
                self.record_log_fp.flush()
            finally:
                self.record_log_fp.close()

        if self.record_path is not None:
            print(f"[Server] 停止录制原图: {self.record_path}")
        if self.record_log_path is not None:
            print(f"[Server] 停止记录状态: {self.record_log_path}")

        self.writer = None
        self.record_path = None
        self.record_log_path = None
        self.record_log_fp = None
        self.recording = False

    def run(self):
        try:
            while not self.stop_event.is_set():
                self.frame_ready.wait(timeout=0.1)

                with self.lock:
                    raw = None if self.latest_raw is None else self.latest_raw.copy()
                    vis = None if self.latest_vis is None else self.latest_vis.copy()
                    best_category = self.latest_best_category

                if raw is None and vis is None:
                    self.frame_ready.clear()
                    continue

                if self.show:
                    if raw is not None:
                        cv2.imshow(self.raw_window, raw)
                    if vis is not None:
                        cv2.imshow(self.vis_window, vis)

                    key = cv2.waitKey(1) & 0xFF
                    if key == ord("q"):
                        print("[Server] 收到 q，退出。")
                        self.request_stop()
                        break
                    elif key == ord("r"):
                        if raw is not None:
                            if not self.recording:
                                self._start_record(raw)
                            else:
                                self._stop_record()
                    elif key == ord("s"):
                        if vis is not None:
                            ts = time.strftime("%Y%m%d_%H%M%S")
                            img_path = self.output_dir / f"vis_{ts}.jpg"
                            cv2.imwrite(str(img_path), vis)
                            print(f"[Server] 保存拼接图: {img_path}")

                # 录制中：写视频 + 写日志
                if self.recording and self.writer is not None and raw is not None:
                    try:
                        self.writer.write(raw)
                        if self.record_log_fp is not None:
                            self.record_log_fp.write(
                                f"{time.strftime('%Y-%m-%d %H:%M:%S')}\t{best_category or '-'}\n"
                            )
                            self.record_log_fp.flush()
                    except Exception as e:
                        print(f"[Server] 录制失败: {e}")

                with self.lock:
                    self.frame_ready.clear()
        finally:
            if self.writer is not None:
                self.writer.release()
            if self.record_log_fp is not None:
                try:
                    self.record_log_fp.close()
                except Exception:
                    pass
            if self.show:
                cv2.destroyAllWindows()

def get_single_image_from_request(req: dict[str, Any]) -> Image.Image:
    image_b64 = req.get("image_b64")
    if not image_b64:
        raise ValueError("缺少 image_b64")
    return decode_image_b64_to_pil(image_b64)


def summarize_request(req: dict[str, Any]) -> str:
    request_id = str(req.get("request_id", "")).strip() or "-"
    keys = sorted(list(req.keys()))
    image_b64 = req.get("image_b64")
    image_b64_len = len(image_b64) if isinstance(image_b64, str) else 0
    return f"request_id={request_id}, keys={keys}, image_b64_len={image_b64_len}"


def main():
    args = parse_args()
    output_dir = Path(args.output_path)
    output_dir.mkdir(parents=True, exist_ok=True)

    print("[INIT] 单视角模式")
    print(f"[INIT] 使用设备: {DEVICE}")
    print(f"[INIT] ZMQ 地址: {ZMQ_ADDR}")
    if args.dashboard.strip():
        endpoint_list = [build_dashboard_endpoint(args.dashboard, p) for p in parse_dashboard_paths(args.dashboard_api_path, args.dashboard_api_fallbacks)]
        print(f"[INIT] Dashboard upload candidates -> {endpoint_list}")
        print(
            f"[INIT] Upload image compress -> jpeg_quality={args.jpeg_quality}, "
            f"max_size={args.upload_max_width}x{args.upload_max_height}"
        )

    model, processor = load_single_model()
    print("[INIT] 模型加载完成")
    print(f"[INIT] EMA 平滑: {'开启' if USE_SIM_EMA else '关闭'}"
          + (f", beta={EMA_BETA}" if USE_SIM_EMA else ""))

    centers, state_list = load_centers(GRAPH_INFO_PATH)

    ctx = zmq.Context()
    sock = ctx.socket(zmq.REP)
    sock.setsockopt(zmq.RCVTIMEO, 200)
    sock.bind(ZMQ_ADDR)
    print(f"[ZMQ] Inference Server listening on {ZMQ_ADDR}")

    output_worker = VisualizationOutput(
        show=args.show,
        window_name=args.window_name,
        enable_upload=bool(args.dashboard.strip()),
        dashboard=args.dashboard,
        title=args.stream_title,
        source=args.stream_source,
        api_paths=parse_dashboard_paths(args.dashboard_api_path, args.dashboard_api_fallbacks),
        jpeg_quality=args.jpeg_quality,
        upload_max_width=args.upload_max_width,
        upload_max_height=args.upload_max_height,
    )
    output_thread = None
    if args.show or bool(args.dashboard.strip()):
        output_thread = threading.Thread(target=output_worker.run, daemon=True)
        output_thread.start()

    preview = PreviewRecorder(
        show=args.show,
        output_path=args.output_path,
        raw_window="Raw Image",
        vis_window="SigLIP Vis",
    )
    preview_thread = None
    if args.show:
        preview_thread = threading.Thread(target=preview.run, daemon=True)
        preview_thread.start()

    try:
        request_count = 0
        ema_state = None  # 相似度 EMA 状态，持续累积
        while not preview.stop_event.is_set():
            try:
                req = sock.recv_json()
            except zmq.Again:
                continue

            request_count += 1
            res = {"ok": False}
            image_bgr = None
            start_time = time.perf_counter()
            req_summary = summarize_request(req)
            print(f"[REQ {request_count}] 收到请求: {req_summary}")

            try:
                request_id = str(req.get("request_id", "")).strip()

                image = get_single_image_from_request(req)
                image_bgr = decode_image_b64_to_bgr(req["image_b64"])

                feat_np = encode_image(model, processor, image)
                res, ema_state = calculate_similarity(feat_np, centers, state_list,
                                                      ema_state=ema_state)

                if request_id:
                    res["request_id"] = request_id

            except Exception as e:
                print(f"[Server] 推理失败: {e}")
                res = {"ok": False, "error": str(e)}

            sock.send_json(res)

            if res.get("ok"):
                best_category = str(res.get("best_category", "")).strip() or "unknown"
            else:
                best_category = None

            if args.show and req.get("image_b64"):
                try:
                    if image_bgr is None:
                        image_bgr = decode_image_b64_to_bgr(req["image_b64"])
                    elapsed_ms = (time.perf_counter() - start_time) * 1000.0
                    infer_elapsed = max(elapsed_ms / 1000.0, 1e-6)
                    infer_fps = 1.0 / infer_elapsed
                    combined_vis = build_visualization_frame(image_bgr, res, state_list, fps=infer_fps)
                    preview.submit(
                        raw_frame=image_bgr,
                        vis_frame=combined_vis,
                        best_category=best_category,
                    )
                except Exception as e:
                    print(f"[Server] 生成可视化失败: {e}")
    except KeyboardInterrupt:
        print("\n[Server] 服务端手动停止。")
    finally:
        preview.request_stop()
        if preview_thread is not None:
            preview_thread.join(timeout=1.0)
        output_worker.request_stop()
        if output_thread is not None:
            output_thread.join(timeout=1.0)
        sock.close()
        ctx.term()


if __name__ == "__main__":
    main()
