python py_runners/rs_foundation.py \
  --tracking \
  --realsense \
  --pretrained_flow_model_path results/ckpts/FlowNet/rope_fixed_v2.pth \
  --pretrained_scale_model_path results/ckpts/ScaleNet/scalenet.pth \
  --device cuda \
  --frame_gap_threshold 10 \
  --show
