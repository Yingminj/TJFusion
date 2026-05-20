from __future__ import annotations

import base64
import json
import threading
import time
import uuid
from collections.abc import Callable, MutableMapping
from dataclasses import dataclass, field as _dc_field
from pathlib import Path
from typing import Any

try:
    import zmq
except ImportError:  # pragma: no cover - exercised at runtime when dependency is absent
    zmq = None

from fusion_docker.console import print_error, print_status, print_success, print_warning
from fusion_docker.models import BridgeInputMapping, BridgeServiceConfig, ModelNode

try:
    import cv2  # type: ignore[import-not-found]
except ImportError:  # pragma: no cover - exercised at runtime when dependency is absent
    cv2 = None

try:
    import numpy as np  # type: ignore[import-not-found]
except ImportError:  # pragma: no cover - exercised at runtime when dependency is absent
    np = None


def encode_png_base64(img: Any) -> str:
    cv2_module, _ = _require_image_dependencies()
    ok, buf = cv2_module.imencode(".png", img)
    if not ok:
        raise RuntimeError("Failed to encode PNG image.")
    return base64.b64encode(buf.tobytes()).decode("utf-8")


def encode_jpg_bytes(img: Any, quality: int = 85) -> bytes:
    cv2_module, _ = _require_image_dependencies()
    ok, buf = cv2_module.imencode(
        ".jpg",
        img,
        [int(cv2_module.IMWRITE_JPEG_QUALITY), int(quality)],
    )
    if not ok:
        raise RuntimeError("Failed to encode JPG image.")
    return buf.tobytes()


def encode_jpg_base64(img: Any, quality: int = 85) -> str:
    jpg_bytes = encode_jpg_bytes(img, quality=quality)
    return base64.b64encode(jpg_bytes).decode("utf-8")


def decode_b64_image_to_np(image_b64: str, flags: int | None = None) -> Any:
    cv2_module, np_module = _require_image_dependencies()
    effective_flags = cv2_module.IMREAD_UNCHANGED if flags is None else flags
    raw = base64.b64decode(image_b64)
    arr = np_module.frombuffer(raw, dtype=np_module.uint8)
    img = cv2_module.imdecode(arr, effective_flags)
    if img is None:
        raise RuntimeError("Failed to decode base64 image.")
    return img


def print_response(response: dict[str, Any], *, verbose: bool = False, title: str = "RESPONSE") -> None:
    request_id = response.get("request_id", "unknown")
    print_status(title, f"request_id={request_id}", color="magenta")
    if verbose:
        print(json.dumps(response, indent=2, ensure_ascii=False))
    else:
        status = response.get("status", "unknown")
        elapsed = response.get("elapsed_sec", "N/A")
        print_status(title, f"status={status}, elapsed_sec={elapsed}", color="blue")


def _truncate_text(raw: str, limit: int = 280) -> str:
    text = str(raw).replace("\n", "\\n")
    if len(text) <= limit:
        return text
    return text[: limit - 3] + "..."

def _zmq_source_format_hint() -> str:
    return (
        "Expected ZMQ source payload (base64 preferred): "
        "single-part JSON {'rgb_image':'<base64>', 'depth_image':'<base64>'} "
        "or multipart [meta_json_bytes, color_bytes, depth_bytes] "
        "with optional meta {'color_encoding':'base64','depth_encoding':'base64'} "
        "or legacy raw depth via meta {'depth_shape':[H,W]}."
    )

def _summarize_external_request_payload(payload: Any) -> str:
    if not isinstance(payload, dict):
        return f"type={type(payload).__name__}"
    mapping = BridgeInputMapping()
    rgb = _extract_image_field(payload, mapping.rgb_keys)
    depth = _extract_image_field(
        payload,
        tuple(dict.fromkeys((*mapping.depth_keys, *mapping.depth_raw_keys))),
    )
    keys = sorted(str(key) for key in payload.keys())
    request_id = payload.get("request_id", "unknown")
    return (
        f"keys={keys}, request_id={request_id}, "
        f"rgb_image_len={len(str(rgb))}, depth_image_len={len(str(depth))}"
    )


def _summarize_zmq_meta(meta: Any) -> str:
    if not isinstance(meta, dict):
        return f"meta_type={type(meta).__name__}"
    keys = sorted(str(key) for key in meta.keys())
    depth_shape = meta.get("depth_shape", "missing")
    frame_id = meta.get("frame_id", "unknown")
    return f"keys={keys}, frame_id={frame_id}, depth_shape={depth_shape}"

def _log_zmq_input_error(exc: Exception, *, meta: Any = None) -> None:
    print_error(f"{exc}")
    print_status(
        "INPUT",
        f"received_summary={_summarize_zmq_meta(meta)}",
        color="yellow",
    )
    print_status("FORMAT", _zmq_source_format_hint(), color="yellow")


