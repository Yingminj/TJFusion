import torch
import time
import zmq
import base64
from PIL import Image
from sam3.model_builder import build_sam3_image_model
from sam3.model.sam3_image_processor import Sam3Processor
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.patches as patches
import io
import cv2
import yaml
import traceback

SERVER_VERSION = "v2"


def load_config(config_path="/workspace/config.yaml"):
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def _ts():
    return time.strftime("%Y-%m-%d %H:%M:%S")


def print_sam3_startup(version, config_path, host, port, visualize=True, vis_wait=0):
    print("=" * 70)
    print("SAM3 ZeroMQ Server")
    print("=" * 70)
    print(f"[{_ts()}] version      : {version}")
    print(f"[{_ts()}] config_path  : {config_path}")
    print(f"[{_ts()}] host         : {host}")
    print(f"[{_ts()}] port         : {port}")
    print(f"[{_ts()}] visualize    : {visualize}")
    print(f"[{_ts()}] vis_wait     : {vis_wait}")
    print("=" * 70)


def log_info(msg):
    print(f"[{_ts()}] [INFO] {msg}", flush=True)


def log_warn(msg):
    print(f"[{_ts()}] [WARN] {msg}", flush=True)


def log_error(msg):
    print(f"[{_ts()}] [ERROR] {msg}", flush=True)


def log_success(msg):
    print(f"[{_ts()}] [OK] {msg}", flush=True)


def log_kv(key, value):
    print(f"[{_ts()}] [INFO] {key}: {value}", flush=True)


def show_mask(mask, ax, color=None):
    if color is None:
        color = np.concatenate([np.random.random(3), np.array([0.6])], axis=0)
    else:
        color = np.array(list(color) + [0.6])
    h, w = mask.shape[-2:]
    mask_image = mask.reshape(h, w, 1) * color.reshape(1, 1, -1)
    ax.imshow(mask_image)


def show_box(box, score, label, ax):
    x1, y1, x2, y2 = box
    w, h = x2 - x1, y2 - y1
    rect = patches.Rectangle(
        (x1, y1), w, h, linewidth=2, edgecolor="green", facecolor="none"
    )
    ax.add_patch(rect)
    ax.text(
        x1,
        y1 - 5,
        f"{label}: {score:.2f}",
        fontsize=12,
        color="white",
        backgroundcolor="green",
    )


def encode_mask_to_base64_png(mask: np.ndarray) -> str:
    if mask.dtype != np.uint8:
        mask = mask.astype(np.uint8)
    success, buf = cv2.imencode(".png", mask, [cv2.IMWRITE_PNG_COMPRESSION, 3])
    if not success:
        raise RuntimeError("Failed to encode mask to PNG.")
    return base64.b64encode(buf.tobytes()).decode("utf-8")


