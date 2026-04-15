import os
import sys
import argparse
import cv2
import numpy as np
import torch
import time
from ultralytics import YOLO

sys.path.append(os.path.dirname(os.path.dirname(__file__)))
_orig_argv = sys.argv.copy()
sys.argv = [sys.argv[0]]
from inference.inference_helper import Flow
sys.argv = _orig_argv
from inference.combined_mask import make_combined_mask
from dataset.infer_loader import get_infer_dataloader
from utils.infer_utils import draw_frame_info, show_frame
from utils.yomni_vis import visualize_detections
from args import parse_arguments
import pyrealsense2 as rs

def realsense_pipeline(w, h, fps):
    pipeline = rs.pipeline()
    cfg = rs.config()
    cfg.enable_stream(rs.stream.depth, w, h, rs.format.z16, fps)
    cfg.enable_stream(rs.stream.color, w, h, rs.format.bgr8, fps)
    profile = pipeline.start(cfg)
    align = rs.align(rs.stream.color)
    depth_sensor = profile.get_device().first_depth_sensor()
    depth_scale = depth_sensor.get_depth_scale()
    print(f'RealSense initialized (depth scale = {depth_scale} m/unit)')
    return pipeline, align, depth_scale

def wait_frames(pipeline):
    try:
        frames = pipeline.wait_for_frames(timeout_ms=1000)
        return frames
    except Exception as e:
        print(f'RealSense frame timeout or error: {e}. Retrying...')
        pipeline.stop()
        time.sleep(1)

def release_realsense(pipeline=None, align=None):
    try:
        if pipeline is not None:
            pipeline.stop()
            
    except Exception as e:
        print(f'Error stopping RealSense pipeline: {e}')
    finally:
        del pipeline
        del align
        time.sleep(0.5)

def process_frame(frame, depth_raw, flow, yolo, args, writer, frame_idx, depth_scale):
    # run YOLO
    results = yolo.track(frame, persist=True, tracker="bytetrack.yaml", verbose=False)
    # results = yolo.track(frame, conf = 0.8, verbose=False)
    boxes = results[0].boxes
    masks = results[0].masks
    # show YOLO detections
    annotated_frame = results[0].plot()
    cv2.imshow('YOLO', annotated_frame)

    # check for no detections
    if masks is None or len(masks.data) == 0:
        vis = frame.copy()
        num_detections = 0
        draw_frame_info(vis, frame_idx, 0.00, num_detections)
        show_frame(vis, writer, args)
        return None, None, 0.0

    # Extract track IDs for pose persistence
    box_ids = None
    if boxes is not None and hasattr(boxes, 'id') and boxes.id is not None:
        box_ids = [int(id_val) for id_val in boxes.id.cpu().numpy()]

    combined_mask, obj_ids = make_combined_mask(frame.shape[0], frame.shape[1], masks, box_ids)

    if obj_ids is None or (len(np.unique(combined_mask)) != len(obj_ids)):
        vis = frame.copy()
        num_detections = len(masks.data) if masks is not None else 0
        draw_frame_info(vis, frame_idx, None, num_detections)
        show_frame(vis, writer, args)
        return None, None, 0.0

    frame_data = {
        "color": frame,
        "depth": (depth_raw.astype(np.float32) * depth_scale * 1000).astype(np.uint16) if depth_raw is not None else None,
        "mask": combined_mask
    }

    try:
        data = get_infer_dataloader(frame_data, args)
    except Exception as e:
        print(f'Error in get_infer_dataloader: {e}')
        return None, None, 0.0

    obj_ids = list(filter(lambda row: row != [0,0] and row != [255,255], obj_ids))
    if len(obj_ids) == 0 or data is None:
        return None, None, 0.0

    t0 = time.time()
    if args.tracking:
        pose, length = flow.inference(data, obj_ids=obj_ids, frame_idx=frame_idx, enable_tracking=True)
    else:
        pose, length = flow.inference(data, obj_ids=obj_ids, frame_idx=frame_idx, enable_tracking=False)
    t1 = time.time()

    vis = frame.copy()
    valid_output = (
        isinstance(pose, (list, tuple)) and isinstance(length, (list, tuple))
        and len(pose) > 0 and len(length) > 0
        and pose[0] is not None and length[0] is not None
    )

    if valid_output:
        all_final_pose = pose[0].to(torch.float32).cpu().numpy()
        all_final_length = length[0].to(torch.float32).cpu().numpy()
        vis = visualize_detections(vis, all_final_pose, all_final_length, data.cam_intrinsics, color=(0, 255, 0), thickness=2, alpha=0.1)

    num_detections = len(masks.data) if masks is not None else 0
    draw_frame_info(vis, frame_idx, t1-t0, num_detections)
    show_frame(vis, writer, args)
    return pose, length, t1 - t0

def main():
    args = parse_arguments()
    VIDEO_WIDTH, VIDEO_HEIGHT = 640, 480
    VIDEO_FPS = 30
    rs_pipeline = None
    rs_align = None
    depth_scale = None

    device = args.device if torch.cuda.is_available() and 'cuda' in args.device else 'cpu'

    flow = Flow(args)
    yolo = YOLO("results/ckpts/YOLO/best.pt")

    rs_pipeline, rs_align, depth_scale = realsense_pipeline(VIDEO_WIDTH, VIDEO_HEIGHT, VIDEO_FPS)

    writer = None
    frame_idx = 0
    frames = None

    try:
        while True:
            frames = wait_frames(rs_pipeline)
            if frames is None:
                rs_pipeline, rs_align, depth_scale = realsense_pipeline(VIDEO_WIDTH, VIDEO_HEIGHT, VIDEO_FPS)
                continue
            aligned = rs_align.process(frames)
            depth_frame = aligned.get_depth_frame()
            color_frame = aligned.get_color_frame()
            if not depth_frame or not color_frame:
                continue
            frame = np.asanyarray(color_frame.get_data())
            depth_raw = np.asanyarray(depth_frame.get_data())

            pose, length, infer_time = process_frame(frame, depth_raw, flow, yolo, args, writer, frame_idx, depth_scale)
            frame_idx += 1

    except KeyboardInterrupt:
        print('Interrupted by user')

    finally:
        if args.realsense and rs_pipeline is not None:
            try:
                release_realsense(rs_pipeline, rs_align)
                rs_pipeline.stop()
            except Exception:
                pass
        if writer is not None:
            writer.release()
        if args.show:
            cv2.destroyAllWindows()

if __name__ == '__main__':
    main()