def _extract_prompts_from_source_meta(
    source_meta: Any,
    *,
    fallback_prompts: list[str] | None = None,
    required: bool,
) -> list[str]:
    fallback = [str(item).strip() for item in (fallback_prompts or []) if str(item).strip()]
    if not isinstance(source_meta, dict):
        if fallback:
            return fallback
        if required:
            raise RuntimeError("Missing prompts in source payload.")
        return []

    raw_prompts = source_meta.get("prompts")
    if raw_prompts is None:
        if fallback:
            return fallback
        if required:
            raise RuntimeError("Missing prompts in source payload.")
        return []
    if not isinstance(raw_prompts, list):
        raise RuntimeError("Source payload field 'prompts' must be a list of strings.")

    prompts = [str(item).strip() for item in raw_prompts if str(item).strip()]
    if prompts:
        return prompts
    if fallback:
        return fallback
    if required and not prompts:
        raise RuntimeError("Source payload field 'prompts' is empty.")
    return prompts


def _extract_image_field(payload: dict[str, Any], keys: tuple[str, ...]) -> str:
    for key in keys:
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value
    return ""


def _candidate_payloads_for_rgbd(
    request_data: dict[str, Any],
    nested_payload_keys: tuple[str, ...],
) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = [request_data]
    for key in nested_payload_keys:
        nested = request_data.get(key)
        if isinstance(nested, dict):
            candidates.append(nested)
    return candidates


def _extract_depth_shape(
    payload: dict[str, Any],
    root: dict[str, Any],
    mapping: BridgeInputMapping,
) -> tuple[int, int] | None:
    for holder in (
        payload,
        payload.get("meta"),
        root,
        root.get("meta"),
    ):
        if not isinstance(holder, dict):
            continue

        for shape_key in mapping.depth_shape_keys:
            raw_shape = holder.get(shape_key)
            if isinstance(raw_shape, (list, tuple)) and len(raw_shape) >= 2:
                try:
                    h = int(raw_shape[0])
                    w = int(raw_shape[1])
                except Exception:
                    h = w = 0
                if h > 0 and w > 0:
                    return (h, w)

        for height_key in mapping.depth_height_keys:
            for width_key in mapping.depth_width_keys:
                raw_h = holder.get(height_key)
                raw_w = holder.get(width_key)
                try:
                    h = int(raw_h)
                    w = int(raw_w)
                except Exception:
                    h = w = 0
                if h > 0 and w > 0:
                    return (h, w)
    return None


def _bridge_base64_images_payload(
    *,
    rgb_b64: str,
    depth_b64: str,
    combined_mask_b64: str = "",
) -> dict[str, Any]:
    return {
        "rgb_image": rgb_b64,
        "depth_image": depth_b64,
        "combined_mask": combined_mask_b64,
        "image_encoding": {
            "rgb_image": "jpg_base64",
            "depth_image": "png_base64",
            "combined_mask": "png_base64",
        },
    }

def _build_model_result(
    *,
    name: str,
    enabled: bool,
    ok: bool,
    summary: str,
    payload: dict[str, Any] | None,
    elapsed_sec: float | None = None,
) -> dict[str, Any]:
    item: dict[str, Any] = {
        "name": name,
        "enabled": enabled,
        "ok": ok,
        "summary": summary,
    }
    if elapsed_sec is not None:
        item["elapsed_sec"] = round(float(elapsed_sec), 4)
    if payload is not None:
        item["payload"] = payload
    return item


def _print_model_result_line(request_id: str, model_key: str, result: dict[str, Any]) -> None:
    status_text = "ok" if result.get("ok") else "error"
    summary = str(result.get("summary", ""))
    elapsed = result.get("elapsed_sec")
    elapsed_text = f", elapsed={elapsed:.3f}s" if isinstance(elapsed, (int, float)) else ""
    color = "green" if result.get("ok") else "yellow"
    print_status(
        "MODEL",
        f"{request_id} | {model_key}={status_text}{elapsed_text} | {summary}",
        color=color,
    )


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default

def build_instance_names(class_names: list[str]) -> list[str]:
    # FlowPose only needs human-readable labels here; obj_ids already carry instance identity.
    return [str(class_name) for class_name in class_names]

def decode_mask_item(mask_item: Any, h: int, w: int) -> Any:
    cv2_module, np_module = _require_image_dependencies()

    if isinstance(mask_item, str):
        mask = decode_b64_image_to_np(mask_item, cv2_module.IMREAD_GRAYSCALE)
    elif np_module is not None and isinstance(mask_item, np_module.ndarray):
        mask = mask_item
    elif isinstance(mask_item, list):
        mask = np_module.array(mask_item)
    elif isinstance(mask_item, dict):
        for key in ("mask", "segmentation", "binary_mask"):
            if key in mask_item:
                return decode_mask_item(mask_item[key], h, w)
        raise ValueError(f"Unsupported mask item dict keys: {list(mask_item.keys())}")
    else:
        raise ValueError(f"Unsupported mask item type: {type(mask_item)}")

    if mask.ndim == 3:
        mask = mask[..., 0]

    if mask.shape[:2] != (h, w):
        mask = cv2_module.resize(mask.astype(np_module.uint8), (w, h), interpolation=cv2_module.INTER_NEAREST)

    if mask.dtype == np_module.bool_:
        mask = mask.astype(np_module.uint8) * 255
    elif mask.dtype != np_module.uint8:
        mask = (mask > 0).astype(np_module.uint8) * 255

    return mask

