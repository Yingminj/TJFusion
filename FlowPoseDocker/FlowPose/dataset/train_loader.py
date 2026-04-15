import webdataset as wds
from dataset.dataset import OmniXTrainDataset
from dataset.augmentation import *

def get_train_dataloader(args, shard_path, batch_size=32, num_workers=4):
    
    transform = Compose([
        ParseMetaData(),
        CropAndResize(
            img_size=args.img_size,
            dynamic_zoom_params=args.DYNAMIC_ZOOM_IN_PARAMS
        ),
        GeneratePointCloud(
            n_pts=1024,
            deform_2d_params=args.DEFORM_2D_PARAMS
        ),
        # DinoAugmentation(),
        ToTensor(args=args)
    ])

    dataset = (
        wds.WebDataset(shard_path, shardshuffle=1000)
        .shuffle(1000)
        .map(OmniXTrainDataset._pose_data_decoder, handler=wds.warn_and_continue)
        .compose(lambda src: (x for x in src for _ in range(8)))  # 8x repetition
        .map(transform)
        .select(lambda x: x is not None)  # Filter failed transforms
        .batched(batch_size, partial=False)  # batching
    )
    
    dataloader = wds.WebLoader(
        dataset,
        batch_size=None,  # batching already done by WebDataset
        num_workers=num_workers,
        pin_memory=True,
    )
    
    return dataloader