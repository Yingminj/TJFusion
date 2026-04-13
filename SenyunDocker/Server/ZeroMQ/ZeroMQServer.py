import sys
sys.path.append("/usr/lib/python3/dist-packages")

import gi
gi.require_version('Gst', '1.0')
gi.require_version('GstWebRTC', '1.0')
gi.require_version('GstSdp', '1.0')
from gi.repository import Gst, GstWebRTC, GstSdp, GLib
import asyncio
import websockets
import json
import threading
import base64
import cv2
import numpy as np
import zmq
import time
import os

WS_URL = "ws://192.168.11.123:8555/quad_tile"
ZMQ_PUB_BIND = os.getenv("SENYUN_ZMQ_BIND", "tcp://127.0.0.1:4555")
ZMQ_JPEG_QUALITY = int(os.getenv("SENYUN_JPEG_QUALITY", "60"))
ZMQ_MAX_WIDTH = int(os.getenv("SENYUN_MAX_WIDTH", "2560"))

pipeline  = None
webrtcbin = None
glib_loop = None
ws_conn   = None
ws_loop   = asyncio.new_event_loop()

# ── SDP / ICE handlers (run in GLib thread via idle_add) ──────────────────
def _log(msg: str):
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)
class ZmqPublisher:
    def __init__(self, bind: str = "tcp://127.0.0.1:5555", jpeg_quality: int = 60, max_width: int = 2560):
        self._encode_params = [int(cv2.IMWRITE_JPEG_QUALITY), jpeg_quality]
        self._ctx = zmq.Context.instance()
        self._sock = self._ctx.socket(zmq.PUB)
        try:
            self._sock.setsockopt(zmq.SNDHWM, 1)
        except Exception:
            pass
        try:
            self._sock.setsockopt(zmq.LINGER, 0)
        except Exception:
            pass
        self._sock.bind(bind)

        self._latest = None
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._max_width = max_width

        self._worker = threading.Thread(target=self._worker_loop, daemon=True)
        self._worker.start()
        _log(f"ZMQ PUB bind={bind} jpeg_quality={jpeg_quality} max_width={max_width}")

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
        try:
            self._sock.close()
        except Exception:
            pass

# 全局 publisher（main 中会创建/传入）
publisher = None

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

    if transport != "UDP":
        return False
    if ":" in address:
        return False
    if address.endswith(".local"):
        return False
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

# 新增：appsink 回调，把 Gst.Buffer 复制并提交给 publisher
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

    # 尝试用 pts->epoch 映射（若失败回退到 time.time()）
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
    offer = GstWebRTC.WebRTCSessionDescription.new(
        GstWebRTC.WebRTCSDPType.OFFER, sdpmsg
    )
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
# ── GStreamer signals ─────────────────────────────────────────────────────

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
    name   = struct.get_name()  # "application/x-rtp"
    media  = struct.get_string("media")       # "video" or "audio"
    enc    = struct.get_string("encoding-name")  # "H264", "VP8", etc.

    print(f"Linking pad: media={media} encoding={enc} caps={name}")

    if media == "video":
        if enc == "H264":
            depay   = Gst.ElementFactory.make("rtph264depay",  None)
            parse   = Gst.ElementFactory.make("h264parse",     None)
            decode  = Gst.ElementFactory.make("avdec_h264",    None)
        elif enc == "VP8":
            depay   = Gst.ElementFactory.make("rtpvp8depay",   None)
            parse   = Gst.ElementFactory.make("identity",      None)  # no parse needed
            decode  = Gst.ElementFactory.make("vp8dec",        None)
        elif enc == "VP9":
            depay   = Gst.ElementFactory.make("rtpvp9depay",   None)
            parse   = Gst.ElementFactory.make("identity",      None)
            decode  = Gst.ElementFactory.make("vp9dec",        None)
        else:
            print(f"Unsupported video encoding: {enc}")
            return

        convert = Gst.ElementFactory.make("videoconvert",  None)
        # 使用 appsink，回调中把帧发到 ZMQ
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
        enc_map = {
            "OPUS":   ("rtpopusdepay",  "opusdec"),
            "PCMU":   ("rtppcmudepay",  "mulawdec"),
            "PCMA":   ("rtppcmadepay",  "alawdec"),
        }
        if enc in enc_map:
            depay_name, dec_name = enc_map[enc]
        else:
            print(f"Unsupported audio encoding: {enc}, trying decodebin")
            depay_name, dec_name = None, None

        convert  = Gst.ElementFactory.make("audioconvert",  None)
        resample = Gst.ElementFactory.make("audioresample",  None)
        asink    = Gst.ElementFactory.make("autoaudiosink",  None)

        if depay_name:
            depay  = Gst.ElementFactory.make(depay_name, None)
            decode = Gst.ElementFactory.make(dec_name,   None)
            for el in [depay, decode, convert, resample, asink]:
                pipeline.add(el)
                el.sync_state_with_parent()
            pad.link(depay.get_static_pad("sink"))
            depay.link(decode)
            decode.link(convert)
        else:
            dec = Gst.ElementFactory.make("decodebin", None)
            for el in [dec, convert, resample, asink]:
                pipeline.add(el)
                el.sync_state_with_parent()
            pad.link(dec.get_static_pad("sink"))
            dec.connect("pad-added", lambda e, p: p.link(convert.get_static_pad("sink")))

        convert.link(resample)
        resample.link(asink)
        print(f"✓ {enc} audio pipeline linked!")

    else:
        print(f"Unknown media type: {media}, skipping.")

# ── WebSocket ─────────────────────────────────────────────────────────────

async def ws_task():
    global ws_conn
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

# ── GStreamer bus ─────────────────────────────────────────────────────────

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

# ── Main ──────────────────────────────────────────────────────────────────

def main():
    global pipeline, webrtcbin, glib_loop, publisher, ws_conn

    Gst.init(None)

    pipeline  = Gst.Pipeline.new("webrtc-recv")
    webrtcbin = Gst.ElementFactory.make("webrtcbin", "recv")
    if not webrtcbin:
        print("ERROR: webrtcbin missing — install gstreamer1.0-plugins-bad")
        return

    # No STUN needed on LAN, but keep it for safety
    webrtcbin.set_property("bundle-policy", GstWebRTC.WebRTCBundlePolicy.MAX_BUNDLE)
    # webrtcbin.set_property("stun-server", "stun://stun.l.google.com:19302")
    pipeline.add(webrtcbin)

    webrtcbin.connect("on-ice-candidate",              on_ice_candidate)
    webrtcbin.connect("pad-added",                     on_pad_added)
    webrtcbin.connect("notify::ice-connection-state",  on_ice_connection_state)
    webrtcbin.connect("notify::connection-state",      on_connection_state)
    # NO on-negotiation-needed — server sends offer first

    glib_loop = GLib.MainLoop()
    bus = pipeline.get_bus()
    bus.add_signal_watch()
    bus.connect("message", on_gst_message, glib_loop)

    ws_thread = threading.Thread(target=start_ws, daemon=True)
    ws_thread.start()

    # 在启动前创建 ZMQ publisher（bind 地址按需要调整）
    publisher = ZmqPublisher(bind=ZMQ_PUB_BIND, jpeg_quality=ZMQ_JPEG_QUALITY, max_width=ZMQ_MAX_WIDTH)

    pipeline.set_state(Gst.State.PLAYING)
    print("Pipeline running, waiting for server offer...")

    try:
        glib_loop.run()
    except KeyboardInterrupt:
        pass
    finally:
        pipeline.set_state(Gst.State.NULL)
        print("Done.")

if __name__ == "__main__":
    main()
