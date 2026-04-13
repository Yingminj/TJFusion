import sys
import os
import time
import json
import base64
import threading
import argparse
import asyncio
import websockets
import yaml

import cv2
import numpy as np
import zmq

# 确保 GStreamer 库路径正确
sys.path.append("/usr/lib/python3/dist-packages")
import gi
gi.require_version('Gst', '1.0')
gi.require_version('GstWebRTC', '1.0')
gi.require_version('GstSdp', '1.0')
from gi.repository import Gst, GstWebRTC, GstSdp, GLib

# ── 全局变量 ──────────────────────────────────────────────────────────────
pipeline  = None
webrtcbin = None
glib_loop = None
ws_conn   = None
ws_loop   = asyncio.new_event_loop()
publisher = None
WS_URL    = ""

# ── 辅助函数 ──────────────────────────────────────────────────────────────
def _log(msg: str):
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)

def load_config(config_path: str) -> dict:
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)

# ── ZMQ Publisher (后台工作线程) ──────────────────────────────────────────
class ZmqPublisher:
    def __init__(self, bind: str, jpeg_quality: int, max_width: int, vis_enable: bool, vis_window: str):
        self._encode_params = [int(cv2.IMWRITE_JPEG_QUALITY), jpeg_quality]
        self._ctx = zmq.Context.instance()
        self._sock = self._ctx.socket(zmq.PUB)
        
        try:
            self._sock.setsockopt(zmq.SNDHWM, 1)
            self._sock.setsockopt(zmq.LINGER, 0)
        except Exception:
            pass
        self._sock.bind(bind)

        self._latest = None
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._max_width = max_width
        
        self._vis_enable = vis_enable
        self._vis_window = vis_window

        self._worker = threading.Thread(target=self._worker_loop, daemon=True)
        self._worker.start()
        _log(f"ZMQ PUB bind={bind} | jpg_quality={jpeg_quality} | max_width={max_width} | vis={vis_enable}")

    def publish_buffer(self, gst_buffer, width: int, height: int, capture_ts: float = None):
        with self._lock:
            self._latest = ("gstbuf", gst_buffer, width, height, capture_ts)

    def _compress_frame(self, frame: np.ndarray) -> np.ndarray:
        h, w = frame.shape[:2]
        if self._max_width > 0 and w > self._max_width:
            scale = self._max_width / float(w)
            frame = cv2.resize(frame, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)
        return frame

    def _worker_loop(self):
        while not self._stop.is_set():
            item = None
            with self._lock:
                if self._latest is not None:
                    item = self._latest
                    self._latest = None
                    
            if item is None:
                time.sleep(0.005)
                continue

            try:
                if isinstance(item, tuple) and item[0] == "gstbuf":
                    _, gst_buf, width, height, capture_ts = item
                    ok, map_info = gst_buf.map(Gst.MapFlags.READ)
                    if not ok:
                        continue
                    try:
                        view = np.ndarray((height, width, 3), buffer=map_info.data, dtype=np.uint8)
                        frame = np.ascontiguousarray(view)
                    finally:
                        gst_buf.unmap(map_info)
                else:
                    frame = item
                    capture_ts = None

                # 可视化逻辑
                if self._vis_enable:
                    cv2.imshow(self._vis_window, frame)
                    cv2.waitKey(1)

                frame = self._compress_frame(frame)
                ok, encoded = cv2.imencode(".jpg", frame, self._encode_params)
                if not ok:
                    _log("JPEG encode failed")
                    continue
                
                jpeg_bytes = encoded.tobytes()
                image_b64 = base64.b64encode(jpeg_bytes).decode("ascii")
                
                payload = {
                    "ts": time.time(),
                    "capture_ts": capture_ts,
                    "image": image_b64,
                    "width": frame.shape[1],
                    "height": frame.shape[0],
                }
                
                try:
                    self._sock.send_string(json.dumps(payload), flags=zmq.DONTWAIT)
                except zmq.Again:
                    # 下游慢时丢帧
                    continue
            except Exception as e:
                _log(f"PUB WORKER ERR: {e}")
                continue

    def close(self):
        self._stop.set()
        self._worker.join(timeout=1.0)
        if self._vis_enable:
            cv2.destroyAllWindows()
        try:
            self._sock.close()
        except Exception:
            pass

