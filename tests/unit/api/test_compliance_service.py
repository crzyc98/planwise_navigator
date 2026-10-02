"""Compliance reports reconcile with drilldown and retain archived evidence."""

import hashlib
from pathlib import Path
from unittest.mock import MagicMock

import duckdb
import pytest

from planalign_api.services.compliance_service import (
    ComplianceService,
    ComplianceEvidenceChangedError,
)
from planalign_api.services.compliance_metrics import limit_status, annual_additions
from planalign_api.services.database_path_resolver import ResolvedDatabasePath
from planalign_api.services.ndt_service import NDTService

pytestmark = pytest.mark.fast


@pytest.fixture
def report(tmp_path):
    path = tmp_path / "simulation.duckdb"
    seed = Path(__file__).resolve().parents[3] / "dbt/seeds/config_irs_limits.csv"
    with duckdb.connect(str(path)) as conn:
        conn.execute(
            "CREATE TABLE config_irs_limits AS SELECT * FROM read_csv_auto(?)",
            [str(seed)],
        )
        conn.execute(
            """CREATE TABLE fct_workforce_snapshot (
            employee_id VARCHAR, plan_design_id VARCHAR, simulation_year INTEGER,
            current_age INTEGER, current_compensation DOUBLE, prorated_annual_compensation DOUBLE,
            prorated_annual_contributions DOUBLE, employer_match_amount DOUBLE, employer_core_amount DOUBLE,
            current_eligibility_status VARCHAR, is_enrolled_flag BOOLEAN, current_tenure DOUBLE
        )"""
        )
        for index, age in enumerate((49, 50, 59, 60, 63, 64)):
            conn.execute(
                "INSERT INTO fct_workforce_snapshot VALUES (?, 'design', 2026, ?, 400000, 400000, 32500, 10000, 5000, 'eligible', true, 5)",
                [f"EMP{index}", age],
            )
    resolver = MagicMock()
    resolver.resolve.return_value = ResolvedDatabasePath(
        path=path, source="run", run_id="successful"
    )
    storage = MagicMock()
    return ComplianceService(storage, resolver), path, resolver


def test_report_is_read_only_and_reuses_ndt(report):
    service, path, resolver = report
    before = hashlib.sha256(path.read_bytes()).hexdigest()
    summary = service.summary("w", "s", "Scenario", 2026)
    expected = NDTService(service.storage, resolver).run_415_test(
        "w", "s", "Scenario", 2026, True
    )
    assert summary.annual_additions.over_limit == expected.breach_count
    assert (
        summary.annual_additions.near_limit + summary.annual_additions.at_limit
        == expected.at_risk_count
    )
    assert summary.ndt[2].result == expected.test_result
    assert hashlib.sha256(path.read_bytes()).hexdigest() == before
    assert summary.compensation.over_limit == 6
    assert summary.compensation.excess == 240000


def test_age_boundaries_and_catch_up_reconciliation(report):
    service, _, _ = report
    result = service.summary("w", "s", "Scenario", 2026)
    assert result.catch_up.eligible_count == 3
    assert result.super_catch_up.eligible_count == 2
    assert result.catch_up.used == 24000
    assert result.catch_up.remaining_capacity == 0
    assert result.super_catch_up.used == 16000
    assert result.super_catch_up.remaining_capacity == 6500
    assert result.deferrals.over_limit == 1
    assert result.deferrals.at_limit == 3
    for group, rollup in (
        ("catch_up", result.catch_up),
        ("super_catch_up", result.super_catch_up),
    ):
        page = service.employees("w", "s", 2026, result.evidence, group)
        assert page.total == rollup.eligible_count
        assert sum(e.modeled_catch_up_used for e in page.employees) == rollup.used


@pytest.mark.parametrize(
    "amount,expected",
    [
        (94.99, "below_threshold"),
        (95, "near_limit"),
        (100, "at_limit"),
        (100.01, "over_limit"),
        (None, "unavailable"),
    ],
)
def test_cent_boundaries(amount, expected):
    assert limit_status(amount, 100, 0.95) == expected


def test_pagination_and_stale_evidence(report):
    service, path, resolver = report
    summary = service.summary("w", "s", "Scenario", 2026)
    first = service.employees(
        "w", "s", 2026, summary.evidence, "401a17", "over_limit", limit=2
    )
    second = service.employees(
        "w", "s", 2026, summary.evidence, "401a17", "over_limit", offset=2, limit=2
    )
    assert first.total == second.total == 6
    assert not {e.employee_id for e in first.employees} & {
        e.employee_id for e in second.employees
    }
    resolver.resolve.return_value = ResolvedDatabasePath(
        path=path, source="run", run_id="replacement"
    )
    with pytest.raises(ComplianceEvidenceChangedError):
        service.employees("w", "s", 2026, summary.evidence, "402g")


