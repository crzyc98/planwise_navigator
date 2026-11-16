"""Isolated-DB coverage for the points-based core service minimum (#1222).

The client case: points bands [0, 30) 1%, [30, 50) 2%, 50+ 3%, and a flat 1%
for anyone under three whole years of service. Each run builds its own
disposable database over 2025-2026, through both the single-design dbt vars and
the per-design `plan_design_parameters` path, with the setting on and off.
"""

from __future__ import annotations

import os
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

import duckdb
import pytest

from planalign_orchestrator import ConstructionSpec, build_orchestrator
from planalign_orchestrator.config import (
    PlanDesignParametersMap,
    SimulationConfig,
    load_simulation_config,
)
from tests.fixtures.edge_config_matrix import SHARED_DEV_DB, file_signature

pytestmark = [pytest.mark.integration, pytest.mark.very_slow]

FIXTURE_ROOT = Path(__file__).resolve().parents[1] / "fixtures/points_core_min_service"
CENSUS = FIXTURE_ROOT / "points_core_min_service.csv"
CONFIG = FIXTURE_ROOT / "points_core_min_service.yaml"

BANDS = ((0, 30, 0.01), (30, 50, 0.02), (50, None, 0.03))
MIN_SERVICE_YEARS = 3
PRE_SERVICE_RATE = 0.01

CORE_ROWS = """
SELECT
    ec.employee_id,
    ec.simulation_year,
    ec.applied_years_of_service,
    FLOOR(ws.current_age)::INT + ec.applied_years_of_service AS points,
    CAST(ec.core_contribution_rate AS DOUBLE) AS core_contribution_rate
FROM int_employer_core_contributions ec
JOIN int_workforce_state_accumulator ws
  ON ws.employee_id = ec.employee_id
 AND ws.simulation_year = ec.simulation_year
 AND ws.scenario_id = ec.scenario_id
WHERE ec.eligible_for_core
ORDER BY ec.employee_id, ec.simulation_year
"""


def band_rate(points: int) -> float:
    """Resolve the half-open points band independently of the SQL."""
    for low, high, rate in BANDS:
        if points >= low and (high is None or points < high):
            return rate
    raise AssertionError(f"{points} points is not covered by the bands")


def expected_rate(points: int, years_of_service: int, min_service: bool) -> float:
    if min_service and years_of_service < MIN_SERVICE_YEARS:
        return PRE_SERVICE_RATE
    return band_rate(points)


def _design_parameters(min_service: bool) -> dict[str, object]:
    core: dict[str, object] = {
        "family": "points_based",
        "contribution_rate": 0.001,
        "points_schedule": [
            {"min_points": low, "max_points": high, "rate": rate * 100}
            for low, high, rate in BANDS
        ],
    }
    if min_service:
        core["points_min_service_years"] = MIN_SERVICE_YEARS
        core["points_pre_service_rate"] = PRE_SERVICE_RATE * 100
    return {
        "match": {
            "family": "deferral_based",
            "cap_percent": 0.04,
            "tiers": [{"employee_min": 0.0, "employee_max": 0.06, "match_rate": 0.5}],
        },
        "employer_core": core,
        "auto_enrollment": {
            "default_deferral_rate": 0.04,
            "window_days": 45,
            "scope": "new_hires_only",
        },
        "deferral_escalation": {"increment": 0.01, "cap": 0.06},
        "eligibility": {"waiting_period_days": 0},
    }


def _config(per_design: bool, min_service: bool) -> SimulationConfig:
    config = load_simulation_config(CONFIG, env_overrides=False)
    if per_design or not min_service:
        # Per-design runs must get the setting only from their design payload,
        # and "off" runs must not inherit the run-global one.
        config.employer_core_contribution["points_min_service_years"] = None
        config.employer_core_contribution["points_pre_service_rate"] = None
    if per_design:
        config.plan_design_parameters = PlanDesignParametersMap.model_validate(
            {config.plan_design_id: _design_parameters(min_service)}
        )
    return config


@contextmanager
def _database_environment(database: Path) -> Iterator[None]:
    previous = os.environ.get("DATABASE_PATH")
    os.environ["DATABASE_PATH"] = str(database)
    try:
        yield
    finally:
        if previous is None:
            os.environ.pop("DATABASE_PATH", None)
        else:
            os.environ["DATABASE_PATH"] = previous


