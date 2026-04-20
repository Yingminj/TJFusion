from __future__ import annotations

from fusion_docker.bridges.base import BridgeDefinition
from fusion_docker.bridges.profiled import BridgeProfile, load_profiled_bridge_config


def _mutate_multi_zmq_pub_bridge_config(config):
    config.run_sam3_flowpose = True
    config.flowpose_sidecar_server_addr = ""
    if not config.sam3_server_addr or not config.flowpose_server_addr:
        raise ValueError(
            "multi_zmq_pub_bridge requires bridge.sam3_server_addr and bridge.flowpose_server_addr."
        )
    if not config.siglip2_server_addr:
        raise ValueError(
            "multi_zmq_pub_bridge requires bridge.siglip2_server_addr."
        )
    if not config.result_pub_addr:
        raise ValueError(
            "multi_zmq_pub_bridge requires bridge.result_pub_addr."
        )
    return config


def _run_multi_zmq_pub_bridge(config, *, verbose: bool = False, save_json: bool = False) -> None:
    from fusion_docker.bridge_pub import BridgeResultPublisher
    from fusion_docker.bridge_service import run_bridge_service
    from fusion_docker.console import print_status

    publisher = BridgeResultPublisher(
        config.result_pub_addr,
        frame_id=config.result_pub_frame_id,
        siglip_topic=config.result_siglip_topic,
        tf_topic=config.result_tf_topic,
        siglip_vote_window=config.result_siglip_vote_window,
    )
    print_status("PUB", f"Result PUB       : {config.result_pub_addr}", color="cyan")
    print_status("PUB", f"TF frame id      : {config.result_pub_frame_id}", color="cyan")
    print_status("PUB", f"Siglip topic     : {config.result_siglip_topic}", color="cyan")
    print_status("PUB", f"Siglip vote k    : {config.result_siglip_vote_window}", color="cyan")
    print_status("PUB", f"TF topic         : {config.result_tf_topic}", color="cyan")

    try:
        run_bridge_service(
            config,
            verbose=verbose,
            save_json=save_json,
            result_callback=publisher.publish,
        )
    finally:
        publisher.close()


MULTI_ZMQ_PUB_BRIDGE = BridgeDefinition(
    kind="multi_zmq_pub_bridge",
    description=(
        "Dual-branch bridge: routes RGB to siglip2 and RGB-D through sam3->flowpose, "
        "then publishes siglip2 results and tf-style poses over ZMQ PUB."
    ),
    load_config=lambda config_path: load_profiled_bridge_config(
        config_path,
        BridgeProfile(
            kind="multi_zmq_pub_bridge",
            description="multi_zmq_pub_bridge",
            aliases=("zmq_pub_dual", "siglip2_flowpose_pub"),
            mutate_config=_mutate_multi_zmq_pub_bridge_config,
        ),
    ),
    run=_run_multi_zmq_pub_bridge,
    aliases=("zmq_pub_dual", "siglip2_flowpose_pub"),
)
