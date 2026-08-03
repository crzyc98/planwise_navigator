"""Isolated integration coverage for the complete ensemble aggregation path."""

from __future__ import annotations

from pathlib import Path

import duckdb
import pytest

from planalign_ensemble.models import EnsembleSpec
from planalign_ensemble.planner import plan_ensemble
from planalign_ensemble.runner import _discard_seed_databases, run_ensemble
from planalign_orchestrator.config import SimulationConfig
from planalign_orchestrator.run_metadata import compute_config_fingerprint


def _write_seed_snapshot(database: Path, seed: int) -> None:
    """Build a tiny deterministic per-seed mart used in place of dbt for this test."""
    database.parent.mkdir(parents=True, exist_ok=True)
    with duckdb.connect(str(database)) as conn:
        conn.execute(
            "CREATE TABLE fct_workforce_snapshot ("
            "simulation_year INTEGER, employment_status VARCHAR, "
            "prorated_annual_compensation DOUBLE, employer_match_amount DOUBLE, "
            "total_employer_contributions DOUBLE, participation_status VARCHAR, "
            "current_deferral_rate DOUBLE)"
        )
        conn.execute(
            "INSERT INTO fct_workforce_snapshot VALUES (?, 'active', ?, ?, ?, "
            "'participating', 0.06)",
            [2027, float(seed), float(seed) / 10, float(seed) / 5],
        )


def _mtime(path: Path) -> int | None:
    """Capture write metadata without opening a potentially PII-bearing database."""
    return path.stat().st_mtime_ns if path.exists() else None


@pytest.mark.integration
def test_ensemble_uses_isolated_seed_dbs_and_never_mutates_them_after_run(
    tmp_path, monkeypatch
) -> None:
    """Aggregation reads immutable seed results and leaves the shared DB untouched."""
    plan = plan_ensemble(
        EnsembleSpec(
            scenario_id="small-census",
            seed_count=3,
            start_year=2027,
            end_year=2027,
            min_seeds=2,
        ),
        output_root=tmp_path,
    )

    import planalign_ensemble.runner as runner

    def fake_seed_worker(job):
        _write_seed_snapshot(job.db_path, job.seed)
        return {"config_fingerprint": "fixture"}

    shared_database = Path("dbt/simulation.duckdb")
    shared_before = _mtime(shared_database)
    monkeypatch.setattr(runner, "run_seed_worker", fake_seed_worker)

    result = run_ensemble(plan, parallel=1, config=object())

    seed_mtimes = {seed: _mtime(path) for seed, path in plan.seed_db_paths.items()}
    assert all(outcome.succeeded for outcome in result.outcomes)
    assert plan.ensemble_db_path.exists()
    assert all(timestamp is not None for timestamp in seed_mtimes.values())
    assert _mtime(shared_database) == shared_before

    with duckdb.connect(str(plan.ensemble_db_path), read_only=True) as conn:
        assert conn.execute(
            "SELECT COUNT(*) FROM fct_metric_seed_values"
        ).fetchone() == (18,)
        assert conn.execute(
            "SELECT COUNT(*) FROM fct_metric_distributions"
        ).fetchone() == (6,)

    assert {
        seed: _mtime(path) for seed, path in plan.seed_db_paths.items()
    } == seed_mtimes


@pytest.mark.integration
def test_discard_seed_dbs_retains_only_the_aggregate_after_aggregation(
    tmp_path, monkeypatch
) -> None:
    """The explicit discard option removes only known seed paths after persistence."""
    plan = plan_ensemble(
        EnsembleSpec(
            scenario_id="small-census",
            seed_count=2,
            start_year=2027,
            end_year=2027,
            min_seeds=2,
            discard_seed_dbs=True,
        ),
        output_root=tmp_path,
    )

    import planalign_ensemble.runner as runner

    def fake_seed_worker(job):
        _write_seed_snapshot(job.db_path, job.seed)
        return {"config_fingerprint": "fixture"}

    monkeypatch.setattr(runner, "run_seed_worker", fake_seed_worker)

    run_ensemble(plan, parallel=1, config=object())

    assert plan.ensemble_db_path.exists()
    assert not any(path.exists() for path in plan.seed_db_paths.values())


@pytest.mark.integration
def test_discard_seed_dbs_also_removes_attribution_seed_worlds(tmp_path) -> None:
    """The opt-in cleanup never leaves frozen seed databases behind."""
    plan = plan_ensemble(
        EnsembleSpec(
            scenario_id="cleanup-fixture",
            seed_count=2,
            start_year=2027,
            end_year=2027,
            discard_seed_dbs=True,
        ),
        output_root=tmp_path,
    )
    plan.ensemble_db_path.parent.mkdir(parents=True, exist_ok=True)
    plan.ensemble_db_path.touch()
    frozen_path = (
        plan.ensemble_db_path.parent / "attribution" / "termination" / "seed_42.duckdb"
    )
    frozen_path.parent.mkdir(parents=True)
    frozen_path.touch()
    for path in plan.seed_db_paths.values():
        path.touch()

    _discard_seed_databases(plan)

    assert plan.ensemble_db_path.exists()
    assert not frozen_path.exists()
    assert not any(path.exists() for path in plan.seed_db_paths.values())


