from __future__ import annotations

import base64
from collections.abc import Callable, MutableMapping
import json
import threading
import time
import uuid
from pathlib import Path
from typing import Any

try:
    import zmq
except ImportError:  # pragma: no cover - exercised at runtime when dependency is absent
    zmq = None

from fusion_docker.console import print_error, print_status, print_success, print_warning
from fusion_docker.models import (
    BridgeInputMapping,
    BridgeSchemaCheckConfig,
    BridgeSchemaLink,
    BridgeServiceConfig,
)

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


def _external_request_format_hint() -> str:
    return (
        "Expected external JSON payload: "
        "{'rgb_image': '<base64_image>', 'depth_image': '<base64_image>', "
        "'request_id': '<optional>'}. "
        "Also supports aliases like color_image/rgb and depth/depth_raw_base64(+depth_shape)."
    )


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


def _log_external_input_error(
    exc: Exception,
    *,
    raw_message: str | None = None,
    parsed_payload: Any = None,
) -> None:
    print_error(f"{exc}")
    print_status(
        "INPUT",
        f"received_summary={_summarize_external_request_payload(parsed_payload)}",
        color="yellow",
    )
    if raw_message is not None:
        print_status(
            "INPUT",
            f"received_preview={_truncate_text(raw_message)}",
            color="yellow",
        )
    print_status("FORMAT", _external_request_format_hint(), color="yellow")


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


_REQUEST_INPUT_CANDIDATES = ("input.schema.json", "input.json")
_REQUEST_OUTPUT_CANDIDATES = ("output.schema.json", "output.json")
_SCHEMA_SOURCE_ALIASES = {
    "source",
    "__source__",
    "external",
    "external_json",
    "camera",
    "zmq_source",
}
_DEFAULT_PASSTHROUGH_FIELDS = {
    "request_id",
    "rgb_image",
    "depth_image",
    "rgb_image_base64",
    "depth_image_base64",
}


def _normalize_schema_name(name: str) -> str:
    lowered = str(name).strip().lower()
    return "".join(ch for ch in lowered if ch.isalnum())


def _looks_like_json_schema_document(raw: Any) -> bool:
    if not isinstance(raw, dict):
        return False
    if "$schema" in raw or "properties" in raw:
        return True
    if "oneOf" in raw or "anyOf" in raw or "allOf" in raw:
        return True
    raw_type = str(raw.get("type", "")).strip().lower()
    return raw_type in {"object", "array", "string", "number", "integer", "boolean", "null"}


