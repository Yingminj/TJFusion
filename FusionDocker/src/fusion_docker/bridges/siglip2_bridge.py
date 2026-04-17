from __future__ import annotations

from fusion_docker.bridges.profiled import BridgeProfile, create_profiled_bridge_definition


def _mutate_siglip2_bridge_config(config):
    config.run_sam3_flowpose = False
    config.flowpose_server_addr = ""
    config.sam3_server_addr = ""
    config.flowpose_sidecar_server_addr = ""
    config.prompts = []
    config.obj_id_map = {}
    config.return_masks = False
    config.clear_previous = False
    config.output_json = ""
    if not config.siglip2_server_addr:
        raise ValueError(
            "siglip2_bridge requires bridge.siglip2_server_addr in its config."
        )
    return config


SIGLIP2_BRIDGE = create_profiled_bridge_definition(
    BridgeProfile(
        kind="siglip2_bridge",
        description=(
            "Dedicated bridge for external_json/zmq_source input routed to "
            "the siglip2 inference branch only."
        ),
        aliases=("siglip2", "classification"),
        mutate_config=_mutate_siglip2_bridge_config,
    )
)
