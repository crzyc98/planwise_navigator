"""Age-appropriate IRS caps on match-responsive deferral rates."""

from __future__ import annotations

import csv
from pathlib import Path

import duckdb
import pytest
import yaml

from planalign_orchestrator import ConstructionSpec, build_orchestrator
from planalign_orchestrator.config import SimulationConfig

ROOT = Path(__file__).resolve().parents[2]
CENSUS = ROOT / "tests/fixtures/invariant_census.csv"
CONFIG = ROOT / "tests/fixtures/invariant_config.yaml"
EMPLOYEE_BIRTH_YEARS = {
    "INV_EMP_0001": 1972,  # 55 in 2027: ordinary catch-up
    "INV_EMP_0002": 1965,  # 62 in 2027: super catch-up
    "INV_EMP_0003": 1978,  # 49 in 2027: base limit
}


def _census_with_high_earners(tmp_path: Path) -> Path:
    with CENSUS.open(newline="") as source:
        reader = csv.DictReader(source)
        rows = list(reader)
        columns = reader.fieldnames

    for row in rows:
        if row["employee_id"] not in EMPLOYEE_BIRTH_YEARS:
            continue
        row.update(
            employee_birth_date=f"{EMPLOYEE_BIRTH_YEARS[row['employee_id']]}-06-15",
            employee_hire_date="2010-01-01",
            employee_gross_compensation="300000.00",
            employee_capped_compensation="300000.00",
            employee_deferral_rate="0.04000",
            employee_contribution="12000.00",
            pre_tax_contribution="12000.00",
            eligibility_entry_date="2010-01-01",
        )

    csv_path = tmp_path / "census.csv"
    with csv_path.open("w", newline="") as output:
        writer = csv.DictWriter(output, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)

    census_path = tmp_path / "census.parquet"
    with duckdb.connect() as connection:
        connection.read_csv(str(csv_path)).write_parquet(str(census_path))
    return census_path


def _config(census_path: Path) -> SimulationConfig:
    raw = yaml.safe_load(CONFIG.read_text())
    raw["simulation"].update(start_year=2027, end_year=2027)
    raw["setup"].update(
        census_parquet_path=str(census_path),
        plan_year_start_date="2026-01-01",
        plan_year_end_date="2026-12-31",
    )
    raw["deferral_match_response"] = {
        "enabled": True,
        "upward_participation_rate": 1.0,
        "upward_maximize_rate": 1.0,
        "upward_partial_increase_rate": 0.0,
        "downward_enabled": False,
    }
    raw["deferral_auto_escalation"].update(enabled=True, maximum_rate=0.15)
    raw["employer_match"]["formulas"]["tiered_match"].update(
        tiers=[{"tier": 1, "employee_min": 0, "employee_max": 0.15, "match_rate": 1.0}],
        max_match_percentage=0.15,
    )
    return SimulationConfig.model_validate(raw)


@pytest.mark.integration
def test_match_response_uses_year_end_age_and_2027_limits(tmp_path, monkeypatch):
    """All three age tiers use the seeded 2027 cap, including catch-up."""
    census_path = _census_with_high_earners(tmp_path)
    database = tmp_path / "irs_deferral_caps.duckdb"
    monkeypatch.setenv("DATABASE_PATH", str(database))
    monkeypatch.setenv("DBT_TARGET_PATH", str(tmp_path / "target"))
    monkeypatch.setenv("DBT_LOG_PATH", str(tmp_path / "logs"))
    orchestrator = build_orchestrator(
        ConstructionSpec(
            config=_config(census_path),
            database=database,
            threads=1,
            entry_point="cli.simulate",
            validation_mode=True,
        )
    ).orchestrator
    orchestrator.execute_multi_year_simulation(start_year=2027, end_year=2027)

    with duckdb.connect(str(database), read_only=True) as connection:
        events = connection.execute("""
            SELECT e.employee_id, e.compensation_amount, e.employee_deferral_rate,
                   2027 - YEAR(c.employee_birth_date) AS year_end_age,
                   CASE
                     WHEN 2027 - YEAR(c.employee_birth_date)
                          BETWEEN l.super_catch_up_age_min AND l.super_catch_up_age_max
                       THEN l.super_catch_up_limit
                     WHEN 2027 - YEAR(c.employee_birth_date) >= l.catch_up_age_threshold
                       THEN l.catch_up_limit
                     ELSE l.base_limit
                   END AS age_limit
            FROM fct_yearly_events e
            JOIN stg_census_data c USING (employee_id)
            JOIN config_irs_limits l ON l.limit_year = e.simulation_year
            WHERE e.event_type = 'deferral_match_response'
            """).fetchall()
        selected = {row[0]: row for row in events if row[0] in EMPLOYEE_BIRTH_YEARS}
        assert set(selected) == set(EMPLOYEE_BIRTH_YEARS)
        assert {row[3]: row[4] for row in selected.values()} == {
            49: 25000,
            55: 33000,
            62: 36250,
        }
        for employee_id, compensation, rate, _, limit in events:
            assert float(rate) * compensation <= limit, employee_id
        for employee_id, compensation, rate, _, limit in selected.values():
            expected_rate = int(limit / compensation * 10000) / 10000
            assert float(rate) == pytest.approx(expected_rate), employee_id
        for employee_id in ("INV_EMP_0001", "INV_EMP_0002"):
            _, compensation, rate, _, _ = selected[employee_id]
            assert float(rate) > 23500 / compensation

        state = connection.execute("""
            SELECT employee_id, current_deferral_rate, rate_source
            FROM int_deferral_rate_state_accumulator
            WHERE simulation_year = 2027
              AND employee_id IN ('INV_EMP_0001', 'INV_EMP_0002')
            """).fetchall()
        assert len(state) == 2
        for employee_id, rate, source in state:
            assert source == "match_response_plus_escalation"
            assert float(rate) == pytest.approx(float(selected[employee_id][2]))

        excess_count = connection.execute("""
            SELECT COUNT(*)
            FROM int_employee_contributions
            WHERE annual_contribution_amount > applicable_irs_limit
              AND simulation_year = 2027
            """).fetchone()[0]
        assert excess_count == 0