def _read_json_file(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _resolve_docker_folder(docker_model_root: Path, docker_name: str) -> Path:
    direct_path = docker_model_root / docker_name
    if direct_path.is_dir():
        return direct_path

    target = _normalize_schema_name(docker_name)
    for candidate in docker_model_root.iterdir():
        if not candidate.is_dir():
            continue
        if _normalize_schema_name(candidate.name) == target:
            return candidate
    raise FileNotFoundError(
        f"Docker folder not found for '{docker_name}' under {docker_model_root}"
    )


def _find_first_existing_file(base_dir: Path, names: tuple[str, ...]) -> Path | None:
    for name in names:
        candidate = base_dir / name
        if candidate.is_file():
            return candidate
    return None


def _load_request_format_docs(
    docker_model_root: Path,
    docker_name: str,
) -> tuple[Path, Any, Path, Any]:
    docker_dir = _resolve_docker_folder(docker_model_root, docker_name)
    request_format_dir = docker_dir / "RequestFormat"
    if not request_format_dir.is_dir():
        raise FileNotFoundError(
            f"RequestFormat not found for '{docker_name}' at {request_format_dir}"
        )

    input_path = _find_first_existing_file(request_format_dir, _REQUEST_INPUT_CANDIDATES)
    output_path = _find_first_existing_file(request_format_dir, _REQUEST_OUTPUT_CANDIDATES)
    if input_path is None:
        raise FileNotFoundError(
            f"Missing input schema for '{docker_name}'. "
            f"Expected one of: {', '.join(_REQUEST_INPUT_CANDIDATES)}"
        )
    if output_path is None:
        raise FileNotFoundError(
            f"Missing output schema for '{docker_name}'. "
            f"Expected one of: {', '.join(_REQUEST_OUTPUT_CANDIDATES)}"
        )

    input_doc = _read_json_file(input_path)
    output_doc = _read_json_file(output_path)
    return input_path, input_doc, output_path, output_doc


def _collect_schema_properties(schema_doc: Any) -> set[str]:
    if not isinstance(schema_doc, dict):
        return set()
    if _looks_like_json_schema_document(schema_doc):
        properties = schema_doc.get("properties")
        if isinstance(properties, dict):
            return {str(key).strip() for key in properties.keys() if str(key).strip()}
    return set()


def _collect_input_expected_fields(input_doc: Any) -> set[str]:
    if isinstance(input_doc, dict) and _looks_like_json_schema_document(input_doc):
        required_raw = input_doc.get("required")
        if isinstance(required_raw, list):
            required_fields = {
                str(item).strip() for item in required_raw if str(item).strip()
            }
            if required_fields:
                return required_fields
        properties = _collect_schema_properties(input_doc)
        if properties:
            # If required is not declared, treat listed properties as expected input fields.
            return properties
        return set()

    if isinstance(input_doc, dict):
        return {str(key).strip() for key in input_doc.keys() if str(key).strip()}
    return set()


def _collect_output_available_fields(output_doc: Any) -> set[str]:
    if isinstance(output_doc, dict) and _looks_like_json_schema_document(output_doc):
        fields = _collect_schema_properties(output_doc)
        required_raw = output_doc.get("required")
        if isinstance(required_raw, list):
            fields.update(str(item).strip() for item in required_raw if str(item).strip())
        return fields
    if isinstance(output_doc, dict):
        return {str(key).strip() for key in output_doc.keys() if str(key).strip()}
    return set()


def _is_source_link(from_docker: str) -> bool:
    return _normalize_schema_name(from_docker) in {
        _normalize_schema_name(item) for item in _SCHEMA_SOURCE_ALIASES
    }


def _check_schema_link(
    link: BridgeSchemaLink,
    *,
    docker_model_root: Path,
) -> tuple[bool, list[str]]:
    diagnostics: list[str] = []

    if _is_source_link(link.from_docker):
        upstream_fields = set(_DEFAULT_PASSTHROUGH_FIELDS)
        diagnostics.append("upstream=source")
    else:
        _, _, upstream_output_path, upstream_output_doc = _load_request_format_docs(
            docker_model_root,
            link.from_docker,
        )
        upstream_fields = _collect_output_available_fields(upstream_output_doc)
        diagnostics.append(f"upstream_output={upstream_output_path}")

    downstream_input_path, downstream_input_doc, _, _ = _load_request_format_docs(
        docker_model_root,
        link.to_docker,
    )
    expected_fields = _collect_input_expected_fields(downstream_input_doc)
    diagnostics.append(f"downstream_input={downstream_input_path}")

    available_fields = set(upstream_fields)
    available_fields.update(_DEFAULT_PASSTHROUGH_FIELDS)
    available_fields.update(link.provides)

    missing: list[str] = []
    for downstream_field in sorted(expected_fields):
        mapped_source_field = link.field_map.get(downstream_field, downstream_field)
        if mapped_source_field not in available_fields:
            missing.append(f"{downstream_field} <- {mapped_source_field}")

    if not expected_fields:
        diagnostics.append("downstream_expected_fields=empty (nothing to validate)")
    if link.provides:
        diagnostics.append(f"provides={list(link.provides)}")
    if link.field_map:
        diagnostics.append(f"field_map={link.field_map}")
    if missing:
        diagnostics.append(f"missing={missing}")
        return False, diagnostics
    return True, diagnostics


def run_schema_connectivity_check(config: BridgeServiceConfig) -> None:
    schema_check: BridgeSchemaCheckConfig = config.schema_check
    if not schema_check.enabled:
        return

    docker_root_raw = schema_check.docker_model_root.strip()
    if not docker_root_raw:
        message = (
            "schema_check.enabled=true but docker_model_root is empty. "
            "Skip schema connectivity check."
        )
        if schema_check.strict:
            raise RuntimeError(message)
        print_warning(message)
        return

    docker_model_root = Path(docker_root_raw).expanduser()
    if not docker_model_root.is_dir():
        message = f"schema_check docker_model_root does not exist: {docker_model_root}"
        if schema_check.strict:
            raise RuntimeError(message)
        print_warning(message)
        return

    if not schema_check.links:
        message = "schema_check enabled but no links configured."
        if schema_check.strict:
            raise RuntimeError(message)
        print_warning(message)
        return

    print_status(
        "SCHEMA",
        f"Checking {len(schema_check.links)} link(s) under {docker_model_root}",
        color="cyan",
    )

    failed: list[str] = []
    for link in schema_check.links:
        link_label = f"{link.from_docker} -> {link.to_docker}"
        try:
            ok, diagnostics = _check_schema_link(
                link,
                docker_model_root=docker_model_root,
            )
        except Exception as exc:
            ok = False
            diagnostics = [str(exc)]

        if ok:
            print_success(f"[SCHEMA] {link_label} | compatible")
            for line in diagnostics:
                print_status("SCHEMA", f"{link_label} | {line}", color="blue")
        else:
            failed.append(link_label)
            print_error(f"[SCHEMA] {link_label} | incompatible")
            for line in diagnostics:
                print_status("SCHEMA", f"{link_label} | {line}", color="yellow")

    if failed:
        message = (
            f"Schema connectivity check failed ({len(failed)}): {', '.join(failed)}"
        )
        if schema_check.strict:
            raise RuntimeError(message)
        print_warning(message + " (strict=false, continue startup)")
    else:
        print_success("[SCHEMA] All configured links are compatible.")


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


def _build_meta_for_siglip2(source_meta: dict[str, Any] | None) -> dict[str, Any]:
    if isinstance(source_meta, dict):
        return dict(source_meta)
    return {}


def _normalize_sidecar_result(result: Any, source: str) -> dict[str, Any]:
    if not isinstance(result, dict):
        return {
            "source": source,
            "ok": False,
            "error": f"unexpected response type: {type(result).__name__}",
            "raw_result": str(result),
            "timestamp": time.time(),
        }
    if source in {"yomni", "flowpose"} and isinstance(result.get("response"), dict):
        outer_elapsed = result.get("elapsed_sec")
        merged = dict(result["response"])
        if outer_elapsed is not None and "elapsed_sec" not in merged:
            merged["elapsed_sec"] = outer_elapsed
        result = merged
    ok = bool(result.get("ok", result.get("status") == "ok"))
    payload = {"source": source, **result, "ok": ok, "timestamp": time.time()}
    if not ok and "error" not in payload:
        payload["error"] = str(result.get("message", "inference failed"))
    return payload


def _request_siglip2_once(
    endpoint: str,
    *,
    timeout_ms: int,
    meta: dict[str, Any],
    rgb_jpg_bytes: bytes,
) -> dict[str, Any]:
    zmq_module = _require_zmq()
    context = zmq_module.Context.instance()
    socket = make_req_socket(context, endpoint, timeout_ms)
    request_payload = dict(meta)
    request_payload["image_b64"] = base64.b64encode(rgb_jpg_bytes).decode("utf-8")
    try:
        socket.send_json(request_payload)
        return socket.recv_json()
    except zmq_module.error.Again as exc:
        raise TimeoutError(f"Siglip2 request timeout after {timeout_ms} ms") from exc
    finally:
        safe_close_socket(socket)


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


def _normalize_configured_obj_ids(
    configured_obj_ids: list[Any] | None,
    *,
    fallback_obj_ids: list[list[int]],
) -> list[Any]:
    if not configured_obj_ids:
        return fallback_obj_ids

    normalized: list[Any] = []
    for index, item in enumerate(configured_obj_ids, start=1):
        if isinstance(item, (list, tuple)) and len(item) >= 2:
            track_id = _safe_int(item[0], 0)
            instance_id = _safe_int(item[1], 0)
            if track_id > 0 and instance_id > 0:
                normalized.append([track_id, instance_id])
                continue

        track_id = _safe_int(item, 0)
        if track_id > 0:
            normalized.append([track_id, index])

    return normalized or fallback_obj_ids


def _request_flowpose_sidecar_once(
    endpoint: str,
    *,
    timeout_ms: int,
    request_id: str,
    rgb_b64: str,
    depth_b64: str,
) -> dict[str, Any]:
    zmq_module = _require_zmq()
    context = zmq_module.Context.instance()
    socket = make_req_socket(context, endpoint, timeout_ms)
    request_payload = {
        "request_id": request_id,
        "rgb_image": rgb_b64,
        "depth_image": depth_b64,
    }
    try:
        socket.send_string(json.dumps(request_payload, ensure_ascii=False))
        response_raw = socket.recv_string()
        return json.loads(response_raw)
    except zmq_module.error.Again as exc:
        raise TimeoutError(f"FlowPose sidecar request timeout after {timeout_ms} ms") from exc
    finally:
        safe_close_socket(socket)


def build_combined_mask_and_labels_from_sam3(
    sam3_response: dict[str, Any],
    h: int,
    w: int,
    obj_id_map: dict[str, int | str] | None = None,
    prompts: list[str] | None = None,
) -> tuple[Any, list[list[int]], list[str], list[str]]:
    _, np_module = _require_image_dependencies()

    if obj_id_map is None:
        obj_id_map = {}
    if prompts is None:
        prompts = []

    response_payload = extract_candidates_from_sam3(sam3_response)
    detections = response_payload.get("detections", None)
    if detections is None or not isinstance(detections, list):
        raise ValueError(
            "Cannot parse SAM3 response into combined_mask. "
            f"Top-level keys: {list(response_payload.keys())}"
        )

    combined_mask = np_module.zeros((h, w), dtype=np_module.uint8)
    obj_ids: list[list[int]] = []
    class_names: list[str] = []
    inst_id = 1

    for detection in detections:
        if not isinstance(detection, dict):
            continue

        mask_b64 = detection.get("mask_png_b64")
        if mask_b64 is None:
            for key in ("mask", "segmentation", "binary_mask", "bitmap"):
                if key in detection:
                    mask_b64 = detection[key]
                    break
        if mask_b64 is None:
            continue

        mask = decode_mask_item(mask_b64, h, w)
        if np_module.count_nonzero(mask) == 0:
            continue

        label = detection.get(
            "label",
            detection.get("class_name", detection.get("name", detection.get("prompt"))),
        )
        if label is None:
            class_id = detection.get("class_id")
            try:
                index = int(class_id)
            except (TypeError, ValueError):
                index = -1
            if 0 <= index < len(prompts):
                label = prompts[index]
        if label is None:
            label = "obj"

        if str(label) in obj_id_map:
            track_id = int(obj_id_map[str(label)])
        else:
            raw_track_id = detection.get("track_id", detection.get("obj_id", detection.get("id")))
            try:
                track_id = int(raw_track_id)
            except (TypeError, ValueError):
                track_id = inst_id

        if track_id <= 0:
            track_id = inst_id

        combined_mask[mask > 0] = inst_id
        obj_ids.append([track_id, inst_id])
        class_names.append(str(label))

        inst_id += 1
        if inst_id >= 255:
            raise ValueError("Too many instances for uint8 combined_mask.")

    if not obj_ids:
        raise ValueError("SAM3 detections found, but no valid masks were decoded.")

    instance_names = build_instance_names(class_names)

    return combined_mask, obj_ids, class_names, instance_names


def build_instance_names(class_names: list[str]) -> list[str]:
    # FlowPose only needs human-readable labels here; obj_ids already carry instance identity.
    return [str(class_name) for class_name in class_names]


def extract_candidates_from_sam3(sam3_response: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(sam3_response, dict):
        raise ValueError("SAM3 response is not a dict.")

    for nested_key in ("output", "result", "data"):
        nested = sam3_response.get(nested_key)
        if isinstance(nested, dict) and any(
            key in nested
            for key in (
                "combined_mask",
                "masks",
                "detections",
                "results",
                "annotations",
                "objects",
                "predictions",
            )
        ):
            return nested

    return sam3_response


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


def make_req_socket(context: zmq.Context, addr: str, timeout_ms: int) -> zmq.Socket:
    _require_zmq()
    sock = context.socket(zmq.REQ)
    sock.setsockopt(zmq.RCVTIMEO, timeout_ms)
    sock.setsockopt(zmq.SNDTIMEO, timeout_ms)
    sock.setsockopt(zmq.LINGER, 0)
    sock.connect(addr)
    return sock


def recreate_req_sockets(
    context: zmq.Context,
    sam3_addr: str,
    flowpose_addr: str,
    sam3_timeout_ms: int,
    flowpose_timeout_ms: int,
) -> tuple[zmq.Socket | None, zmq.Socket | None]:
    if not sam3_addr or not flowpose_addr:
        return None, None
    sam3_socket = make_req_socket(context, sam3_addr, sam3_timeout_ms)
    flowpose_socket = make_req_socket(context, flowpose_addr, flowpose_timeout_ms)
    return sam3_socket, flowpose_socket


def safe_close_socket(sock: zmq.Socket | None) -> None:
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


def recv_external_json_rgbd(rep_socket: zmq.Socket) -> tuple[Any, Any, dict[str, Any]]:
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
    sub_socket: zmq.Socket,
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
    sub_socket: zmq.Socket,
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


def process_once(
    sam3_socket: zmq.Socket | None,
    flowpose_socket: zmq.Socket | None,
    rgb: Any,
    depth: Any,
    prompts: list[str],
    obj_ids: list[Any] | None = None,
    obj_id_map: dict[str, int | str] | None = None,
    req_timeout_ms: int = 1000,
    sam3_timeout_ms: int | None = None,
    return_masks: bool = True,
    clear_previous: bool = True,
    output_json: str | None = None,
    verbose: bool = False,
    rgb_jpg_quality: int = 85,
    source_meta: dict[str, Any] | None = None,
    siglip2_server_addr: str = "",
    flowpose_sidecar_server_addr: str = "",
    run_sam3_flowpose: bool = True,
) -> dict[str, Any]:
    _, np_module = _require_image_dependencies()
    zmq_module = _require_zmq()

    request_id = str(uuid.uuid4())
    start_time = time.time()
    needs_depth_image = bool(run_sam3_flowpose or flowpose_sidecar_server_addr)
    rgb_jpg_bytes = encode_jpg_bytes(rgb, quality=rgb_jpg_quality)
    rgb_b64 = base64.b64encode(rgb_jpg_bytes).decode("utf-8")
    depth_b64 = encode_png_base64(depth) if needs_depth_image else ""
    combined_mask_b64 = ""
    flowpose_response: dict[str, Any] = build_empty_response(
        request_id,
        start_time,
        rgb_b64=rgb_b64,
        depth_b64=depth_b64,
    )
    model_results: dict[str, dict[str, Any]] = {}
    effective_sam3_timeout_ms = int(sam3_timeout_ms or req_timeout_ms)
    siglip2_thread: threading.Thread | None = None
    siglip2_async_result: dict[str, Any] = {}

    if siglip2_server_addr:
        def _siglip2_worker() -> None:
            siglip_start = time.time()
            try:
                siglip_meta = _build_meta_for_siglip2(source_meta)
                siglip2_result = _request_siglip2_once(
                    siglip2_server_addr,
                    timeout_ms=req_timeout_ms,
                    meta=siglip_meta,
                    rgb_jpg_bytes=rgb_jpg_bytes,
                )
                siglip2_payload = _normalize_sidecar_result(siglip2_result, "siglip2")
            except Exception as exc:
                print_warning(f"Siglip2 sidecar failed: {exc}")
                siglip2_payload = {
                    "source": "siglip2",
                    "ok": False,
                    "error": str(exc),
                    "timestamp": time.time(),
                }
            siglip2_async_result["payload"] = siglip2_payload
            siglip2_async_result["elapsed"] = time.time() - siglip_start

        siglip2_thread = threading.Thread(target=_siglip2_worker, daemon=True)
        siglip2_thread.start()

    sam3_flowpose_enabled = bool(
        run_sam3_flowpose and sam3_socket is not None and flowpose_socket is not None
    )
    if run_sam3_flowpose and not sam3_flowpose_enabled:
        print_warning("SAM3/FlowPose sockets unavailable. Continuing with siglip2 only.")

    if sam3_flowpose_enabled:

        sam3_request = {
            "request_id": request_id,
            "rgb_image": rgb_b64,
            "prompts": prompts,
            "return_masks": return_masks,
            "clear_previous": clear_previous,
        }

        try:
            sam3_socket.send_json(sam3_request)
            sam3_response = sam3_socket.recv_json()
        except zmq_module.error.Again as exc:
            print_warning(f"SAM3 request timeout after {effective_sam3_timeout_ms} ms: {exc}")
            sam3_response = {
                "status": "timeout",
                "request_id": request_id,
                "num_detections": 0,
                "detections": [],
            }

        sam3_elapsed = time.time()
        sam3_cost = sam3_elapsed - start_time

        if verbose:
            print_response(sam3_response, verbose=True, title="SAM3")

        if output_json:
            output_path = Path(output_json).expanduser()
            output_path.parent.mkdir(parents=True, exist_ok=True)
            with output_path.open("w", encoding="utf-8") as handle:
                json.dump(sam3_response, handle, indent=2, ensure_ascii=False)

        num_detections = sam3_response.get("num_detections")
        detections = sam3_response.get("detections")
        no_detection = False
        if num_detections is not None and int(num_detections) == 0:
            no_detection = True
        elif isinstance(detections, list) and len(detections) == 0:
            no_detection = True

        model_results["sam3"] = _build_model_result(
            name="sam3",
            enabled=True,
            ok=not no_detection,
            summary=(
                f"detections={len(detections) if isinstance(detections, list) else _safe_int(num_detections, 0)}"
            ),
            payload={
                "status": sam3_response.get("status", "unknown"),
                "request_id": sam3_response.get("request_id", request_id),
                "num_detections": _safe_int(num_detections, 0) if num_detections is not None else None,
                "detections_count": len(detections) if isinstance(detections, list) else None,
            },
            elapsed_sec=sam3_cost,
        )

        if no_detection:
            print_status(
                "DONE",
                f"{request_id} | sam3_only={sam3_elapsed - start_time:.3f}s",
                color="yellow",
            )
            model_results["flowpose"] = _build_model_result(
                name="flowpose",
                enabled=True,
                ok=False,
                summary="skipped: no valid sam3 detections.",
                payload=None,
                elapsed_sec=0.0,
            )
        else:
            combined_mask_np, resolved_obj_ids, class_names, instance_names = build_combined_mask_and_labels_from_sam3(
                sam3_response=sam3_response,
                h=rgb.shape[0],
                w=rgb.shape[1],
                obj_id_map=obj_id_map,
                prompts=prompts,
            )
            resolved_obj_ids = _normalize_configured_obj_ids(
                obj_ids,
                fallback_obj_ids=resolved_obj_ids,
            )

            if len(resolved_obj_ids) == 0 or np_module.count_nonzero(combined_mask_np) == 0:
                print_status(
                    "DONE",
                    f"{request_id} | empty_mask={time.time() - start_time:.3f}s",
                    color="yellow",
                )
                model_results["flowpose"] = _build_model_result(
                    name="flowpose",
                    enabled=True,
                    ok=False,
                    summary="skipped: empty combined_mask.",
                    payload=None,
                    elapsed_sec=0.0,
                )
            else:
                combined_mask_b64 = encode_png_base64(combined_mask_np)
                flowpose_request = {
                    "request_id": request_id,
                    "rgb_image": rgb_b64,
                    "depth_image": depth_b64,
                    "combined_mask": combined_mask_b64,
                    "obj_ids": resolved_obj_ids,
                    "class_names": class_names,
                    "instance_names": instance_names,
                }
                try:
                    flowpose_socket.send_json(flowpose_request)
                    flowpose_reply = flowpose_socket.recv_json()
                except zmq_module.error.Again as exc:
                    print_warning(f"FlowPose request timeout after {req_timeout_ms} ms: {exc}")
                    flowpose_reply = {
                        "status": "timeout",
                        "request_id": request_id,
                        "objects": [],
                        "message": f"FlowPose request timeout after {req_timeout_ms} ms",
                    }

                total_elapsed = time.time()
                if verbose:
                    print_response(flowpose_reply, verbose=True, title="FLOWPOSE")

                print_success(
                    (
                        f"{request_id} | sam3={sam3_elapsed - start_time:.3f}s "
                        f"flow={total_elapsed - sam3_elapsed:.3f}s "
                        f"total={total_elapsed - start_time:.3f}s "
                        f"class_names={class_names} "
                        f"instance_names={instance_names}"
                    )
                )
                if isinstance(flowpose_reply, dict):
                    flowpose_response = flowpose_reply
                else:
                    flowpose_response = {
                        "status": "ok",
                        "request_id": request_id,
                        "objects": [],
                        "elapsed_sec": round(total_elapsed - start_time, 4),
                        "raw_response": flowpose_reply,
                    }
                flowpose_objects = flowpose_response.get("objects", [])
                flowpose_ok = bool(flowpose_response.get("status", "ok") == "ok")
                model_results["flowpose"] = _build_model_result(
                    name="flowpose",
                    enabled=True,
                    ok=flowpose_ok,
                    summary=(
                        f"objects={len(flowpose_objects) if isinstance(flowpose_objects, list) else 0}, "
                        f"class_names={class_names}"
                    ),
                    payload={
                        "status": flowpose_response.get("status", "unknown"),
                        "request_id": flowpose_response.get("request_id", request_id),
                        "objects_count": len(flowpose_objects) if isinstance(flowpose_objects, list) else None,
                    },
                    elapsed_sec=total_elapsed - sam3_elapsed,
                )
    else:
        if run_sam3_flowpose:
            flowpose_response["message"] = "sam3_flowpose pipeline unavailable (service/socket not ready)."
            sam3_summary = "unavailable: service/socket not ready."
            flowpose_summary = "unavailable: service/socket not ready."
        else:
            flowpose_response["message"] = "sam3_flowpose pipeline is disabled in bridge config."
            sam3_summary = "disabled by config."
            flowpose_summary = "disabled by config."
        model_results["sam3"] = _build_model_result(
            name="sam3",
            enabled=bool(run_sam3_flowpose),
            ok=False,
            summary=sam3_summary,
            payload=None,
        )
        model_results["flowpose"] = _build_model_result(
            name="flowpose",
            enabled=bool(run_sam3_flowpose),
            ok=False,
            summary=flowpose_summary,
            payload=None,
        )

    base64_payload = {"rgb_image": rgb_b64}
    if depth_b64:
        base64_payload["depth_image"] = depth_b64
    if combined_mask_b64:
        base64_payload["combined_mask"] = combined_mask_b64
    flowpose_response.update(base64_payload)
    pipelines = flowpose_response.setdefault("pipelines", {})
    if isinstance(pipelines, dict):
        sam3_ok = bool(model_results.get("sam3", {}).get("ok", False))
        flow_ok = bool(model_results.get("flowpose", {}).get("ok", False))
        pipelines.setdefault(
            "sam3_flowpose",
            {
                "enabled": sam3_flowpose_enabled,
                "ok": bool(sam3_flowpose_enabled and sam3_ok and flow_ok),
            },
        )

    if siglip2_server_addr:
        if siglip2_thread is not None:
            siglip2_thread.join()
        siglip2_payload = siglip2_async_result.get("payload", {
            "source": "siglip2",
            "ok": False,
            "error": "siglip2 worker did not return payload",
            "timestamp": time.time(),
        })
        siglip_elapsed = float(siglip2_async_result.get("elapsed", 0.0))
        flowpose_response["siglip2"] = siglip2_payload
        # Backward compatibility for older dashboards/scripts.
        flowpose_response["siglip"] = siglip2_payload
        if isinstance(pipelines, dict):
            pipelines["siglip2"] = {
                "enabled": True,
                "ok": bool(siglip2_payload.get("ok", False)),
            }
        model_results["siglip2"] = _build_model_result(
            name="siglip2",
            enabled=True,
            ok=bool(siglip2_payload.get("ok", False)),
            summary=(
                f"best_category={siglip2_payload.get('best_category', 'unknown')}, "
                f"best_similarity={siglip2_payload.get('best_similarity', 'N/A')}"
            ),
            payload={
                "status": siglip2_payload.get("status", "unknown"),
                "best_category": siglip2_payload.get("best_category"),
                "best_similarity": siglip2_payload.get("best_similarity"),
            },
            elapsed_sec=siglip_elapsed,
        )
    else:
        model_results["siglip2"] = _build_model_result(
            name="siglip2",
            enabled=False,
            ok=False,
            summary="disabled by config.",
            payload=None,
        )

    if flowpose_sidecar_server_addr:
        try:
            flowpose_sidecar_result = _request_flowpose_sidecar_once(
                flowpose_sidecar_server_addr,
                timeout_ms=req_timeout_ms,
                request_id=request_id,
                rgb_b64=rgb_b64,
                depth_b64=depth_b64,
            )
            flowpose_sidecar_payload = _normalize_sidecar_result(
                flowpose_sidecar_result,
                "flowpose",
            )
        except Exception as exc:
            print_warning(f"FlowPose sidecar failed: {exc}")
            flowpose_sidecar_payload = {
                "source": "flowpose",
                "ok": False,
                "error": str(exc),
                "timestamp": time.time(),
            }
        flowpose_response["flowpose_sidecar"] = flowpose_sidecar_payload
        # Backward compatibility for older dashboards/scripts.
        flowpose_response["yomni"] = flowpose_sidecar_payload
        if isinstance(pipelines, dict):
            pipelines["flowpose_sidecar"] = {
                "enabled": True,
                "ok": bool(flowpose_sidecar_payload.get("ok", False)),
            }

    flowpose_response["bridge_elapsed_sec"] = round(time.time() - start_time, 4)
    flowpose_response["model_results"] = model_results
    for model_key in ("sam3", "flowpose", "siglip2"):
        if model_key in model_results:
            _print_model_result_line(request_id, model_key, model_results[model_key])
    return flowpose_response


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

    output_json = config.output_json if save_json else None
    context = zmq_module.Context()
    sam3_timeout_ms = int(config.sam3_timeout_ms or config.req_timeout_ms)
    flowpose_timeout_ms = int(config.req_timeout_ms)
    sam3_socket, flowpose_socket = recreate_req_sockets(
        context,
        config.sam3_server_addr if config.run_sam3_flowpose else "",
        config.flowpose_server_addr if config.run_sam3_flowpose else "",
        sam3_timeout_ms,
        flowpose_timeout_ms,
    )

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

    if config.run_sam3_flowpose:
        print_status("BRIDGE", f"SAM3 server      : {config.sam3_server_addr}", color="cyan")
        print_status("BRIDGE", f"FlowPose server  : {config.flowpose_server_addr}", color="cyan")
    else:
        print_status("BRIDGE", "SAM3->FlowPose pipeline disabled.", color="yellow")
    if config.siglip2_server_addr:
        print_status("BRIDGE", f"Siglip2 server   : {config.siglip2_server_addr}", color="cyan")
    if config.flowpose_sidecar_server_addr:
        print_status(
            "BRIDGE",
            f"FlowPose sidecar : {config.flowpose_sidecar_server_addr}",
            color="cyan",
        )
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
                    required=bool(config.run_sam3_flowpose),
                )
                result = process_once(
                    sam3_socket=sam3_socket,
                    flowpose_socket=flowpose_socket,
                    rgb=rgb,
                    depth=depth,
                    prompts=prompts,
                    obj_ids=config.obj_ids,
                    obj_id_map=config.obj_id_map,
                    req_timeout_ms=config.req_timeout_ms,
                    sam3_timeout_ms=sam3_timeout_ms,
                    return_masks=config.return_masks,
                    clear_previous=config.clear_previous,
                    output_json=output_json,
                    verbose=verbose,
                    rgb_jpg_quality=config.rgb_jpg_quality,
                    source_meta=meta,
                    siglip2_server_addr=config.siglip2_server_addr,
                    flowpose_sidecar_server_addr=config.flowpose_sidecar_server_addr,
                    run_sam3_flowpose=config.run_sam3_flowpose,
                )
                if result_callback is not None:
                    result_callback(result)
            except TimeoutError as exc:
                _log_zmq_input_error(exc, meta=meta)
                print_warning("Skipping current frame and continuing.")
                safe_close_socket(sam3_socket)
                safe_close_socket(flowpose_socket)
                sam3_socket, flowpose_socket = recreate_req_sockets(
                    context,
                    config.sam3_server_addr if config.run_sam3_flowpose else "",
                    config.flowpose_server_addr if config.run_sam3_flowpose else "",
                    sam3_timeout_ms,
                    flowpose_timeout_ms,
                )
            except Exception as exc:
                _log_zmq_input_error(exc, meta=meta)
                print_warning("Skipping current frame and continuing.")
                safe_close_socket(sam3_socket)
                safe_close_socket(flowpose_socket)
                sam3_socket, flowpose_socket = recreate_req_sockets(
                    context,
                    config.sam3_server_addr if config.run_sam3_flowpose else "",
                    config.flowpose_server_addr if config.run_sam3_flowpose else "",
                    sam3_timeout_ms,
                    flowpose_timeout_ms,
                )
    except KeyboardInterrupt:
        print_warning("ZMQ source bridge service stopped.")
    finally:
        stop_flag["stop"] = True
        capture_thread.join(timeout=1.0)
        safe_close_socket(source_socket)
        safe_close_socket(sam3_socket)
        safe_close_socket(flowpose_socket)
        context.term()


def run_bridge_service(
    config: BridgeServiceConfig,
    *,
    verbose: bool = False,
    save_json: bool = False,
    result_callback: Callable[[dict[str, Any]], None] | None = None,
) -> None:
    run_schema_connectivity_check(config)

    if config.source_mode == "zmq_source":
        run_zmq_source_bridge_service(
            config,
            verbose=verbose,
            save_json=save_json,
            result_callback=result_callback,
        )
        return

    _require_image_dependencies()
    zmq_module = _require_zmq()

    output_json = config.output_json if save_json else None
    context = zmq_module.Context()
    sam3_timeout_ms = int(config.sam3_timeout_ms or config.req_timeout_ms)
    flowpose_timeout_ms = int(config.req_timeout_ms)
    sam3_socket, flowpose_socket = recreate_req_sockets(
        context,
        config.sam3_server_addr if config.run_sam3_flowpose else "",
        config.flowpose_server_addr if config.run_sam3_flowpose else "",
        sam3_timeout_ms,
        flowpose_timeout_ms,
    )

    external_socket = context.socket(zmq_module.REP)
    external_socket.setsockopt(zmq_module.LINGER, 0)
    external_socket.bind(f"tcp://{config.listen_host}:{config.listen_port}")

    if config.run_sam3_flowpose:
        print_status("BRIDGE", f"SAM3 server      : {config.sam3_server_addr}", color="cyan")
        print_status("BRIDGE", f"FlowPose server  : {config.flowpose_server_addr}", color="cyan")
    else:
        print_status("BRIDGE", "SAM3->FlowPose pipeline disabled.", color="yellow")
    if config.siglip2_server_addr:
        print_status("BRIDGE", f"Siglip2 server   : {config.siglip2_server_addr}", color="cyan")
    if config.flowpose_sidecar_server_addr:
        print_status(
            "BRIDGE",
            f"FlowPose sidecar : {config.flowpose_sidecar_server_addr}",
            color="cyan",
        )
    print_status(
        "BRIDGE",
        f"External listen  : tcp://{config.listen_host}:{config.listen_port}",
        color="cyan",
    )
    print_status("BRIDGE", f"SAM3 timeout     : {sam3_timeout_ms} ms", color="cyan")
    print_status("BRIDGE", f"FlowPose timeout : {flowpose_timeout_ms} ms", color="cyan")
    print_status("WAIT", "Waiting external JSON RGB-D requests...", color="yellow")

    try:
        while True:
            raw_message: str | None = None
            parsed_payload: Any = None
            try:
                raw_message = external_socket.recv_string()
                try:
                    parsed_payload = json.loads(raw_message)
                except Exception:
                    parsed_payload = None

                rgb, depth, request_data = decode_external_json_rgbd_message(
                    raw_message,
                    input_mapping=config.input_mapping,
                )
                parsed_payload = request_data
                prompts = _extract_prompts_from_source_meta(
                    request_data,
                    fallback_prompts=config.prompts,
                    required=bool(config.run_sam3_flowpose),
                )
                result = process_once(
                    sam3_socket=sam3_socket,
                    flowpose_socket=flowpose_socket,
                    rgb=rgb,
                    depth=depth,
                    prompts=prompts,
                    obj_ids=config.obj_ids,
                    obj_id_map=config.obj_id_map,
                    req_timeout_ms=config.req_timeout_ms,
                    sam3_timeout_ms=sam3_timeout_ms,
                    return_masks=config.return_masks,
                    clear_previous=config.clear_previous,
                    output_json=output_json,
                    verbose=verbose,
                    rgb_jpg_quality=config.rgb_jpg_quality,
                    source_meta=request_data,
                    siglip2_server_addr=config.siglip2_server_addr,
                    flowpose_sidecar_server_addr=config.flowpose_sidecar_server_addr,
                    run_sam3_flowpose=config.run_sam3_flowpose,
                )
                if request_id := request_data.get("request_id"):
                    result.setdefault("external_request_id", request_id)
                if result_callback is not None:
                    result_callback(result)
                external_socket.send_string(json.dumps(result, ensure_ascii=False))
            except TimeoutError as exc:
                error_payload = {"status": "error", "message": str(exc)}
                _log_external_input_error(
                    exc,
                    raw_message=raw_message,
                    parsed_payload=parsed_payload,
                )
                try:
                    external_socket.send_string(json.dumps(error_payload, ensure_ascii=False))
                except Exception:
                    pass
                safe_close_socket(sam3_socket)
                safe_close_socket(flowpose_socket)
                sam3_socket, flowpose_socket = recreate_req_sockets(
                    context,
                    config.sam3_server_addr if config.run_sam3_flowpose else "",
                    config.flowpose_server_addr if config.run_sam3_flowpose else "",
                    sam3_timeout_ms,
                    flowpose_timeout_ms,
                )
            except Exception as exc:
                error_payload = {"status": "error", "message": str(exc)}
                _log_external_input_error(
                    exc,
                    raw_message=raw_message,
                    parsed_payload=parsed_payload,
                )
                try:
                    external_socket.send_string(json.dumps(error_payload, ensure_ascii=False))
                except Exception:
                    pass
                safe_close_socket(sam3_socket)
                safe_close_socket(flowpose_socket)
                sam3_socket, flowpose_socket = recreate_req_sockets(
                    context,
                    config.sam3_server_addr if config.run_sam3_flowpose else "",
                    config.flowpose_server_addr if config.run_sam3_flowpose else "",
                    sam3_timeout_ms,
                    flowpose_timeout_ms,
                )
    except KeyboardInterrupt:
        print_warning("Bridge service stopped.")
    finally:
        safe_close_socket(external_socket)
        safe_close_socket(sam3_socket)
        safe_close_socket(flowpose_socket)
        context.term()
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
