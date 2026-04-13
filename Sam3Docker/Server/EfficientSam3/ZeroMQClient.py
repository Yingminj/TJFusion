# ZeroMQClient_EfficientSAM3.py
import zmq
import base64
import json
import cv2
import numpy as np
from PIL import Image
from io import BytesIO


def image_file_to_base64(image_path: str) -> str:
    with open(image_path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


def decode_mask_b64_to_numpy(mask_b64: str) -> np.ndarray:
    mask_bytes = base64.b64decode(mask_b64)
    mask_np = np.frombuffer(mask_bytes, dtype=np.uint8)
    mask_img = cv2.imdecode(mask_np, cv2.IMREAD_GRAYSCALE)
    return mask_img


def visualize_response(image_path: str, response: dict, save_path="efficientsam3_client_result.png"):
    image = cv2.imread(image_path)
    if image is None:
        print(f"[WARN] Failed to read image for visualization: {image_path}")
        return

    overlay = image.copy()

    detections = response.get("detections", [])

    for det in detections:
        score = det["score"]
        box = det["bbox_xyxy"]
        x1, y1, x2, y2 = map(int, box)

        # 画框
        cv2.rectangle(overlay, (x1, y1), (x2, y2), (0, 255, 0), 2)
        cv2.putText(
            overlay,
            f"{score:.2f}",
            (x1, max(20, y1 - 5)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.6,
            (0, 255, 0),
            2,
        )

        # 叠加 mask
        if "mask_png_b64" in det:
            mask = decode_mask_b64_to_numpy(det["mask_png_b64"])
            if mask is not None:
                color_mask = np.zeros_like(image)
                color_mask[:, :, 2] = mask  # 红色通道
                overlay = cv2.addWeighted(overlay, 1.0, color_mask, 0.25, 0)

    cv2.imwrite(save_path, overlay)
    print(f"[INFO] Visualization saved to: {save_path}")


def main():
    zmq_addr = "tcp://127.0.0.1:5555"   # 改成你的 server 地址
    image_path = "image.jpg"

    prompts = ["dog", "person", "woman"]

    request = {
        "request_id": "test_001",
        "prompts": prompts,
        "clear_previous": True,
        "return_masks": True,
        "rgb_image": image_file_to_base64(image_path),
    }

    context = zmq.Context()
    socket = context.socket(zmq.REQ)
    socket.connect(zmq_addr)

    print(f"[INFO] Connected to {zmq_addr}")
    print(f"[INFO] Sending request with prompts: {prompts}")

    socket.send_json(request)
    response = socket.recv_json()

    print("\n========== RESPONSE ==========")
    print(json.dumps(response, indent=2, ensure_ascii=False))
    print("================================\n")

    if response.get("status") == "ok":
        timing = response.get("timing", {})
        print("[TIMING]")
        print(f"decode_sec          : {timing.get('decode_sec')}")
        print(f"vis_prep_sec        : {timing.get('vis_prep_sec')}")
        print(f"image_embedding_sec : {timing.get('image_embedding_sec')}")
        print(f"prompt_total_sec    : {timing.get('prompt_total_sec')}")
        print(f"draw_sec            : {timing.get('draw_sec')}")
        print(f"total_request_sec   : {timing.get('total_request_sec')}")
        print(f"fps                 : {timing.get('fps')}")
        print(f"fps_smooth          : {timing.get('fps_smooth')}")

        print("\n[PROMPT BREAKDOWN]")
        for item in timing.get("prompt_breakdown", []):
            print(f"prompt={item['prompt']}, elapsed_sec={item['elapsed_sec']}")

        print(f"\n[DETECTIONS] num={response.get('num_detections', 0)}")
        for det in response.get("detections", []):
            print(
                f"track_id={det['track_id']}, "
                f"class_id={det['class_id']}, "
                f"score={det['score']:.4f}, "
                f"bbox={det['bbox_xyxy']}"
            )

        visualize_response(image_path, response)
    else:
        print(f"[ERROR] Request failed: {response.get('message')}")

    socket.close()
    context.term()


if __name__ == "__main__":
    main()