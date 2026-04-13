import json
import cv2
import numpy as np
import zmq


def recv_latest_rgbd(sub_socket, timeout_ms=3000):
    """
    只取最新一帧 multipart:
    [meta_json, color_jpg_bytes, depth_bytes]
    和当前 server 对齐：
      meta = {"depth_shape": ...}
      color = jpg bytes
      depth = uint16 bytes
    """
    poller = zmq.Poller()
    poller.register(sub_socket, zmq.POLLIN)

    socks = dict(poller.poll(timeout_ms))
    if sub_socket not in socks:
        raise TimeoutError(f"Timeout waiting for ZMQ message ({timeout_ms} ms)")

    latest_parts = None

    parts = sub_socket.recv_multipart()
    if len(parts) == 3:
        latest_parts = parts

    # 清空积压，只保留最后一帧
    while True:
        try:
            parts = sub_socket.recv_multipart(flags=zmq.NOBLOCK)
            if len(parts) == 3:
                latest_parts = parts
        except zmq.Again:
            break

    if latest_parts is None:
        raise RuntimeError("No valid 3-part multipart message received.")

    meta_bytes, color_bytes, depth_bytes = latest_parts
    meta = json.loads(meta_bytes.decode("utf-8"))

    # ---------- RGB ----------
    color_np = np.frombuffer(color_bytes, dtype=np.uint8)
    color = cv2.imdecode(color_np, cv2.IMREAD_COLOR)
    if color is None:
        raise RuntimeError("Failed to decode color image.")

    # ---------- Depth ----------
    if "depth_shape" not in meta:
        raise RuntimeError("Missing 'depth_shape' in meta.")

    depth_shape = tuple(meta["depth_shape"])
    depth = np.frombuffer(depth_bytes, dtype=np.uint16).reshape(depth_shape)

    return meta, color, depth


def visualize_depth(depth_u16):
    """
    当前 server 发的是 uint16 毫米深度
    这里显示时转成 float32 便于归一化
    """
    depth_mm = depth_u16.astype(np.float32)

    valid = depth_mm > 0
    if np.any(valid):
        dmin_mm = float(depth_mm[valid].min())
        dmax_mm = float(depth_mm[valid].max())
    else:
        dmin_mm, dmax_mm = 0.0, 1.0

    norm = np.zeros_like(depth_mm, dtype=np.float32)
    if dmax_mm > dmin_mm:
        norm[valid] = (depth_mm[valid] - dmin_mm) / (dmax_mm - dmin_mm)
    elif np.any(valid):
        norm[valid] = 1.0

    depth_u8 = (norm * 255).astype(np.uint8)
    depth_color = cv2.applyColorMap(depth_u8, cv2.COLORMAP_JET)

    # 转成米方便显示
    dmin_m = dmin_mm / 1000.0
    dmax_m = dmax_mm / 1000.0
    return depth_color, dmin_m, dmax_m


def draw_info_panel(image, depth_min_m, depth_max_m):
    lines = [
        "depth_dtype=uint16(mm)",
        f"depth_range=[{depth_min_m:.3f}, {depth_max_m:.3f}] m",
    ]

    y0 = 30
    for i, text in enumerate(lines):
        y = y0 + i * 30
        cv2.putText(
            image,
            text,
            (20, y),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.8,
            (0, 255, 0),
            2,
            cv2.LINE_AA
        )


def main():
    context = zmq.Context()
    socket = context.socket(zmq.SUB)

    # 尽量减少积压
    socket.setsockopt(zmq.RCVHWM, 1)
    socket.connect("tcp://127.0.0.1:4445")
    socket.setsockopt(zmq.SUBSCRIBE, b"")

    print("Subscriber started...")

    cv2.namedWindow("RGB + Depth", cv2.WINDOW_NORMAL)

    try:
        while True:
            try:
                meta, color, depth = recv_latest_rgbd(socket, timeout_ms=3000)
            except TimeoutError as e:
                print(e)
                continue
            except Exception as e:
                print(f"Receive/decode failed: {e}")
                continue

            # ---------- Depth visualization ----------
            depth_vis, dmin_m, dmax_m = visualize_depth(depth)

            # ---------- 拼接 ----------
            if color.shape[:2] != depth_vis.shape[:2]:
                color = cv2.resize(color, (depth_vis.shape[1], depth_vis.shape[0]))

            combined = np.hstack((color, depth_vis))

            # ---------- 信息 ----------
            draw_info_panel(combined, dmin_m, dmax_m)

            # ---------- 显示 ----------
            cv2.imshow("RGB + Depth", combined)

            if cv2.waitKey(1) & 0xFF == 27:
                break

    finally:
        cv2.destroyAllWindows()
        socket.close(0)
        context.term()


if __name__ == "__main__":
    main()