"""Regression tests for #1196 and #1200: seed parameter lookups.

#1196: ``int_effective_parameters`` labelled its seed fallback rows ``default``,
so ``resolve_parameter`` (which filters on the run's ``scenario_id``) found
nothing in batch/CLI runs and every caller used its hard-coded fallback.

#1200: ``resolve_parameter`` compared ``event_type`` exactly, but
``stg_comp_levers`` stores it upper-cased, so a lowercase caller missed.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

DBT_DIR = Path(__file__).resolve().parents[1] / "dbt"
SCENARIO_VARS = json.dumps({"scenario_id": "batch_edge_case", "simulation_year": 2025})


def _dbt(args: list[str], database: Path) -> subprocess.CompletedProcess[str]:
    dbt = shutil.which("dbt") or str(Path(sys.executable).with_name("dbt"))
    return subprocess.run(
        [dbt, *args, "--threads", "1", "--vars", SCENARIO_VARS],
        cwd=DBT_DIR,
        env={**os.environ, "DATABASE_PATH": str(database)},
        capture_output=True,
        text=True,
        check=False,
    )


@pytest.mark.integration
@pytest.mark.dbt
def test_seed_parameters_resolve_for_non_default_scenario(tmp_path: Path) -> None:
    database = tmp_path / "iso.duckdb"
    build = _dbt(
        ["build", "--select", "comp_levers stg_comp_levers int_effective_parameters"],
        database,
    )
    assert build.returncode == 0, build.stdout[-3000:]

    inline = (
        "select "
        "{{ resolve_parameter(1, 'HIRE', 'compensation_percentile', 2025) }} as pct, "
        "{{ resolve_parameter(1, 'hire', 'new_hire_salary_adjustment', 2025) }} as adj"
    )
    show = _dbt(["show", "--quiet", "--inline", inline, "--output", "json"], database)
    assert show.returncode == 0, show.stdout[-3000:]

    row = json.loads(show.stdout)["show"][0]  # --quiet prints only the result
    assert row["pct"] == pytest.approx(0.25)  # seed, not the 0.50 fallback
    assert row["adj"] == pytest.approx(1.05)  # seed, not the 1.149 fallback
