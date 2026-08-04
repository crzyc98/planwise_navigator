"""Regression tests for issue #532: response security headers and the
absolute ``storage_path`` no longer leaking out of workspace responses.
"""

from __future__ import annotations

import pytest

pytestmark = [pytest.mark.fast]


def _create_workspace(client, name: str = "Security Test Workspace") -> dict:
    response = client.post("/api/workspaces", json={"name": name})
    assert response.status_code == 201
    return response.json()


def test_workspace_responses_omit_storage_path(client_factory) -> None:
    client = client_factory(None)

    created = _create_workspace(client)
    assert "storage_path" not in created

    fetched = client.get(f"/api/workspaces/{created['id']}")
    assert fetched.status_code == 200
    assert "storage_path" not in fetched.json()

    updated = client.put(
        f"/api/workspaces/{created['id']}", json={"description": "updated"}
    )
    assert updated.status_code == 200
    assert "storage_path" not in updated.json()


@pytest.mark.parametrize("path", ["/api/health", "/api/workspaces"])
def test_json_responses_get_locked_down_security_headers(
    client_factory, path: str
) -> None:
    client = client_factory(None)

    response = client.get(path)

    assert response.status_code == 200
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"
    assert response.headers["Referrer-Policy"] == "no-referrer"
    assert response.headers["Content-Security-Policy"] == (
        "default-src 'none'; frame-ancestors 'none'"
    )


def test_docs_page_gets_a_scoped_csp_that_still_allows_swagger_assets(
    client_factory,
) -> None:
    client = client_factory(None)

    response = client.get("/api/docs")

    assert response.status_code == 200
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"
    csp = response.headers["Content-Security-Policy"]
    assert "cdn.jsdelivr.net" in csp
    assert "frame-ancestors 'none'" in csp
