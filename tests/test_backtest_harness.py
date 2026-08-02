"""Integration tests for the complete backtest harness."""

import pytest

from planalign_backtest.models import MetricValue
from tests.fixtures.backtest_history import (
    SELF_TEST_BUCKET_PREFIX,
    SELF_TEST_BUCKET_TOLERANCE,
    SELF_TEST_TOLERANCE,
)
from tests.fixtures.backtest_history import generate_backtest_history
from planalign_backtest import BacktestOptions
from planalign_backtest.runner import run_backtest
from pathlib import Path
from planalign_backtest.models import METRIC_REGISTRY
from planalign_backtest.report import to_json
from planalign_fit.bands import load_band_definitions
from planalign_fit.snapshots import load_snapshots
from planalign_fit.transitions import build_transitions
import duckdb
import uuid
from planalign_fit.pack import write_pack
from planalign_backtest.report import write_scorecard
from planalign_fit.apply import apply_pack
from planalign_orchestrator.config import load_simulation_config
from planalign_orchestrator.run_metadata import check_and_record_run
from planalign_orchestrator.utils import DatabaseConnectionManager
import planalign_backtest.runner as runner_module
from planalign_backtest.models import SeedRun

pytestmark = pytest.mark.integration


# `flows.promotions` is excluded from the self-test tolerance, and only from it.
# The actual side infers a promotion from a level increase between censuses, but
# the simulator's level is seeded by compensation banding, so an ordinary raise
# that crosses a band boundary is indistinguishable from a promotion when the
# "census" is simulator output (measured: 221 inferred vs 104 promotion events).
# A real client census with persistent job levels does not have this ambiguity,
# so the metric stays scored — it just cannot be certified by this fixture.
SELF_TEST_EXCLUSIONS = frozenset({"flows.promotions"})


@pytest.fixture(scope="session")
def simulated_history(tmp_path_factory):
    """One real multi-year simulation, exported as annual censuses.

    Session-scoped: generating it runs the simulator for four years, so every
    test that needs simulator-produced history shares this one run.
    """
    return generate_backtest_history(tmp_path_factory.mktemp("history") / "census")


@pytest.fixture(scope="module")
def completed_backtest(tmp_path_factory, simulated_history):
    root = tmp_path_factory.mktemp("backtest-e2e")
    history = simulated_history
    shared = Path("dbt/simulation.duckdb")
    before = (
        (shared.stat().st_size, shared.stat().st_mtime_ns) if shared.exists() else None
    )
    run = run_backtest(
        history.directory,
        BacktestOptions(
            seeds=(42,),
            output=root / "pack",
            workdir=root / "run",
            keep_databases=True,
        ),
    )
    after = (
        (shared.stat().st_size, shared.stat().st_mtime_ns) if shared.exists() else None
    )
    return run, before, after, history


def test_four_snapshots_fit_first_three_and_simulate_only_holdout(
    completed_backtest,
) -> None:
    run, _, _, _ = completed_backtest
    assert len(run.split.all_years) == 4
    assert run.split.fit_years == run.split.all_years[:3]
    assert run.seed_runs[0].years_simulated == run.split.holdout_years


def test_full_backtest_leaves_shared_database_untouched(completed_backtest) -> None:
    _, before, after, _ = completed_backtest
    assert after == before


def _tolerance_for(metric: str) -> float:
    """Per-level counts bucket a quantity that itself carries error; see fixture."""
    if metric.startswith(SELF_TEST_BUCKET_PREFIX):
        return SELF_TEST_BUCKET_TOLERANCE
    return SELF_TEST_TOLERANCE


def _self_test_errors(scorecard) -> dict[str, float]:
    """Per-metric absolute percentage error, over everything the fixture certifies."""
    return {
        comparison.metric: abs(comparison.percent_error)
        for comparison in scorecard.comparisons
        if comparison.period != "cumulative"
        and comparison.observable
        and comparison.percent_error is not None
        and comparison.metric not in SELF_TEST_EXCLUSIONS
    }


