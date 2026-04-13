from __future__ import annotations

from fusion_docker.bridges.profiled import BridgeProfile, create_profiled_bridge_definition


def _mutate_sam3_flowpose_config(config):
    config.run_sam3_flowpose = True
    config.siglip2_server_addr = ""
    config.flowpose_sidecar_server_addr = ""
    return config


SAM3_FLOWPOSE_BRIDGE = create_profiled_bridge_definition(
    BridgeProfile(
        kind="sam3_flowpose",
        description=(
            "Dedicated bridge for external_json/zmq_source input routed through "
            "the sam3 -> flowpose pipeline only."
        ),
        aliases=("sam3", "flowpose_main"),
        mutate_config=_mutate_sam3_flowpose_config,
    )
)
