"""Regression test for #1038: DuckDB file names that are not plain identifiers.

dbt-duckdb names the catalog after the ``.duckdb`` file stem, and callers choose
that stem (a scenario named ``stable-baseline-101``). With database quoting off,
dbt emitted ``create table stable-baseline-101.main.comp_levers`` and the seed
step failed with a parser error.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

DBT_DIR = Path(__file__).resolve().parents[1] / "dbt"


@pytest.mark.fast
@pytest.mark.dbt
def test_dbt_project_quotes_database_names() -> None:
    project = yaml.safe_load((DBT_DIR / "dbt_project.yml").read_text())
    assert project["quoting"]["database"] is True


@pytest.mark.integration
@pytest.mark.dbt
@pytest.mark.parametrize("stem", ["stable-baseline-101", "my scenario 2"])
def test_seed_into_non_identifier_database_name(tmp_path: Path, stem: str) -> None:
    dbt = shutil.which("dbt") or str(Path(sys.executable).with_name("dbt"))
    database = tmp_path / f"{stem}.duckdb"
    result = subprocess.run(
        [dbt, "seed", "--threads", "1", "--select", "comp_levers"],
        cwd=DBT_DIR,
        env={**os.environ, "DATABASE_PATH": str(database)},
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout[-2000:]
    assert database.exists()
