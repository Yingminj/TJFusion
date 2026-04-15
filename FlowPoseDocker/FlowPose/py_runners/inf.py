import numpy as np
import cv2
from argparse import Namespace
from api_runner import PoseInferenceSession
from inference.combined_mask import make_combined_mask
from inference.inference_helper import Flow
from ultralytics import YOLO

def main():

    args = Namespace(
        pretrained_flow_model_path = "results/ckpts/FlowNet/ckpt_epoch5.pth",
        pretrained_scale_model_path = "results/ckpts/ScaleNet/scalenet.pth",
        device = "cuda",
        img_size = 224,
        n_pts = 1024,
        frame_gap_threshold = 10,
        # T0 = 10,
        # Tp = 10,
        eval_repeat_num = 25,
        retain_ratio = 0.4,
        enable_tracking = False,
        seed = 0,
        dropout = 0,
        use_edm_aug = False,
        log_dir = 'debug',
        use_pretrain = False,
        is_train = False,
        pose_mode = 'rot_matrix',
        optimizer = 'Adam',
        lr = 1e-2,
        lr_decay = 0.98,
        num_points = 1024,
        scale_embedding = 180,
        ema_rate = 0.999,
        repeat_num = 20,
        clustering = 1,
        clustering_eps = 0.05,
        clustering_minpts = 0.1667,
        
    )

    yolo = YOLO("results/ckpts/YOLO/best.pt")
    flow = Flow(args)

    inferencer = PoseInferenceSession(flow, args)

    rgb_path = '/media/kewei/KMD_DATA/own/infer/ikea/0000/0000_color.png'
    depth_path = '/media/kewei/KMD_DATA/own/infer/ikea/0000/0000_depth.exr'

    rgb = cv2.imread(rgb_path, cv2.IMREAD_COLOR).astype(np.uint8)
    depth = cv2.imread(depth_path, cv2.IMREAD_ANYDEPTH).astype(np.float32)

    # cv2.imshow("RGB", rgb)
    # cv2.waitKey(0)
    
    # YOLO results
    results = yolo.track(rgb, persist=True, tracker="bytetrack.yaml", verbose=False, conf=0.8)
    masks = results[0].masks
    boxes = results[0].boxes
    if boxes.id is not None:
        box_ids = [int(id_val) for id_val in boxes.id.cpu().numpy()]
    
    # combined mask and obj_ids for tracking
    combined_mask, obj_ids = make_combined_mask(rgb.shape[0], rgb.shape[1], masks, box_ids)
    obj_ids = list(filter(lambda row: row != [0,0] and row != [255,255], obj_ids))

    ##
    # pose: List[torch.Tensor] of shape (N, 4, 4)
    # length: List[torch.Tensor]
    ##
    pose, length = inferencer.infer(rgb, depth, combined_mask, obj_ids)
    print("Pose:", pose)
    print("Length:", length)


if __name__ == "__main__":  
    main()