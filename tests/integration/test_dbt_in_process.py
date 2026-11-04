"""Real dbt serial invocation and DuckDB ownership checks (no simulation)."""

import json
import subprocess
import sys
from pathlib import Path

import duckdb
import pytest

from planalign_orchestrator.dbt_runner import DbtRunner

pytestmark = [pytest.mark.integration, pytest.mark.dbt]
ROOT = Path(__file__).resolve().parents[2]


def test_serial_vars_and_database_release(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pytest.importorskip("dbt.cli.main")
    if not (ROOT / "dbt/dbt_packages").is_dir():
        pytest.skip("dbt/dbt_packages is missing")
    database = tmp_path / "serial.duckdb"
    runner = DbtRunner(
        working_dir=ROOT / "dbt",
        database_path=str(database),
        dbt_artifacts_dir=tmp_path / "artifacts",
    )
    monkeypatch.setenv("PLANALIGN_DBT_IN_PROCESS", "1")
    for year in (2025, 2026):
        result = runner.execute_command(
            [
                "show",
                "--inline",
                "select {{ var('simulation_year') }} as y",
                "--output",
                "json",
                "--threads",
                "1",
            ],
            simulation_year=year,
            stream_output=False,
        )
        assert result.success, result.stdout + result.stderr
        assert f'"y": {year}' in result.stdout
        artifact = json.loads((runner.target_path / "run_results.json").read_text())
        assert artifact["args"]["vars"]["simulation_year"] == year
        with duckdb.connect(str(database)) as connection:
            assert connection.execute("select 1").fetchone() == (1,)
        opened = subprocess.run(
            [
                sys.executable,
                "-c",
                "import duckdb,sys; c=duckdb.connect(sys.argv[1]); c.close()",
                str(database),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        assert opened.returncode == 0, opened.stderr
