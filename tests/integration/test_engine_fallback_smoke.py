"""Feature 119 T006: compiled engine completes end-to-end via delegation.

The foundational guarantee: with ``execution_engine: compiled``, a fresh-DB
single-year simulation completes and produces events regardless of how much
of the compiled path exists — anything not compiled-executable delegates to
in-process dbt. Post-T012 the same run should show run-invocations on the
compiled path; this test intentionally does not constrain fallback counts.
"""


import duckdb
import pytest

from planalign_orchestrator import create_orchestrator
from tests.fixtures.invariant_simulation import (
    CENSUS_CSV,
    _database_environment,
    _simulation_config,
)

pytestmark = [pytest.mark.integration, pytest.mark.slow]


@pytest.fixture(scope="module")
def tiny_parquet(tmp_path_factory):
    path = tmp_path_factory.mktemp("engine-smoke") / "census.parquet"
    with duckdb.connect() as conn:
        conn.read_csv(str(CENSUS_CSV)).write_parquet(str(path))
    return path


def test_compiled_engine_completes_single_year(tmp_path_factory, tiny_parquet):
    db = tmp_path_factory.mktemp("engine-smoke-db") / "smoke.duckdb"
    config = _simulation_config(tiny_parquet)
    config.simulation.start_year = 2025
    config.simulation.end_year = 2025
    config.optimization.execution_engine = "compiled"

    with _database_environment(db):
        orchestrator = create_orchestrator(config, db_path=db, threads=1)
        orchestrator.execute_multi_year_simulation(start_year=2025, end_year=2025)

    with duckdb.connect(str(db), read_only=True) as conn:
        events = conn.execute("SELECT COUNT(*) FROM fct_yearly_events").fetchone()[0]
    assert events > 0

    log = orchestrator.dbt_runner.record_log
    assert log.delegations, "seed/build/no-vars invocations must be recorded"
    reasons = {r.reason for r in log.delegations}
    assert "command_type" in reasons  # seed + hazard-cache builds
