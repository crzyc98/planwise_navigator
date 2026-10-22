"""Safety and decision-quality tests for experimental candidate screening."""

from pathlib import Path
from collections.abc import Callable, Sequence
import json
import sys

import pytest
import duckdb

from planalign_optimizer.evaluate import classify_candidate
from planalign_optimizer.models import (
    BaselineSpec,
    ConstraintSpec,
    DesignSpaceSpec,
    LeverSpec,
    ObjectiveConstraintSpec,
    ObjectiveTerm,
    OptimizerSpec,
    Candidate,
    LeverValue,
)
from scripts.perf_profile.screening import ScreeningPolicy, select_for_validation
from scripts.perf_profile.screening_benchmark import (
    BenchmarkSettings,
    compare_quality,
    run_screening_benchmark,
    summarize_benchmark,
)
from planalign_orchestrator.config import SimulationConfig, load_simulation_config
from planalign_orchestrator.run_pool import (
    PoolEvent,
    ScenarioRunPool,
    WorkerBudget,
    resolve_worker_count,
)

pytestmark = pytest.mark.fast


def _spec(two_objectives: bool = False) -> OptimizerSpec:
    objectives: tuple[ObjectiveTerm, ...] = (
        ObjectiveTerm(metric="total_employer_plan_cost", direction="minimize"),
    )
    if two_objectives:
        objectives += (ObjectiveTerm(metric="avg_deferral_rate", direction="maximize"),)
    return OptimizerSpec(
        baseline=BaselineSpec(config_path=Path("config/simulation_config.yaml")),
        design_space=DesignSpaceSpec(
            levers=(
                LeverSpec(
                    name="eligibility.waiting_period_days",
                    kind="discrete",
                    choices=(0, 365),
                ),
                LeverSpec(
                    name="auto_escalation.enabled",
                    kind="discrete",
                    choices=(False, True),
                ),
            )
        ),
        objective=ObjectiveConstraintSpec(
            objectives=objectives,
            constraints=(
                ConstraintSpec(
                    metric="participation_rate", operator=">=", threshold=0.80
                ),
            ),
        ),
    )


def _candidate(
    identifier: str,
    participation: float | None = 0.9,
    cost: float = 100.0,
    deferral: float = 0.05,
    spec: OptimizerSpec | None = None,
) -> Candidate:
    return classify_candidate(
        identifier,
        {},
        None,
        (spec or _spec()).objective,
        {
            "participation_rate": participation,
            "total_employer_plan_cost": cost,
            "avg_deferral_rate": deferral,
        },
    )


def test_screening_keeps_feasible_borderline_and_unknown_evidence() -> None:
    candidates = (
        _candidate("feasible"),
        _candidate("borderline", participation=0.79),
        _candidate("unknown", participation=None),
        _candidate("failed").model_copy(update={"status": "failed"}),
    )
    selected = select_for_validation(
        candidates, _spec().objective, ScreeningPolicy(), seed=1
    )
    assert selected == {
        "borderline": "near_constraint_boundary",
        "failed": "uncertain_evidence",
        "feasible": "screen_feasible",
        "unknown": "uncertain_evidence",
    }


def test_audit_is_deterministic_and_does_not_reclassify_rejected_points() -> None:
    candidates = tuple(_candidate(str(index), participation=0.3) for index in range(10))
    selected = select_for_validation(
        candidates, _spec().objective, ScreeningPolicy(), seed=7
    )
    assert len(selected) == 1 and set(selected.values()) == {"audit_sample"}
    assert selected == select_for_validation(
        candidates[::-1], _spec().objective, ScreeningPolicy(), seed=7
    )
    assert all(candidate.status == "infeasible" for candidate in candidates)


def test_cost_ceiling_keeps_borderline_candidates_and_audits_far_violations() -> None:
    spec = _spec().objective.model_copy(
        update={
            "constraints": (
                ConstraintSpec(
                    metric="total_employer_plan_cost", operator="<=", threshold=100
                ),
            )
        }
    )
    candidates = tuple(
        classify_candidate(
            identifier, {}, None, spec, {"total_employer_plan_cost": cost}
        )
        for identifier, cost in (("near", 103), ("far-a", 200), ("far-b", 300))
    )
    selected = select_for_validation(candidates, spec, ScreeningPolicy(), seed=1)
    assert selected["near"] == "near_constraint_boundary"
    assert list(selected.values()).count("audit_sample") == 1


@pytest.mark.parametrize("value", [float("inf"), float("nan"), None])
def test_nonfinite_or_missing_screen_evidence_is_retained(value: float | None) -> None:
    candidate = _candidate("uncertain", participation=value)
    assert "uncertain" in select_for_validation(
        (candidate,), _spec().objective, ScreeningPolicy(), seed=1
    )


