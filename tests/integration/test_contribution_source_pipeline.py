"""Three-year synthetic run through the real pipeline, with isolated artifacts."""

from pathlib import Path

import duckdb
import pandas as pd
import pytest

from planalign_orchestrator import ConstructionSpec, build_orchestrator
from planalign_orchestrator.config import load_simulation_config
from planalign_orchestrator.config.contribution_sources import (
    ContributionSourceSettings,
)

pytestmark = [pytest.mark.integration, pytest.mark.slow]
ROOT = Path(__file__).resolve().parents[2]


def _run_source_pipeline(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> list[tuple]:
    tmp_path.mkdir()
    database = tmp_path / "sources.duckdb"
    monkeypatch.setenv("DATABASE_PATH", str(database))
    monkeypatch.setenv("DBT_TARGET_PATH", str(tmp_path / "target"))
    monkeypatch.setenv("DBT_LOG_PATH", str(tmp_path / "logs"))
    fixture = ROOT / "tests/fixtures/edge_config/auto_escalation_low_cap"
    config = load_simulation_config(fixture.with_suffix(".yaml"), env_overrides=False)
    config.simulation.end_year = 2027
    config.simulation.target_growth_rate = 0
    config.deferral_auto_escalation.enabled = False
    frame = pd.read_csv(fixture.with_suffix(".csv"))
    template = frame.iloc[0].to_dict()
    rows = []
    evidence = []
    for index, age in enumerate([49, 50, 59, 60, 63, 64]):
        employee_id = f"SOURCE_{age}"
        rows.append(
            {
                **template,
                "employee_id": employee_id,
                "employee_ssn": f"999-80-{index:04d}",
                "employee_birth_date": f"{2026-age}-01-01",
                "employee_gross_compensation": 200000,
                "employee_capped_compensation": 200000,
                "employee_deferral_rate": 0.20,
            }
        )
        for wage_year in [2024, 2025, 2026]:
            evidence.append(
                {
                    "employee_id": employee_id,
                    "employer_id": "synthetic",
                    "wage_year": wage_year,
                    "wages": 100000 if age == 64 else 200000,
                    "basis": "confirmed",
                    "provenance": "synthetic fixture",
                }
            )
    census = tmp_path / "census.parquet"
    csv_path = tmp_path / "census.csv"
    pd.DataFrame(rows).to_csv(csv_path, index=False)
    with duckdb.connect() as connection:
        connection.read_csv(str(csv_path)).write_parquet(str(census))
    config.setup["census_parquet_path"] = str(census)
    config.contribution_sources = ContributionSourceSettings.model_validate(
        {
            "mandatory_roth_enabled": True,
            "applicability": "single_employer_401k",
            "employer_id": "synthetic",
            "wage_evidence": evidence,
            "projected_thresholds": [
                {"year": 2027, "threshold": 155000, "provenance": "test projection"}
            ],
        }
    )
    orchestrator = build_orchestrator(
        ConstructionSpec(
            config=config,
            database=database,
            threads=1,
            entry_point="invariant_test",
            validation_mode=True,
        )
    ).orchestrator
    orchestrator.execute_multi_year_simulation(start_year=2025, end_year=2027)
    with duckdb.connect(str(database), read_only=True) as connection:
        assert (
            connection.execute(
                "SELECT COUNT(DISTINCT simulation_year) FROM fct_workforce_snapshot"
            ).fetchone()[0]
            == 3
        )
        assert (
            connection.execute(
                "SELECT COUNT(*) FROM fct_workforce_snapshot WHERE pre_tax_contributions IS NULL OR roth_contributions IS NULL OR disallowed_catch_up_contributions IS NULL OR pre_tax_contributions + roth_contributions + disallowed_catch_up_contributions != ROUND(ytd_contributions, 2)"
            ).fetchone()[0]
            == 0
        )
        statuses = dict(
            connection.execute(
                "SELECT employee_id, mandatory_roth_status FROM fct_workforce_snapshot WHERE simulation_year = 2026"
            ).fetchall()
        )
        assert statuses["SOURCE_49"] == "no_base_limit_catch_up"
        assert statuses["SOURCE_50"] == "required"
        assert statuses["SOURCE_59"] == "required"
        assert statuses["SOURCE_60"] == "required"
        assert statuses["SOURCE_63"] == "required"
        assert statuses["SOURCE_64"] == "below_or_equal_threshold"
        wages = dict(
            connection.execute(
                "SELECT employee_id, prior_year_employer_fica_wages FROM fct_workforce_snapshot WHERE simulation_year = 2026"
            ).fetchall()
        )
        assert wages["SOURCE_50"] == 200000
        assert wages["SOURCE_64"] == 100000
        limits = dict(
            connection.execute(
                "SELECT employee_id, ytd_contributions FROM fct_workforce_snapshot WHERE simulation_year = 2026"
            ).fetchall()
        )
        assert limits["SOURCE_50"] == 32500
        seed_limits = connection.execute(
            "SELECT catch_up_limit, super_catch_up_limit FROM config_irs_limits WHERE limit_year = 2026"
        ).fetchone()
        assert limits["SOURCE_59"] == seed_limits[0]
        assert limits["SOURCE_60"] == 35750
        assert limits["SOURCE_63"] == seed_limits[1]
        assert limits["SOURCE_64"] == seed_limits[0]
        assert (
            connection.execute(
                "SELECT COUNT(*) FROM fct_workforce_snapshot WHERE simulation_year = 2027 AND mandatory_roth_status = 'required_under_assumptions'"
            ).fetchone()[0]
            == 5
        )
        assert (
            connection.execute(
                "SELECT COUNT(*) FROM fct_workforce_snapshot WHERE mandatory_roth_status IN ('required', 'required_under_assumptions') AND roth_contributions < mandatory_roth_required"
            ).fetchone()[0]
            == 0
        )
        return connection.execute(
            "SELECT employee_id, simulation_year, ytd_contributions, pre_tax_contributions, "
            "roth_contributions, disallowed_catch_up_contributions, mandatory_roth_status, mandatory_roth_required, "
            "mandatory_roth_reallocated, prior_year_employer_fica_wages "
            "FROM fct_workforce_snapshot ORDER BY employee_id, simulation_year"
        ).fetchall()


def test_source_allocation_three_year_pipeline(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    first = _run_source_pipeline(tmp_path / "first", monkeypatch)
    second = _run_source_pipeline(tmp_path / "second", monkeypatch)
    assert first == second
