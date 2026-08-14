"""Authenticated API contract for scenario evidence packs."""

import pytest

from tests.fixtures.evidence_pack import create_evidence_scenario

pytestmark = pytest.mark.fast


def test_api_returns_bound_deterministic_pack_and_text(
    client_factory, tmp_path
) -> None:
    scenario = create_evidence_scenario(tmp_path)
    client = client_factory(None)
    url = f"/api/workspaces/{scenario.workspace_id}/scenarios/{scenario.scenario_id}/evidence-pack"
    params = {"metric": "employer_match_cost", "base_year": 2025, "target_year": 2027}

    response = client.get(url, params=params)

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["pack"]["provenance"]["run_id"] == scenario.run_id
    assert payload["pack"]["change"]["total_change"]["value"] == "6"
    assert payload["text_export"].startswith("# Evidence Pack: Employer match cost")
    assert response.headers["X-PlanAlign-Result-Run-Id"] == scenario.run_id
    assert client.get(url, params=params).json() == payload


def test_api_maps_missing_year_and_scenario(client_factory, tmp_path) -> None:
    scenario = create_evidence_scenario(tmp_path)
    client = client_factory(None)
    url = f"/api/workspaces/{scenario.workspace_id}/scenarios/{scenario.scenario_id}/evidence-pack"
    unsupported = client.get(
        url,
        params={"metric": "active_headcount", "base_year": 2025, "target_year": 2026},
    )
    assert unsupported.status_code == 422
    assert unsupported.json()["detail"]["available_years"] == [2025, 2027]
    missing = client.get(
        f"/api/workspaces/{scenario.workspace_id}/scenarios/missing/evidence-pack",
        params={"metric": "active_headcount", "base_year": 2025, "target_year": 2027},
    )
    assert missing.status_code == 404


def test_api_route_uses_existing_auth(client_factory, tmp_path) -> None:
    scenario = create_evidence_scenario(tmp_path)
    client = client_factory("secret")
    url = f"/api/workspaces/{scenario.workspace_id}/scenarios/{scenario.scenario_id}/evidence-pack"
    params = {"metric": "active_headcount", "base_year": 2025, "target_year": 2027}
    assert client.get(url, params=params).status_code == 401
    assert (
        client.get(url, params=params, headers={"X-API-Token": "secret"}).status_code
        == 200
    )
