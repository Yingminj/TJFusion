"""Bridge type for user-defined DAG pipelines via the ``pipeline:`` YAML section.

When a config contains an explicit ``pipeline:`` list, the bridge type is
``custom_pipeline``.  No profile mutation is needed — the pipeline nodes
themselves define which models to call and in what order.
"""

from __future__ import annotations

from fusion_docker.bridges.profiled import BridgeProfile, create_profiled_bridge_definition

CUSTOM_PIPELINE_BRIDGE = create_profiled_bridge_definition(
    BridgeProfile(
        kind="custom_pipeline",
        description=(
            "User-defined DAG pipeline. Models, dependencies and parallelism "
            "are specified entirely in the ``pipeline:`` YAML section."
        ),
        aliases=("pipeline", "dag"),
    )
)
