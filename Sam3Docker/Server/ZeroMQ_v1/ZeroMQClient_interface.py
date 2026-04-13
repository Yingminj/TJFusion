import base64
import json
import uuid
import zmq
import time
import argparse
import yaml
import cv2
import numpy as np


def load_config(config_path="ClientConfig.yaml"):
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def encode_png_base64(img: np.ndarray) -> str:
    ok, buf = cv2.imencode(".png", img)
    if not ok:
        raise RuntimeError("Failed to encode PNG image.")
    return base64.b64encode(buf.tobytes()).decode("utf-8")


def encode_jpg_base64(img: np.ndarray, quality: int = 85) -> str:
    ok, buf = cv2.imencode(".jpg", img, [int(cv2.IMWRITE_JPEG_QUALITY), int(quality)])
    if not ok:
        raise RuntimeError("Failed to encode JPG image.")
    return base64.b64encode(buf.tobytes()).decode("utf-8")


def decode_b64_image_to_np(image_b64: str, flags=cv2.IMREAD_UNCHANGED):
    raw = base64.b64decode(image_b64)
    arr = np.frombuffer(raw, dtype=np.uint8)
    img = cv2.imdecode(arr, flags)
    if img is None:
        raise RuntimeError("Failed to decode base64 image.")
    return img


def print_response(response, verbose=False, title="RESPONSE"):
    request_id = response.get("request_id", "unknown")
    print(f"========== {title} {request_id} ==========")
    if verbose:
        print(json.dumps(response, indent=2, ensure_ascii=False))
    else:
        status = response.get("status", "unknown")
        elapsed = response.get("elapsed_sec", "N/A")
        print(f"status={status}, elapsed_sec={elapsed}")
    print("=" * 67 + "\n")


def decode_mask_item(mask_item, h, w):
    if isinstance(mask_item, str):
        mask = decode_b64_image_to_np(mask_item, cv2.IMREAD_GRAYSCALE)
    elif isinstance(mask_item, np.ndarray):
        mask = mask_item
    elif isinstance(mask_item, list):
        mask = np.array(mask)
    elif isinstance(mask_item, dict):
        for k in ["mask", "segmentation", "binary_mask"]:
            if k in mask_item:
                return decode_mask_item(mask_item[k], h, w)
        raise ValueError(f"Unsupported mask item dict keys: {list(mask_item.keys())}")
    else:
        raise ValueError(f"Unsupported mask item type: {type(mask_item)}")

    if mask.ndim == 3:
        mask = mask[..., 0]

    if mask.shape[:2] != (h, w):
        mask = cv2.resize(mask.astype(np.uint8), (w, h), interpolation=cv2.INTER_NEAREST)

    if mask.dtype == np.bool_:
        mask = mask.astype(np.uint8) * 255
    elif mask.dtype != np.uint8:
        mask = (mask > 0).astype(np.uint8) * 255

    return mask


def extract_candidates_from_sam3(sam3_response):
    if not isinstance(sam3_response, dict):
        raise ValueError("SAM3 response is not a dict.")

    for nested_key in ["output", "result", "data"]:
        if nested_key in sam3_response and isinstance(sam3_response[nested_key], dict):
            inner = sam3_response[nested_key]
            if any(k in inner for k in [
                "combined_mask", "masks", "detections", "results",
                "annotations", "objects", "predictions"
            ]):
                return inner

    return sam3_response


def build_combined_mask_and_labels_from_sam3(
    sam3_response,
    h,
    w,
    obj_id_map=None,
    prompts=None,
):
    if obj_id_map is None:
        obj_id_map = {}
    if prompts is None:
        prompts = []

    sam3_response = extract_candidates_from_sam3(sam3_response)
    detections = sam3_response.get("detections", None)

    if detections is None or not isinstance(detections, list):
        raise ValueError(
            f"Cannot parse SAM3 response into combined_mask. Top-level keys: {list(sam3_response.keys())}"
        )

    combined_mask = np.zeros((h, w), dtype=np.uint8)
    obj_ids = []
    class_names = []
    inst_id = 1

    for det in detections:
        if not isinstance(det, dict):
            continue

        mask_b64 = det.get("mask_png_b64")
        if mask_b64 is None:
            for k in ["mask", "segmentation", "binary_mask", "bitmap"]:
                if k in det:
                    mask_b64 = det[k]
                    break

        if mask_b64 is None:
            continue

        mask = decode_mask_item(mask_b64, h, w)
        if np.count_nonzero(mask) == 0:
            continue

        # 先直接取 detection 自带标签
        label = det.get("label", det.get("class_name", det.get("name", det.get("prompt", None))))

        # 如果没有，再根据 class_id 去映射 prompts
        if label is None:
            class_id = det.get("class_id", None)
            if class_id is not None:
                try:
                    class_id = int(class_id)
                    if 0 <= class_id < len(prompts):
                        label = prompts[class_id]
                except Exception:
                    pass

        if label is None:
            label = "obj"

        if str(label) in obj_id_map:
            track_id = int(obj_id_map[str(label)])
        else:
            raw_track_id = det.get("track_id", det.get("obj_id", det.get("id", None)))
            try:
                track_id = int(raw_track_id)
            except Exception:
                track_id = inst_id

        if track_id <= 0:
            track_id = inst_id

        combined_mask[mask > 0] = inst_id
        obj_ids.append([track_id, inst_id])
        class_names.append(str(label))

        inst_id += 1
        if inst_id >= 255:
            raise ValueError("Too many instances for uint8 combined_mask.")

    if len(obj_ids) == 0:
        raise ValueError("SAM3 detections found, but no valid masks were decoded.")

    class_counter = {}
    instance_names = []
    for class_name in class_names:
        class_counter[class_name] = class_counter.get(class_name, 0) + 1
        instance_names.append(f"{class_name}_{class_counter[class_name]}")

    return combined_mask, obj_ids, class_names, instance_names

