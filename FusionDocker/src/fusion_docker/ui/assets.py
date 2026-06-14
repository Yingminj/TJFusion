"""Static frontend asset loading for the dashboard UI.

The dashboard HTML/CSS/JS used to be embedded as a single ~4,200-line Python
string. It now lives as real files under ``ui/static/`` so it can be edited with
proper tooling, linted, and diffed. This module reads those files once, caches
them in memory, and exposes them with the right content type and a stable ETag.
"""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from threading import Lock

_STATIC_ROOT = Path(__file__).resolve().parent / "static"

# Only these files may be served. This is an explicit allow-list so the static
# route can never be turned into an arbitrary-file-read primitive.
_CONTENT_TYPES = {
    "index.html": "text/html; charset=utf-8",
    "styles.css": "text/css; charset=utf-8",
    "app.js": "application/javascript; charset=utf-8",
}

_CACHE: dict[str, "StaticAsset"] = {}
_CACHE_LOCK = Lock()


@dataclass(frozen=True)
class StaticAsset:
    """An in-memory static asset ready to be written to an HTTP response."""

    name: str
    body: bytes
    content_type: str
    etag: str


def _load_asset(name: str) -> StaticAsset:
    content_type = _CONTENT_TYPES[name]
    body = (_STATIC_ROOT / name).read_bytes()
    etag = '"%s"' % sha256(body).hexdigest()[:32]
    return StaticAsset(name=name, body=body, content_type=content_type, etag=etag)


def get_static_asset(name: str) -> StaticAsset | None:
    """Return the named static asset, or ``None`` if it is not allow-listed.

    Assets are cached after the first read. The cache lives for the lifetime of
    the process; restart the dashboard to pick up edits to the static files.
    """

    if name not in _CONTENT_TYPES:
        return None
    cached = _CACHE.get(name)
    if cached is not None:
        return cached
    with _CACHE_LOCK:
        cached = _CACHE.get(name)
        if cached is None:
            cached = _load_asset(name)
            _CACHE[name] = cached
    return cached


def render_index_html() -> str:
    """Return the dashboard index document as text (kept for compatibility)."""

    asset = get_static_asset("index.html")
    assert asset is not None  # index.html is always allow-listed
    return asset.body.decode("utf-8")
