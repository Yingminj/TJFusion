import base64
import json
import uuid
import zmq
import time
import argparse
import yaml
import cv2
import pyrealsense2 as rs
import numpy as np
import threading


def load_config(config_path="ClientConfig.yaml"):
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def encode_file_to_base64(path: str) -> str:
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


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


class LatestFrameBuffer:
    def __init__(self):
        self.lock = threading.Lock()
        self.rgb = None
        self.depth = None
        self.meta = None
        self.frame_id = 0
        self.timestamp = 0.0

    def update(self, rgb, depth, meta=None):
        with self.lock:
            self.rgb = rgb
            self.depth = depth
            self.meta = meta
            self.frame_id += 1
            self.timestamp = time.time()

    def get(self):
        with self.lock:
            if self.rgb is None or self.depth is None:
                return None, None, None, None, None
            return (
                self.rgb.copy(),
                self.depth.copy(),
                self.meta,
                self.frame_id,
                self.timestamp,
            )


class RealSenseGrabber:
    def __init__(self, width=640, height=480, fps=30, align_to_color=True):
        self.pipeline = rs.pipeline()
        self.config = rs.config()
        self.config.enable_stream(rs.stream.color, width, height, rs.format.bgr8, fps)
        self.config.enable_stream(rs.stream.depth, width, height, rs.format.z16, fps)
        self.pipeline.start(self.config)
        self.align = rs.align(rs.stream.color) if align_to_color else None

        for _ in range(5):
            try:
                frames = self.pipeline.wait_for_frames(timeout_ms=1000)
                if self.align is not None:
                    self.align.process(frames)
            except Exception:
                pass

    def get_rgbd_latest(self, timeout_sec=3.0):
        start = time.time()
        latest_frames = None

        while time.time() - start < timeout_sec:
            try:
                latest_frames = self.pipeline.wait_for_frames(timeout_ms=200)
                break
            except Exception:
                pass

        if latest_frames is None:
            raise RuntimeError("Failed to get RealSense RGB-D frame within timeout.")

        while True:
            frames = self.pipeline.poll_for_frames()
            if not frames:
                break
            latest_frames = frames

        if self.align is not None:
            latest_frames = self.align.process(latest_frames)

        color_frame = latest_frames.get_color_frame()
        depth_frame = latest_frames.get_depth_frame()

        if not color_frame or not depth_frame:
            raise RuntimeError("Latest RealSense frame is invalid.")

        color_image = np.asanyarray(color_frame.get_data())
        depth_image = np.asanyarray(depth_frame.get_data())

        if color_image is None or color_image.size == 0:
            raise RuntimeError("Latest RealSense RGB is empty.")
        if depth_image is None or depth_image.size == 0:
            raise RuntimeError("Latest RealSense depth is empty.")

        return color_image, depth_image

    def close(self):
        try:
            self.pipeline.stop()
        except Exception:
            pass


def recv_zmq_rgbd(zmq_sub_socket, timeout_sec=3.0):
    poller = zmq.Poller()
    poller.register(zmq_sub_socket, zmq.POLLIN)

    socks = dict(poller.poll(int(timeout_sec * 1000)))
    if zmq_sub_socket not in socks:
        raise RuntimeError(f"Timeout waiting for ZMQ RGB-D data ({timeout_sec}s).")

    latest_parts = None

    parts = zmq_sub_socket.recv_multipart()
    if len(parts) == 3:
        latest_parts = parts

    while True:
        try:
            parts = zmq_sub_socket.recv_multipart(flags=zmq.NOBLOCK)
            if len(parts) == 3:
                latest_parts = parts
        except zmq.Again:
            break

    if latest_parts is None or len(latest_parts) != 3:
        raise RuntimeError("Invalid ZMQ multipart message.")

    meta_bytes, color_bytes, depth_bytes = latest_parts
    meta = json.loads(meta_bytes.decode())

    color_np = np.frombuffer(color_bytes, dtype=np.uint8)
    color = cv2.imdecode(color_np, cv2.IMREAD_COLOR)
    if color is None:
        raise RuntimeError("Failed to decode ZMQ color image.")

    if "depth_shape" not in meta:
        raise RuntimeError("ZMQ meta missing 'depth_shape'.")

    depth_shape = tuple(meta["depth_shape"])
    depth = np.frombuffer(depth_bytes, dtype=np.uint16).reshape(depth_shape)

    return color, depth, meta