def main():
    cfg = load_config()

    host = cfg["server"].get("host", "0.0.0.0")
    port = int(cfg["server"]["port"])
    score_threshold = float(cfg["sam3"].get("score_threshold", 0.4))

    print_sam3_startup(
        version=SERVER_VERSION,
        config_path="ServerConfig.yaml",
        host=host,
        port=port,
        visualize=True,
        vis_wait=0,
    )

    log_info("Initializing ZeroMQ context...")
    context = zmq.Context()
    socket = context.socket(zmq.REP)

    bind_host = "*" if host in ("0.0.0.0", "*") else host
    socket.bind(f"tcp://{bind_host}:{port}")
    log_success(f"ZeroMQ REP socket bound at tcp://{bind_host}:{port}")

    log_info("Loading SAM3 model, please wait...")
    start_load_time = time.time()

    model = build_sam3_image_model(
        checkpoint_path=cfg["sam3"]["checkpoint_path"],
        load_from_HF=False,
        enable_segmentation=True,
    )
    processor = Sam3Processor(model)

    end_load_time = time.time()
    log_success(f"Model loaded successfully in {end_load_time - start_load_time:.2f} seconds")

    log_info("SAM3 runtime configuration:")
    log_kv("checkpoint_path", cfg["sam3"]["checkpoint_path"])
    log_kv("score_threshold", score_threshold)
    log_kv("segmentation", True)

    log_success(f"Server is running and listening on port {port}")

    plt.ion()
    fig, ax = plt.subplots(figsize=(10, 8))
    plt.show(block=False)

    fps_smooth = None
    fps_alpha = 0.2
    fps_text = None

    while True:
        message = socket.recv_json()
        request_total_start = time.time()

        request_id = message.get("request_id", "")
        prompts = message.get("prompts", [])
        clear_previous = message.get("clear_previous", True)

        log_info(f"Received request_id={request_id}")
        log_kv("prompts", prompts)
        log_kv("clear_previous", clear_previous)

        try:
            t_decode_start = time.time()

            image_b64 = message.get("rgb_image", None)
            if image_b64 is None:
                raise ValueError("Missing required field 'rgb_image' in request.")

            image_data = base64.b64decode(image_b64)
            image = Image.open(io.BytesIO(image_data)).convert("RGB")
            image_np = np.array(image)

            decode_time = time.time() - t_decode_start
            log_info(f"Image decode time: {decode_time:.4f} s")

            t_vis_prep_start = time.time()
            if clear_previous:
                ax.clear()
                ax.imshow(image_np)
                ax.axis("off")
            vis_prep_time = time.time() - t_vis_prep_start
            log_info(f"Visualization prep time: {vis_prep_time:.4f} s")

            log_info("Extracting global image features...")
            t_embed_start = time.time()
            inference_state = processor.set_image(image)
            embed_time = time.time() - t_embed_start
            log_info(f"Image embedding time: {embed_time:.4f} s")

            detections = []
            global_det_id = 1
            prompt_timings = []

            t_prompt_total_start = time.time()

            for prompt_idx, prompt in enumerate(prompts):
                log_info(f"Running prompt: '{prompt}'")
                start_prompt_time = time.time()

                output = processor.set_text_prompt(state=inference_state, prompt=prompt)

                prompt_duration = time.time() - start_prompt_time
                prompt_timings.append({
                    "prompt": prompt,
                    "elapsed_sec": round(prompt_duration, 4),
                })
                log_success(f"Prompt '{prompt}' finished in {prompt_duration:.4f} s")

                current_masks = output["masks"].cpu().numpy()
                current_boxes = output["boxes"].cpu().numpy()
                current_scores = output["scores"].cpu().numpy()

                for i in range(len(current_scores)):
                    score = float(current_scores[i])
                    if score <= score_threshold:
                        continue

                    box = current_boxes[i]
                    mask = current_masks[i].squeeze()

                    instance_color = plt.colormaps.get_cmap("tab20")(np.random.randint(0, 20))[:3]
                    show_mask(mask, ax, color=instance_color)
                    show_box(box, score, prompt, ax)

                    binary_mask = (mask > 0.5).astype(np.uint8) * 255

                    det = {
                        "id": int(global_det_id),
                        "label": str(prompt),
                        "score": score,
                        "bbox": [float(v) for v in box.tolist()],
                        "mask_png_b64": encode_mask_to_base64_png(binary_mask),
                    }

                    detections.append(det)
                    global_det_id += 1

            prompt_total_time = time.time() - t_prompt_total_start
            log_info(f"All prompts total time: {prompt_total_time:.4f} s")

            total_request_time = time.time() - request_total_start
            fps = 1.0 / total_request_time if total_request_time > 1e-8 else 0.0

            if fps_smooth is None:
                fps_smooth = fps
            else:
                fps_smooth = fps_alpha * fps + (1.0 - fps_alpha) * fps_smooth

            log_info(f"Total request time: {total_request_time:.4f} s")
            log_info(f"FPS: {fps:.2f}, Smoothed FPS: {fps_smooth:.2f}")

            if fps_text is not None:
                try:
                    fps_text.remove()
                except Exception:
                    pass
                fps_text = None

            fps_text = ax.text(
                10,
                30,
                f"FPS: {fps:.2f} | Avg FPS: {fps_smooth:.2f} | Single Reasoning(s): {total_request_time:.4f}",
                fontsize=14,
                color="yellow",
                bbox=dict(facecolor="black", alpha=0.6, edgecolor="none"),
                verticalalignment="top",
            )

            t_draw_start = time.time()
            fig.canvas.draw()
            fig.canvas.flush_events()
            draw_time = time.time() - t_draw_start
            log_info(f"Matplotlib draw time: {draw_time:.4f} s")

            response = {
                "status": "ok",
                "request_id": request_id,
                "detections": detections,
                "elapsed_sec": round(total_request_time, 4),
            }

            socket.send_json(response)
            log_success(
                f"Response sent successfully | request_id={request_id} | "
                f"num_detections={len(detections)} | total={total_request_time:.4f}s | fps={fps:.2f}"
            )

        except Exception as e:
            total_request_time = time.time() - request_total_start
            log_error(f"Request failed: {e}")
            print(traceback.format_exc())
            log_info(f"Elapsed before failure: {total_request_time:.4f} s")
            socket.send_json({
                "status": "error",
                "request_id": request_id,
                "message": str(e),
                "elapsed_sec": round(total_request_time, 4),
            })


if __name__ == "__main__":
    main()