@pytest.mark.parametrize("two_objectives", [False, True])
def test_quality_detects_rejected_long_term_winner(two_objectives: bool) -> None:
    spec = _spec(two_objectives)
    winner = _candidate("later_winner", cost=80, deferral=0.07, spec=spec)
    other = _candidate("early_winner", cost=100, deferral=0.05, spec=spec)
    quality = compare_quality((winner, other), (other,), spec)
    assert quality.missed_feasible == ("later_winner",)
    assert quality.frontier_retention == 0.0
    assert quality.evidence_complete and quality.replay_matches
    assert quality.objective_loss_fraction == (None if two_objectives else 0.25)


def test_quality_detects_validation_failure_instead_of_treating_it_as_recall() -> None:
    candidate = _candidate("winner")
    failed = candidate.model_copy(update={"status": "failed", "objective_values": {}})
    quality = compare_quality((candidate,), (failed,), _spec())
    assert not quality.evidence_complete
    assert not quality.replay_matches
    assert quality.frontier_retention == 0.0


def test_nonfinite_objectives_cannot_pass_quality_gate() -> None:
    candidate = _candidate("invalid", cost=float("inf"))
    assert not compare_quality((candidate,), (candidate,), _spec()).evidence_complete


def _fake_evaluator(
    calls: list[tuple[int, Path, int, int]],
) -> Callable[..., tuple[Candidate, ...]]:
    def evaluate(
        values: Sequence[dict[str, LeverValue]],
        spec: OptimizerSpec,
        config: SimulationConfig,
        directory: Path,
        limit: int,
        budget: WorkerBudget,
        pool_factory: Callable[[int], ScenarioRunPool],
        on_event: Callable[[PoolEvent], None] | None,
    ) -> tuple[Candidate, ...]:
        calls.append(
            (config.simulation.end_year, directory, budget.workers, len(values))
        )
        full = config.simulation.end_year > config.simulation.start_year
        return tuple(
            _candidate(
                f"candidate-{index:04d}",
                participation=(
                    0.9 if full or not value["eligibility.waiting_period_days"] else 0.3
                ),
                cost=100 if not value["eligibility.waiting_period_days"] else 80,
                spec=spec,
            ).model_copy(update={"lever_values": value})
            for index, value in enumerate(values)
        )

    return evaluate


def test_paired_benchmark_isolated_bounded_and_preserves_original_ids(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[tuple[int, Path, int, int]] = []
    monkeypatch.setattr(
        "scripts.perf_profile.screening_benchmark._evaluate_candidate_values",
        _fake_evaluator(calls),
    )
    baseline = load_simulation_config(
        "config/simulation_config.yaml", env_overrides=False
    )
    original = baseline.model_dump()
    settings = BenchmarkSettings(candidate_count=4, repetitions=1, max_simulations=12)
    report = run_screening_benchmark(
        _spec(), baseline, settings, tmp_path / "run", resolve_worker_count(2, 4)
    )
    assert [call[0] for call in calls] == [2029, 2025, 2029]
    assert all(call[2] == 2 and call[1].is_relative_to(tmp_path) for call in calls)
    assert len({call[1] for call in calls}) == 3
    assert baseline.model_dump() == original
    assert report.simulation_count == sum(call[3] for call in calls) <= 12
    trial = report.trials[0]
    assert {candidate.candidate_id for candidate in trial.validation.candidates} == set(
        trial.selection
    )
    assert trial.quality.replay_matches
    assert len(trial.quality.missed_feasible) == 1
    assert report.decision == "NO_GO"
    assert (tmp_path / "run/settings.json").exists()
    assert trial.reference.config_fingerprint != trial.screening.config_fingerprint


def test_prespecified_budget_rejects_before_any_runs_or_writes(tmp_path: Path) -> None:
    baseline = load_simulation_config(
        "config/simulation_config.yaml", env_overrides=False
    )
    with pytest.raises(ValueError, match="reserve at least 12"):
        run_screening_benchmark(
            _spec(),
            baseline,
            BenchmarkSettings(candidate_count=4, repetitions=1, max_simulations=11),
            tmp_path / "run",
            resolve_worker_count(2, 4),
        )
    assert not (tmp_path / "run").exists()


def test_existing_output_is_never_reused(tmp_path: Path) -> None:
    baseline = load_simulation_config(
        "config/simulation_config.yaml", env_overrides=False
    )
    with pytest.raises(ValueError, match="must be fresh"):
        run_screening_benchmark(
            _spec(),
            baseline,
            BenchmarkSettings(candidate_count=4, repetitions=1, max_simulations=12),
            tmp_path,
            resolve_worker_count(2, 4),
        )


def test_percentile_constraints_are_rejected_without_point_fallback(
    tmp_path: Path,
) -> None:
    spec = _spec()
    constraint = spec.objective.constraints[0].model_copy(update={"percentile": 90})
    spec = spec.model_copy(
        update={
            "objective": spec.objective.model_copy(
                update={"constraints": (constraint,)}
            )
        }
    )
    baseline = load_simulation_config(
        "config/simulation_config.yaml", env_overrides=False
    )
    with pytest.raises(ValueError, match="point estimates only"):
        run_screening_benchmark(
            spec,
            baseline,
            BenchmarkSettings(candidate_count=4, repetitions=1, max_simulations=12),
            tmp_path / "run",
            resolve_worker_count(2, 4),
        )


def test_single_fast_trial_cannot_authorize_rollout(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "scripts.perf_profile.screening_benchmark._evaluate_candidate_values",
        _fake_evaluator([]),
    )
    baseline = load_simulation_config(
        "config/simulation_config.yaml", env_overrides=False
    )
    settings = BenchmarkSettings(candidate_count=4, repetitions=1, max_simulations=12)
    budget = resolve_worker_count(2, 4)
    report = run_screening_benchmark(
        _spec(), baseline, settings, tmp_path / "run", budget
    )
    trial = report.trials[0].model_copy(
        update={
            "speedup": 2.0,
            "quality": report.trials[0].quality.model_copy(
                update={"missed_feasible": ()}
            ),
        }
    )
    report = summarize_benchmark(_spec(), baseline, settings, budget, (trial,))
    assert report.decision == "INSUFFICIENT_EVIDENCE"


def test_no_go_savings_are_not_inferred_from_failed_runs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "scripts.perf_profile.screening_benchmark._evaluate_candidate_values",
        _fake_evaluator([]),
    )
    baseline = load_simulation_config(
        "config/simulation_config.yaml", env_overrides=False
    )
    settings = BenchmarkSettings(candidate_count=4, repetitions=1, max_simulations=12)
    budget = resolve_worker_count(2, 4)
    report = run_screening_benchmark(
        _spec(), baseline, settings, tmp_path / "run", budget
    )
    trial = report.trials[0].model_copy(
        update={
            "speedup": 0.1,
            "quality": report.trials[0].quality.model_copy(
                update={
                    "missed_feasible": (),
                    "evidence_complete": False,
                    "replay_matches": False,
                }
            ),
        }
    )
    result = summarize_benchmark(_spec(), baseline, settings, budget, (trial,))
    assert result.decision == "INSUFFICIENT_EVIDENCE"
    assert result.reasons == (
        "three complete repetitions with feasible evidence are required",
    )


