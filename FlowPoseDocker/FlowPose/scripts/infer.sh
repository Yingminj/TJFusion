python py_runners/infer.py \
  --data_path /home/kewei/repo/FoundationStereo/output \
  --tracking \
  --pretrained_flow_model_path results/ckpts/FlowNet/ckpt_epoch2.pth \
  --pretrained_scale_model_path results/ckpts/ScaleNet/ckpt_epoch1.pth \
  --device cuda \
  --frame_gap_threshold 10 \
  --show
