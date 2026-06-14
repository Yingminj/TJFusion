"""Request authorization for the dashboard UI.

The dashboard exposes endpoints that are effectively remote code execution
(running commands in containers, editing config files, spawning terminals). The
policy here keeps it safe by default:

- **Loopback bind (default):** no token required, but the ``Host`` header must be
  a loopback name. This blocks DNS-rebinding attacks where a malicious web page
  resolves a hostname to 127.0.0.1 and drives the local dashboard.
- **Non-loopback bind (opt-in network exposure):** a token is required on every
  ``/api/*`` request. The token is supplied via the ``X-Auth-Token`` header or a
  ``?token=`` query parameter (the startup banner prints a ready-to-use URL).

Cross-site state changes are blocked for both modes: any POST that carries an
``Origin`` header must be same-origin with the ``Host`` it is talking to.

Static assets and the index page never require a token so the page can bootstrap
and then read the token from its own URL.
"""

from __future__ import annotations

from dataclasses import dataclass
import hmac
import secrets
from urllib.parse import parse_qs, urlparse

_LOOPBACK_HOSTNAMES = {"127.0.0.1", "::1", "localhost", "0:0:0:0:0:0:0:1"}


def _is_loopback_bind(host: str) -> bool:
    cleaned = (host or "").strip().lower().strip("[]")
    if cleaned in _LOOPBACK_HOSTNAMES:
        return True
    return cleaned.startswith("127.")


def _host_only(host_header: str) -> str:
    """Return the lowercase hostname portion of a ``Host``/``Origin`` value."""

    value = (host_header or "").strip().lower()
    if not value:
        return ""
    # Strip a scheme if this came from an Origin header.
    if "://" in value:
        value = value.split("://", 1)[1]
    # IPv6 literal like [::1]:8765
    if value.startswith("["):
        return value[1 : value.find("]")] if "]" in value else value[1:]
    return value.split(":", 1)[0]


@dataclass(frozen=True)
class AuthResult:
    """Outcome of an authorization check."""

    ok: bool
    status: int = 200
    message: str = ""


_OK = AuthResult(ok=True)


class AuthPolicy:
    """Decides whether an incoming request is allowed."""

    def __init__(self, *, bind_host: str, token: str | None, require_token: bool) -> None:
        self._bind_host = bind_host
        self._token = token or None
        self._require_token = require_token and bool(token)
        self._loopback = _is_loopback_bind(bind_host)

    @classmethod
    def create(cls, *, host: str, token: str | None = None) -> "AuthPolicy":
        """Build a policy for the given bind host.

        For non-loopback binds a token is mandatory; one is generated when the
        caller does not supply it.
        """

        loopback = _is_loopback_bind(host)
        require_token = not loopback
        effective_token = (token or "").strip() or None
        if require_token and effective_token is None:
            effective_token = secrets.token_urlsafe(24)
        return cls(bind_host=host, token=effective_token, require_token=require_token)

    @property
    def token(self) -> str | None:
        return self._token

    @property
    def require_token(self) -> bool:
        return self._require_token

    def url_token_suffix(self) -> str:
        """Query suffix (``?token=...``) to append to the dashboard URL, if any."""

        return f"?token={self._token}" if self._require_token and self._token else ""

    def authorize(self, *, method: str, path: str, query: str, headers) -> AuthResult:
        """Authorize a request. ``headers`` is any mapping-like header container."""

        # Public bootstrap surface: the page shell and its static assets never
        # need a token (they carry no secrets) and are exempt from Origin checks.
        is_api = path.startswith("/api/")

        host_result = self._check_host_header(headers)
        if not host_result.ok:
            return host_result

        if not is_api:
            return _OK

        if method.upper() == "POST":
            origin_result = self._check_origin(headers)
            if not origin_result.ok:
                return origin_result

        if self._require_token and not self._token_matches(query, headers):
            return AuthResult(
                ok=False,
                status=401,
                message=(
                    "Missing or invalid auth token. Open the dashboard using the "
                    "tokenized URL printed at startup, or pass the X-Auth-Token header."
                ),
            )

        return _OK

    def _check_host_header(self, headers) -> AuthResult:
        # DNS-rebinding protection only matters for loopback binds: a token guards
        # network binds, and the real external hostname is unknown to us.
        if not self._loopback:
            return _OK
        host = _host_only(headers.get("Host", ""))
        if host == "" or host in _LOOPBACK_HOSTNAMES:
            return _OK
        return AuthResult(
            ok=False,
            status=403,
            message="Host header is not a loopback address; refusing possible DNS-rebinding request.",
        )

    def _check_origin(self, headers) -> AuthResult:
        origin = headers.get("Origin")
        if not origin:
            # Non-browser clients (curl, the model servers) send no Origin.
            return _OK
        if _host_only(origin) == _host_only(headers.get("Host", "")):
            return _OK
        return AuthResult(
            ok=False,
            status=403,
            message="Cross-origin request rejected.",
        )

    def _token_matches(self, query: str, headers) -> bool:
        if not self._token:
            return False
        provided = headers.get("X-Auth-Token", "")
        if not provided:
            provided = (parse_qs(query).get("token", [""]) or [""])[0]
        return bool(provided) and hmac.compare_digest(provided, self._token)
