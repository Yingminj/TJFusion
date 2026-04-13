
import zmq
import json
import base64
import cv2
import numpy as np
import time

class ZmqVideoClient:
    """
    ZMQ SUB client for receiving video frames from the GStreamer WebRTC bridge.
    Connects to the PUB socket and displays/decodes JPEG frames.
    """
    
    def __init__(self, connect_addr: str = "tcp://127.0.0.1:5555"):
        self.ctx = zmq.Context.instance()
        self.sock = self.ctx.socket(zmq.SUB)
        
        # Subscribe to all messages (empty prefix)
        self.sock.setsockopt_string(zmq.SUBSCRIBE, "")
        
        # Set receive timeout for non-blocking checks
        self.sock.setsockopt(zmq.RCVTIMEO, 100)  # 100ms timeout
        
        # Connect to publisher
        self.sock.connect(connect_addr)
        print(f"[ZMQ Client] Connected to {connect_addr}")
        
        self.frame_count = 0
        self.start_time = time.time()
        
    def receive_frame(self, timeout_ms: int = 1000):
        """
        Receive and decode a single frame.
        Returns: (frame: np.ndarray, metadata: dict) or (None, None) on timeout
        """
        # Set timeout for this receive
        old_timeout = self.sock.rcvtimeo
        self.sock.rcvtimeo = timeout_ms
        
        try:
            msg = self.sock.recv_string()
        except zmq.Again:
            self.sock.rcvtimeo = old_timeout
            return None, None
        finally:
            self.sock.rcvtimeo = old_timeout
            
        # Parse JSON payload
        try:
            data = json.loads(msg)
        except json.JSONDecodeError as e:
            print(f"[Error] Failed to parse JSON: {e}")
            return None, None
            
        # Decode base64 JPEG
        try:
            jpeg_bytes = base64.b64decode(data["image"])
            frame = cv2.imdecode(
                np.frombuffer(jpeg_bytes, dtype=np.uint8),
                cv2.IMREAD_COLOR
            )
        except Exception as e:
            print(f"[Error] Failed to decode image: {e}")
            return None, None
            
        if frame is None:
            return None, None
            
        self.frame_count += 1
        
        # Calculate FPS
        elapsed = time.time() - self.start_time
        fps = self.frame_count / elapsed if elapsed > 0 else 0
        
        metadata = {
            "timestamp": data.get("ts"),
            "capture_timestamp": data.get("capture_ts"),
            "width": data.get("width"),
            "height": data.get("height"),
            "fps": fps,
            "frame_num": self.frame_count
        }
        
        return frame, metadata
        
    def run_display_loop(self):
        """Continuously receive and display frames using OpenCV."""
        print("[ZMQ Client] Starting display loop (Press 'q' to quit)...")
        
        try:
            while True:
                frame, meta = self.receive_frame(timeout_ms=1000)
                
                if frame is not None:
                    # Overlay info
                    info_text = f"FPS: {meta['fps']:.1f} | {meta['width']}x{meta['height']} | Frame #{meta['frame_num']}"
                    cv2.putText(frame, info_text, (10, 30), 
                               cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
                    
                    # Show latency if available
                    if meta['capture_timestamp']:
                        latency = (time.time() - meta['capture_timestamp']) * 1000
                        latency_text = f"Latency: {latency:.1f}ms"
                        cv2.putText(frame, latency_text, (10, 60),
                                   cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2)
                    
                    cv2.imshow("ZMQ Video Stream", frame)
                    
                if cv2.waitKey(1) & 0xFF == ord('q'):
                    break
                    
        except KeyboardInterrupt:
            print("\n[ZMQ Client] Interrupted by user")
        finally:
            self.close()
            
    def close(self):
        """Clean up resources."""
        self.sock.close()
        cv2.destroyAllWindows()
        print(f"[ZMQ Client] Closed. Total frames received: {self.frame_count}")


# Simple non-display version for data processing
class ZmqVideoReceiver:
    """Lightweight receiver that yields frames without OpenCV display."""
    
    def __init__(self, connect_addr: str = "tcp://127.0.0.1:4555"):
        self.ctx = zmq.Context()
        self.sock = self.ctx.socket(zmq.SUB)
        self.sock.setsockopt_string(zmq.SUBSCRIBE, "")
        self.sock.connect(connect_addr)
        
    def frames(self):
        """Generator that yields (frame_array, metadata) tuples."""
        while True:
            try:
                msg = self.sock.recv_string()
                data = json.loads(msg)
                jpeg_bytes = base64.b64decode(data["image"])
                frame = cv2.imdecode(
                    np.frombuffer(jpeg_bytes, dtype=np.uint8),
                    cv2.IMREAD_COLOR
                )
                if frame is not None:
                    yield frame, data
            except Exception as e:
                print(f"Receive error: {e}")
                continue
                
    def close(self):
        self.sock.close()
        self.ctx.term()


if __name__ == "__main__":
    import sys
    
    # Allow custom connection address from command line
    addr = sys.argv[1] if len(sys.argv) > 1 else "tcp://127.0.0.1:4555"
    
    client = ZmqVideoClient(connect_addr=addr)
    client.run_display_loop()

