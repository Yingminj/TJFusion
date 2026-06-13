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

import cv2
import numpy as np
import torch
import yaml
import zmq
from PIL import Image
from torchvision.transforms import functional as F, InterpolationMode


# =============================================================================
# 模型定义（与训练脚本保持一致）
# =============================================================================

class QuickGELU(torch.nn.Module):
    def forward(self, x):
        return x * torch.sigmoid(1.702 * x)


class ResidualAttentionBlock(torch.nn.Module):
    def __init__(self, d_model, n_head, mlp_ratio=4.0):
        super().__init__()
        self.attn = torch.nn.MultiheadAttention(d_model, n_head, batch_first=True)
        self.ln_1 = torch.nn.LayerNorm(d_model)
        self.mlp = torch.nn.Sequential(
            torch.nn.Linear(d_model, int(d_model * mlp_ratio)),
            QuickGELU(),
            torch.nn.Linear(int(d_model * mlp_ratio), d_model),
        )
        self.ln_2 = torch.nn.LayerNorm(d_model)

    def forward(self, x, attn_mask=None):
        attn_out, _ = self.attn(
            self.ln_1(x), self.ln_1(x), self.ln_1(x),
            attn_mask=attn_mask, need_weights=False
        )
        x = x + attn_out
        x = x + self.mlp(self.ln_2(x))
        return x


