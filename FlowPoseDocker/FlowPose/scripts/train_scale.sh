CUDA_VISIBLE_DEVICES=0 python py_runners/train.py \
--arch scalenet \
--log_dir ScaleNet \
--agent_type scale \
--sampler_mode ode \
--sampling_steps 200 \
--eval_freq 1 \
--batch_size 128 \
--n_epochs 5 \
--seed 0 \
--is_train \
--dino pointwise \
--num_workers 12 \
--num_gpu 1 \
--lr 1e-6 \
--pretrained_flow_model_path results/ckpts/FlowNet/ckpt_epoch2.pth \
# --pretrained_scale_model_path results/ckpts/ScaleNet/scalenet.pth \