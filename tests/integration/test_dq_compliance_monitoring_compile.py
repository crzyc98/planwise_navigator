"""Keep the disabled compliance monitor compilable until it is integrated."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest


@pytest.mark.integration
def test_disabled_compliance_monitor_compiles(tmp_path: Path) -> None:
    source = Path(__file__).resolve().parents[2] / "dbt"
    project = tmp_path / "dbt"
    shutil.copytree(source, project, ignore=shutil.ignore_patterns("target", "logs"))
    model = project / "models/marts/data_quality/dq_compliance_monitoring.sql"
    sql = model.read_text()
    assert sql.startswith("{{config(enabled=false)}}")
    model.write_text(sql.replace("{{config(enabled=false)}}", "", 1))

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