@pytest.mark.integration
def test_attribution_ranks_dominant_stream_and_marks_structural_absences(
    tmp_path, monkeypatch
) -> None:
    """A synthetic world isolates a large termination effect from a zero effect."""
    plan = plan_ensemble(
        EnsembleSpec(
            scenario_id="attribution-fixture",
            seed_count=3,
            start_year=2029,
            end_year=2029,
            min_seeds=2,
            attribution=True,
            attribution_seed_count=3,
        ),
        output_root=tmp_path,
    )
    config = SimulationConfig(
        scenario_id="attribution-fixture",
        simulation={"start_year": 2029, "end_year": 2029, "random_seed": 42},
        compensation={},
    )
    executed: list[str] = []

    import planalign_ensemble.runner as runner

    def fake_seed_worker(job):
        executed.append(job.name)
        frozen = job.config.ensemble.frozen_subsystem_seeds
        termination_seed = frozen.get("termination", job.seed)
        hiring_seed = frozen.get("hiring", job.seed)
        # Promotion is intentionally deterministic in this fixture. The
        # termination component dominates the spread by an order of magnitude.
        value = (10.0 * termination_seed) + hiring_seed
        _write_attribution_snapshot(job.db_path, value)
        return {"config_fingerprint": compute_config_fingerprint(job.config)}

    monkeypatch.setattr(runner, "run_seed_worker", fake_seed_worker)
    result = run_ensemble(plan, parallel=1, config=config)

    cost_shares = [
        share
        for share in result.attribution
        if share.metric == "total_employer_plan_cost" and share.simulation_year == 2029
    ]
    stochastic = [
        share for share in cost_shares if share.stochastic_status == "stochastic"
    ]
    by_subsystem = {share.subsystem.value: share for share in cost_shares}

    assert stochastic[0].subsystem.value == "termination"
    assert (
        by_subsystem["termination"].variance_share
        > by_subsystem["hiring"].variance_share
    )
    assert by_subsystem["promotion"].variance_share == 0.0
    assert by_subsystem["termination"].baselines_reused == 3
    assert by_subsystem["termination"].baselines_executed == 0
    assert by_subsystem["enrollment"].stochastic_status == "not_stochastic"
    assert by_subsystem["enrollment"].variance_share is None
    assert by_subsystem["merit"].stochastic_status == "not_stochastic"
    assert not any(name.startswith("baseline_") for name in executed)

    with duckdb.connect(str(plan.ensemble_db_path), read_only=True) as conn:
        assert (
            conn.execute("SELECT COUNT(*) FROM fct_variance_attribution").fetchone()[0]
            > 0
        )


@pytest.mark.integration
def test_thin_sample_skips_attribution_instead_of_reporting_degenerate_shares(
    tmp_path, monkeypatch
) -> None:
    """Below the configured band floor, attribution must not invent a finding."""
    plan = plan_ensemble(
        EnsembleSpec(
            scenario_id="thin-attribution-fixture",
            seed_count=3,
            start_year=2029,
            end_year=2029,
            min_seeds=4,
            attribution=True,
            attribution_seed_count=3,
        ),
        output_root=tmp_path,
    )
    config = SimulationConfig(
        scenario_id="thin-attribution-fixture",
        simulation={"start_year": 2029, "end_year": 2029, "random_seed": 42},
        compensation={},
    )

    import planalign_ensemble.runner as runner

    def fake_seed_worker(job):
        _write_attribution_snapshot(job.db_path, float(job.seed))
        return {"config_fingerprint": compute_config_fingerprint(job.config)}

    monkeypatch.setattr(runner, "run_seed_worker", fake_seed_worker)
    result = run_ensemble(plan, parallel=1, config=config)

    assert result.attribution == ()
    assert not (plan.ensemble_db_path.parent / "attribution" / "termination").exists()


def _write_attribution_snapshot(database: Path, value: float) -> None:
    """Write a one-row mart whose component formula is controlled by the test."""
    database.parent.mkdir(parents=True, exist_ok=True)
    with duckdb.connect(str(database)) as conn:
        conn.execute(
            "CREATE TABLE fct_workforce_snapshot ("
            "simulation_year INTEGER, employment_status VARCHAR, "
            "prorated_annual_compensation DOUBLE, employer_match_amount DOUBLE, "
            "total_employer_contributions DOUBLE, participation_status VARCHAR, "
            "current_deferral_rate DOUBLE)"
        )
        conn.execute(
            "INSERT INTO fct_workforce_snapshot VALUES "
            "(2029, 'active', ?, ?, ?, 'participating', 0.06)",
            [value, value, value],
        )