def make_req_socket(context: Any, addr: str, timeout_ms: int) -> Any:
    _require_zmq()
    sock = context.socket(zmq.REQ)
    sock.setsockopt(zmq.RCVTIMEO, timeout_ms)
    sock.setsockopt(zmq.SNDTIMEO, timeout_ms)
    sock.setsockopt(zmq.LINGER, 0)
    sock.connect(addr)
    return sock

def safe_close_socket(sock: Any | None) -> None:
    if sock is None:
        return
    try:
        sock.close(0)
    except Exception:
        pass

def decode_external_json_rgbd_message(
    message_str: str,
    input_mapping: BridgeInputMapping | None = None,
) -> tuple[Any, Any, dict[str, Any]]:
    cv2_module, np_module = _require_image_dependencies()
    mapping = input_mapping or BridgeInputMapping()
    request_data = json.loads(message_str)
    if not isinstance(request_data, dict):
        raise RuntimeError("External request JSON root must be an object.")

    last_summary = _summarize_external_request_payload(request_data)
    for payload in _candidate_payloads_for_rgbd(
        request_data,
        nested_payload_keys=mapping.nested_payload_keys,
    ):
        rgb_b64 = _extract_image_field(
            payload,
            mapping.rgb_keys,
        )
        depth_b64 = _extract_image_field(
            payload,
            mapping.depth_keys,
        )
        depth_raw_b64 = _extract_image_field(
            payload,
            mapping.depth_raw_keys,
        )
        last_summary = _summarize_external_request_payload(payload)

        if rgb_b64 and depth_b64:
            rgb = decode_b64_image_to_np(rgb_b64, cv2_module.IMREAD_COLOR)
            depth = decode_b64_image_to_np(depth_b64, cv2_module.IMREAD_ANYDEPTH)
            if rgb is None or depth is None:
                raise RuntimeError("Failed to decode external base64 rgb/depth images.")
            return rgb, depth, request_data

        if rgb_b64 and depth_raw_b64:
            depth_shape = _extract_depth_shape(payload, request_data, mapping)
            if depth_shape is None:
                raise RuntimeError(
                    "Found depth_raw_base64 but missing depth_shape "
                    "(or depth_height/depth_width)."
                )
            raw = base64.b64decode(depth_raw_b64)
            depth_flat = np_module.frombuffer(raw, dtype=np_module.uint16)
            expected = int(depth_shape[0] * depth_shape[1])
            if depth_flat.size != expected:
                raise RuntimeError(
                    f"depth_raw size mismatch: got={depth_flat.size}, expected={expected}, "
                    f"shape={depth_shape}"
                )
            rgb = decode_b64_image_to_np(rgb_b64, cv2_module.IMREAD_COLOR)
            depth = depth_flat.reshape(depth_shape)
            request_data.setdefault("depth_shape", [depth_shape[0], depth_shape[1]])
            return rgb, depth, request_data

    raise RuntimeError(
        "Missing base64 image fields. Required rgb/depth images. "
        f"Parsed summary: {last_summary}"
    )


def recv_external_json_rgbd(rep_socket: Any) -> tuple[Any, Any, dict[str, Any]]:
    message_str = rep_socket.recv_string()
    return decode_external_json_rgbd_message(message_str)


class LatestFrameBuffer:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.rgb: Any | None = None
        self.depth: Any | None = None
        self.meta: dict[str, Any] | None = None
        self.frame_id = 0
        self.timestamp = 0.0

    def update(self, rgb: Any, depth: Any, meta: dict[str, Any] | None = None) -> None:
        with self._lock:
            self.rgb = rgb
            self.depth = depth
            self.meta = meta
            self.frame_id += 1
            self.timestamp = time.time()

    def get(self) -> tuple[Any | None, Any | None, dict[str, Any] | None, int, float]:
        with self._lock:
            if self.rgb is None or self.depth is None:
                return None, None, None, -1, 0.0
            return (
                self.rgb.copy(),
                self.depth.copy(),
                dict(self.meta or {}),
                self.frame_id,
                self.timestamp,
            )


