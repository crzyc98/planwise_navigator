"""Fast API tests for the Studio ensembles router (issue #554).

Exercises discovery, distributions, risk, and attribution reads against a
small fixture ensemble database, plus the path-validation rejections
(non-.duckdb, missing file, the shared dev database, a database missing the
required table).
"""

from __future__ import annotations

from pathlib import Path

import duckdb
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from planalign_api.routers import ensembles as ensembles_router

pytestmark = [pytest.mark.fast]


@pytest.fixture
def client() -> TestClient:
    app = FastAPI()
    app.include_router(ensembles_router.router, prefix="/api")
    return TestClient(app)


def _write_fixture_ensemble(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with duckdb.connect(str(path)) as conn:
        conn.execute(
            "CREATE TABLE fct_metric_distributions ("
            "ensemble_id VARCHAR, scenario_id VARCHAR, metric VARCHAR, "
            "simulation_year INTEGER, p10 DOUBLE, p25 DOUBLE, p50 DOUBLE, "
            "p75 DOUBLE, p90 DOUBLE, mean DOUBLE, stddev DOUBLE, "
            "n_seeds INTEGER, n_seeds_requested INTEGER, is_sufficient BOOLEAN, "
            "percentile_method VARCHAR)"
        )
        conn.execute(
            "INSERT INTO fct_metric_distributions VALUES "
            "('ens-1', 'baseline', 'total_employer_plan_cost', 2029, "
            "1.0, 2.0, 3.0, 4.0, 5.0, 3.0, 1.0, 10, 10, TRUE, 'linear')"
        )
        conn.execute(
            "CREATE TABLE fct_metric_seed_values ("
            "ensemble_id VARCHAR, scenario_id VARCHAR, metric VARCHAR, "
            "simulation_year INTEGER, seed BIGINT, value DOUBLE)"
        )
        conn.executemany(
            "INSERT INTO fct_metric_seed_values VALUES (?, ?, ?, ?, ?, ?)",
            [
                (
                    "ens-1",
                    "baseline",
                    "total_employer_plan_cost",
                    2029,
                    seed,
                    float(seed),
                )
                for seed in range(1, 11)
            ],
        )
        conn.execute(
            "CREATE TABLE fct_variance_attribution ("
            "ensemble_id VARCHAR, scenario_id VARCHAR, metric VARCHAR, "
            "simulation_year INTEGER, subsystem VARCHAR, variance_share DOUBLE, "
            "ci_low DOUBLE, ci_high DOUBLE, baseline_variance DOUBLE, "
            "frozen_variance DOUBLE, anchor_seeds VARCHAR, n_anchors INTEGER, "
            "n_seeds INTEGER, bootstrap_iterations INTEGER, baselines_reused INTEGER, "
            "baselines_executed INTEGER, stochastic_status VARCHAR)"
        )
        conn.execute(
            "INSERT INTO fct_variance_attribution VALUES "
            "('ens-1', 'baseline', 'total_employer_plan_cost', 2029, 'termination', "
            "0.61, 0.50, 0.70, 10, 3.9, '1,2,3', 3, 10, 2000, 10, 0, 'stochastic'), "
            "('ens-1', 'baseline', 'total_employer_plan_cost', 2029, 'hiring', "
            "0.20, 0.10, 0.30, 10, 8.0, '1,2,3', 3, 10, 2000, 10, 0, 'stochastic')"
        )


def test_discover_finds_fixture_database(tmp_path: Path, client: TestClient) -> None:
    root = tmp_path / "ensembles"
    _write_fixture_ensemble(root / "run-1" / "ensemble.duckdb")
    resp = client.get("/api/ensembles/discover", params={"root": str(root)})
    assert resp.status_code == 200
    [summary] = resp.json()
    assert summary["ensemble_ids"] == ["ens-1"]
    assert summary["scenario_ids"] == ["baseline"]
    assert summary["metrics"] == ["total_employer_plan_cost"]
    assert summary["min_simulation_year"] == 2029


def test_discover_skips_duckdb_files_missing_the_required_table(
    tmp_path: Path, client: TestClient
) -> None:
    root = tmp_path / "ensembles"
    stray = root / "run-2" / "ensemble.duckdb"
    stray.parent.mkdir(parents=True)
    with duckdb.connect(str(stray)) as conn:
        conn.execute("CREATE TABLE unrelated (id INTEGER)")
    resp = client.get("/api/ensembles/discover", params={"root": str(root)})
    assert resp.status_code == 200
    assert resp.json() == []


def test_discover_rejects_missing_root(tmp_path: Path, client: TestClient) -> None:
    resp = client.get(
        "/api/ensembles/discover", params={"root": str(tmp_path / "missing")}
    )
    assert resp.status_code == 404


def test_get_distributions_returns_fixture_rows(
    tmp_path: Path, client: TestClient
) -> None:
    db_path = tmp_path / "ensemble.duckdb"
    _write_fixture_ensemble(db_path)
    resp = client.get(
        "/api/ensembles/distributions",
        params={
            "database": str(db_path),
            "ensemble_scenario_id": "baseline",
            "ensemble_id": "ens-1",
        },
    )
    assert resp.status_code == 200
    [row] = resp.json()
    assert row["metric"] == "total_employer_plan_cost"
    assert row["p50"] == 3.0
    assert row["is_sufficient"] is True


def test_get_risk_evaluates_ad_hoc_threshold(
    tmp_path: Path, client: TestClient
) -> None:
    db_path = tmp_path / "ensemble.duckdb"
    _write_fixture_ensemble(db_path)
    resp = client.get(
        "/api/ensembles/risk",
        params={
            "database": str(db_path),
            "ensemble_scenario_id": "baseline",
            "ensemble_id": "ens-1",
            "threshold": ["total_employer_plan_cost:5"],
        },
    )
    assert resp.status_code == 200
    [statement] = resp.json()
    assert statement["is_evaluable"] is True
    assert statement["exceedance_probability"] == pytest.approx(
        0.5
    )  # seeds 6..10 of 1..10 exceed 5


def test_get_risk_reports_unavailable_metric(
    tmp_path: Path, client: TestClient
) -> None:
    db_path = tmp_path / "ensemble.duckdb"
    _write_fixture_ensemble(db_path)
    resp = client.get(
        "/api/ensembles/risk",
        params={
            "database": str(db_path),
            "ensemble_scenario_id": "baseline",
            "ensemble_id": "ens-1",
            "threshold": ["participation_rate:0.5"],
        },
    )
    assert resp.status_code == 200
    [statement] = resp.json()
    assert statement["is_evaluable"] is False


def test_get_risk_rejects_malformed_threshold(
    tmp_path: Path, client: TestClient
) -> None:
    db_path = tmp_path / "ensemble.duckdb"
    _write_fixture_ensemble(db_path)
    resp = client.get(
        "/api/ensembles/risk",
        params={
            "database": str(db_path),
            "ensemble_scenario_id": "baseline",
            "ensemble_id": "ens-1",
            "threshold": ["not-valid"],
        },
    )
    assert resp.status_code == 422


def test_get_attribution_is_ranked_by_variance_share_descending(
    tmp_path: Path, client: TestClient
) -> None:
    db_path = tmp_path / "ensemble.duckdb"
    _write_fixture_ensemble(db_path)
    resp = client.get(
        "/api/ensembles/attribution",
        params={
            "database": str(db_path),
            "ensemble_scenario_id": "baseline",
            "ensemble_id": "ens-1",
        },
    )
    assert resp.status_code == 200
    rows = resp.json()
    assert [row["subsystem"] for row in rows] == ["termination", "hiring"]


@pytest.mark.parametrize(
    "make_path",
    [
        lambda tmp_path: tmp_path / "not_a_duckdb.txt",
        lambda tmp_path: tmp_path / "missing.duckdb",
    ],
)
def test_distributions_rejects_invalid_paths(
    tmp_path: Path, client: TestClient, make_path
) -> None:
    path = make_path(tmp_path)
    if path.suffix == ".txt":
        path.write_text("not a database")
    resp = client.get(
        "/api/ensembles/distributions",
        params={
            "database": str(path),
            "ensemble_scenario_id": "baseline",
            "ensemble_id": "ens-1",
        },
    )
    assert resp.status_code == 404


def test_distributions_rejects_shared_dev_database(client: TestClient) -> None:
    resp = client.get(
        "/api/ensembles/distributions",
        params={
            "database": "dbt/simulation.duckdb",
            "ensemble_scenario_id": "baseline",
            "ensemble_id": "ens-1",
        },
    )
    assert resp.status_code == 404


def test_distributions_rejects_database_without_required_table(
    tmp_path: Path, client: TestClient
) -> None:
    db_path = tmp_path / "ensemble.duckdb"
    with duckdb.connect(str(db_path)) as conn:
        conn.execute("CREATE TABLE unrelated (id INTEGER)")
    resp = client.get(
        "/api/ensembles/distributions",
        params={
            "database": str(db_path),
            "ensemble_scenario_id": "baseline",
            "ensemble_id": "ens-1",
        },
    )
    assert resp.status_code == 404
