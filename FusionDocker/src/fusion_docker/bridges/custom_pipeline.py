"""Bridge type for user-defined DAG pipelines via the ``pipeline:`` YAML section.

When a config contains an explicit ``pipeline:`` list, the bridge type is
``custom_pipeline``.  If ``result_pub_addr`` is set, raw pipeline outputs
are forwarded to a ZMQ PUB socket so that downstream consumers (e.g.
MarvinDocker) can handle post-processing.
"""

from __future__ import annotations

from fusion_docker.bridges.base import BridgeDefinition
from fusion_docker.bridges.profiled import BridgeProfile, load_profiled_bridge_config


def _run_custom_pipeline(config, *, verbose: bool = False, save_json: bool = False) -> None:
    from fusion_docker.bridge_pub import BridgeResultPublisher
    from fusion_docker.bridge_service import run_bridge_service
    from fusion_docker.console import print_status

    publisher = None
    result_callback = None

    if getattr(config, "result_pub_addr", ""):
        pose_topic = getattr(config, "result_tf_topic", "/fusion/pose") or "/fusion/pose"
        status_topic = getattr(config, "result_siglip_topic", "/fusion/status") or "/fusion/status"
        publisher = BridgeResultPublisher(
            config.result_pub_addr,
            pose_topic=pose_topic,
            status_topic=status_topic,
        )
        result_callback = publisher.publish
        print_status(
            "PUB",
            f"Result forwarding enabled -> {config.result_pub_addr}",
            color="cyan",
        )

    try:
        run_bridge_service(
            config,
            verbose=verbose,
            save_json=save_json,
            result_callback=result_callback,
        )
    finally:
        if publisher is not None:
            publisher.close()


# Reuse the same config-loading path (no mutation needed) but with a
# custom *run* that wires in the optional ZMQ PUB publisher.
CUSTOM_PIPELINE_BRIDGE = BridgeDefinition(
    kind="custom_pipeline",
    description=(
        "User-defined DAG pipeline. Models, dependencies and parallelism "
        "are specified entirely in the ``pipeline:`` YAML section.  When "
        "``result_pub_addr`` is set, raw pipeline outputs are forwarded "
        "via ZMQ PUB."
    ),
    load_config=lambda config_path: load_profiled_bridge_config(
        config_path,
        BridgeProfile(
            kind="custom_pipeline",
            description="custom_pipeline",
            aliases=("pipeline", "dag"),
        ),
    ),
    run=_run_custom_pipeline,
    aliases=("pipeline", "dag"),
)
