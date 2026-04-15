import torch
from dataset.dataset import OmniXInferDataset

def get_infer_dataloader(frame_data, args):
    return OmniXInferDataset.alternetive_init(frame_data, img_size=args.img_size, device=torch.device(args.device), n_pts=args.n_pts)