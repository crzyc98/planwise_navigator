"""
Hazard cache batching tests (Feature 121 — Reduce Production-Path dbt Invocations, Tier A).

Verifies that ``HazardCacheManager.rebuild_hazard_caches`` issues the *batched*
invocation schedule — one ``run`` for ``int_effective_parameters`` plus one
``build`` for all four ``dim_*_hazards`` cache models and the metadata model —
instead of six separate single-model invocations, while preserving:

- the ``hazard_params_hash`` dbt var on every call,
- ``--full-refresh`` semantics, and
- per-model failure attribution (FR-012).

See specs/121-reduce-dbt-invocations/contracts/hazard-cache-batch.md.
"""

from unittest.mock import MagicMock, patch

import pytest

from planalign_orchestrator.hazard_cache_manager import (
    HazardCacheManager,
    HazardCacheError,
)


FIXED_HASH = "a" * 64


def _make_manager():
    """Construct a HazardCacheManager with a mocked dbt runner and stub config.

    ``compute_hazard_params_hash`` and ``_log_cache_statistics`` are patched so the
    test exercises only the invocation schedule, with no filesystem/DuckDB access.
    """
    dbt_runner = MagicMock()
    manager = HazardCacheManager(config=MagicMock(), dbt_runner=dbt_runner)
    manager.compute_hazard_params_hash = MagicMock(return_value=FIXED_HASH)
    manager._log_cache_statistics = MagicMock()
    return manager, dbt_runner


def _success():
    result = MagicMock()
    result.success = True
    return result


def test_rebuild_issues_two_invocations_not_six():
    """The rebuild must collapse 6 single-model calls into exactly 2 invocations."""
    manager, dbt_runner = _make_manager()
    dbt_runner.execute_command.return_value = _success()

    manager.rebuild_hazard_caches()

    assert dbt_runner.execute_command.call_count == 2, (
        "Tier A must batch the 4 dim_*_hazards + metadata into one build "
        "(int_effective_parameters run + batched build = 2 invocations)"
    )


def test_batched_selection_and_full_refresh_and_vars():
    """Assert the exact batched selection, --full-refresh, and hazard_params_hash var."""
    manager, dbt_runner = _make_manager()
    dbt_runner.execute_command.return_value = _success()

    manager.rebuild_hazard_caches()

    calls = dbt_runner.execute_command.call_args_list

    # Call 1: int_effective_parameters materialized on its own (kept as `run`).
    args1, kwargs1 = calls[0]
    assert args1[0] == [
        "run",
        "--select",
        "int_effective_parameters",
        "--full-refresh",
    ]
    assert kwargs1["dbt_vars"] == {"hazard_params_hash": FIXED_HASH}

    # Call 2: the four cache models + metadata in one --full-refresh build, DAG-ordered.
    args2, kwargs2 = calls[1]
    assert args2[0] == [
        "build",
        "--select",
        "dim_promotion_hazards",
        "dim_termination_hazards",
        "dim_merit_hazards",
        "dim_enrollment_hazards",
        "hazard_cache_metadata",
        "--full-refresh",
    ]
    assert kwargs2["dbt_vars"] == {"hazard_params_hash": FIXED_HASH}


def test_batched_selection_matches_cache_model_constants():
    """The batched selection is derived from CACHE_MODELS + METADATA_MODEL (no drift)."""
    manager, dbt_runner = _make_manager()
    dbt_runner.execute_command.return_value = _success()

    manager.rebuild_hazard_caches()

    args2, _ = dbt_runner.execute_command.call_args_list[1]
    selection = args2[0][2:-1]  # between "--select" and "--full-refresh"
    assert selection == [
        *HazardCacheManager.CACHE_MODELS,
        HazardCacheManager.METADATA_MODEL,
    ]


def test_batched_failure_still_names_failing_model():
    """A failure in the batched build surfaces the specific failing node (FR-012)."""
    manager, dbt_runner = _make_manager()

    failed = MagicMock()
    failed.success = False
    # First call (int_effective_parameters) succeeds; second (batched build) fails.
    dbt_runner.execute_command.side_effect = [_success(), failed]

    with patch(
        "planalign_orchestrator.hazard_cache_manager.extract_dbt_failure_detail",
        return_value="dim_merit_hazards: Binder Error — column not found",
    ):
        with pytest.raises(HazardCacheError) as exc:
            manager.rebuild_hazard_caches()

    assert "dim_merit_hazards" in str(exc.value)
