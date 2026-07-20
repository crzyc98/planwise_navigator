"""Forced known-unsupported delegation matrix for Feature 119."""

from pathlib import Path

import duckdb
import pytest

from planalign_orchestrator.config import load_simulation_config, to_dbt_vars
from planalign_orchestrator.engine.compiled_runner import CompiledRunner
from planalign_orchestrator.engine.fallback import invoke_dbt_delegated
from planalign_orchestrator.engine.preflight import KnownUnsupportedSemantics
from planalign_orchestrator.engine.workspace import RunArtifactWorkspace
from planalign_orchestrator.run_execution_metadata import (
    append_run_execution_metadata,
)
from planalign_orchestrator.run_summary import aggregate_execution_records
from planalign_orchestrator.tools.parity import compare_table_multisets
from planalign_orchestrator.utils import DatabaseConnectionManager
from tests.fixtures.invariant_simulation import CONFIG_YAML

pytestmark = [pytest.mark.integration, pytest.mark.slow]

REASON_CODES = (
    "command",
    "option",
    "selector_context",
    "empty_selection",
    "resource_type",
    "materialization",
    "incremental_strategy",
    "hook",
    "schema_change",
    "full_refresh",
)


def _seed(manager: DatabaseConnectionManager, workspace: RunArtifactWorkspace) -> None:
    result = invoke_dbt_delegated(
        ["seed", "--full-refresh"],
        workspace=workspace,
        sequence=0,
        db_manager=manager,
    )
    assert result.success, result.stderr


def test_forced_reason_codes_delegate_before_writes_with_identical_output(
    tmp_path: Path, monkeypatch
) -> None:
    baseline_db = tmp_path / "baseline.duckdb"
    candidate_db = tmp_path / "candidate.duckdb"
    baseline_manager = DatabaseConnectionManager(baseline_db)
    candidate_manager = DatabaseConnectionManager(candidate_db)
    baseline_workspace = RunArtifactWorkspace.create(
        db_manager=baseline_manager, artifact_root=tmp_path / "baseline-ws"
    )
    candidate_workspace = RunArtifactWorkspace.create(
        db_manager=candidate_manager, artifact_root=tmp_path / "candidate-ws"
    )
    _seed(baseline_manager, baseline_workspace)
    _seed(candidate_manager, candidate_workspace)

    config = load_simulation_config(CONFIG_YAML, env_overrides=False)
    dbt_vars = to_dbt_vars(config)
    baseline = invoke_dbt_delegated(
        ["run", "--select", "stg_config_age_bands"],
        workspace=baseline_workspace,
        sequence=1,
        db_manager=baseline_manager,
        simulation_year=2025,
        dbt_vars=dbt_vars,
    )
    assert baseline.success, baseline.stderr

    runner = CompiledRunner(
        working_dir=Path("dbt"),
        threads=1,
        db_manager=candidate_manager,
        database_path=str(candidate_db),
    )
    runner._workspace = candidate_workspace

    def no_direct_execution(**_kwargs):
        raise AssertionError("forced preflight delegation reached direct execution")

    monkeypatch.setattr(
        "planalign_orchestrator.engine.transaction.execute_invocation_transaction",
        no_direct_execution,
    )

    for code in REASON_CODES:
        candidate_manager.close_all()
        with duckdb.connect(str(candidate_db)) as connection:
            connection.execute("DROP TABLE IF EXISTS stg_config_age_bands")

        def force_unsupported(_request, reason=code):
            raise KnownUnsupportedSemantics(reason, "forced matrix case")

        monkeypatch.setattr(runner, "_preflight", force_unsupported)
        result = runner.execute_command(
            ["run", "--select", "stg_config_age_bands"],
            description="forced-delegation-matrix",
            simulation_year=2025,
            dbt_vars=dbt_vars,
        )
        assert result.success
        parity = compare_table_multisets(
            baseline_db,
            candidate_db,
            table="stg_config_age_bands",
        )
        assert parity.identical, (code, parity)

    summary = aggregate_execution_records(runner.execution_records)
    assert summary["unexpected_fallbacks"] == 0
    assert set(summary["reason_counts"]) == set(REASON_CODES)

    append_run_execution_metadata(
        candidate_manager,
        run_id="forced-delegation-matrix",
        status="success",
        execution_engine="compiled",
        records=runner.execution_records,
    )
    candidate_manager.close_all()
    with duckdb.connect(str(candidate_db), read_only=True) as connection:
        reason_json = connection.execute(
            "SELECT reason_counts_json FROM run_execution_metadata"
        ).fetchone()[0]
    assert all(f'"{code}"' in reason_json for code in REASON_CODES)