def print_response(response, verbose=False, title="RESPONSE"):
    request_id = response.get("request_id", "unknown")
    print(f"========== {title} {request_id} ==========")
    if verbose:
        print(json.dumps(response, indent=2, ensure_ascii=False))
    else:
        status = response.get("status", "unknown")
        elapsed = response.get("elapsed_sec", "N/A")
        print(f"status={status}, elapsed_sec={elapsed}")
        if "num_detections" in response:
            print(f"num_detections={response.get('num_detections')}")
    print("=" * 67 + "\n")


def mask_to_uint8(mask, h, w):
    if isinstance(mask, list):
        mask = np.array(mask)

    if mask.ndim == 3:
        mask = mask[..., 0]

    if mask.shape[:2] != (h, w):
        mask = cv2.resize(mask.astype(np.uint8), (w, h), interpolation=cv2.INTER_NEAREST)

    if mask.dtype == np.bool_:
        mask = mask.astype(np.uint8) * 255
    elif mask.dtype != np.uint8:
        mask = (mask > 0).astype(np.uint8) * 255

    return mask


def decode_mask_item(mask_item, h, w):
    if isinstance(mask_item, str):
        mask = decode_b64_image_to_np(mask_item, cv2.IMREAD_GRAYSCALE)
        return mask_to_uint8(mask, h, w)

    if isinstance(mask_item, np.ndarray):
        return mask_to_uint8(mask_item, h, w)

    if isinstance(mask_item, list):
        return mask_to_uint8(np.array(mask_item), h, w)

    if isinstance(mask_item, dict):
        for k in ["mask", "segmentation", "binary_mask"]:
            if k in mask_item:
                return decode_mask_item(mask_item[k], h, w)

    raise ValueError(f"Unsupported mask item type: {type(mask_item)}")


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
                sam3_response = inner
                break

    return sam3_response


