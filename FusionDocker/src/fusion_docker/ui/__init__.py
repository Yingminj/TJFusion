"""Web dashboard support package for fusion_docker.

The dashboard frontend (HTML/CSS/JS) lives as plain files under ``static/`` and
is served by :mod:`fusion_docker.ui.assets`. Cross-cutting concerns that used to
be buried inside the monolithic ``ui_server`` module now live here:

- :mod:`fusion_docker.ui.assets` — load/cache the static frontend assets.
- :mod:`fusion_docker.ui.auth` — request authorization (token + CSRF/Origin).
- :mod:`fusion_docker.ui.status_cache` — background runtime-status refresher.
"""

from fusion_docker.ui.assets import StaticAsset, get_static_asset, render_index_html
from fusion_docker.ui.auth import AuthPolicy, AuthResult
from fusion_docker.ui.status_cache import RuntimeStatusRefresher

__all__ = [
    "StaticAsset",
    "get_static_asset",
    "render_index_html",
    "AuthPolicy",
    "AuthResult",
    "RuntimeStatusRefresher",
]
