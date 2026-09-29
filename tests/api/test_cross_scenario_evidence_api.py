"""Authenticated API contract for cross-scenario evidence packs (#585)."""

import json

import pytest

from tests.fixtures.evidence_pack import DEFAULT_ROWS, create_evidence_scenario

pytestmark = pytest.mark.fast

RUN_B = "00000000-0000-0000-0000-000000000585"


def _scenarios(tmp_path, *, managed_b: bool = True):
    a = create_evidence_scenario(tmp_path, scenario_id="scenario-a")
    rows_b = tuple((*row[:3], row[3] + 25, *row[4:]) for row in DEFAULT_ROWS)
    b = create_evidence_scenario(
        tmp_path, rows=rows_b, scenario_id="scenario-b", run_id=RUN_B, managed=managed_b
    )
    return a, b


def _url(workspace_id: str) -> str:
    return f"/api/workspaces/{workspace_id}/evidence-pack/compare"


def _params(**overrides):
    return {
        "scenario_a": "scenario-a",
        "scenario_b": "scenario-b",
        "metric": "total_compensation",
        "year": 2025,
        **overrides,
    }


def test_api_returns_bound_deterministic_cross_pack_and_text(
    client_factory, tmp_path
) -> None:
    a, b = _scenarios(tmp_path)
    client = client_factory(None)

    response = client.get(_url(a.workspace_id), params=_params())

    assert response.status_code == 200, response.text
    payload = response.json()
    pack = payload["pack"]
    assert pack["provenance_a"]["run_id"] == a.run_id
    assert pack["provenance_b"]["run_id"] == b.run_id
    assert pack["config_differences"] == []
    assert pack["executive_summary"][0].startswith(
        "Total compensation: Evidence Scenario (A) $"
    )
    assert payload["text_export"].startswith(
        "# Cross-Scenario Evidence Pack: Total compensation, 2025"
    )
    assert "No effective configuration differences" in payload["text_export"]
    assert (
        payload["filename"]
        == "evidence-pack-evidence-scenario-vs-evidence-scenario-total_compensation-2025.md"
    )
    assert response.headers["X-PlanAlign-Result-Run-Id"] == (
        f"scenario-a={a.run_id},scenario-b={b.run_id}"
    )
    assert client.get(_url(a.workspace_id), params=_params()).json() == payload


def test_api_cites_config_differences_and_flags_census_mismatch(
    client_factory, tmp_path
) -> None:
    a, b = _scenarios(tmp_path)
    config_b = b.run_dir / "config.yaml"
    config_b.write_text(
        config_b.read_text(encoding="utf-8")
        + "setup:\n  census_parquet_path: data/other_census.parquet\n",
        encoding="utf-8",
    )
    client = client_factory(None)

    payload = client.get(_url(a.workspace_id), params=_params()).json()

    differences = {d["path"]: d for d in payload["pack"]["config_differences"]}
    setup = differences["setup"]
    assert setup["value_a"] is None
    assert "data/other_census.parquet" in setup["value_b"]
    assert setup["status"] == "only_b"
    codes = {w["code"]: w for w in payload["pack"]["warnings"]}
    assert codes["census_mismatch"]["severity"] == "caution"
    unrecorded = payload["text_export"].split(
        "### Recorded in only one run's configuration"
    )
    assert len(unrecorded) == 2, "one-sided settings belong in their own subsection"
    assert "| `setup` |" in unrecorded[1]


def _write_workspace(scenario) -> None:
    """Give legacy (unmanaged) scenarios a resolvable effective config."""
    (scenario.scenario_path.parent.parent / "workspace.json").write_text(
        json.dumps(
            {
                "id": scenario.workspace_id,
                "name": "Evidence Workspace",
                "created_at": "2026-08-12T11:00:00+00:00",
                "updated_at": "2026-08-12T11:00:00+00:00",
                "base_config": {"simulation": {"start_year": 2025, "random_seed": 42}},
            }
        ),
        encoding="utf-8",
    )


def test_api_labels_each_sides_trust_warnings(client_factory, tmp_path) -> None:
    a, _ = _scenarios(tmp_path, managed_b=False)
    _write_workspace(a)
    client = client_factory(None)

    response = client.get(_url(a.workspace_id), params=_params())
    assert response.status_code == 200, response.text
    payload = response.json()

    legacy = [w for w in payload["pack"]["warnings"] if w["code"] == "legacy_result"]
    assert [w["message"].split(":")[0] for w in legacy] == ["Scenario B"]


def test_api_maps_invalid_pairs_years_and_scenarios(client_factory, tmp_path) -> None:
    a, _ = _scenarios(tmp_path)
    client = client_factory(None)
    url = _url(a.workspace_id)

    same = client.get(url, params=_params(scenario_b="scenario-a"))
    assert same.status_code == 422
    assert "distinct" in same.json()["detail"]["message"]
    missing_year = client.get(url, params=_params(year=2026))
    assert missing_year.status_code == 422
    assert missing_year.json()["detail"]["available_years"] == [2025, 2027]
    assert client.get(url, params=_params(scenario_b="missing")).status_code == 404


def test_api_route_uses_existing_auth(client_factory, tmp_path) -> None:
    a, _ = _scenarios(tmp_path)
    client = client_factory("secret")
    url = _url(a.workspace_id)

    assert client.get(url, params=_params()).status_code == 401
    authorized = client.get(url, params=_params(), headers={"X-API-Token": "secret"})
    assert authorized.status_code == 200


def test_api_refuses_when_a_config_cannot_be_cited(client_factory, tmp_path) -> None:
    a, _ = _scenarios(tmp_path, managed_b=False)
    client = client_factory(None)

    response = client.get(_url(a.workspace_id), params=_params())

    assert response.status_code == 422
    assert "cannot be cited" in response.json()["detail"]["message"]
