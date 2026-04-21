import argparse
import base64
import time
import traceback

import cv2
import numpy as np
import yaml
import zmq
from ultralytics import YOLO

SERVER_VERSION = "v2"


def load_config(config_path: str = "/workspace/config.yaml"):
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def _ts():
    return time.strftime("%Y-%m-%d %H:%M:%S")


def log_info(msg):
    print(f"[{_ts()}] [INFO] {msg}", flush=True)


def log_error(msg):
    print(f"[{_ts()}] [ERROR] {msg}", flush=True)


def log_success(msg):
    print(f"[{_ts()}] [OK] {msg}", flush=True)


def decode_bgr_from_base64(image_b64: str) -> np.ndarray:
    image_data = base64.b64decode(image_b64)
    image_array = np.frombuffer(image_data, dtype=np.uint8)
    image_bgr = cv2.imdecode(image_array, cv2.IMREAD_COLOR)
    if image_bgr is None:
        raise ValueError("Failed to decode input image from base64.")
    return image_bgr


def encode_mask_to_base64_png(mask: np.ndarray) -> str:
    if mask.dtype != np.uint8:
        mask = mask.astype(np.uint8)
    success, buf = cv2.imencode(".png", mask, [cv2.IMWRITE_PNG_COMPRESSION, 3])
    if not success:
        raise RuntimeError("Failed to encode mask to PNG.")
    return base64.b64encode(buf.tobytes()).decode("utf-8")


def encode_bgr_to_base64_jpg(image_bgr: np.ndarray, quality: int = 90) -> str:
    success, buf = cv2.imencode(".jpg", image_bgr, [cv2.IMWRITE_JPEG_QUALITY, int(quality)])
    if not success:
        raise RuntimeError("Failed to encode image to JPG.")
    return base64.b64encode(buf.tobytes()).decode("utf-8")