def recv_zmq_rgbd(
    sub_socket: Any,
    timeout_sec: float = 3.0,
    input_mapping: BridgeInputMapping | None = None,
) -> tuple[Any, Any, dict[str, Any]]:
    cv2_module, np_module = _require_image_dependencies()
    zmq_module = _require_zmq()
    mapping = input_mapping or BridgeInputMapping()
    poller = zmq_module.Poller()
    poller.register(sub_socket, zmq_module.POLLIN)

    events = dict(poller.poll(int(timeout_sec * 1000)))
    if sub_socket not in events:
        raise RuntimeError(f"Timeout waiting for ZMQ RGB-D data ({timeout_sec}s).")

    latest_parts: list[bytes] | None = None
    parts = sub_socket.recv_multipart()
    if len(parts) in {1, 2, 3}:
        latest_parts = parts

    while True:
        try:
            parts = sub_socket.recv_multipart(flags=zmq_module.NOBLOCK)
        except zmq_module.Again:
            break
        if len(parts) in {1, 2, 3}:
            latest_parts = parts

    if latest_parts is None:
        raise RuntimeError("Invalid ZMQ source message.")

    if len(latest_parts) == 1:
        try:
            message_str = latest_parts[0].decode("utf-8")
        except Exception as exc:
            raise RuntimeError(f"Single-part ZMQ payload is not UTF-8 JSON: {exc}") from exc
        try:
            rgb, depth, request_data = decode_external_json_rgbd_message(
                message_str,
                input_mapping=mapping,
            )
        except Exception as exc:
            summary = ""
            try:
                parsed = json.loads(message_str)
                summary = _summarize_external_request_payload(parsed)
            except Exception:
                summary = _truncate_text(message_str, limit=180)
            raise RuntimeError(f"{exc} | zmq_json_summary={summary}") from exc
        request_data.setdefault("source_format", "zmq_json_base64")
        return rgb, depth, request_data

    if len(latest_parts) == 2:
        decode_errors: list[str] = []
        for idx in (1, 0):
            part = latest_parts[idx]
            try:
                message_str = part.decode("utf-8")
                rgb, depth, request_data = decode_external_json_rgbd_message(
                    message_str,
                    input_mapping=mapping,
                )
                request_data.setdefault("source_format", "zmq_topic_json_base64")
                return rgb, depth, request_data
            except Exception as exc:
                decode_errors.append(f"part{idx}: {exc}")
        raise RuntimeError(
            "Unsupported 2-part ZMQ payload. Expected [topic, json_payload]. "
            + " | ".join(decode_errors)
        )

    if len(latest_parts) != 3:
        raise RuntimeError("Invalid ZMQ RGB-D message format.")

    meta_bytes, color_bytes, depth_bytes = latest_parts
    meta = json.loads(meta_bytes.decode("utf-8"))
    if not isinstance(meta, dict):
        raise RuntimeError("ZMQ RGB-D meta must be a JSON object.")

    color_encoding = str(meta.get("color_encoding", "")).strip().lower()
    if color_encoding in {"base64", "b64", "jpg_base64", "jpeg_base64", "png_base64"}:
        rgb = decode_b64_image_to_np(color_bytes.decode("utf-8"), cv2_module.IMREAD_COLOR)
    else:
        color_np = np_module.frombuffer(color_bytes, dtype=np_module.uint8)
        rgb = cv2_module.imdecode(color_np, cv2_module.IMREAD_COLOR)
        if rgb is None:
            raise RuntimeError("Failed to decode ZMQ RGB image.")

    # New Fast-Foundation source may publish a corrected 2x2 stitched image.
    # When so, downstream Sam3/FlowPose should consume left_eye (top-left) as RGB input.
    color_layout = str(meta.get("color_layout", "")).strip().lower()
    if color_layout in {"quad_2x2", "2x2", "quad"}:
        left_eye = None

        left_eye_rect = meta.get("left_eye_rect")
        if isinstance(left_eye_rect, (list, tuple)) and len(left_eye_rect) >= 4:
            try:
                x = int(left_eye_rect[0])
                y = int(left_eye_rect[1])
                w = int(left_eye_rect[2])
                h = int(left_eye_rect[3])
            except Exception:
                x = y = w = h = 0

            if w > 0 and h > 0 and x >= 0 and y >= 0 and x + w <= rgb.shape[1] and y + h <= rgb.shape[0]:
                left_eye = rgb[y:y + h, x:x + w]

        if left_eye is None:
            single_view_shape = meta.get("single_view_shape")
            if isinstance(single_view_shape, (list, tuple)) and len(single_view_shape) >= 2:
                try:
                    h = int(single_view_shape[0])
                    w = int(single_view_shape[1])
                except Exception:
                    h = w = 0
                if h > 0 and w > 0 and h <= rgb.shape[0] and w <= rgb.shape[1]:
                    left_eye = rgb[0:h, 0:w]

        if left_eye is None:
            half_h = rgb.shape[0] // 2
            half_w = rgb.shape[1] // 2
            if half_h > 0 and half_w > 0:
                left_eye = rgb[0:half_h, 0:half_w]

        if left_eye is not None and left_eye.size > 0:
            rgb = left_eye
            meta["rgb_selected_view"] = "left_eye"

    depth_encoding = str(meta.get("depth_encoding", "")).strip().lower()
    if depth_encoding in {"base64", "b64", "png_base64", "depth_png_base64"}:
        depth = decode_b64_image_to_np(depth_bytes.decode("utf-8"), cv2_module.IMREAD_ANYDEPTH)
    else:
        depth_shape_raw = meta.get("depth_shape")
        if not isinstance(depth_shape_raw, list | tuple) or len(depth_shape_raw) < 2:
            raise RuntimeError("ZMQ meta missing valid 'depth_shape'.")

        depth_shape = tuple(int(item) for item in depth_shape_raw[:2])
        depth = np_module.frombuffer(depth_bytes, dtype=np_module.uint16).reshape(depth_shape)
    return rgb, depth, meta


