import webdataset as wds
from dataset.dataset import OmniXValDataset
from dataset.augmentation import *

def flatten_per_object(src):
    """Flatten samples when per_object=True returns a list of samples per image."""
    for sample in src:
        if isinstance(sample, list):
            for s in sample:
                yield s
        elif sample is not None:
            yield sample

def _drop_step_filter(src, step):
    """Keep every *step*-th sample.  Implemented as a composable pipeline
    stage so it works correctly with multi-worker DataLoader (each worker
    processes its own shard subset and the counter lives inside the
    generator, so it resets naturally on every new iteration)."""
    for i, sample in enumerate(src):
        if i % step == 0:
            yield sample

def get_validation_dataloader(args, shard_path, batch_size=32, num_workers=4):
    
    args.DYNAMIC_ZOOM_IN_PARAMS['DZI_TYPE'] = 'none' 
    args.DEFORM_2D_PARAMS['roi_mask_pro'] = 0

    transform = Compose([
        ParseMetaData(
            per_object=True
        ),
        CropAndResize(
            img_size=args.img_size,
            dynamic_zoom_params=args.DYNAMIC_ZOOM_IN_PARAMS
        ),
        GeneratePointCloud(
            n_pts=1024,
            deform_2d_params=args.DEFORM_2D_PARAMS
        ),
        ToTensor(args=args)
    ])

    drop_step = getattr(args, 'drop_step', 1)

    dataset = (
        wds.WebDataset(shard_path, shardshuffle=False)
        .map(OmniXValDataset._decode_sample, handler=wds.warn_and_continue)
    )
    
    # Apply drop_step as a composable pipeline stage so the counter
    # is created fresh each time the pipeline is iterated.
    if drop_step > 1:
        dataset = dataset.compose(lambda src: _drop_step_filter(src, drop_step))
    
    dataset = (
        dataset
        .map(transform)
        .compose(flatten_per_object)  # Flatten per-object samples before batching
        .select(lambda x: x is not None)  # Filter failed transforms
        .batched(batch_size, partial=False)  # Add batching
    )
    
    dataloader = wds.WebLoader(
        dataset,
        batch_size=None,  # batching already done by WebDataset
        num_workers=num_workers,
        pin_memory=True,
    )
    
    return dataloader