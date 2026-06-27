#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""YOLO as a standard-protocol ``mask`` server.

Migrated off the old base64-JSON protocol: this now subclasses
``BaseModelServer`` and speaks the shared NumPy-multipart wire format, so it is a
drop-in alternative to SAM3 as the mask/detection source (contract:
protocol/schemas/mask.json).  The output layout matches ``Sam3Docker`` exactly
(combined label mask + aligned obj_ids/class_names/instance_names) so downstream
FlowPose can consume either interchangeably.

  request.arrays  : color [H,W,3] uint8
  request.fields  : prompts? (filter to these class names), return_masks?,
                    conf?, tracker?, persist?
  response.arrays : combined_mask [H,W] uint8 (label image), masks? [N,H,W]
  response.fields : obj_ids, class_names, instance_names, scores, detections

The tracking / classify / detect branches are lifted from the old server; only
the I/O layer changed (no base64, no cv2 window / annotated-image upload).
"""

from __future__ import annotations

import os

import numpy as np
import yaml
from ultralytics import YOLO

from tjfusion_protocol.envelope import Message
from tjfusion_protocol.server import BaseModelServer

CONFIG_PATH = os.environ.get("YOLO_CONFIG", "/workspace/config.yaml")


def _load_config(path: str = CONFIG_PATH) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def _normalize_prompt_set(prompts) -> set[str]:
    if not prompts:
        return set()
    return {str(p).strip().lower() for p in prompts if str(p).strip()}


class YOLOStatusServer(BaseModelServer):
    data_type = "mask"

    def __init__(self, *, bind_addr: str, config_path: str = CONFIG_PATH) -> None:
        super().__init__(bind_addr=bind_addr)
        self.config_path = config_path
        self.yolo = None
        self.model_task = "detect"
        self.model_path = ""
        self.score_threshold = 0.4
        self.tracker = "bytetrack.yaml"
        self.persist = True
        self.return_masks = True

    def load_model(self) -> None:
        cfg = _load_config(self.config_path)
        yolo_cfg = cfg.get("yolo", {})
        self.model_path = yolo_cfg.get("model_path", "/workspace/model/best.pt")
        self.score_threshold = float(yolo_cfg.get("score_threshold", 0.4))
        self.tracker = yolo_cfg.get("tracker", "bytetrack.yaml")
        self.persist = bool(yolo_cfg.get("persist", True))
        self.return_masks = bool(yolo_cfg.get("return_masks", True))

        print(f"[mask] loading YOLO from {self.model_path} ...")
        self.yolo = YOLO(self.model_path)
        self.model_task = getattr(self.yolo, "task", "detect")
        print(f"[mask] YOLO ready (task={self.model_task}, score_threshold={self.score_threshold}).")

    def _class_name(self, names, class_id: int) -> str:
        if isinstance(names, dict) and class_id in names:
            return str(names[class_id])
        if isinstance(names, (list, tuple)) and 0 <= class_id < len(names):
            return str(names[class_id])
        return str(class_id)

    def infer(self, request: Message) -> Message:
        color = request.arrays["color"]                 # uint8 [H,W,3]
        prompts = request.fields.get("prompts", []) or []
        return_masks = bool(request.fields.get("return_masks", self.return_masks))
        conf = float(request.fields.get("conf", self.score_threshold))
        tracker = request.fields.get("tracker", self.tracker)
        persist = bool(request.fields.get("persist", self.persist))

        rgb = np.ascontiguousarray(color)
        h, w = rgb.shape[:2]

        # The wire format is RGB system-wide, but Ultralytics interprets a numpy
        # array as BGR (cv2 convention). Flip channels only for the model input.
        bgr = np.ascontiguousarray(rgb[:, :, ::-1])

        if self.model_task == "classify":
            results = self.yolo.predict(bgr, verbose=False, conf=conf)
        else:
            results = self.yolo.track(
                bgr, persist=persist, tracker=tracker, verbose=False, conf=conf,
            )
        result0 = results[0] if results else None

        prompt_set = _normalize_prompt_set(prompts)

        combined_mask = np.zeros((h, w), dtype=np.uint8)
        per_instance: list[np.ndarray] = []
        obj_ids: list[list[int]] = []
        class_names: list[str] = []
        instance_names: list[str] = []
        scores: list[float] = []
        detections: list[dict] = []
        global_det_id = 1

        if result0 is not None and getattr(result0, "boxes", None) is not None and len(result0.boxes) > 0:
            boxes = result0.boxes
            masks = getattr(result0, "masks", None)
            names = result0.names if hasattr(result0, "names") else self.yolo.names

            xyxy = boxes.xyxy.cpu().numpy() if boxes.xyxy is not None else None
            cls = boxes.cls.cpu().numpy() if boxes.cls is not None else None
            box_conf = boxes.conf.cpu().numpy() if boxes.conf is not None else None
            track_ids = boxes.id.cpu().numpy() if getattr(boxes, "id", None) is not None else None
            mask_data = (
                masks.data.cpu().numpy()
                if (masks is not None and masks.data is not None) else None
            )

            for i in range(len(boxes)):
                class_id = int(cls[i]) if cls is not None else -1
                score = float(box_conf[i]) if box_conf is not None else 0.0
                label = self._class_name(names, class_id)

                if prompt_set and label.strip().lower() not in prompt_set and str(class_id) not in prompt_set:
                    continue

                # Build the per-instance binary mask: real segmentation if the
                # model produces it, otherwise fall back to the bbox rectangle.
                if mask_data is not None and i < len(mask_data):
                    binary_mask = (mask_data[i] > 0.5).astype(np.uint8) * 255
                    if binary_mask.shape[:2] != (h, w):
                        # ultralytics masks can be at model resolution; pad/crop-safe resize.
                        import cv2
                        binary_mask = cv2.resize(binary_mask, (w, h), interpolation=cv2.INTER_NEAREST)
                else:
                    binary_mask = np.zeros((h, w), dtype=np.uint8)
                    if xyxy is not None:
                        x1, y1, x2, y2 = (int(round(v)) for v in xyxy[i].tolist())
                        x1, y1 = max(0, x1), max(0, y1)
                        x2, y2 = min(w, x2), min(h, y2)
                        binary_mask[y1:y2, x1:x2] = 255

                combined_mask[binary_mask > 0] = global_det_id
                if return_masks:
                    per_instance.append(binary_mask)

                track_id = int(track_ids[i]) if track_ids is not None else global_det_id
                obj_ids.append([track_id, int(global_det_id)])
                class_names.append(label)
                instance_names.append(label)
                scores.append(score)
                detections.append({
                    "id": int(global_det_id),
                    "track_id": track_id,
                    "class": label,
                    "class_id": class_id,
                    "score": score,
                    "bbox": [float(v) for v in xyxy[i].tolist()] if xyxy is not None else [],
                })
                global_det_id += 1

        arrays: dict[str, np.ndarray] = {"combined_mask": combined_mask}
        if return_masks:
            if per_instance:
                arrays["masks"] = np.stack(per_instance, axis=0).astype(np.uint8)
            else:
                arrays["masks"] = np.zeros((0, h, w), dtype=np.uint8)

        return self.ok(
            request,
            arrays=arrays,
            fields={
                "obj_ids": obj_ids,
                "class_names": class_names,
                "instance_names": instance_names,
                "scores": scores,
                "detections": detections,
            },
        )


def main() -> None:
    cfg = _load_config()
    server_cfg = cfg.get("server", {})
    host = server_cfg.get("host", "0.0.0.0")
    port = int(server_cfg.get("port", 5555))
    bind_addr = f"tcp://{host}:{port}"
    YOLOStatusServer(bind_addr=bind_addr).serve_forever()


if __name__ == "__main__":
    main()
