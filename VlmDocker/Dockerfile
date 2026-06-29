# VlmDocker — fine-tuned Qwen3.5-VL + LoRA → `status`.
# Built on tjfusion-gpu-base (torch 2.9.0 cu128 + common deps + protocol).
FROM tjfusion-gpu-base:latest

WORKDIR /workspace

# transformers>=5.9 is REQUIRED for the Qwen3.5-VL (qwen3_5) architecture; peft
# attaches the LoRA adapter at inference; accelerate provides device_map="auto".
# numpy / opencv-python / pyzmq / pyyaml / pillow come from the base.
RUN python3 -m pip install --no-cache-dir \
    "transformers>=5.9.0" \
    "peft>=0.13.0" \
    "accelerate>=1.0.0" \
    "qwen-vl-utils>=0.0.8"

CMD ["/bin/bash"]
