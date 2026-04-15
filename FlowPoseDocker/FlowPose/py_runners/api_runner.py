import numpy as np
import torch
import sys, os
from typing import Optional, Tuple

sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from dataset.infer_loader import get_infer_dataloader

# return combined mask and obj_ids (list of [mask_label, box_id])
def _build_obj_ids(mask: np.ndarray) -> list:
    unique_ids = np.unique(mask)
    unique_ids = unique_ids[(unique_ids != 0) & (unique_ids != 255)]
    return [[int(mid), int(mid)] for mid in unique_ids]

# PoseInferece Object
class PoseInferenceSession:

    # PoseInference Constructor
    def __init__(
        self,
        flow,
        args
    ) -> None:
        self.args = args
        # self.flow = Flow(args=self.args)
        self.flow = flow
        self.intrinsics = {
            "fx": 606.5540161132812,
            "fy": 606.3988647460938,
            "cx": 325.6007080078125,
            "cy": 252.87457275390625,
            "width": 640,
            "height": 480
        }
        self.enable_tracking = self.args.enable_tracking
        self.frame_idx = 0

    # Inference Function
    def infer(
        self,
        rgb: np.ndarray,
        depth: np.ndarray,
        mask: np.ndarray,
        obj_ids: Optional[list] = None,
        frame_idx: Optional[int] = None,
        depth_scale: float = 0.001,
    ) -> Tuple[Optional[torch.Tensor], Optional[torch.Tensor]]:
        
        if len(obj_ids) == 0:
            obj_ids = _build_obj_ids(mask)
        
        frame_data = {
            "color": rgb,
            "depth": (depth.astype(np.float32) * depth_scale * 1000.0).astype(np.uint16), # legacy depth scaling (Mr.Kang)
            "mask": mask,
        }

        data = get_infer_dataloader(frame_data, self.args)

        idx = self.frame_idx
        print("Frame: ", idx)

        if self.args.enable_tracking:
            pose, length = self.flow.inference(data, obj_ids=obj_ids, frame_idx=idx, enable_tracking=True)
        else:
            pose, length = self.flow.inference(data, obj_ids=obj_ids, frame_idx=idx, enable_tracking=False)

        self.frame_idx = idx + 1

        if not pose or not length or pose[0] is None or length[0] is None:
            print("Inference failed for frame_idx:", idx)
            return None, None

        return pose, length