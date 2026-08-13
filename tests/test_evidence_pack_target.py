"""Read-only target boundary tests for evidence packs."""

from __future__ import annotations

import pytest

from planalign_evidence.service import EvidenceTarget, UnsupportedEvidenceError
from tests.fixtures.evidence_pack import create_evidence_scenario


@pytest.mark.fast
def test_target_discovers_schema_and_years_without_writing(tmp_path) -> None:
    scenario = create_evidence_scenario(tmp_path)
    before = scenario.database_path.stat()
    target = EvidenceTarget(
        database_path=scenario.database_path,
        result_store=scenario.result_store,
        scenario_id=scenario.scenario_id,
        run_id=scenario.run_id,
    )

    support = target.inspect()

    after = scenario.database_path.stat()
    assert support.available_years == (2025, 2027)
    assert "employee_id" in support.columns
    assert (after.st_size, after.st_mtime_ns) == (before.st_size, before.st_mtime_ns)


@pytest.mark.fast
def test_target_rejects_missing_table_and_absolute_locator(tmp_path) -> None:
    missing = tmp_path / "missing.duckdb"
    with pytest.raises(ValueError):
        EvidenceTarget(
            database_path=missing,
            result_store="/absolute/simulation.duckdb",
            scenario_id="scenario",
            run_id="legacy",
        )
    missing.touch()
    target = EvidenceTarget(
        database_path=missing,
        result_store="simulation.duckdb",
        scenario_id="scenario",
        run_id="legacy",
    )
    with pytest.raises(UnsupportedEvidenceError):
        target.inspect()
