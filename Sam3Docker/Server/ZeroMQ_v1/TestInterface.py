#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
import time
import base64
import argparse
import zmq
import cv2
import numpy as np


def save_json(data, path: str):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def recreate_req_socket(context, server_addr, timeout_ms):
    sock = context.socket(zmq.REQ)
    sock.setsockopt(zmq.RCVTIMEO, timeout_ms)
    sock.setsockopt(zmq.SNDTIMEO, timeout_ms)
    sock.connect(server_addr)
    return sock


def safe_close_socket(sock):
    try:
        sock.close(0)
    except Exception:
        pass


def recv_latest_rgbd(sub_socket, timeout_ms=3000):
    """
    从 zmq-source 取最新一帧:
      [meta_json, color_bytes, depth_bytes]
    """
    poller = zmq.Poller()
    poller.register(sub_socket, zmq.POLLIN)

    socks = dict(poller.poll(timeout_ms))
    if sub_socket not in socks:
        raise TimeoutError(f"Timeout waiting for ZMQ source message ({timeout_ms} ms)")

    latest_parts = None

    parts = sub_socket.recv_multipart()
    if len(parts) == 3:
        latest_parts = parts

    while True:
        try:
            parts = sub_socket.recv_multipart(flags=zmq.NOBLOCK)
            if len(parts) == 3:
                latest_parts = parts
        except zmq.Again:
            break

    if latest_parts is None:
        raise RuntimeError("No valid 3-part multipart message received from zmq-source.")

    meta_bytes, color_bytes, depth_bytes = latest_parts
    meta = json.loads(meta_bytes.decode("utf-8"))

    color_np = np.frombuffer(color_bytes, dtype=np.uint8)
    color = cv2.imdecode(color_np, cv2.IMREAD_COLOR)
    if color is None:
        raise RuntimeError("Failed to decode color image from zmq-source.")

    if "depth_shape" not in meta:
        raise RuntimeError("ZMQ source meta missing 'depth_shape'.")

    depth_shape = tuple(meta["depth_shape"])
    depth_dtype_name = meta.get("depth_dtype", "uint16")

    dtype_map = {
        "uint16": np.uint16,
        "float32": np.float32,
        "float64": np.float64,
    }
    depth_dtype = dtype_map.get(depth_dtype_name, np.uint16)
    depth = np.frombuffer(depth_bytes, dtype=depth_dtype).reshape(depth_shape)

    return meta, color, depth, color_bytes


def encode_png_base64(img: np.ndarray) -> str:
    ok, buf = cv2.imencode(".png", img)
    if not ok:
        raise RuntimeError("Failed to encode PNG image.")
    return base64.b64encode(buf.tobytes()).decode("utf-8")


def print_objects_summary(response):
    objects = response.get("objects", [])
    if not isinstance(objects, list) or len(objects) == 0:
        return

    print("Objects:")
    for i, obj in enumerate(objects):
        if not isinstance(obj, dict):
            continue
        name = obj.get("name", "")
        obj_id = obj.get("obj_id", [])
        box_id = obj.get("box_id", None)
        print(f"  [{i}] name={name}, obj_id={obj_id}, box_id={box_id}")


def forward_one_frame(req_socket, color_bytes, depth, save_request=None, save_response=None):
    """
    把 zmq-source 的一帧，转成当前中间 client 需要的 JSON 格式：
    {
        "rgb_image": "...",
        "depth_image": "..."
    }
    """
    rgb_b64 = base64.b64encode(color_bytes).decode("utf-8")
    depth_b64 = encode_png_base64(depth)

    request_data = {
        "rgb_image": rgb_b64,
        "depth_image": depth_b64,
    }

    if save_request:
        save_json(request_data, save_request)

    t0 = time.time()
    req_socket.send_string(json.dumps(request_data, ensure_ascii=False))
    response_str = req_socket.recv_string()
    elapsed = time.time() - t0

    response_data = json.loads(response_str)

    if save_response:
        wrapped = {
            "elapsed_sec": round(elapsed, 4),
            "response": response_data
        }
        save_json(wrapped, save_response)

    return response_data, elapsed


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-addr", type=str, default="tcp://127.0.0.1:4444", help="zmq-source SUB address")
    parser.add_argument("--server-addr", type=str, default="tcp://127.0.0.1:5556", help="middle client address")
    parser.add_argument("--source-timeout-ms", type=int, default=3000, help="timeout for source frame")
    parser.add_argument("--req-timeout-ms", type=int, default=10000, help="timeout for request/response")
    parser.add_argument("--save-request", type=str, default="live_request.json", help="save latest request json")
    parser.add_argument("--save-response", type=str, default="live_response.json", help="save latest response json")
    parser.add_argument("--show", action="store_true", help="show source rgb/depth")
    args = parser.parse_args()

    context = zmq.Context()

    # 订阅 zmq-source
    sub_socket = context.socket(zmq.SUB)
    sub_socket.setsockopt(zmq.RCVHWM, 1)
    sub_socket.connect(args.source_addr)
    sub_socket.setsockopt(zmq.SUBSCRIBE, b"")

    # 发给中间 client
    req_socket = recreate_req_socket(context, args.server_addr, args.req_timeout_ms)

    print(f"ZMQ source : {args.source_addr}")
    print(f"Server     : {args.server_addr}")
    print("Receiving live RGB-D and forwarding...")

    try:
        while True:
            try:
                meta, color, depth, color_bytes = recv_latest_rgbd(
                    sub_socket, timeout_ms=args.source_timeout_ms
                )
            except Exception as e:
                print(f"[SOURCE ERROR] {e}")
                continue

            if args.show:
                depth_vis = depth.astype(np.float32)
                valid = np.isfinite(depth_vis)
                if np.any(valid):
                    mn = depth_vis[valid].min()
                    mx = depth_vis[valid].max()
                    if mx > mn:
                        depth_vis = (depth_vis - mn) / (mx - mn)
                    else:
                        depth_vis[:] = 0
                else:
                    depth_vis[:] = 0

                depth_vis = np.clip(depth_vis * 255, 0, 255).astype(np.uint8)
                depth_vis = cv2.applyColorMap(depth_vis, cv2.COLORMAP_JET)

                show_color = color
                if show_color.shape[:2] != depth_vis.shape[:2]:
                    show_color = cv2.resize(show_color, (depth_vis.shape[1], depth_vis.shape[0]))

                combined = np.hstack((show_color, depth_vis))
                cv2.imshow("Live RGB | Depth", combined)
                if cv2.waitKey(1) & 0xFF == 27:
                    break

            try:
                response, elapsed = forward_one_frame(
                    req_socket=req_socket,
                    color_bytes=color_bytes,
                    depth=depth,
                    save_request=args.save_request,
                    save_response=args.save_response,
                )

                print(json.dumps(response, indent=2, ensure_ascii=False))
                print_objects_summary(response)
                print(f"[FORWARD DONE] elapsed={elapsed:.4f}s")

            except zmq.error.Again:
                print(f"[REQUEST ERROR] Timeout after {args.req_timeout_ms} ms")
                safe_close_socket(req_socket)
                req_socket = recreate_req_socket(context, args.server_addr, args.req_timeout_ms)

            except Exception as e:
                print(f"[REQUEST ERROR] {e}")
                safe_close_socket(req_socket)
                req_socket = recreate_req_socket(context, args.server_addr, args.req_timeout_ms)

    except KeyboardInterrupt:
        print("Stopped.")
    finally:
        safe_close_socket(sub_socket)
        safe_close_socket(req_socket)
        context.term()
        if args.show:
            cv2.destroyAllWindows()


if __name__ == "__main__":
    main()