def make_req_socket(context, addr, timeout_ms):
    sock = context.socket(zmq.REQ)
    sock.setsockopt(zmq.RCVTIMEO, timeout_ms)
    sock.setsockopt(zmq.SNDTIMEO, timeout_ms)
    sock.connect(addr)
    return sock


def recreate_req_sockets(context, sam3_addr, downstream_addr, timeout_ms):
    sam3_socket = make_req_socket(context, sam3_addr, timeout_ms)
    downstream_socket = make_req_socket(context, downstream_addr, timeout_ms)
    return sam3_socket, downstream_socket


def safe_close_socket(sock):
    try:
        sock.close(0)
    except Exception:
        pass


def recv_external_json_rgbd(rep_socket):
    message_str = rep_socket.recv_string()
    request_data = json.loads(message_str)

    if "rgb_image" not in request_data or "depth_image" not in request_data:
        raise RuntimeError("Missing 'rgb_image' or 'depth_image' in external request.")

    rgb = decode_b64_image_to_np(request_data["rgb_image"], cv2.IMREAD_COLOR)
    depth = decode_b64_image_to_np(request_data["depth_image"], cv2.IMREAD_ANYDEPTH)

    if rgb is None or depth is None:
        raise RuntimeError("Failed to decode external base64 rgb/depth images.")

    return rgb, depth, request_data


def build_empty_response(request_id, start_time):
    return {
        "status": "ok",
        "request_id": request_id,
        "objects": [],
        "elapsed_sec": round(time.time() - start_time, 4),
    }


def process_once(
    sam3_socket,
    downstream_socket,
    rgb,
    depth,
    prompts,
    obj_id_map=None,
    req_timeout_ms=1000,
    return_masks=True,
    clear_previous=True,
    output_json=None,
    verbose=False,
    rgb_jpg_quality=85,
):
    request_id = str(uuid.uuid4())
    t0 = time.time()

    rgb_b64 = encode_jpg_base64(rgb, quality=rgb_jpg_quality)

    sam3_request = {
        "request_id": request_id,
        "rgb_image": rgb_b64,
        "prompts": prompts,
        "return_masks": return_masks,
        "clear_previous": clear_previous
    }

    try:
        sam3_socket.send_json(sam3_request)
        sam3_response = sam3_socket.recv_json()
    except zmq.error.Again:
        raise TimeoutError(f"SAM3 request timeout after {req_timeout_ms} ms")

    t1 = time.time()

    if verbose:
        print_response(sam3_response, verbose=True, title="SAM3 RESPONSE")

    if output_json:
        with open(output_json, "w", encoding="utf-8") as f:
            json.dump(sam3_response, f, indent=2, ensure_ascii=False)

    num_detections = sam3_response.get("num_detections", None)
    detections = sam3_response.get("detections", None)

    no_detection = False
    if num_detections is not None and int(num_detections) == 0:
        no_detection = True
    elif isinstance(detections, list) and len(detections) == 0:
        no_detection = True

    if no_detection:
        print(f"[DONE] {request_id} | sam3_only={t1 - t0:.3f}s")
        return build_empty_response(request_id, t0)

    combined_mask_np, obj_ids, class_names, instance_names = build_combined_mask_and_labels_from_sam3(
        sam3_response=sam3_response,
        h=rgb.shape[0],
        w=rgb.shape[1],
        obj_id_map=obj_id_map,
        prompts=prompts,
    )

    if len(obj_ids) == 0 or np.count_nonzero(combined_mask_np) == 0:
        print(f"[DONE] {request_id} | empty_mask={time.time() - t0:.3f}s")
        return build_empty_response(request_id, t0)

    combined_mask_b64 = encode_png_base64(combined_mask_np)
    depth_b64 = encode_png_base64(depth)

    downstream_request = {
        "request_id": request_id,
        "rgb_image": rgb_b64,
        "depth_image": depth_b64,
        "combined_mask": combined_mask_b64,
        "obj_ids": obj_ids,
        "class_names": class_names,
        # "instance_names": instance_names,
    }

    try:
        downstream_socket.send_json(downstream_request)
        downstream_response = downstream_socket.recv_json()
    except zmq.error.Again:
        raise TimeoutError(f"FlowPose request timeout after {req_timeout_ms} ms")

    t2 = time.time()

    if verbose:
        print_response(downstream_response, verbose=True, title="FLOWPOSE RESPONSE")

    print(
        f"[DONE] {request_id} | "
        f"sam3={t1 - t0:.3f}s "
        f"flow={t2 - t1:.3f}s "
        f"total={t2 - t0:.3f}s "
        f"class_names={class_names} "
        f"instance_names={instance_names}"
    )

    return downstream_response


