"""Workspace navigation API contracts for issues #622 and #623."""

import pytest


pytestmark = pytest.mark.fast


def test_workspace_list_is_searchable_paginated_and_lifecycle_aware(client_factory):
    client = client_factory("shared-secret")
    headers = {"Authorization": "Bearer shared-secret"}
    alpha = client.post(
        "/api/workspaces", json={"name": "Alpha Client"}, headers=headers
    ).json()
    client.post("/api/workspaces", json={"name": "Zulu Client"}, headers=headers)
    archived = client.post(
        "/api/workspaces", json={"name": "Alpha Archive"}, headers=headers
    ).json()
    archive_response = client.put(
        f"/api/workspaces/{archived['id']}",
        json={"lifecycle": "archived"},
        headers=headers,
    )
    assert archive_response.status_code == 200

    response = client.get(
        "/api/workspaces?q=client&lifecycle=active&sort=name&limit=1&offset=0",
        headers=headers,
    )

    assert response.status_code == 200
    page = response.json()
    assert page["total"] == 2
    assert page["limit"] == 1
    assert page["offset"] == 0
    assert [item["id"] for item in page["items"]] == [alpha["id"]]

    archived_page = client.get(
        "/api/workspaces?lifecycle=archived", headers=headers
    ).json()
    assert archived_page["total"] == 1
    assert archived_page["items"][0]["id"] == archived["id"]


def test_recent_workspace_endpoint_returns_active_only(client_factory):
    client = client_factory("shared-secret")
    headers = {"Authorization": "Bearer shared-secret"}
    archived = client.post(
        "/api/workspaces", json={"name": "Archived"}, headers=headers
    ).json()
    client.put(
        f"/api/workspaces/{archived['id']}",
        json={"lifecycle": "archived"},
        headers=headers,
    )
    active = client.post(
        "/api/workspaces", json={"name": "Active"}, headers=headers
    ).json()

    response = client.get("/api/workspaces/recent?limit=5", headers=headers)

    assert response.status_code == 200
    assert [workspace["id"] for workspace in response.json()] == [active["id"]]