def _run(config: SimulationConfig, database: Path) -> None:
    census_parquet = database.with_suffix(".census.parquet")
    with duckdb.connect() as connection:
        connection.read_csv(str(CENSUS)).write_parquet(str(census_parquet))
    config.setup["census_parquet_path"] = str(census_parquet)
    with _database_environment(database):
        orchestrator = build_orchestrator(
            ConstructionSpec(
                config=config,
                database=database,
                threads=1,
                entry_point="invariant_test",
                validation_mode=True,
            )
        ).orchestrator
        orchestrator.execute_multi_year_simulation(
            start_year=config.simulation.start_year,
            end_year=config.simulation.end_year,
        )


RUNS = {
    "single_design_on": (False, True),
    "single_design_off": (False, False),
    "per_design_on": (True, True),
    "per_design_off": (True, False),
}


@pytest.fixture(scope="session")
def core_rows(
    tmp_path_factory: pytest.TempPathFactory,
    shared_dev_database_guard: tuple[int, str] | None,
) -> Iterator[dict[str, list[tuple]]]:
    """Build every variant once and return its eligible core rows."""
    rows: dict[str, list[tuple]] = {}
    for name, (per_design, min_service) in RUNS.items():
        database = tmp_path_factory.mktemp(name) / f"{name}.duckdb"
        _run(_config(per_design, min_service), database)
        with duckdb.connect(str(database), read_only=True) as connection:
            rows[name] = connection.execute(CORE_ROWS).fetchall()
    yield rows
    assert (
        file_signature(SHARED_DEV_DB) == shared_dev_database_guard
    ), f"the simulation modified the shared dev database {SHARED_DEV_DB}"


@pytest.mark.parametrize("name", list(RUNS))
def test_every_rate_matches_the_reference(
    core_rows: dict[str, list[tuple]], name: str
) -> None:
    min_service = RUNS[name][1]
    rows = core_rows[name]
    assert rows, f"{name}: no eligible core rows"
    wrong = [
        row
        for row in rows
        if row[4] != pytest.approx(expected_rate(row[3], row[2], min_service))
    ]
    assert not wrong, f"{name}: (id, year, service, points, rate) mismatches {wrong}"


@pytest.mark.parametrize("name", ["single_design_on", "per_design_on"])
def test_client_cases_are_exercised(
    core_rows: dict[str, list[tuple]], name: str
) -> None:
    rows = core_rows[name]
    under_minimum_high_points = [r for r in rows if r[2] < 3 and r[3] >= 30]
    assert under_minimum_high_points, "no employee under 3 years with 30+ points"
    assert all(r[4] == pytest.approx(0.01) for r in under_minimum_high_points)

    exactly_30 = [r for r in rows if r[2] >= 3 and r[3] == 30]
    assert exactly_30, "no employee at exactly 30 points with 3+ years"
    assert all(r[4] == pytest.approx(0.02) for r in exactly_30)

    assert any(r[2] >= 3 and r[4] == pytest.approx(0.03) for r in rows)


@pytest.mark.parametrize("name", ["single_design_on", "per_design_on"])
def test_rate_changes_in_the_year_service_reaches_the_minimum(
    core_rows: dict[str, list[tuple]], name: str
) -> None:
    crosser = {
        r[1]: (r[2], r[4]) for r in core_rows[name] if r[0] == "PTS_SENIOR_CROSSER"
    }
    assert crosser[2025] == (2, pytest.approx(0.01))
    assert crosser[2026] == (3, pytest.approx(0.03))


@pytest.mark.parametrize("path", ["single_design", "per_design"])
def test_setting_only_changes_employees_under_the_minimum(
    core_rows: dict[str, list[tuple]], path: str
) -> None:
    on = {(r[0], r[1]): r for r in core_rows[f"{path}_on"]}
    off = {(r[0], r[1]): r for r in core_rows[f"{path}_off"]}
    assert on.keys() == off.keys()
    for key, row in on.items():
        if row[2] >= MIN_SERVICE_YEARS:
            assert row[4] == pytest.approx(off[key][4]), key