# ── SDP / ICE 处理逻辑 ────────────────────────────────────────────────────
def sanitize_remote_sdp(sdp_text: str) -> str:
    filtered = []
    removed = 0
    for line in sdp_text.splitlines():
        if line.startswith("a=candidate:"):
            cand = line[len("a="):]
            if not should_forward_candidate(cand):
                removed += 1
                continue
        filtered.append(line)
    if removed > 0:
        print(f"REMOTE SDP SANITIZE removed_candidates={removed}")
    return "\r\n".join(filtered) + "\r\n"

def should_forward_candidate(candidate: str) -> bool:
    parts = candidate.split()
    if len(parts) < 6:
        return False
    transport = parts[2].upper()
    address = parts[4]
    if transport != "UDP": return False
    if ":" in address: return False
    if address.endswith(".local"): return False
    return True

def sanitize_local_sdp(sdp_text: str) -> str:
    filtered = []
    removed = 0
    for line in sdp_text.splitlines():
        if line.startswith("a=candidate:"):
            cand = line[len("a="):]
            if not should_forward_candidate(cand):
                removed += 1
                continue
        filtered.append(line)
    if removed > 0:
        print(f"SDP SANITIZE removed_candidates={removed}")
    return "\r\n".join(filtered) + "\r\n"

# Appsink 回调：将 Gst.Buffer 复制并提交给 publisher
def on_appsink_sample_to_zmq(sink):
    global publisher
    sample = sink.emit("pull-sample")
    if sample is None:
        return Gst.FlowReturn.ERROR
    buf = sample.get_buffer()
    caps = sample.get_caps()
    s = caps.get_structure(0)
    width = s.get_value("width")
    height = s.get_value("height")

    try:
        buf_copy = buf.copy()
    except Exception:
        return Gst.FlowReturn.ERROR

    # 尝试用 pts->epoch 映射
    pts = getattr(buf, "pts", Gst.CLOCK_TIME_NONE)
    try:
        if pts is None or pts == Gst.CLOCK_TIME_NONE:
            raise RuntimeError("no pts")
        base_time = sink.get_parent().get_parent().get_base_time() if sink.get_parent() is not None else 0
        gst_now = sink.get_parent().get_parent().get_clock().get_time() if sink.get_parent() is not None else 0
        wall_now = time.time()
        buffer_abs = base_time + pts
        capture_ts = wall_now + (buffer_abs - gst_now) / Gst.SECOND
    except Exception:
        capture_ts = time.time()

    if publisher is not None:
        publisher.publish_buffer(buf_copy, width, height, capture_ts)
    return Gst.FlowReturn.OK

def handle_server_offer(sdp_text):
    sdp_text = sanitize_remote_sdp(sdp_text)
    print(f"Setting remote offer:\n{sdp_text[:200]}")
    _, sdpmsg = GstSdp.SDPMessage.new_from_text(sdp_text)
    offer = GstWebRTC.WebRTCSessionDescription.new(GstWebRTC.WebRTCSDPType.OFFER, sdpmsg)
    promise = Gst.Promise.new_with_change_func(on_remote_desc_set, webrtcbin, None)
    webrtcbin.emit("set-remote-description", offer, promise)
    return False

def on_remote_desc_set(promise, webrtcbin, _):
    promise.wait()
    print("Remote description set, creating answer...")
    promise2 = Gst.Promise.new_with_change_func(on_answer_created, webrtcbin, None)
    webrtcbin.emit("create-answer", None, promise2)

def on_answer_created(promise, webrtcbin, _):
    promise.wait()
    reply = promise.get_reply()
    answer = reply.get_value("answer")

    promise2 = Gst.Promise.new()
    webrtcbin.emit("set-local-description", answer, promise2)
    promise2.interrupt()

    sdp = sanitize_local_sdp(answer.sdp.as_text())
    print(f"Sending answer:\n{sdp[:200]}")
    msg = json.dumps({"type": "sdp", "data": {"type": "answer", "sdp": sdp}})
    asyncio.run_coroutine_threadsafe(ws_conn.send(msg), ws_loop)

def handle_remote_ice(candidate, mlineindex):
    if not should_forward_candidate(candidate):
        print(f"REMOTE ICE DROP [{mlineindex}]: {candidate[:80]}")
        return False
    print(f"Remote ICE [{mlineindex}]: {candidate[:80]}")
    webrtcbin.emit("add-ice-candidate", mlineindex, candidate)
    return False

