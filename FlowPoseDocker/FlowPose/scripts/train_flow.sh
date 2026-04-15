SHARD_PATH="/media/kewei/KMD_DATA/dataSOPE_webdataset/train-{000000..000937}.tar"
CUDA_VISIBLE_DEVICES=0 python py_runners/train.py \
--arch pointnet \
--log_dir FlowNet \
--sampling_steps 100 \
--sampler_mode ode \
--shard_path $SHARD_PATH \
--eval_freq 1 \
--batch_size 128 \
--n_epochs 20 \
--seed 0 \
--is_train \
--dino pointwise \
--num_workers 16 \
--num_gpu 1 \
--lr 1e-5 \