def test_estimated_and_recorded_limit_labels(report):
    service, path, _ = report
    with duckdb.connect(str(path)) as conn:
        conn.execute(
            "UPDATE config_irs_limits SET base_limit = 23500 WHERE limit_year = 2026"
        )
    summary = service.summary("w", "s", "Scenario", 2026)
    assert summary.limits.differs_from_current_seed
    assert summary.limits.base_limit == 23500
    with duckdb.connect(str(path)) as conn:
        conn.execute("UPDATE fct_workforce_snapshot SET simulation_year = 2027")
    assert service.summary("w", "s", "Scenario", 2027).limits.is_estimated


def test_missing_limits_and_null_inputs_are_unavailable(report):
    service, path, _ = report
    with duckdb.connect(str(path)) as conn:
        conn.execute(
            "UPDATE fct_workforce_snapshot SET current_age = NULL, prorated_annual_contributions = NULL WHERE employee_id = 'EMP0'"
        )
    summary = service.summary("w", "s", "Scenario", 2026)
    assert summary.deferrals.unavailable == 1
    assert summary.annual_additions.unavailable == 1
    assert summary.ndt[0].result == "unavailable"
    assert summary.ndt[2].result == "unavailable"
    with duckdb.connect(str(path)) as conn:
        conn.execute("DELETE FROM config_irs_limits WHERE limit_year = 2026")
    summary = service.summary("w", "s", "Scenario", 2026)
    assert summary.limits is None
    assert summary.deferrals.unavailable == 6
    assert summary.catch_up.utilization is None


def test_no_eligible_population_and_missing_year(report):
    service, path, _ = report
    with duckdb.connect(str(path)) as conn:
        conn.execute(
            "UPDATE fct_workforce_snapshot SET current_eligibility_status = 'ineligible'"
        )
    summary = service.summary("w", "s", "Scenario", 2026)
    assert summary.participant_count == 0
    assert all(r.result == "unavailable" for r in summary.ndt)
    with pytest.raises(ValueError, match="No snapshot"):
        service.summary("w", "s", "Scenario", 2040)


def test_ineligible_catch_up_is_not_excluded():
    assert annual_additions(31000, 5000, 3000, 23500, 49, 50, 23500) == 39000
    assert annual_additions(31000, 5000, 3000, 23500, 50, 50, 31000) == 31500
    assert annual_additions(31000, 5000, 3000, 23500, None, 50, None) == 39000
    assert annual_additions(100000, 5000, 3000, 23500, 50, 50, 31000) == 100500


def test_legacy_archive_is_preserved_and_evidence_pins_options(report):
    service, path, _ = report
    with duckdb.connect(str(path)) as conn:
        conn.execute(
            "ALTER TABLE config_irs_limits DROP COLUMN social_security_wage_base"
        )
        conn.execute("ALTER TABLE config_irs_limits DROP COLUMN is_estimated")
        conn.execute("ALTER TABLE fct_workforce_snapshot DROP COLUMN plan_design_id")
    before = path.read_bytes()
    summary = service.summary("w", "s", "Scenario", 2026)
    assert summary.limits.is_estimated is None
    assert path.read_bytes() == before
    page = service.employees("w", "s", 2026, summary.evidence, "402g")
    assert all(e.plan_design_id is None for e in page.employees)
    with pytest.raises(ComplianceEvidenceChangedError):
        service.employees("w", "s", 2026, summary.evidence, "402g", threshold=0.90)


def test_super_group_requires_an_enhanced_limit(report):
    service, path, _ = report
    with duckdb.connect(str(path)) as conn:
        conn.execute("UPDATE fct_workforce_snapshot SET simulation_year = 2024")
    summary = service.summary("w", "s", "Scenario", 2024)
    assert summary.catch_up.eligible_count == 5
    assert summary.super_catch_up.eligible_count == 0


def test_api_pagination_validation_and_conflict(report):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from types import SimpleNamespace
    from planalign_api.routers.ndt import router, get_storage, get_compliance_service

    service, path, resolver = report
    storage = MagicMock()
    storage._scenario_path.return_value = path.parent
    storage.get_scenario.return_value = SimpleNamespace(
        name="Scenario", status="completed"
    )
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_storage] = lambda: storage
    app.dependency_overrides[get_compliance_service] = lambda: service
    with TestClient(app) as client:
        response = client.get(
            "/w/analytics/ndt/compliance", params={"scenarios": "s", "year": 2026}
        )
        assert response.status_code == 200
        summary = response.json()["results"][0]
        params = {
            "scenario_id": "s",
            "year": 2026,
            "evidence": summary["evidence"],
            "metric": "401a17",
            "limit_status": "over_limit",
            "limit": 2,
        }
        response = client.get("/w/analytics/ndt/compliance/employees", params=params)
        assert response.status_code == 200
        assert response.json()["total"] == 6
        assert len(response.json()["employees"]) == 2
        assert (
            client.get(
                "/w/analytics/ndt/compliance/employees", params={**params, "limit": 201}
            ).status_code
            == 422
        )
        resolver.resolve.return_value = ResolvedDatabasePath(
            path=path, source="run", run_id="new"
        )
        assert (
            client.get(
                "/w/analytics/ndt/compliance/employees", params=params
            ).status_code
            == 409
        )
