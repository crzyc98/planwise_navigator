"""Keep the disabled compliance monitor compilable until it is integrated."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import duckdb
import pytest


def _compiled_model(tmp_path: Path) -> str:
    source = Path(__file__).resolve().parents[2] / "dbt"
    project = tmp_path / "dbt"
    shutil.copytree(source, project, ignore=shutil.ignore_patterns("target", "logs"))
    model = project / "models/marts/data_quality/dq_compliance_monitoring.sql"
    assert not model.read_text().startswith("{{config(enabled=false)}}")

    environment = os.environ.copy()
    environment.update(
        DATABASE_PATH=str(tmp_path / "compile.duckdb"),
        DBT_TARGET_PATH=str(tmp_path / "target"),
        DBT_LOG_PATH=str(tmp_path / "logs"),
    )
    dbt = Path(sys.executable).with_name("dbt")
    result = subprocess.run(
        [str(dbt), "compile", "--select", "dq_compliance_monitoring", "--threads", "1"],
        cwd=project,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    compiled = (
        tmp_path
        / "target/compiled/fidelity_planalign_engine/models/marts/data_quality/dq_compliance_monitoring.sql"
    )
    assert compiled.exists()
    return compiled.read_text()


@pytest.mark.integration
def test_compliance_monitor_compiles(tmp_path: Path) -> None:
    assert "IRS_402G_COMPLIANCE" in _compiled_model(tmp_path)


@pytest.mark.integration
def test_compliance_monitor_classifies_fixture_states(tmp_path: Path) -> None:
    sql = _compiled_model(tmp_path)
    with duckdb.connect(str(tmp_path / "compile.duckdb")) as connection:
        connection.execute("""
            CREATE TABLE config_irs_limits AS
            SELECT 2025 AS limit_year, 50 AS catch_up_age_threshold,
                   23500 AS base_limit, 31000 AS catch_up_limit,
                   350000 AS compensation_limit
        """)
        connection.execute("""
            CREATE TABLE int_employee_contributions AS
            SELECT employee_id, 2025 AS simulation_year, contribution AS annual_contribution_amount,
                   requested AS requested_contribution_amount, 0.06 AS effective_annual_deferral_rate,
                   40 AS current_age, 23500 AS applicable_irs_limit,
                   limited AS irs_limit_applied, TRUE AS is_enrolled_flag,
                   pay AS prorated_annual_compensation, flag AS data_quality_flag,
                   source AS deferral_rate_source_quality
            FROM (VALUES
                ('normal', 6000, 6000, FALSE, 100000, 'NORMAL', 'VALID'),
                ('limited', 23500, 30000, TRUE, 500000, 'IRS_LIMITED', 'VALID'),
                ('fallback', 0, 0, FALSE, 0, 'NORMAL', 'default_zero'),
                ('bad_rate', 0, 0, FALSE, 100000, 'NORMAL', 'INVALID_RATE'),
                ('bad_id', 0, 0, FALSE, 100000, 'IRS_LIMITED', 'INVALID_EMPLOYEE_ID'),
                ('over_402g', 24000, 24000, FALSE, 100000, 'NORMAL', 'VALID')
            ) AS rows(employee_id, contribution, requested, limited, pay, flag, source)
        """)
        rows = connection.execute(
            f"SELECT compliance_category, violation_count, employees_with_excess, "
            f"total_excess_contributions, compliance_status FROM ({sql})"
        ).fetchall()

    categories = {row[0]: row[1:] for row in rows}
    assert categories == {
        "IRS_402G_COMPLIANCE": (1, 1, 500, "VIOLATIONS_DETECTED"),
        "PLAN_ADMINISTRATION_COMPLIANCE": (2, 0, 0, "ADMINISTRATIVE_ISSUES"),
    }