# ── GStreamer 信号处理 ────────────────────────────────────────────────────
def on_ice_candidate(element, mlineindex, candidate):
    if not should_forward_candidate(candidate):
        print(f"ICE DROP [{mlineindex}]: {candidate[:80]}")
        return
    print(f"Local ICE [{mlineindex}]: {candidate[:80]}")
    msg = json.dumps({
        "type": "ice",
        "data": {"sdpMLineIndex": mlineindex, "candidate": candidate}
    })
    asyncio.run_coroutine_threadsafe(ws_conn.send(msg), ws_loop)

def on_ice_connection_state(element, pspec):
    state = element.get_property("ice-connection-state")
    print(f"ICE state: {state}")

def on_connection_state(element, pspec):
    state = element.get_property("connection-state")
    print(f"WebRTC connection state: {state}")

def on_pad_added(element, pad):
    caps = pad.get_current_caps()
    print(f"Pad added: {pad.get_name()} caps={caps.to_string() if caps else 'None'}")
    if not caps:
        pad.connect("notify::caps", lambda p, _: link_pad(p))
        return
    link_pad(pad)

def link_pad(pad):
    caps = pad.get_current_caps()
    if not caps:
        pad.connect("notify::caps", lambda p, _: link_pad(p))
        return

    struct = caps.get_structure(0)
    name   = struct.get_name() 
    media  = struct.get_string("media")       
    enc    = struct.get_string("encoding-name")

    print(f"Linking pad: media={media} encoding={enc} caps={name}")

    if media == "video":
        if enc == "H264":
            depay   = Gst.ElementFactory.make("rtph264depay",  None)
            parse   = Gst.ElementFactory.make("h264parse",     None)
            decode  = Gst.ElementFactory.make("avdec_h264",    None)
        elif enc == "VP8":
            depay   = Gst.ElementFactory.make("rtpvp8depay",   None)
            parse   = Gst.ElementFactory.make("identity",      None)
            decode  = Gst.ElementFactory.make("vp8dec",        None)
        elif enc == "VP9":
            depay   = Gst.ElementFactory.make("rtpvp9depay",   None)
            parse   = Gst.ElementFactory.make("identity",      None)
            decode  = Gst.ElementFactory.make("vp9dec",        None)
        else:
            print(f"Unsupported video encoding: {enc}")
            return

        convert = Gst.ElementFactory.make("videoconvert",  None)
        capsfilter = Gst.ElementFactory.make("capsfilter", None)
        capsfilter.set_property("caps", Gst.Caps.from_string("video/x-raw,format=BGR"))
        
        appsink = Gst.ElementFactory.make("appsink", "framesink")
        appsink.set_property("emit-signals", True)
        appsink.set_property("drop", True)
        appsink.set_property("max-buffers", 1)
        appsink.connect("new-sample", lambda s: on_appsink_sample_to_zmq(s))

        chain = [depay, parse, decode, convert, capsfilter, appsink]
        for el in chain:
            if el is None:
                print("ERROR failed_to_create_gstreamer_element")
                return
            pipeline.add(el)
            el.sync_state_with_parent()

        if pad.link(depay.get_static_pad("sink")) != Gst.PadLinkReturn.OK:
            print("ERROR failed_to_link_incoming_rtp_pad")
            return
        if parse is not None:
            depay.link(parse)
            parse.link(decode)
        else:
            depay.link(decode)
        decode.link(convert)
        convert.link(capsfilter)
        capsfilter.link(appsink)
        print(f"✓ {enc} video pipeline linked (appsink->ZMQ)!")

    elif media == "audio":
        print(f"Skipping audio stream (media={media}, encoding={enc})")
    else:
        print(f"Unknown media type: {media}, skipping.")

