"""Shared fixtures for the API test package."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

import planalign_api.config as api_config
from planalign_api.main import create_app


@pytest.fixture()
def client_factory(tmp_path, monkeypatch):
    """Build an app with per-test settings without reloading application modules."""

    def _create(
        api_token: str | None, *, raise_server_exceptions: bool = True
    ) -> TestClient:
        monkeypatch.delenv("PLANALIGN_API_TOKEN", raising=False)
        if api_token is not None:
            monkeypatch.setenv("PLANALIGN_API_TOKEN", api_token)

        settings = api_config.APISettings(workspaces_root=tmp_path / "workspaces")
        monkeypatch.setattr(api_config, "settings", settings)
        return TestClient(create_app(), raise_server_exceptions=raise_server_exceptions)

    return _create
