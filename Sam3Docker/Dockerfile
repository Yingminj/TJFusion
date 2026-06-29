# Sam3Docker — promptable segmentation (`mask`).
# Built on tjfusion-gpu-base (torch 2.9.0 cu128 + common deps + protocol).
FROM tjfusion-gpu-base:latest

WORKDIR /workspace

# Sam3-specific runtime deps (numpy / opencv-python / pyzmq / pyyaml come from base).
RUN python3 -m pip install --no-cache-dir \
    decord \
    psutil \
    flask

# Vendored upstream SAM3 model code.
COPY Sam3Docker/sam3-main /workspace/sam3-main

WORKDIR /workspace/sam3-main
RUN python3 -m pip install --no-cache-dir -e .
RUN python3 -m pip install --no-cache-dir -e ".[notebooks]"
RUN python3 -m pip install --no-cache-dir -e ".[train,dev]"

WORKDIR /workspace
CMD ["/bin/bash"]