class LASTViTVisionEncoder(torch.nn.Module):
    """ViT-B/16 + LAST-ViT 频域 token 选择"""
    def __init__(self, embed_dim=512, image_size=224, patch_size=16,
                 width=768, layers=12, heads=12, mlp_ratio=4.0):
        super().__init__()
        self.image_size = image_size
        self.patch_size = patch_size
        self.grid_size = image_size // patch_size
        self.width = width
        scale = width ** -0.5

        self.conv1 = torch.nn.Conv2d(3, width, kernel_size=patch_size, stride=patch_size, bias=False)
        num_patches = self.grid_size * self.grid_size
        self.class_embedding = torch.nn.Parameter(scale * torch.randn(width))
        self.positional_embedding = torch.nn.Parameter(scale * torch.randn(num_patches + 1, width))
        self.ln_pre = torch.nn.LayerNorm(width)
        self.transformer = torch.nn.Sequential(*[
            ResidualAttentionBlock(width, heads, mlp_ratio) for _ in range(layers)
        ])
        self.ln_post = torch.nn.LayerNorm(width)
        self.proj = torch.nn.Parameter(scale * torch.randn(width, embed_dim))
        self.register_buffer('_cached_gaussian', None, persistent=False)

    def _build_gaussian_kernel(self, device):
        w = self.width
        kernel = torch.exp(-0.5 * (torch.arange(-w//2+1, w//2+1, device=device).float() / (w**0.5)) ** 2)
        return (kernel / kernel.max()).unsqueeze(0).unsqueeze(0)

    def forward(self, x):
        x = self.conv1(x)
        B, C, H, W = x.shape
        x = x.reshape(B, C, H*W).permute(0, 2, 1).contiguous()
        cls_token = self.class_embedding.view(1, 1, -1).expand(B, -1, -1)
        x = torch.cat([cls_token, x], dim=1) + self.positional_embedding.unsqueeze(0)
        x = self.ln_pre(x)
        x = self.transformer(x)

        # LAST-ViT: frequency-domain token selection
        if self._cached_gaussian is None or self._cached_gaussian.device != x.device:
            self._cached_gaussian = self._build_gaussian_kernel(x.device)
        x_detach = x[:, 1:]
        x_f = torch.fft.fftshift(torch.fft.fft(x_detach, dim=-1), dim=-1)
        x_smooth = torch.fft.ifft(torch.fft.ifftshift(x_f * self._cached_gaussian, dim=-1), dim=-1).real
        diff = x_detach / torch.abs(x_smooth - x_detach).clamp(min=1e-8)
        _, idx = torch.topk(diff, k=1, dim=1, largest=True)
        x = torch.mean(torch.gather(x_detach, 1, idx), dim=1)
        x = self.ln_post(x)
        return x @ self.proj if self.proj is not None else x


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
    return parser.parse_args()


def load_single_model():
    print(f"[INIT] 构建 LAST-ViT vision encoder...")
    model = LASTViTVisionEncoder(embed_dim=512)

    print(f"[INIT] 加载训练权重: {CHECKPOINT_PATH}")
    checkpoint = torch.load(CHECKPOINT_PATH, map_location="cpu", weights_only=False)
    state_dict = checkpoint.get("model_state_dict", checkpoint)

    # 提取 vision_encoder 的权重
    vis_state_dict = {}
    for k, v in state_dict.items():
        if k.startswith("vision_encoder."):
            vis_state_dict[k[len("vision_encoder."):]] = v

    missing, unexpected = model.load_state_dict(vis_state_dict, strict=False)
    if missing:
        print(f"[WARN] 缺失键: {[k for k in missing if 'cached' not in k][:5]}")
    if unexpected:
        print(f"[WARN] 多余键: {unexpected[:5]}")

    model = model.to(DEVICE)
    model.eval()
    return model


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
        center_raw = n.get("center_feature_lastvit", None)
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


def apply_padding_head(image: Image.Image) -> Image.Image:
    w, h = image.size
    cutoff = int(h * 0.25)
    if cutoff <= 0:
        return image
    pixels = image.load()
    for y in range(cutoff):
        for x in range(w):
            pixels[x, y] = (0, 0, 0)
    return image


def preprocess_image(image: Image.Image, image_size=224):
    """CLIP 标准预处理：Resize → CenterCrop → ToTensor → Normalize"""
    img = F.resize(image, [image_size, image_size], interpolation=InterpolationMode.BICUBIC)
    img = F.to_tensor(img)
    img = F.normalize(img, mean=[0.48145466, 0.4578275, 0.40821073],
                      std=[0.26862954, 0.26130258, 0.27577711])
    return img.unsqueeze(0)  # [1, 3, 224, 224]


@torch.inference_mode()
def encode_image(model, image: Image.Image) -> np.ndarray:
    pixel_values = preprocess_image(image).to(DEVICE)
    feature = model(pixel_values)
    feature = feature / feature.norm(dim=-1, keepdim=True).clamp(min=1e-12)

    feat_np = feature[0].detach().cpu().numpy().astype(np.float32)
    return feat_np


def calculate_similarity(feat_np: np.ndarray, centers: dict, state_list: list):
    sims = {k: float(np.dot(feat_np, v)) for k, v in centers.items()}
    best = max(sims.items(), key=lambda x: x[1])
    topk = sorted(sims.items(), key=lambda x: x[1], reverse=True)[:TOPK]

    return {
        "ok": True,
        "best_category": best[0],
        "best_similarity": best[1],
        "topk": [{"category": k, "similarity": v} for k, v in topk],
        "total_category": state_list
    }


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
    enable_upload = bool(args.dashboard.strip())
    dashboard_api_paths = parse_dashboard_paths(args.dashboard_api_path, args.dashboard_api_fallbacks)
    print("[INIT] 单视角模式")
    print(f"[INIT] 使用设备: {DEVICE}")
    print(f"[INIT] ZMQ 地址: {ZMQ_ADDR}")
    if enable_upload:
        endpoint_list = [build_dashboard_endpoint(args.dashboard, p) for p in dashboard_api_paths]
        print(f"[INIT] Dashboard upload candidates -> {endpoint_list}")
        print(
            f"[INIT] Upload image compress -> jpeg_quality={args.jpeg_quality}, "
            f"max_size={args.upload_max_width}x{args.upload_max_height}"
        )

    model = load_single_model()
    print("[INIT] 模型加载完成")

    centers, state_list = load_centers(GRAPH_INFO_PATH)

    ctx = zmq.Context()
    sock = ctx.socket(zmq.REP)
    sock.setsockopt(zmq.RCVTIMEO, 200)
    sock.bind(ZMQ_ADDR)
    print(f"[ZMQ] Inference Server listening on {ZMQ_ADDR}")

    output_worker = VisualizationOutput(
        show=args.show,
        window_name=args.window_name,
        enable_upload=enable_upload,
        dashboard=args.dashboard,
        title=args.stream_title,
        source=args.stream_source,
        api_paths=dashboard_api_paths,
        jpeg_quality=args.jpeg_quality,
        upload_max_width=args.upload_max_width,
        upload_max_height=args.upload_max_height,
    )
    output_thread = None
    if args.show or enable_upload:
        output_thread = threading.Thread(target=output_worker.run, daemon=True)
        output_thread.start()

    try:
        request_count = 0
        while not output_worker.stop_event.is_set():
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
                image = apply_padding_head(image)
                if args.show:
                    image_bgr = decode_image_b64_to_bgr(req["image_b64"])
                feat_np = encode_image(model, image)
                res = calculate_similarity(feat_np, centers, state_list)

                if request_id:
                    res["request_id"] = request_id

            except Exception as e:
                print(f"[Server] 推理失败: {e}")
                res = {"ok": False, "error": str(e)}

            sock.send_json(res)
            elapsed_ms = (time.perf_counter() - start_time) * 1000.0
            if res.get("ok"):
                best_category = str(res.get("best_category", "")).strip() or "unknown"
                best_similarity = float(res.get("best_similarity", 0.0))
                print(
                    f"[REQ {request_count}] 响应完成: ok=True, category={best_category}, "
                    f"similarity={best_similarity:.4f}, elapsed_ms={elapsed_ms:.2f}"
                )
            else:
                err = str(res.get("error", "unknown"))
                print(f"[REQ {request_count}] 响应完成: ok=False, error={err}, elapsed_ms={elapsed_ms:.2f}")

            if (args.show or enable_upload) and req.get("image_b64"):
                try:
                    if image_bgr is None:
                        image_bgr = decode_image_b64_to_bgr(req["image_b64"])
                    infer_elapsed = max(elapsed_ms / 1000.0, 1e-6)
                    infer_fps = 1.0 / max(infer_elapsed, 1e-6)
                    combined_vis = build_visualization_frame(image_bgr, res, state_list, fps=infer_fps)
                    output_worker.submit(combined_vis)
                except Exception as e:
                    print(f"[Server] 生成可视化失败: {e}")

    except KeyboardInterrupt:
        print("\n[Server] 服务端手动停止。")
    finally:
        output_worker.request_stop()
        if output_thread is not None:
            output_thread.join(timeout=1.0)
        sock.close()
        ctx.term()


if __name__ == "__main__":
    main()