def main():
    cfg = load_config()

    parser = argparse.ArgumentParser()
    parser.add_argument("-v", action="store_true", help="print verbose response")
    parser.add_argument("--req-timeout-ms", type=int, default=1000, help="REQ/REP send/recv timeout in ms")
    parser.add_argument("--save-json", action="store_true", help="save SAM3 response json to disk")
    parser.add_argument("--rgb-jpg-quality", type=int, default=85, help="RGB jpg quality for requests")
    parser.add_argument("--listen-host", type=str, default="0.0.0.0", help="external request listen host")
    parser.add_argument("--listen-port", type=int, default=5556, help="external request listen port")
    args = parser.parse_args()

    client_cfg = cfg["client"]

    sam3_server_addr = client_cfg["sam3_server_addr"]
    downstream_server_addr = client_cfg["downstream_server_addr"]
    prompts = client_cfg["prompts"]
    obj_id_map = client_cfg.get("obj_id_map", {})
    return_masks = client_cfg.get("return_masks", True)
    clear_previous = client_cfg.get("clear_previous", True)
    output_json = client_cfg.get("output_json", "response_sam3.json") if args.save_json else None

    context = zmq.Context()
    sam3_socket, downstream_socket = recreate_req_sockets(
        context,
        sam3_server_addr,
        downstream_server_addr,
        args.req_timeout_ms,
    )

    external_socket = context.socket(zmq.REP)
    external_socket.setsockopt(zmq.LINGER, 0)
    external_socket.bind(f"tcp://{args.listen_host}:{args.listen_port}")

    print(f"SAM3 server      : {sam3_server_addr}")
    print(f"Downstream server: {downstream_server_addr}")
    print(f"External listen  : tcp://{args.listen_host}:{args.listen_port}")
    print(f"obj_id_map       : {obj_id_map}")
    print(f"REQ timeout      : {args.req_timeout_ms} ms")
    print("Waiting external JSON RGB-D requests...")

    try:
        while True:
            try:
                rgb, depth, request_data = recv_external_json_rgbd(external_socket)
                result = process_once(
                    sam3_socket=sam3_socket,
                    downstream_socket=downstream_socket,
                    rgb=rgb,
                    depth=depth,
                    prompts=prompts,
                    obj_id_map=obj_id_map,
                    req_timeout_ms=args.req_timeout_ms,
                    return_masks=return_masks,
                    clear_previous=clear_previous,
                    output_json=output_json,
                    verbose=args.v,
                    rgb_jpg_quality=args.rgb_jpg_quality,
                )
                external_socket.send_string(json.dumps(result, ensure_ascii=False))

            except TimeoutError as e:
                err = {"status": "error", "message": str(e)}
                print(f"[TIMEOUT] {e}")
                try:
                    external_socket.send_string(json.dumps(err, ensure_ascii=False))
                except Exception:
                    pass

                safe_close_socket(sam3_socket)
                safe_close_socket(downstream_socket)
                sam3_socket, downstream_socket = recreate_req_sockets(
                    context,
                    sam3_server_addr,
                    downstream_server_addr,
                    args.req_timeout_ms,
                )

            except Exception as e:
                err = {"status": "error", "message": str(e)}
                print(f"[ERROR] {e}")
                try:
                    external_socket.send_string(json.dumps(err, ensure_ascii=False))
                except Exception:
                    pass

                safe_close_socket(sam3_socket)
                safe_close_socket(downstream_socket)
                sam3_socket, downstream_socket = recreate_req_sockets(
                    context,
                    sam3_server_addr,
                    downstream_server_addr,
                    args.req_timeout_ms,
                )

    except KeyboardInterrupt:
        print("Stopped.")
    finally:
        safe_close_socket(external_socket)
        safe_close_socket(sam3_socket)
        safe_close_socket(downstream_socket)
        context.term()


if __name__ == "__main__":
    main()