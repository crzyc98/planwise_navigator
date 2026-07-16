"""Exhaustive auth-boundary tests over the live route table (Feature 115, US2).

Iterates every registered HTTP route on the app — never a hand-maintained
list — so a router added after this file ships is covered automatically.
This guards against the #397/#415 failure mode: a new endpoint silently
missing the shared-token auth dependency.
"""

from __future__ import annotations

import re

import pytest
from starlette.routing import Route

pytestmark = [pytest.mark.fast]

# Application routes that are intentionally public. Adding a new public route
# requires a reviewed, one-line addition here in the same PR that adds it.
PUBLIC_ROUTES: frozenset[tuple[str, str]] = frozenset(
    {
        ("/api/health", "GET"),
    }
)

# FastAPI's own scaffolding (docs UI, schema); not application endpoints.
_FRAMEWORK_PATHS = frozenset(
    {
        "/api/docs",
        "/api/redoc",
        "/api/openapi.json",
        "/docs/oauth2-redirect",
    }
)

# Substituted for every {path_param}; matches the default [^/]+ converter and
# is syntactically valid for str/UUID-shaped parameters, so requests route to
# the endpoint and reach its auth dependency instead of 404ing in the router.
_PARAM_PLACEHOLDER = "00000000-0000-4000-8000-000000000115"


def _enumerate_routes(app) -> list[tuple[str, str]]:
    """Every (path, method) pair for the app's HTTP routes, framework scaffolding excluded."""
    pairs: list[tuple[str, str]] = []
    for route in app.routes:
        if not isinstance(route, Route) or not route.methods:
            continue  # WebSocket routes and mounts are covered elsewhere
        if route.path in _FRAMEWORK_PATHS:
            continue
        for method in sorted(route.methods - {"HEAD", "OPTIONS"}):
            pairs.append((route.path, method))
    return sorted(pairs)


def _requestable_url(path: str) -> str:
    return re.sub(r"{[^}]+}", _PARAM_PLACEHOLDER, path)


def test_route_table_enumeration_is_nonempty_and_covers_known_routers() -> None:
    from planalign_api.main import create_app

    pairs = _enumerate_routes(create_app())

    assert len(pairs) >= 90, f"suspiciously few routes enumerated: {len(pairs)}"
    paths = {path for path, _ in pairs}
    assert "/api/health" in paths
    assert any(path.startswith("/api/workspaces") for path in paths)
    assert any(path.startswith("/api/calibration") for path in paths)


def test_every_route_rejects_missing_token_when_token_configured(
    client_factory,
) -> None:
    client = client_factory("shared-secret", raise_server_exceptions=False)

    unprotected = [
        (path, method)
        for path, method in _enumerate_routes(client.app)
        if (path, method) not in PUBLIC_ROUTES
        and client.request(method, _requestable_url(path)).status_code != 401
    ]

    assert not unprotected, (
        "Routes reachable WITHOUT the configured API token (add an auth "
        "dependency, or add to PUBLIC_ROUTES if intentionally public): "
        f"{unprotected}"
    )


def test_every_route_accepts_valid_token_when_token_configured(
    client_factory,
) -> None:
    client = client_factory("shared-secret", raise_server_exceptions=False)
    headers = {"Authorization": "Bearer shared-secret"}

    falsely_rejected = [
        (path, method)
        for path, method in _enumerate_routes(client.app)
        if client.request(method, _requestable_url(path), headers=headers).status_code
        == 401
    ]

    assert (
        not falsely_rejected
    ), f"Routes that rejected a VALID API token: {falsely_rejected}"


def test_every_route_reachable_when_no_token_configured(client_factory) -> None:
    client = client_factory(None, raise_server_exceptions=False)

    blocked = [
        (path, method)
        for path, method in _enumerate_routes(client.app)
        if client.request(method, _requestable_url(path)).status_code == 401
    ]

    assert not blocked, (
        "Routes that required auth despite PLANALIGN_API_TOKEN being unset "
        f"(local-dev mode must stay open): {blocked}"
    )
