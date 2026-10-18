"""Exercise real dbt event publication against a disposable DuckDB database."""

from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess

import duckdb
import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
pytestmark = pytest.mark.integration

SOURCE = """
{{ config(materialized='ephemeral') }}
SELECT
  'event' AS event_id,
  '{{ var('scenario_id') }}' AS scenario_id,
  'default' AS plan_design_id,
  'employee_{{ var('scenario_id') }}' AS employee_id,
  'synthetic' AS employee_ssn,
  'raise' AS event_type,
  {{ var('simulation_year') }} AS simulation_year,
  DATE '2025-01-01' AS effective_date,
  'synthetic event' AS event_details,
  CAST({{ var('amount', 10) }} AS {{ var('amount_type', 'DECIMAL(10,2)') }}) AS compensation_amount,
  1.0 AS previous_compensation,
  0.05 AS employee_deferral_rate,
  0.04 AS prev_employee_deferral_rate,
  40 AS employee_age,
  5 AS employee_tenure,
  1 AS level_id,
  '35-45' AS age_band,
  '5-10' AS tenure_band,
  1.0 AS event_probability,
  'compensation' AS event_category,
  1 AS event_sequence,
  TIMESTAMP '2025-01-01' AS created_at,
  'default' AS parameter_scenario_id,
  'test' AS parameter_source,
  'valid' AS data_quality_flag
WHERE NOT {{ var('empty', false) }}
"""


def _project(path: Path) -> Path:
    for folder in ("models", "macros"):
        (path / folder).mkdir()
    (path / "dbt_project.yml").write_text(
        yaml.safe_dump(
            {"name": "event_test", "version": "1.0", "profile": "event_test"}
        )
    )
    database = path / "events.duckdb"
    (path / "profiles.yml").write_text(
        yaml.safe_dump(
            {
                "event_test": {
                    "target": "test",
                    "outputs": {
                        "test": {
                            "type": "duckdb",
                            "path": str(database),
                            "threads": 1,
                        }
                    },
                },
            }
        )
    )
    shutil.copy2(ROOT / "dbt/models/marts/fct_yearly_events.sql", path / "models")
    # Inject a failure after insertion to exercise the real materialization's rollback.
    with (path / "models/fct_yearly_events.sql").open("a") as model:
        model.write(
            "\n{% if var('fail_publication', false) %}"
            "{{ config(post_hook=\"SELECT error('injected publication failure')\") }}"
            "{% endif %}\n"
        )
    macro = ROOT / "dbt/macros/utils/incremental_year_replace.sql"
    shutil.copy2(macro, path / "macros")
    (path / "models/int_current_year_events.sql").write_text(SOURCE)
    return database


def _run(path: Path, **variables: object) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env.update(
        DBT_TARGET_PATH=str(path / "target"),
        DBT_LOG_PATH=str(path / "logs"),
        DBT_SEND_ANONYMOUS_USAGE_STATS="false",
    )
    return subprocess.run(
        [
            "dbt",
            "run",
            "--profiles-dir",
            str(path),
            "--threads",
            "1",
            "--vars",
            json.dumps(variables),
        ],
        cwd=path,
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )


def _rows(database: Path) -> list[tuple]:
    with duckdb.connect(str(database), read_only=True) as connection:
        return connection.execute(
            "SELECT scenario_id, simulation_year, compensation_amount "
            "FROM fct_yearly_events ORDER BY 1, 2"
        ).fetchall()


def test_event_schema_change_preserves_history_and_atomic_replacement(
    tmp_path: Path,
) -> None:
    database = _project(tmp_path)
    for scenario, year in (("alpha", 2025), ("alpha", 2026), ("beta", 2026)):
        result = _run(tmp_path, scenario_id=scenario, simulation_year=year)
        assert result.returncode == 0, result.stdout + result.stderr

    # A calibration candidate changes an inferred SQL type in an existing table.
    result = _run(
        tmp_path,
        scenario_id="alpha",
        simulation_year=2026,
        amount_type="DOUBLE",
        amount=20.123456,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    expected = [("alpha", 2025, 10.0), ("alpha", 2026, 20.123456), ("beta", 2026, 10.0)]
    assert _rows(database) == expected

    # Repeating the candidate must replace, not duplicate, the year's events.
    result = _run(
        tmp_path,
        scenario_id="alpha",
        simulation_year=2026,
        amount_type="DOUBLE",
        amount=20.123456,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert _rows(database) == expected

    # Roll back schema changes, deletion AND insertion if a later step fails.
    result = _run(
        tmp_path,
        scenario_id="alpha",
        simulation_year=2026,
        amount_type="DECIMAL(18,6)",
        amount=99,
        fail_publication=True,
    )
    assert result.returncode != 0
    assert "injected publication failure" in result.stdout
    assert _rows(database) == expected
    with duckdb.connect(str(database), read_only=True) as connection:
        assert connection.execute(
            "SELECT data_type FROM information_schema.columns "
            "WHERE table_name='fct_yearly_events' AND column_name='compensation_amount'"
        ).fetchone() == ("DOUBLE",)

    # Zero current events must still clear the target year, preserving other scopes.
    result = _run(
        tmp_path,
        scenario_id="alpha",
        simulation_year=2026,
        amount_type="DOUBLE",
        empty=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert _rows(database) == [("alpha", 2025, 10.0), ("beta", 2026, 10.0)]