class YOLOZMQServer:
    def __init__(self, config_path: str = "/workspace/config.yaml"):
        self.cfg = load_config(config_path)

        server_cfg = self.cfg.get("server", {})
        yolo_cfg = self.cfg.get("yolo", {})

        self.host = server_cfg.get("host", "0.0.0.0")
        self.port = int(server_cfg.get("port", 5555))

        self.model_path = yolo_cfg.get("model_path", "results/drawer_cup.pt")
        self.score_threshold = float(yolo_cfg.get("score_threshold", 0.4))
        self.tracker = "bytetrack.yaml"
        self.persist = True
        self.return_masks = True
        self.return_annotated_image = True
        self.show_window = True
        self.window_name = "YOLO Detections"
        self._window_available = True

        print("=" * 70)
        print("YOLO ZeroMQ Server")
        print("=" * 70)
        log_info(f"version      : {SERVER_VERSION}")
        log_info(f"config_path  : {config_path}")
        log_info(f"host         : {self.host}")
        log_info(f"port         : {self.port}")
        log_info(f"model_path   : {self.model_path}")
        log_info(f"score_thresh : {self.score_threshold}")
        print("=" * 70)

        log_info("Loading YOLO model, please wait...")
        t0 = time.time()
        self.yolo = YOLO(self.model_path)
        self.model_task = getattr(self.yolo, "task", "detect")
        log_success(f"Model loaded in {time.time() - t0:.2f} s")
        log_info(f"model_task   : {self.model_task}")

        self.context = zmq.Context()
        self.socket = self.context.socket(zmq.REP)
        bind_host = "*" if self.host in ("0.0.0.0", "*") else self.host
        self.socket.bind(f"tcp://{bind_host}:{self.port}")
        log_success(f"ZeroMQ REP socket bound at tcp://{bind_host}:{self.port}")

    def get_class_id(self, class_name):
        """Get class id by class name from model names."""
        if class_name is None:
            return None
        target = str(class_name).strip().lower()
        if not target:
            return None

        names = getattr(self.yolo, "names", None)
        if isinstance(names, dict):
            for class_id, name in names.items():
                if str(name).strip().lower() == target:
                    return int(class_id)
        elif isinstance(names, (list, tuple)):
            for class_id, name in enumerate(names):
                if str(name).strip().lower() == target:
                    return int(class_id)
        return None

    def process_request(self, req: dict) -> dict:
        request_total_start = time.time()

        request_id = req.get("request_id", "")
        _ = req.get("prompts", [])  # Keep request schema compatibility, but ignore prompt filtering.
        _ = req.get("clear_previous", True)  # Keep same input interface as SAM3

        if "bgr_image" in req:
            bgr = decode_bgr_from_base64(req["bgr_image"])
        elif "rgb_image" in req:
            # Backward-compatible fallback for older clients.
            bgr = decode_bgr_from_base64(req["rgb_image"])
        else:
            raise ValueError("Missing required field 'bgr_image' in request.")

        conf = float(req.get("conf", self.score_threshold))
        tracker = req.get("tracker", self.tracker)
        persist = bool(req.get("persist", self.persist))
        return_masks = bool(req.get("return_masks", self.return_masks))
        return_annotated_image = bool(req.get("return_annotated_image", self.return_annotated_image))
        show_window = bool(req.get("show_window", self.show_window))

        if self.model_task == "classify":
            results = self.yolo.predict(
                bgr,
                verbose=False,
                conf=conf,
            )
        else:
            results = self.yolo.track(
                bgr,
                persist=persist,
                tracker=tracker,
                verbose=False,
                conf=conf,
            )

        detections = []
        global_det_id = 1
        annotated_image_b64 = None

        result0 = results[0] if results else None
        if result0 is not None:
            annotated_bgr = result0.plot()
        else:
            annotated_bgr = bgr.copy()

        if return_annotated_image:
            annotated_image_b64 = encode_bgr_to_base64_jpg(annotated_bgr)

        if show_window and self._window_available:
            try:
                cv2.imshow(self.window_name, annotated_bgr)
                cv2.waitKey(1)
            except Exception as e:
                self._window_available = False
                log_error(f"OpenCV window display disabled: {e}")

        if self.model_task == "classify":
            names = result0.names if (result0 is not None and hasattr(result0, "names")) else self.yolo.names
            probs = result0.probs if result0 is not None else None
            if probs is not None and hasattr(probs, "top5") and hasattr(probs, "top5conf"):
                top5_ids = probs.top5
                top5_confs = probs.top5conf.tolist()
                for class_id, score in zip(top5_ids, top5_confs):
                    class_id = int(class_id)
                    label = (
                        str(names[class_id])
                        if isinstance(names, dict) and class_id in names
                        else str(class_id)
                    )
                    detections.append(
                        {
                            "id": int(global_det_id),
                            "label": label,
                            "class": label,
                            "class_id": class_id,
                            "score": float(score),
                            "bbox": [],
                        }
                    )
                    global_det_id += 1
        elif result0 is not None and result0.boxes is not None and len(result0.boxes) > 0:
            boxes = result0.boxes
            masks = result0.masks

            xyxy = boxes.xyxy.cpu().numpy() if boxes.xyxy is not None else None
            cls = boxes.cls.cpu().numpy() if boxes.cls is not None else None
            scores = boxes.conf.cpu().numpy() if boxes.conf is not None else None
            mask_data = masks.data.cpu().numpy() if (masks is not None and masks.data is not None) else None

            names = result0.names if hasattr(result0, "names") else self.yolo.names

            for i in range(len(boxes)):
                class_id = int(cls[i]) if cls is not None else -1
                score = float(scores[i]) if scores is not None else 0.0

                label = str(names[class_id]) if isinstance(names, dict) and class_id in names else str(class_id)
                det = {
                    "id": int(global_det_id),
                    "label": label,
                    "class": label,
                    "class_id": class_id,
                    "score": score,
                    "bbox": [float(v) for v in xyxy[i].tolist()] if xyxy is not None else [],
                }

                if return_masks and mask_data is not None and i < len(mask_data):
                    binary_mask = (mask_data[i] > 0.5).astype(np.uint8) * 255
                    det["mask_png_b64"] = encode_mask_to_base64_png(binary_mask)
                elif return_masks and xyxy is not None:
                    # Fallback for detect-only models without segmentation heads.
                    x1, y1, x2, y2 = [int(round(v)) for v in xyxy[i].tolist()]
                    h, w = bgr.shape[:2]
                    x1 = max(0, min(x1, w - 1))
                    x2 = max(0, min(x2, w))
                    y1 = max(0, min(y1, h - 1))
                    y2 = max(0, min(y2, h))
                    if x2 > x1 and y2 > y1:
                        binary_mask = np.zeros((h, w), dtype=np.uint8)
                        binary_mask[y1:y2, x1:x2] = 255
                        det["mask_png_b64"] = encode_mask_to_base64_png(binary_mask)

                detections.append(det)
                global_det_id += 1

        total_request_time = time.time() - request_total_start
        return {
            "status": "ok",
            "request_id": request_id,
            "num_detections": len(detections),
            "detections": detections,
            "annotated_image_b64": annotated_image_b64,
            "elapsed_sec": round(total_request_time, 4),
        }

    def serve_forever(self):
        while True:
            message = self.socket.recv_json()
            request_id = message.get("request_id", "")
            log_info(f"Received request_id={request_id}")

            try:
                resp = self.process_request(message)
                self.socket.send_json(resp)
                log_success(
                    f"Response sent | request_id={request_id} | "
                    f"num_detections={len(resp.get('detections', []))} | "
                    f"elapsed={resp.get('elapsed_sec', 0):.4f}s"
                )
            except Exception as e:
                elapsed = 0.0
                log_error(f"Request failed: {e}")
                print(traceback.format_exc())
                err = {
                    "status": "error",
                    "request_id": request_id,
                    "message": str(e),
                    "elapsed_sec": round(elapsed, 4),
                }
                try:
                    self.socket.send_json(err)
                except Exception:
                    pass


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=str, default="/workspace/config.yaml", help="Path to config yaml")
    args = parser.parse_args()

    server = YOLOZMQServer(config_path=args.config)
    server.serve_forever()


if __name__ == "__main__":
    main()