def zmq_capture_loop(
    sub_socket: Any,
    frame_buffer: LatestFrameBuffer,
    timeout_sec: float,
    stop_flag: MutableMapping[str, bool],
    input_mapping: BridgeInputMapping | None = None,
) -> None:
    last_error_log_ts = 0.0
    while not stop_flag.get("stop", False):
        try:
            rgb, depth, meta = recv_zmq_rgbd(
                sub_socket,
                timeout_sec=timeout_sec,
                input_mapping=input_mapping,
            )
            frame_buffer.update(rgb, depth, meta)
        except Exception as exc:
            now = time.time()
            # Avoid flooding logs when source stream is unavailable or malformed.
            if now - last_error_log_ts >= 2.0:
                _log_zmq_input_error(exc, meta=None)
                last_error_log_ts = now
            time.sleep(0.01)


def build_empty_response(
    request_id: str,
    start_time: float,
    *,
    rgb_b64: str,
    depth_b64: str,
) -> dict[str, Any]:
    payload = {
        "status": "ok",
        "request_id": request_id,
        "objects": [],
        "elapsed_sec": round(time.time() - start_time, 4),
    }
    payload.update(
        _bridge_base64_images_payload(
            rgb_b64=rgb_b64,
            depth_b64=depth_b64,
            combined_mask_b64="",
        )
    )
    return payload


@dataclass
class _PipelineContext:
    """Shared mutable state passed to every model handler."""

    rgb: Any
    depth: Any
    rgb_jpg_bytes: bytes
    rgb_b64: str
    depth_b64: str
    prompts: list[str]
    source_meta: dict[str, Any]
    request_id: str
    start_time: float
    obj_ids: list[Any]
    obj_id_map: dict[str, int | str]
    return_masks: bool
    clear_previous: bool
    store: dict[str, Any]
    output_keys: list[str]
    node_index: dict[str, ModelNode]
    model_results: dict[str, dict[str, Any]] = _dc_field(default_factory=dict)
    intermediate: dict[str, Any] = _dc_field(default_factory=dict)


# --------------- Handler registry ---------------

def _get_by_path(payload: Any, path: Any) -> Any:
    if path is None:
        return None
    if isinstance(path, list):
        current = payload
        for key in path:
            if not isinstance(current, dict):
                return None
            current = current.get(str(key))
        return current
    if isinstance(path, str):
        if not path:
            return None
        current = payload
        for key in path.split("."):
            if not isinstance(current, dict):
                return None
            current = current.get(key)
        return current
    return None


def _resolve_value_from_store(store: dict[str, Any], spec: Any) -> Any:
    if isinstance(spec, dict) and "value" in spec:
        return spec["value"]
    if isinstance(spec, str):
        key = spec[1:] if spec.startswith("$") else spec
        return store.get(key)
    return spec


def _resolve_output_keys(pipeline: list[ModelNode], output_keys: list[str]) -> list[str]:
    if output_keys:
        return output_keys
    derived: list[str] = []
    seen: set[str] = set()
    for node in pipeline:
        for key in node.outputs:
            if key and key not in seen:
                derived.append(key)
                seen.add(key)
        for key in node.response_map.keys():
            if key and key not in seen:
                derived.append(key)
                seen.add(key)
    return derived


def _pipeline_requires_key(pipeline: list[ModelNode], key: str) -> bool:
    for node in pipeline:
        if key in node.inputs:
            return True
        for spec in node.request_map.values():
            if isinstance(spec, str) and spec.lstrip("$") == key:
                return True
    return False


def _generic_build_request(node: ModelNode, ctx: _PipelineContext) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    if node.inputs:
        missing = [key for key in node.inputs if key not in ctx.store]
        if missing:
            raise RuntimeError(f"Missing inputs for {node.name}: {missing}")
    if node.request_map:
        for key, spec in node.request_map.items():
            payload[key] = _resolve_value_from_store(ctx.store, spec)
    elif node.inputs:
        for key in node.inputs:
            payload[key] = ctx.store.get(key)
    return payload


