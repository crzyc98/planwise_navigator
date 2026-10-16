"""Real dbt materializations using every affected model's production config."""

from pathlib import Path
from decimal import Decimal
import re

import duckdb
import pytest

from tests.integration.test_event_publication_schema_changes import ROOT, _project, _run

pytestmark = pytest.mark.integration

SCENARIO_PARTITIONS = (
    "int_workforce_state_accumulator",
    "int_plan_design_assignment_accumulator",
    "int_deferral_escalation_state_accumulator",
    "int_enrollment_events",
    "int_employer_core_contributions",
    "int_employee_match_calculations",
    "int_employer_eligibility",
)
YEAR_PARTITIONS = ("int_plan_eligibility_override", "int_eligibility_events")
KEYED_MODELS = (
    "int_enrollment_state_accumulator",
    "int_deferral_rate_state_accumulator",
)


def _model_configs(project: Path) -> None:
    for name in (*SCENARIO_PARTITIONS, *YEAR_PARTITIONS, *KEYED_MODELS):
        source = next((ROOT / "dbt/models").rglob(f"{name}.sql")).read_text()
        config = re.search(r"^\{\{ config\([\s\S]*?^\) \}\}", source, re.MULTILINE)
        assert config is not None, name
        # Isolate schema evolution from model input generation. Full model SQL
        # is exercised separately by calibration transferability/invariant tests.
        (project / "models" / f"{name}.sql").write_text(
            config.group() + "\nSELECT * FROM {{ ref('int_current_year_events') }}\n"
            "{% if var('fail_publication', false) %}"
            "{{ config(post_hook=\"SELECT error('injected publication failure')\") }}"
            "{% endif %}\n"
        )


def _rows(database: Path, model: str) -> list[tuple]:
    with duckdb.connect(str(database), read_only=True) as connection:
        return connection.execute(
            f'SELECT scenario_id, simulation_year, compensation_amount FROM "{model}" ORDER BY 1, 2'
        ).fetchall()


def test_all_incremental_configs_allow_schema_changes_and_preserve_scope(
    tmp_path: Path,
) -> None:
    database = _project(tmp_path)
    _model_configs(tmp_path)
    for scenario, year in (("alpha", 2025), ("beta", 2026)):
        result = _run(tmp_path, scenario_id=scenario, simulation_year=year)
        assert result.returncode == 0, result.stdout + result.stderr

    for _ in range(2):
        result = _run(
            tmp_path,
            scenario_id="alpha",
            simulation_year=2026,
            amount_type="DOUBLE",
            amount=20.123456,
        )
        assert result.returncode == 0, result.stdout + result.stderr
        for model in (*SCENARIO_PARTITIONS, *KEYED_MODELS):
            assert _rows(database, model) == [
                ("alpha", 2025, 10.0),
                ("alpha", 2026, 20.123456),
                ("beta", 2026, 10.0),
            ], model
        for model in YEAR_PARTITIONS:
            # These models retain the adapter's default 'ignore' schema policy.
            assert _rows(database, model) == [
                ("alpha", 2025, 10.0),
                ("alpha", 2026, Decimal("20.12")),
            ], model

    models = (*SCENARIO_PARTITIONS, *YEAR_PARTITIONS, *KEYED_MODELS)
    before_failure = {model: _rows(database, model) for model in models}
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
    for model in models:
        assert _rows(database, model) == before_failure[model], model

    result = _run(
        tmp_path,
        scenario_id="alpha",
        simulation_year=2026,
        amount_type="DOUBLE",
        empty=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    for model in SCENARIO_PARTITIONS:
        assert _rows(database, model) == [
            ("alpha", 2025, 10.0),
            ("beta", 2026, 10.0),
        ], model
    for model in YEAR_PARTITIONS:
        assert _rows(database, model) == [("alpha", 2025, 10.0)], model
