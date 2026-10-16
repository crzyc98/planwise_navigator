"""HTTP contracts for census analysis outside IRS threshold coverage."""

import pytest


@pytest.mark.fast
@pytest.mark.parametrize(
    ("as_of", "missing_seed", "expected_count"),
    [
        (None, False, None),
        ("2023-12-31", False, None),
        ("2024-12-31", False, 1),
        ("2024-12-31", True, None),
    ],
)
def test_census_hce_availability_response(
    client_factory, tmp_path, monkeypatch, as_of, missing_seed, expected_count
):
    workspace = tmp_path / "workspaces" / "test-ws"
    workspace.mkdir(parents=True)
    (workspace / "census.csv").write_text(
        "employee_id,employee_birth_date,employee_hire_date,"
        "employee_gross_compensation,employee_deferral_rate,active\n"
        "synthetic-1,1980-01-01,2023-01-01,200000,0.06,true\n"
    )
    if missing_seed:
        monkeypatch.setattr(
            "planalign_api.services.census_analysis_service.IRS_LIMITS_SEED",
            tmp_path / "missing.csv",
        )
    request = {"file_path": "census.csv"}
    if as_of:
        request["as_of_date"] = as_of
    with client_factory(None) as client:
        response = client.post("/api/workspaces/test-ws/analyze-census", json=request)

    assert response.status_code == 200, response.text
    result = response.json()
    assert result["overall"]["hce_count"] == expected_count
    assert result["as_of_date_source"] == ("provided" if as_of else "inferred")
    assert result["as_of_date"] == (as_of or "2023-12-31")
    assert result["overall"]["participation_rate"] == 1.0
    assert (result["hce_compensation_threshold"] is None) == (expected_count is None)