def test_end_to_end_self_test_is_inside_near_perfect_tolerance(
    completed_backtest,
) -> None:
    """Scoring the simulator against its own output must be near-perfect.

    This is the assertion that makes every other scorecard admissible: the
    history came from the simulator under the same base config the backtest
    runs, so anything the fitter does not fit agrees by construction and the
    residual is harness error.
    """
    errors = _self_test_errors(completed_backtest[0].scorecard)
    assert len(errors) >= 15, f"too few metrics certified: {sorted(errors)}"
    assert "headcount.total" in errors and "compensation.average" in errors
    over = {
        metric: error
        for metric, error in errors.items()
        if error > _tolerance_for(metric)
    }
    assert not over, f"metrics outside self-test tolerance: {over}"


def test_end_to_end_self_test_detects_a_comparison_defect(
    completed_backtest, monkeypatch
) -> None:
    """A broken comparison must fail the self-test rather than pass vacuously."""
    scorecard = completed_backtest[0].scorecard
    defective = scorecard.model_copy(
        update={
            "comparisons": tuple(
                comparison.model_copy(update={"percent_error": 0.5})
                if comparison.metric == "headcount.total"
                and comparison.period != "cumulative"
                else comparison
                for comparison in scorecard.comparisons
            )
        }
    )
    errors = _self_test_errors(defective)
    assert any(error > _tolerance_for(metric) for metric, error in errors.items())


def test_every_registry_metric_is_present_for_each_period(completed_backtest) -> None:
    run, _, _, _ = completed_backtest
    for definition in METRIC_REGISTRY:
        matching = [
            comparison
            for comparison in run.scorecard.comparisons
            if comparison.metric == definition.identifier
            or comparison.metric.startswith(definition.identifier + ".")
        ]
        assert matching, definition.identifier
        assert {comparison.period for comparison in matching} == {
            *run.split.holdout_years,
            "cumulative",
        }


def test_actual_and_predicted_band_labels_agree(completed_backtest) -> None:
    run, _, _, history = completed_backtest
    with duckdb.connect(":memory:") as conn:
        snapshots = load_snapshots(history.directory, conn)
        build_transitions(conn, snapshots, load_band_definitions())
        database = str(run.seed_runs[0].database).replace("'", "''")
        conn.execute(f"ATTACH '{database}' AS simulation (READ_ONLY)")
        year = run.split.holdout_years[-1]
        mismatch = conn.execute(
            f"SELECT COUNT(*) FROM banded_{year} actual "
            "JOIN simulation.fct_workforce_snapshot predicted USING (employee_id) "
            "WHERE actual.is_active AND predicted.simulation_year = ? "
            "AND predicted.employment_status = 'active' "
            "AND (actual.age_band <> predicted.age_band "
            "OR actual.tenure_band <> predicted.tenure_band)",
            [year],
        ).fetchone()[0]
    assert mismatch == 0


def test_completed_scorecard_serialization_is_byte_stable(completed_backtest) -> None:
    run, _, _, _ = completed_backtest
    assert to_json(run.scorecard) == to_json(run.scorecard)