def _generic_on_result(response: Any, node: ModelNode, ctx: _PipelineContext) -> None:
    if isinstance(response, dict):
        if node.response_map:
            for ctx_key, path in node.response_map.items():
                ctx.store[ctx_key] = _get_by_path(response, path)
        elif node.outputs:
            for key in node.outputs:
                if key in response:
                    ctx.store[key] = response[key]
        ctx.store[f"{node.name}_response"] = response
        ok = bool(response.get("ok", response.get("status") == "ok"))
        summary = f"response_keys={list(response.keys())}"
    else:
        ok = False
        summary = f"unexpected response type: {type(response).__name__}"
    ctx.model_results[node.name] = _build_model_result(
        name=node.name,
        enabled=True,
        ok=ok,
        summary=summary,
        payload={"kind": node.kind},
    )


def _generic_on_error(error: Exception, node: ModelNode, ctx: _PipelineContext) -> None:
    ctx.model_results[node.name] = _build_model_result(
        name=node.name,
        enabled=True,
        ok=False,
        summary=f"error: {error}",
        payload={"kind": node.kind, "error": str(error)},
    )


ADAPTER_REGISTRY: dict[str, dict[str, Callable]] = {
    "generic": {
        "build_request": _generic_build_request,
        "on_result": _generic_on_result,
        "on_error": _generic_on_error,
    },
}

# --------------- DAG executor ---------------

def _topological_layers(
    pipeline: list[ModelNode],
) -> list[list[ModelNode]]:
    """Group pipeline nodes into execution layers.

    Nodes in the same layer have no dependencies on each other and can
    run concurrently.  Layers are executed sequentially so that a later
    layer only starts after all earlier layers have completed.
    """
    completed: set[str] = set()
    layers: list[list[ModelNode]] = []
    name_set = {n.name for n in pipeline}

    while len(completed) < len(pipeline):
        layer = [
            n
            for n in pipeline
            if n.name not in completed
            and all(d in completed or d not in name_set for d in n.depends_on)
        ]
        if not layer:
            layer = [n for n in pipeline if n.name not in completed]
        layers.append(layer)
        completed.update(n.name for n in layer)

    return layers

def _run_single_model(
    node: ModelNode,
    zmq_context: Any,
    ctx: _PipelineContext,
    default_timeout_ms: int,
) -> None:
    """Invoke one model node via ZMQ REQ and dispatch to its handler."""
    adapter = ADAPTER_REGISTRY.get(node.kind, ADAPTER_REGISTRY["generic"])

    zmq_module = _require_zmq()
    timeout_ms = node.timeout_ms or default_timeout_ms

    try:
        request_payload = adapter["build_request"](node, ctx)
        socket = make_req_socket(zmq_context, node.endpoint, timeout_ms)
        try:
            socket.send_json(request_payload)
            response = socket.recv_json()
        except zmq_module.error.Again as exc:
            raise TimeoutError(
                f"{node.name} request timeout after {timeout_ms} ms"
            ) from exc
        finally:
            safe_close_socket(socket)
        adapter["on_result"](response, node, ctx)
    except Exception as exc:
        adapter.get("on_error", _generic_on_error)(exc, node, ctx)


def _execute_pipeline(
    pipeline: list[ModelNode],
    zmq_context: Any,
    ctx: _PipelineContext,
    default_timeout_ms: int,
) -> None:
    """Execute the full model pipeline respecting dependency ordering."""
    if not pipeline:
        return

    layers = _topological_layers(pipeline)
    failed: set[str] = set()

    for layer in layers:
        threads: list[tuple[str, threading.Thread]] = []

        for node in layer:
            if any(d in failed for d in node.depends_on):
                adapter = ADAPTER_REGISTRY.get(node.kind, ADAPTER_REGISTRY["generic"])
                adapter.get("on_error", _generic_on_error)(
                    RuntimeError("skipped: dependency failed"), node, ctx
                )
                failed.add(node.name)
                continue

            t = threading.Thread(
                target=_run_single_model,
                args=(node, zmq_context, ctx, default_timeout_ms),
                daemon=True,
            )
            threads.append((node.name, t))
            t.start()

        for _name, t in threads:
            t.join(timeout=30.0)

        # Mark any thread that didn't produce a successful result as failed.
        for name, _t in threads:
            result = ctx.model_results.get(name)
            if result is None or not result.get("ok", False):
                failed.add(name)


def _assemble_pipeline_response(ctx: _PipelineContext) -> dict[str, Any]:
    """Build the final response dict from pipeline context."""
    response = {
        "status": "ok",
        "request_id": ctx.request_id,
        "elapsed_sec": round(time.time() - ctx.start_time, 4),
    }
    for key in ctx.output_keys:
        if key in ctx.store:
            response[key] = ctx.store[key]

    response["bridge_elapsed_sec"] = round(time.time() - ctx.start_time, 4)
    response["model_results"] = dict(ctx.model_results)
    response["pipeline"] = {
        node_name: {
            "enabled": node.enabled,
            "kind": node.kind,
            "ok": bool(ctx.model_results.get(node_name, {}).get("ok", False)),
        }
        for node_name, node in ctx.node_index.items()
    }

    return response


