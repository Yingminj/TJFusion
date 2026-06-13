#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""SAM3 as a standard-protocol ``mask`` server.

Promptable segmentation: given a color image and text prompts, return a single
combined label mask plus (optionally) per-instance masks and aligned identity
lists.  Contract: protocol/schemas/mask.json.

  request.arrays  : color [H,W,3] uint8
  request.fields  : prompts (string list), return_masks?, clear_previous?
  response.arrays : combined_mask [H,W] uint8 (label image), masks? [N,H,W] uint8
  response.fields : obj_ids, class_names, instance_names, scores

The segmentation math is lifted verbatim from the old base64-JSON
``Server/Sam3/ZeroMQServer.py``; only the I/O layer changed (no base64, no
matplotlib visualization) and the model now subclasses ``BaseModelServer``.
"""

from __future__ import annotations

import os

import numpy as np
import yaml
from PIL import Image

from tjfusion_protocol.envelope import Message
from tjfusion_protocol.server import BaseModelServer

from sam3.model_builder import build_sam3_image_model
from sam3.model.sam3_image_processor import Sam3Processor

CONFIG_PATH = os.environ.get("SAM3_CONFIG", "/workspace/config.yaml")


def _load_config(path: str = CONFIG_PATH) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


class Sam3MaskServer(BaseModelServer):
    data_type = "mask"

    def __init__(self, *, bind_addr: str, config_path: str = CONFIG_PATH) -> None:
        super().__init__(bind_addr=bind_addr)
        self.config_path = config_path
        self.score_threshold = 0.4
        self.checkpoint_path = ""
        self.processor = None

    def load_model(self) -> None:
        cfg = _load_config(self.config_path)
        self.checkpoint_path = cfg["sam3"]["checkpoint_path"]
        self.score_threshold = float(cfg["sam3"].get("score_threshold", 0.4))

        print(f"[mask] loading SAM3 from {self.checkpoint_path} ...")
        model = build_sam3_image_model(
            checkpoint_path=self.checkpoint_path,
            load_from_HF=False,
            enable_segmentation=True,
        )
        self.processor = Sam3Processor(model)
        print(f"[mask] SAM3 ready (score_threshold={self.score_threshold}).")

    def infer(self, request: Message) -> Message:
        color = request.arrays["color"]                 # uint8 [H,W,3] RGB
        prompts = request.fields.get("prompts", []) or []
        return_masks = bool(request.fields.get("return_masks", True))

        image = Image.fromarray(np.ascontiguousarray(color)).convert("RGB")
        h, w = color.shape[:2]

        inference_state = self.processor.set_image(image)

        combined_mask = np.zeros((h, w), dtype=np.uint8)
        per_instance: list[np.ndarray] = []
        obj_ids: list[list[int]] = []
        class_names: list[str] = []
        instance_names: list[str] = []
        scores: list[float] = []
        global_det_id = 1

        for prompt in prompts:
            output = self.processor.set_text_prompt(state=inference_state, prompt=prompt)
            current_masks = output["masks"].cpu().numpy()
            current_scores = output["scores"].cpu().numpy()

            for i in range(len(current_scores)):
                score = float(current_scores[i])
                if score <= self.score_threshold:
                    continue

                mask = current_masks[i].squeeze()
                binary_mask = (mask > 0.5).astype(np.uint8) * 255

                combined_mask[binary_mask > 0] = global_det_id
                if return_masks:
                    per_instance.append(binary_mask)
                obj_ids.append([int(global_det_id), int(global_det_id)])
                class_names.append(str(prompt))
                instance_names.append(str(prompt))
                scores.append(score)
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
            },
        )


def main() -> None:
    cfg = _load_config()
    server_cfg = cfg.get("server", {})
    host = server_cfg.get("host", "0.0.0.0")
    port = int(server_cfg.get("port", 5562))
    bind_addr = f"tcp://{host}:{port}"
    Sam3MaskServer(bind_addr=bind_addr).serve_forever()


if __name__ == "__main__":
    main()