# ── WebSocket 通信 ────────────────────────────────────────────────────────
async def ws_task():
    global ws_conn, WS_URL
    print(f"Connecting to {WS_URL} ...")
    async with websockets.connect(WS_URL) as ws:
        ws_conn = ws
        print("WebSocket connected, waiting for server offer...")

        async for raw in ws:
            print(f"WS ← {raw[:150]}")
            try:
                msg = json.loads(raw)
            except Exception:
                print(f"Non-JSON: {raw}")
                continue

            t    = msg.get("type", "")
            data = msg.get("data", {})

            if t == "sdp":
                sdp_type = data.get("type", "")
                sdp_text = data.get("sdp",  "")
                if sdp_type == "offer":
                    GLib.idle_add(handle_server_offer, sdp_text)
                elif sdp_type == "answer":
                    print("Unexpected answer from server (we expected offer)")

            elif t == "ice":
                candidate = data.get("candidate", "")
                mline     = data.get("sdpMLineIndex", 0)
                GLib.idle_add(handle_remote_ice, candidate, mline)
            else:
                print(f"Unknown message: {msg}")

def start_ws():
    asyncio.set_event_loop(ws_loop)
    ws_loop.run_until_complete(ws_task())

def on_gst_message(bus, message, loop):
    t = message.type
    if t == Gst.MessageType.ERROR:
        err, dbg = message.parse_error()
        print(f"GST ERROR: {err}\n{dbg}")
        loop.quit()
    elif t == Gst.MessageType.EOS:
        print("GST EOS")
        loop.quit()
    elif t == Gst.MessageType.WARNING:
        w, dbg = message.parse_warning()
        print(f"GST WARNING: {w}\n{dbg}")

# ── 主程序 ────────────────────────────────────────────────────────────────
def main():
    global pipeline, webrtcbin, glib_loop, publisher, WS_URL

    # ==================== 配置解析块 ====================
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=str, default="config.yaml", help="Path to config yaml")
    args = parser.parse_args()

    cfg = load_config(args.config)
    
    # 解析 Source 参数
    source_cfg = cfg.get("source", {})
    WS_URL = source_cfg.get("ws_url", "ws://127.0.0.1:8555/quad_tile")
    expected_width = int(source_cfg.get("expected_width", 2560))
    
    # 解析 Server 参数 (ZMQ Pub Bind 地址)
    server_cfg = cfg.get("server", {})
    host = server_cfg.get("host", "0.0.0.0")
    port = int(server_cfg.get("port", 7777))
    zmq_bind_addr = f"tcp://{host}:{port}"
    
    # 解析 ZMQ 参数
    zmq_cfg = cfg.get("zmq", {})
    jpg_quality = int(zmq_cfg.get("jpg_quality", 80))
    
    # 解析 可视化 参数
    vis_cfg = cfg.get("visualization", {})
    vis_enable = vis_cfg.get("enable", False)
    vis_window = vis_cfg.get("window_name", "WebRTC Forward Preview")
    # ====================================================

    Gst.init(None)

    pipeline  = Gst.Pipeline.new("webrtc-recv")
    webrtcbin = Gst.ElementFactory.make("webrtcbin", "recv")
    if not webrtcbin:
        print("ERROR: webrtcbin missing — install gstreamer1.0-plugins-bad")
        return

    webrtcbin.set_property("bundle-policy", GstWebRTC.WebRTCBundlePolicy.MAX_BUNDLE)
    pipeline.add(webrtcbin)

    webrtcbin.connect("on-ice-candidate",              on_ice_candidate)
    webrtcbin.connect("pad-added",                     on_pad_added)
    webrtcbin.connect("notify::ice-connection-state",  on_ice_connection_state)
    webrtcbin.connect("notify::connection-state",      on_connection_state)

    glib_loop = GLib.MainLoop()
    bus = pipeline.get_bus()
    bus.add_signal_watch()
    bus.connect("message", on_gst_message, glib_loop)

    # 创建并启动 WebSocket 线程
    ws_thread = threading.Thread(target=start_ws, daemon=True)
    ws_thread.start()

    # 创建 ZMQ publisher (动态读取配置)
    publisher = ZmqPublisher(
        bind=zmq_bind_addr, 
        jpeg_quality=jpg_quality, 
        max_width=expected_width,
        vis_enable=vis_enable,
        vis_window=vis_window
    )

    pipeline.set_state(Gst.State.PLAYING)
    print("Pipeline running, waiting for server offer...")

    try:
        glib_loop.run()
    except KeyboardInterrupt:
        pass
    finally:
        pipeline.set_state(Gst.State.NULL)
        if publisher:
            publisher.close()
        print("Done.")

if __name__ == "__main__":
    main()