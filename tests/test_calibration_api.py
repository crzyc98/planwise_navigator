"""Fast API tests for the calibration router (Feature 105, US3).

Exercises request/response shape and error mapping (guard -> 409, validation ->
422) with the CalibrationRunner mocked, so no dbt build runs.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from planalign_api.routers import calibration as calibration_router
from planalign_orchestrator.calibration_runner import PerYearCompensationResult
from planalign_orchestrator.exceptions import ConfigurationError

pytestmark = [pytest.mark.fast]


@pytest.fixture
def client() -> TestClient:
    from fastapi import FastAPI

    app = FastAPI()
    app.include_router(calibration_router.router, prefix="/api")
    return TestClient(app)


_SAMPLE = [
    PerYearCompensationResult(
        simulation_year=2025,
        avg_compensation=92153.87,
        yoy_growth_pct=None,
        target_growth_pct=3.0,
        growth_delta_pct=None,
        headcount=6967,
        new_hire_avg_comp=70000.0,
        existing_avg_comp=95000.0,
        new_hire_gap=-25000.0,
    ),
    PerYearCompensationResult(
        simulation_year=2026,
        avg_compensation=95884.11,
        yoy_growth_pct=4.0,
        target_growth_pct=3.0,
        growth_delta_pct=1.0,
        headcount=7176,
        new_hire_avg_comp=71000.0,
        existing_avg_comp=96000.0,
        new_hire_gap=-25000.0,
    ),
]


def test_run_returns_per_year_results(client, monkeypatch) -> None:
    monkeypatch.setattr(
        calibration_router.CalibrationRunner,
        "__init__",
        lambda self, run, **kw: None,
    )
    monkeypatch.setattr(
        calibration_router.CalibrationRunner,
        "run_calibration",
        lambda self: _SAMPLE,
    )

    resp = client.post(
        "/api/calibration/run",
        json={"start_year": 2025, "end_year": 2026, "params": {"cola_rate": 0.03}},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["run_id"].startswith("cal_")
    assert [r["simulation_year"] for r in body["results"]] == [2025, 2026]
    assert body["results"][0]["yoy_growth_pct"] is None
    assert body["results"][1]["growth_delta_pct"] == pytest.approx(1.0)


def test_missing_prerequisites_returns_409(client, monkeypatch) -> None:
    monkeypatch.setattr(
        calibration_router.CalibrationRunner,
        "__init__",
        lambda self, run, **kw: None,
    )

    def _boom(self):
        raise ConfigurationError("missing DC tables; run a full simulation first")

    monkeypatch.setattr(calibration_router.CalibrationRunner, "run_calibration", _boom)

    resp = client.post(
        "/api/calibration/run", json={"start_year": 2025, "end_year": 2026}
    )
    assert resp.status_code == 409
    assert "missing DC tables" in resp.json()["detail"]


def test_bad_year_range_returns_422(client) -> None:
    resp = client.post(
        "/api/calibration/run", json={"start_year": 2029, "end_year": 2025}
    )
    assert resp.status_code == 422


def test_negative_cola_returns_422(client) -> None:
    resp = client.post(
        "/api/calibration/run",
        json={"start_year": 2025, "end_year": 2026, "params": {"cola_rate": -0.1}},
    )
    assert resp.status_code == 422


def test_job_level_compensation_with_name_is_accepted(client, monkeypatch) -> None:
    # Regression: ranges include a string `name`; must not 422 (was Dict[str,float]).
    monkeypatch.setattr(
        calibration_router.CalibrationRunner, "__init__", lambda self, run, **kw: None
    )
    monkeypatch.setattr(
        calibration_router.CalibrationRunner, "run_calibration", lambda self: _SAMPLE
    )
    resp = client.post(
        "/api/calibration/run",
        json={
            "start_year": 2025,
            "end_year": 2026,
            "params": {
                "job_level_compensation": [
                    {
                        "level": 1,
                        "name": "Staff",
                        "min_compensation": 60000,
                        "max_compensation": 90000,
                    }
                ]
            },
        },
    )
    assert resp.status_code == 200
