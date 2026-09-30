"""Failed comparison reads never become observed zeroes (#770)."""

from datetime import datetime, timezone
from unittest.mock import MagicMock

import duckdb
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from planalign_api.models.scenario import Scenario
from planalign_api.routers import comparison as router
from planalign_api.services.comparison_service import ComparisonDataError
from tests.test_comparison_dc_plan import (
    BASELINE_2025,
    _build_service_with_dbs,
    _create_scenario_db,
)

pytestmark = pytest.mark.fast


def _failed_database(tmp_path, failure: str) -> str:
    path = _create_scenario_db(tmp_path, "bad", BASELINE_2025)
    if failure == "corrupt":
        tmp_path.joinpath("bad.duckdb").write_bytes(b"not a database")
    elif failure == "missing":
        tmp_path.joinpath("bad.duckdb").unlink()
    else:
        statements = {
            "snapshot": "DROP TABLE fct_workforce_snapshot",
            "events": "DROP TABLE fct_yearly_events",
            "workforce_column": "ALTER TABLE fct_workforce_snapshot DROP COLUMN employment_status",
            "dc_column": "ALTER TABLE fct_workforce_snapshot DROP COLUMN is_enrolled_flag",
            "empty": "DELETE FROM fct_workforce_snapshot",
        }
        with duckdb.connect(path) as conn:
            conn.execute(statements[failure])
    return path


def _client(service, tmp_path) -> TestClient:
    storage = MagicMock()
    storage.get_workspace.return_value = object()
    storage._scenario_path.side_effect = lambda _, sid: tmp_path / sid
    storage.get_scenario.side_effect = lambda _, sid: Scenario(
        id=sid,
        workspace_id="ws",
        name=sid,
        status="completed",
        created_at=datetime.now(timezone.utc),
    )
    app = FastAPI()
    app.include_router(router.router, prefix="/api/workspaces")
    app.dependency_overrides[router.get_storage] = lambda: storage
    app.dependency_overrides[router.get_comparison_service] = lambda: service
    return TestClient(app)


@pytest.mark.parametrize(
    "failure",
    [
        "snapshot",
        "events",
        "workforce_column",
        "dc_column",
        "corrupt",
        "missing",
        "empty",
    ],
)
@pytest.mark.parametrize("failed_id", ["a", "b"])
def test_failed_reads_reject_entire_service_and_api_comparison(
    tmp_path, failure, failed_id
):
    good = _create_scenario_db(tmp_path, "good", BASELINE_2025)
    paths = {"a": good, "b": good, failed_id: _failed_database(tmp_path, failure)}
    service = _build_service_with_dbs(paths)

    with pytest.raises(ComparisonDataError) as error:
        service.compare_scenarios("ws", ["a", "b"], "a")
    assert error.value.scenario_id == failed_id
    expected_reason = {
        "missing": "database missing",
        "empty": "snapshot results empty",
    }.get(failure, "database read failed")
    assert error.value.reason == expected_reason

    response = _client(service, tmp_path).get(
        "/api/workspaces/ws/comparison",
        params={"scenarios": "a,b", "baseline": "a"},
    )
    assert response.status_code == 409
    assert response.json() == {
        "detail": {"scenario_id": failed_id, "reason": expected_reason}
    }


def test_observed_zero_still_produces_real_negative_one_hundred_percent(tmp_path):
    baseline = _create_scenario_db(tmp_path, "baseline", BASELINE_2025)
    zero = _create_scenario_db(
        tmp_path,
        "zero",
        [
            {
                "employee_id": "E_ZERO",
                "year": 2025,
                "status": "Active",
                "enrolled": False,
                "contributions": 0,
                "match": 0,
                "core": 0,
                "compensation": 0,
            }
        ],
    )
    service = _build_service_with_dbs({"a": baseline, "b": zero})
    response = _client(service, tmp_path).get(
        "/api/workspaces/ws/comparison",
        params={"scenarios": "a,b", "baseline": "a"},
    )
    assert response.status_code == 200
    result = response.json()
    assert result["scenarios"] == ["a", "b"]
    assert result["summary_deltas"]["final_headcount"]["scenarios"]["b"] == 1
    for metric in ("final_participation_rate", "final_employer_cost"):
        assert result["summary_deltas"][metric]["scenarios"]["b"] == 0
        assert result["summary_deltas"][metric]["delta_pcts"]["b"] == -100


def test_legacy_compensation_unavailable_without_masking_other_failures(tmp_path):
    good = _create_scenario_db(tmp_path, "good", BASELINE_2025)
    legacy = _create_scenario_db(tmp_path, "legacy", BASELINE_2025)
    with duckdb.connect(legacy) as conn:
        conn.execute(
            "ALTER TABLE fct_workforce_snapshot DROP COLUMN prorated_annual_compensation"
        )
    service = _build_service_with_dbs({"a": good, "b": legacy})
    response = _client(service, tmp_path).get(
        "/api/workspaces/ws/comparison",
        params={"scenarios": "a,b", "baseline": "a"},
    )
    assert response.status_code == 200
    result = response.json()
    assert result["workforce_comparison"][0]["values"]["b"]["headcount"] > 0
    assert result["workforce_comparison"][0]["values"]["b"]["avg_compensation"] is None
    assert result["workforce_comparison"][0]["deltas"]["b"]["avg_compensation"] is None
    assert result["dc_plan_comparison"][0]["deltas"]["b"]["employer_cost_rate"] is None
    with duckdb.connect(legacy) as conn:
        conn.execute("ALTER TABLE fct_workforce_snapshot DROP COLUMN is_enrolled_flag")
    with pytest.raises(ComparisonDataError):
        service.compare_scenarios("ws", ["a", "b"], "a")


def test_unreadable_database_reports_explicit_api_failure(tmp_path, monkeypatch):
    good = _create_scenario_db(tmp_path, "good", BASELINE_2025)
    unreadable = _create_scenario_db(tmp_path, "unreadable", BASELINE_2025)
    service = _build_service_with_dbs({"a": good, "b": unreadable})
    original_connect = duckdb.connect

    def connect(path, **kwargs):
        if path == unreadable:
            raise PermissionError("synthetic permission failure")
        return original_connect(path, **kwargs)

    monkeypatch.setattr(duckdb, "connect", connect)
    response = _client(service, tmp_path).get(
        "/api/workspaces/ws/comparison",
        params={"scenarios": "a,b", "baseline": "a"},
    )
    assert response.status_code == 409
    assert response.json() == {
        "detail": {"scenario_id": "b", "reason": "database read failed"}
    }


def test_unresolved_database_cannot_silently_skip_requested_scenario(tmp_path):
    good = _create_scenario_db(tmp_path, "good", BASELINE_2025)
    service = _build_service_with_dbs({"a": good})
    with pytest.raises(ComparisonDataError, match="Scenario b: database missing"):
        service.compare_scenarios("ws", ["a", "b"], "a")