def test_relative_workdir_is_resolved_before_dbt_is_invoked(
    tmp_path, monkeypatch, simulated_history
) -> None:
    """The default workdir is relative, and dbt runs with `dbt/` as its cwd.

    Left relative, the overlay project path resolves against `dbt/` and every
    run fails with "project-dir does not exist" — the default CLI invocation.
    """
    history = simulated_history
    base_config = Path("config/simulation_config.yaml").resolve()
    seen: dict[str, Path] = {}

    def capture_run_seed(applied, split, seed, workdir):
        seen["project"] = applied.dbt_project_dir
        seen["workdir"] = workdir
        return SeedRun(
            seed=seed,
            database=workdir / f"seed_{seed}.duckdb",
            config_fingerprint=f"stable-{seed}",
            years_simulated=split.holdout_years,
        )

    monkeypatch.setattr(runner_module, "run_seed", capture_run_seed)
    monkeypatch.setattr(
        runner_module,
        "extract_predicted",
        lambda database, split: {
            MetricValue(metric="headcount.total", period=period): 1.0
            for period in (*split.holdout_years, "cumulative")
        },
    )
    monkeypatch.chdir(tmp_path)

    run_backtest(
        history.directory,
        BacktestOptions(
            seeds=(42,),
            output=Path("relative-out/pack"),
            workdir=Path("relative-work"),
            base_config=base_config,
        ),
    )

    assert seen["workdir"].is_absolute()
    assert seen["project"].is_absolute()
    assert seen["project"].is_dir()


def test_multi_seed_backtest_rerun_is_byte_identical(
    tmp_path, monkeypatch, simulated_history
) -> None:
    history = simulated_history

    def fake_run_seed(applied, split, seed, workdir):
        return SeedRun(
            seed=seed,
            database=workdir / f"seed_{seed}.duckdb",
            config_fingerprint=f"stable-{seed}",
            years_simulated=split.holdout_years,
        )

    def fake_predicted(database, split):
        seed = int(Path(database).stem.split("_")[-1])
        return {
            MetricValue(metric="headcount.total", period=period): float(seed)
            for period in (*split.holdout_years, "cumulative")
        }

    original_provenance = runner_module._provenance

    def stable_provenance(snapshot_set, split, pack):
        return original_provenance(snapshot_set, split, pack).model_copy(
            update={"backtest_date": "2026-08-01T00:00:00+00:00"}
        )

    monkeypatch.setattr(runner_module, "run_seed", fake_run_seed)
    monkeypatch.setattr(runner_module, "extract_predicted", fake_predicted)
    monkeypatch.setattr(runner_module, "_provenance", stable_provenance)

    def execute(parent: str):
        root = tmp_path / parent
        return run_backtest(
            history.directory,
            BacktestOptions(
                seeds=(42, 43, 44),
                output=root / "pack",
                workdir=root / "run",
                keep_databases=True,
            ),
        )

    assert to_json(execute("first").scorecard) == to_json(execute("second").scorecard)


def _record_pack_run(pack_dir: Path, database: Path, workdir: Path):
    applied = apply_pack(
        pack_dir, Path("config/simulation_config.yaml"), workdir=workdir
    )
    config = load_simulation_config(applied.config_path, env_overrides=False)
    manager = DatabaseConnectionManager(database)
    check_and_record_run(
        manager,
        config,
        start_year=2025,
        end_year=2025,
        run_type="simulate",
        full_reset=False,
        run_id=str(uuid.uuid4()),
        construction_signature=None,
    )
    manager.close_all()
    with duckdb.connect(str(database), read_only=True) as conn:
        return conn.execute(
            "SELECT backtest_score_ref FROM run_metadata ORDER BY run_timestamp DESC LIMIT 1"
        ).fetchone()[0]


def test_backtested_pack_run_records_only_current_score_reference(
    completed_backtest, tmp_path
) -> None:
    run, _, _, _ = completed_backtest
    pack_dir = tmp_path / "pack"
    write_pack(run.pack, pack_dir)
    write_scorecard(run.scorecard, pack_dir)
    current = _record_pack_run(
        pack_dir, tmp_path / "current.duckdb", tmp_path / "current-apply"
    )
    assert current is not None

    parameters = pack_dir / "parameters.yaml"
    parameters.write_text(
        parameters.read_text(encoding="utf-8") + "\nbacktest_stale_marker: true\n",
        encoding="utf-8",
    )
    stale = _record_pack_run(
        pack_dir, tmp_path / "stale.duckdb", tmp_path / "stale-apply"
    )
    assert stale is None