def test_three_successful_trials_only_authorize_expanded_benchmark(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "scripts.perf_profile.screening_benchmark._evaluate_candidate_values",
        _fake_evaluator([]),
    )
    baseline = load_simulation_config(
        "config/simulation_config.yaml", env_overrides=False
    )
    settings = BenchmarkSettings(candidate_count=4, repetitions=3, max_simulations=36)
    budget = resolve_worker_count(2, 4)
    report = run_screening_benchmark(
        _spec(), baseline, settings, tmp_path / "run", budget
    )
    trials = tuple(
        trial.model_copy(
            update={
                "speedup": 2.0,
                "quality": trial.quality.model_copy(update={"missed_feasible": ()}),
            }
        )
        for trial in report.trials
    )
    result = summarize_benchmark(_spec(), baseline, settings, budget, trials)
    assert result.decision == "GO_FOR_EXPANDED_BENCHMARK"


def test_benchmark_script_writes_research_evidence_and_source_provenance(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from scripts.benchmark_optimizer_screening import main

    census = tmp_path / "census.parquet"
    with duckdb.connect() as connection:
        connection.sql("SELECT 1 AS synthetic_row").write_parquet(str(census))
    baseline = load_simulation_config(
        "config/simulation_config.yaml", env_overrides=False
    )
    payload = baseline.model_dump(mode="python")
    payload["setup"]["census_parquet_path"] = str(census)
    baseline = SimulationConfig.model_validate(payload)
    monkeypatch.setattr(
        "scripts.benchmark_optimizer_screening.load_baseline", lambda _: baseline
    )
    monkeypatch.setattr(
        "scripts.perf_profile.screening_benchmark._evaluate_candidate_values",
        _fake_evaluator([]),
    )
    output = tmp_path / "report"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "benchmark",
            "--spec",
            "tests/fixtures/optimizer_screening.yaml",
            "--output",
            str(output),
            "--candidates",
            "4",
            "--repetitions",
            "1",
            "--max-simulations",
            "12",
            "--parallel",
            "2",
        ],
    )
    main()
    evidence = json.loads((output / "benchmark.json").read_text())
    assert len(evidence["provenance"]["input_sha256"]) == 64
    assert evidence["provenance"]["source_sha256"]
    assert evidence["provenance"]["dependencies"]["duckdb"]
    assert "First-objective-only quality" in (output / "report.md").read_text()
    assert "ranked_feasible" not in evidence