def _process_once_pipeline(
    *,
    pipeline: list[ModelNode],
    zmq_context: Any,
    rgb: Any,
    depth: Any,
    prompts: list[str],
    source_meta: dict[str, Any] | None,
    rgb_jpg_quality: int,
    req_timeout_ms: int,
    obj_ids: list[Any] | None,
    obj_id_map: dict[str, int | str] | None,
    output_json: str | None,
    verbose: bool,
    return_masks: bool,
    clear_previous: bool,
    output_keys: list[str],
) -> dict[str, Any]:
    """Pipeline-based variant of :func:`process_once`.

    This replaces the hard-coded model sequence with a generic DAG
    executor that respects ``depends_on`` ordering and runs independent
    nodes in parallel.
    """
    request_id = str(uuid.uuid4())
    start_time = time.time()
    _require_image_dependencies()

    rgb_jpg_bytes = encode_jpg_bytes(rgb, quality=rgb_jpg_quality)
    rgb_b64 = base64.b64encode(rgb_jpg_bytes).decode("utf-8")

    # Only encode depth if at least one node needs it.
    needs_depth = any(
        n.name in ("sam3", "flowpose", "flowpose_sidecar") for n in pipeline
    )
    depth_b64 = encode_png_base64(depth) if needs_depth else ""

    store: dict[str, Any] = {
        "request_id": request_id,
        "rgb": rgb,
        "depth": depth,
        "rgb_b64": rgb_b64,
        "depth_b64": depth_b64,
        "rgb_image": rgb_b64,
        "depth_image": depth_b64,
        "prompts": prompts,
        "source_meta": source_meta or {},
        "obj_ids": obj_ids or [],
        "obj_id_map": obj_id_map or {},
    }
    resolved_output_keys = _resolve_output_keys(pipeline, output_keys)
    node_index = {node.name: node for node in pipeline}

    ctx = _PipelineContext(
        rgb=rgb,
        depth=depth,
        rgb_jpg_bytes=rgb_jpg_bytes,
        rgb_b64=rgb_b64,
        depth_b64=depth_b64,
        prompts=prompts,
        source_meta=source_meta or {},
        request_id=request_id,
        start_time=start_time,
        obj_ids=obj_ids or [],
        obj_id_map=obj_id_map or {},
        return_masks=return_masks,
        clear_previous=clear_previous,
        store=store,
        output_keys=resolved_output_keys,
        node_index=node_index,
    )

    _execute_pipeline(pipeline, zmq_context, ctx, req_timeout_ms)

    response = _assemble_pipeline_response(ctx)

    if verbose:
        print_response(response, verbose=True, title="PIPELINE")

    if output_json:
        output_path = Path(output_json).expanduser()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with output_path.open("w", encoding="utf-8") as handle:
            json.dump(response, handle, indent=2, ensure_ascii=False)

    for model_key, result in ctx.model_results.items():
        _print_model_result_line(request_id, model_key, result)

    return response


def process_once(
    *,
    pipeline: list[ModelNode],
    zmq_context: Any,
    rgb: Any,
    depth: Any,
    prompts: list[str],
    obj_ids: list[Any] | None,
    obj_id_map: dict[str, int | str] | None,
    req_timeout_ms: int,
    return_masks: bool,
    clear_previous: bool,
    output_json: str | None,
    verbose: bool,
    rgb_jpg_quality: int,
    source_meta: dict[str, Any] | None,
    output_keys: list[str],
) -> dict[str, Any]:
    if not pipeline:
        raise RuntimeError("Custom pipeline bridge requires a non-empty pipeline list.")
    return _process_once_pipeline(
        pipeline=pipeline,
        zmq_context=zmq_context,
        rgb=rgb,
        depth=depth,
        prompts=prompts,
        source_meta=source_meta,
        rgb_jpg_quality=rgb_jpg_quality,
        req_timeout_ms=req_timeout_ms,
        obj_ids=obj_ids,
        obj_id_map=obj_id_map,
        output_json=output_json,
        verbose=verbose,
        return_masks=return_masks,
        clear_previous=clear_previous,
        output_keys=output_keys,
    )