def build_combined_mask_obj_ids_and_class_names_from_sam3(
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

    for i, det in enumerate(detections):
        if not isinstance(det, dict):
            continue

        mask_b64 = det.get("mask_png_b64", None)
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

        label = det.get(
            "label",
            det.get(
                "class_name",
                det.get(
                    "name",
                    det.get("prompt", prompts[i] if i < len(prompts) else None)
                )
            )
        )

        if label is not None and str(label) in obj_id_map:
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

        if label is None:
            class_names.append(f"obj_{inst_id}")
        else:
            class_names.append(str(label))

        inst_id += 1
        if inst_id >= 255:
            raise ValueError("Too many instances for uint8 combined_mask.")

    filtered_obj_ids = []
    filtered_class_names = []

    for obj_id, class_name in zip(obj_ids, class_names):
        if obj_id != [0, 0] and obj_id != [255, 255]:
            filtered_obj_ids.append(obj_id)
            filtered_class_names.append(class_name)

    if len(filtered_obj_ids) == 0:
        raise ValueError("SAM3 detections found, but no valid masks were decoded.")

    return combined_mask, filtered_obj_ids, filtered_class_names


def make_req_socket(context, addr, timeout_ms):
    sock = context.socket(zmq.REQ)
    sock.setsockopt(zmq.RCVTIMEO, timeout_ms)
    sock.setsockopt(zmq.SNDTIMEO, timeout_ms)
    sock.connect(addr)
    return sock


def zmq_capture_loop(zmq_sub_socket, frame_buffer, zmq_timeout, stop_flag):
    while not stop_flag["stop"]:
        try:
            rgb, depth, meta = recv_zmq_rgbd(zmq_sub_socket, timeout_sec=zmq_timeout)
            frame_buffer.update(rgb, depth, meta)
        except Exception:
            time.sleep(0.01)


def realsense_capture_loop(realsense_grabber, frame_buffer, rs_timeout, stop_flag):
    while not stop_flag["stop"]:
        try:
            rgb, depth = realsense_grabber.get_rgbd_latest(timeout_sec=rs_timeout)
            frame_buffer.update(rgb, depth, None)
        except Exception:
            time.sleep(0.01)


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
    except zmq.error.Again:
        raise TimeoutError(f"SAM3 send timeout after {req_timeout_ms} ms")

    try:
        sam3_response = sam3_socket.recv_json()
    except zmq.error.Again:
        raise TimeoutError(f"SAM3 response timeout after {req_timeout_ms} ms")

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
        return sam3_response, None

    combined_mask_np, obj_ids, class_names = build_combined_mask_obj_ids_and_class_names_from_sam3(
        sam3_response=sam3_response,
        h=rgb.shape[0],
        w=rgb.shape[1],
        obj_id_map=obj_id_map,
        prompts=prompts,
    )

    if len(obj_ids) == 0 or np.count_nonzero(combined_mask_np) == 0:
        print(f"[DONE] {request_id} | empty_mask={time.time() - t0:.3f}s")
        return sam3_response, None

    combined_mask_b64 = encode_png_base64(combined_mask_np)
    depth_b64 = encode_png_base64(depth)

    downstream_request = {
        "request_id": request_id,
        "rgb_image": rgb_b64,
        "depth_image": depth_b64,
        "combined_mask": combined_mask_b64,
        "obj_ids": obj_ids,
        "class_names": class_names,
    }

    try:
        downstream_socket.send_json(downstream_request)
    except zmq.error.Again:
        raise TimeoutError(f"FlowPose send timeout after {req_timeout_ms} ms")

    try:
        downstream_response = downstream_socket.recv_json()
    except zmq.error.Again:
        raise TimeoutError(f"FlowPose response timeout after {req_timeout_ms} ms")

    t2 = time.time()

    if verbose:
        print_response(downstream_response, verbose=True, title="FLOWPOSE RESPONSE")

    print(
        f"[DONE] {request_id} | "
        f"sam3={t1 - t0:.3f}s "
        f"flow={t2 - t1:.3f}s "
        f"total={t2 - t0:.3f}s "
        f"class_names={class_names}"
    )
    return sam3_response, downstream_response


def main():
    cfg = load_config()

    parser = argparse.ArgumentParser()
    parser.add_argument("-t", action="store_true", help="enable periodic processing")
    parser.add_argument("-v", action="store_true", help="print verbose response")
    parser.add_argument("-r", action="store_true", help="use RealSense RGB-D instead of local image")
    parser.add_argument("--zmq-source", action="store_true", help="use ZMQ SUB RGB-D source")
    parser.add_argument("-d", type=float, default=3.0, help="RealSense frame timeout in seconds")
    parser.add_argument("--zmq-timeout", type=float, default=3.0, help="ZMQ RGB-D receive timeout in seconds")
    parser.add_argument("--req-timeout-ms", type=int, default=1000, help="REQ/REP send/recv timeout in ms")
    parser.add_argument("--save-json", action="store_true", help="save SAM3 response json to disk")
    parser.add_argument("--rgb-jpg-quality", type=int, default=85, help="RGB jpg quality for requests")
    args = parser.parse_args()

    client_cfg = cfg["client"]

    sam3_server_addr = client_cfg["sam3_server_addr"]
    downstream_server_addr = client_cfg["downstream_server_addr"]

    rgb_path = client_cfg.get("rgb_path", None)
    depth_path = client_cfg.get("depth_path", None)
    prompts = client_cfg["prompts"]
    obj_id_map = client_cfg.get("obj_id_map", {})
    return_masks = client_cfg.get("return_masks", True)
    clear_previous = client_cfg.get("clear_previous", True)
    output_json = client_cfg.get("output_json", "response_sam3.json") if args.save_json else None
    zmq_source_addr = client_cfg.get("zmq_source_addr", "tcp://localhost:6000")

    context = zmq.Context()
    sam3_socket = make_req_socket(context, sam3_server_addr, args.req_timeout_ms)
    downstream_socket = make_req_socket(context, downstream_server_addr, args.req_timeout_ms)

    print(f"SAM3 server      : {sam3_server_addr}")
    print(f"Downstream server: {downstream_server_addr}")
    print(f"obj_id_map       : {obj_id_map}")
    print(f"REQ timeout      : {args.req_timeout_ms} ms")

    stop_flag = {"stop": False}
    capture_thread = None
    frame_buffer = LatestFrameBuffer()
    realsense_grabber = None
    zmq_sub_socket = None

    try:
        if args.zmq_source:
            zmq_sub_socket = context.socket(zmq.SUB)
            zmq_sub_socket.setsockopt(zmq.RCVHWM, 1)
            zmq_sub_socket.connect(zmq_source_addr)
            zmq_sub_socket.setsockopt(zmq.SUBSCRIBE, b"")
            print(f"ZMQ RGB-D source : {zmq_source_addr}, timeout={args.zmq_timeout} sec")

            capture_thread = threading.Thread(
                target=zmq_capture_loop,
                args=(zmq_sub_socket, frame_buffer, args.zmq_timeout, stop_flag),
                daemon=True,
            )
            capture_thread.start()

        elif args.r:
            realsense_grabber = RealSenseGrabber(width=640, height=480, fps=30, align_to_color=True)
            print(f"RealSense RGB-D mode enabled. timeout={args.d} sec")

            capture_thread = threading.Thread(
                target=realsense_capture_loop,
                args=(realsense_grabber, frame_buffer, args.d, stop_flag),
                daemon=True,
            )
            capture_thread.start()

        else:
            print(f"Image file mode enabled. rgb_path={rgb_path}, depth_path={depth_path}")
            rgb = cv2.imread(rgb_path, cv2.IMREAD_COLOR)
            depth = cv2.imread(depth_path, cv2.IMREAD_UNCHANGED)
            if rgb is None:
                raise RuntimeError(f"Failed to read rgb image: {rgb_path}")
            if depth is None:
                raise RuntimeError(f"Failed to read depth image: {depth_path}")
            frame_buffer.update(rgb, depth, None)

        print("Processing latest frame only...")

        last_processed_frame_id = -1

        while True:
            rgb, depth, meta, frame_id, frame_ts = frame_buffer.get()

            if rgb is None or depth is None:
                time.sleep(0.005)
                continue

            if frame_id == last_processed_frame_id:
                time.sleep(0.001)
                continue

            last_processed_frame_id = frame_id
            age_ms = (time.time() - frame_ts) * 1000.0 if frame_ts is not None else -1.0

            print(f"\n[PROCESS] frame_id={frame_id}, age={age_ms:.1f} ms")

            try:
                process_once(
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
            except TimeoutError as e:
                print(f"[TIMEOUT] {e} -> skip current frame and continue.")
                try:
                    sam3_socket.close(0)
                except Exception:
                    pass
                try:
                    downstream_socket.close(0)
                except Exception:
                    pass
                sam3_socket = make_req_socket(context, sam3_server_addr, args.req_timeout_ms)
                downstream_socket = make_req_socket(context, downstream_server_addr, args.req_timeout_ms)
            except Exception as e:
                print(f"[ERROR] {e} -> skip current frame and continue.")
                try:
                    sam3_socket.close(0)
                except Exception:
                    pass
                try:
                    downstream_socket.close(0)
                except Exception:
                    pass
                sam3_socket = make_req_socket(context, sam3_server_addr, args.req_timeout_ms)
                downstream_socket = make_req_socket(context, downstream_server_addr, args.req_timeout_ms)

            if not args.t:
                break

    except KeyboardInterrupt:
        print("Stopped.")
    finally:
        stop_flag["stop"] = True
        if capture_thread is not None:
            capture_thread.join(timeout=1.0)
        if realsense_grabber is not None:
            realsense_grabber.close()
        if zmq_sub_socket is not None:
            zmq_sub_socket.close(0)
        sam3_socket.close(0)
        downstream_socket.close(0)
        context.term()


if __name__ == "__main__":
    main()