def run_zmq_source_bridge_service(
    config: BridgeServiceConfig,
    *,
    verbose: bool = False,
    save_json: bool = False,
    result_callback: Callable[[dict[str, Any]], None] | None = None,
) -> None:
    _require_image_dependencies()
    zmq_module = _require_zmq()

    if not config.zmq_source_addr:
        raise ValueError("ZMQ source bridge requires bridge.zmq_source_addr.")

    effective_pipeline = [n for n in config.pipeline if n.enabled]
    if not effective_pipeline:
        raise ValueError("custom_pipeline requires a non-empty bridge.pipeline list.")
    requires_prompts = _pipeline_requires_key(effective_pipeline, "prompts")

    output_json = config.output_json if save_json else None
    context = zmq_module.Context()
    sam3_timeout_ms = int(config.sam3_timeout_ms or config.req_timeout_ms)
    flowpose_timeout_ms = int(config.req_timeout_ms)

    source_socket = context.socket(zmq_module.SUB)
    source_socket.setsockopt(zmq_module.RCVHWM, 1)
    source_socket.setsockopt(zmq_module.LINGER, 0)
    source_socket.connect(config.zmq_source_addr)
    source_socket.setsockopt(zmq_module.SUBSCRIBE, b"")

    frame_buffer = LatestFrameBuffer()
    stop_flag: dict[str, bool] = {"stop": False}
    capture_thread = threading.Thread(
        target=zmq_capture_loop,
        args=(
            source_socket,
            frame_buffer,
            config.zmq_timeout_sec,
            stop_flag,
            config.input_mapping,
        ),
        daemon=True,
    )
    capture_thread.start()

    print_status("BRIDGE", f"Pipeline nodes   : {len(effective_pipeline)}", color="cyan")
    print_status("BRIDGE", f"ZMQ source       : {config.zmq_source_addr}", color="cyan")
    print_status("BRIDGE", f"SAM3 timeout     : {sam3_timeout_ms} ms", color="cyan")
    print_status("BRIDGE", f"FlowPose timeout : {flowpose_timeout_ms} ms", color="cyan")
    print_status("BRIDGE", f"ZMQ timeout      : {config.zmq_timeout_sec:.2f} s", color="cyan")
    print_status("WAIT", "Waiting latest ZMQ RGB-D frames...", color="yellow")

    last_processed_frame_id = -1

    try:
        while True:
            rgb, depth, meta, frame_id, frame_ts = frame_buffer.get()
            if rgb is None or depth is None or frame_id < 0:
                time.sleep(0.01)
                continue

            if frame_id == last_processed_frame_id:
                time.sleep(0.002)
                continue

            last_processed_frame_id = frame_id
            frame_age_ms = max((time.time() - frame_ts) * 1000.0, 0.0)
            print_status(
                "PROCESS",
                f"frame_id={frame_id}, age={frame_age_ms:.1f} ms",
                color="blue",
            )

            try:
                prompts = _extract_prompts_from_source_meta(
                    meta,
                    fallback_prompts=config.prompts,
                    required=requires_prompts,
                )
                result = process_once(
                    rgb=rgb,
                    depth=depth,
                    prompts=prompts,
                    obj_ids=config.obj_ids,
                    obj_id_map=config.obj_id_map,
                    req_timeout_ms=config.req_timeout_ms,
                    return_masks=config.return_masks,
                    clear_previous=config.clear_previous,
                    output_json=output_json,
                    verbose=verbose,
                    rgb_jpg_quality=config.rgb_jpg_quality,
                    source_meta=meta,
                    pipeline=effective_pipeline,
                    zmq_context=context,
                    output_keys=config.pipeline_outputs,
                )
                if result_callback is not None:
                    result_callback(result)
            except TimeoutError as exc:
                _log_zmq_input_error(exc, meta=meta)
                print_warning("Skipping current frame and continuing.")
                pass
            except Exception as exc:
                _log_zmq_input_error(exc, meta=meta)
                print_warning("Skipping current frame and continuing.")
                pass
    except KeyboardInterrupt:
        print_warning("ZMQ source bridge service stopped.")
    finally:
        stop_flag["stop"] = True
        capture_thread.join(timeout=1.0)
        safe_close_socket(source_socket)
        context.term()


def run_bridge_service(
    config: BridgeServiceConfig,
    *,
    verbose: bool = False,
    save_json: bool = False,
    result_callback: Callable[[dict[str, Any]], None] | None = None,
) -> None:
    effective_pipeline = [n for n in config.pipeline if n.enabled]
    if not effective_pipeline:
        raise ValueError("custom_pipeline requires a non-empty bridge.pipeline list.")
    requires_prompts = _pipeline_requires_key(effective_pipeline, "prompts")

    if config.source_mode == "zmq_source":
        run_zmq_source_bridge_service(
            config,
            verbose=verbose,
            save_json=save_json,
            result_callback=result_callback,
        )
        return

def _require_image_dependencies() -> tuple[Any, Any]:
    if cv2 is None or np is None:
        raise RuntimeError(
            "Bridge service requires numpy and opencv-python-headless. "
            "Please install the project requirements first."
        )
    return cv2, np

def _require_zmq() -> Any:
    if zmq is None:
        raise RuntimeError(
            "Bridge service requires pyzmq. Please install the project requirements first."
        )
    return zmq
