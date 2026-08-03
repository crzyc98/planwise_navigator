"""Fast rendering tests for ensemble CLI disclosure and bands."""

from __future__ import annotations

from io import StringIO

import pytest
from rich.console import Console

from planalign_ensemble.models import (
    AttributionShare,
    EnsembleSpec,
    MetricDistribution,
    RiskStatement,
    Subsystem,
)
from planalign_ensemble.planner import plan_ensemble
from planalign_ensemble.report import (
    EnsembleProgressReporter,
    print_distribution_tables,
    print_ensemble_plan,
    print_attribution_tables,
    print_risk_statements,
)
from planalign_orchestrator.run_pool import EventKind, PoolEvent, WorkerBudget


def _console() -> tuple[Console, StringIO]:
    """Create a non-terminal Rich console whose output is easy to assert."""
    stream = StringIO()
    return Console(file=stream, force_terminal=False, width=120), stream


def _distribution(*, sufficient: bool) -> MetricDistribution:
    """Return a complete or intentionally withheld distribution fixture."""
    shared = {
        "ensemble_id": "ens",
        "scenario_id": "baseline",
        "metric": "total_employer_plan_cost",
        "simulation_year": 2029,
        "n_seeds": 10 if sufficient else 4,
        "n_seeds_requested": 10,
        "is_sufficient": sufficient,
    }
    if not sufficient:
        return MetricDistribution(**shared)
    return MetricDistribution(
        **shared,
        p10=1_900_000,
        p25=1_950_000,
        p50=2_000_000,
        p75=2_050_000,
        p90=2_100_000,
        mean=2_000_000,
        stddev=50_000,
    )


@pytest.mark.fast
def test_distribution_tables_always_show_sample_size_and_withhold_thin_bands() -> None:
    """Rendered NULL statistics cannot be mistaken for a zero-width band."""
    console, stream = _console()

    print_distribution_tables(
        console,
        [_distribution(sufficient=True), _distribution(sufficient=False)],
        min_seeds=10,
    )

    output = stream.getvalue()
    assert "n=10 seeds" in output
    assert "INSUFFICIENT SAMPLE (n=4, minimum 10)" in output
    assert "Percentiles withheld" in output


@pytest.mark.fast
def test_zero_variance_metric_renders_as_deterministic_not_as_a_band() -> None:
    """A solved quantity must not present five identical percentiles as spread."""
    console, stream = _console()
    solved = MetricDistribution(
        ensemble_id="ens",
        scenario_id="baseline",
        metric="active_headcount",
        simulation_year=2029,
        n_seeds=25,
        n_seeds_requested=25,
        is_sufficient=True,
        p10=7841,
        p25=7841,
        p50=7841,
        p75=7841,
        p90=7841,
        mean=7841,
        stddev=0.0,
    )

    print_distribution_tables(console, [solved], min_seeds=10)

    output = stream.getvalue()
    unwrapped = " ".join(stream.getvalue().split())
    assert "deterministic, identical across all 25 seeds" in unwrapped
    assert "Not stochastic under this configuration" in unwrapped
    assert "P90" not in output


@pytest.mark.fast
def test_nonzero_variance_metric_still_renders_percentile_bands() -> None:
    """Determinism detection must not suppress a genuine band."""
    console, stream = _console()

    print_distribution_tables(console, [_distribution(sufficient=True)], min_seeds=10)

    output = stream.getvalue()
    assert "linear percentiles" in output
    assert "P90" in output


@pytest.mark.fast
def test_plan_disclosure_and_pool_progress_are_visible_before_execution(
    tmp_path,
) -> None:
    """The operator sees seed cost and lifecycle events without worker output."""
    console, stream = _console()
    plan = plan_ensemble(
        EnsembleSpec(
            scenario_id="baseline",
            seed_count=2,
            start_year=2025,
            end_year=2026,
            attribution=True,
            attribution_seed_count=2,
        ),
        output_root=tmp_path,
    )
    budget = WorkerBudget(1, "one worker per scenario", 4, 2, 4096)

    print_ensemble_plan(console, plan, budget)
    reporter = EnsembleProgressReporter(console, total_seeds=2)
    reporter(PoolEvent(EventKind.JOB_STARTED, "seed_42"))
    reporter(PoolEvent(EventKind.JOB_COMPLETED, "seed_42", duration_seconds=1.2))

    output = stream.getvalue()
    assert "Seeds:" in output
    assert "Worker budget:" in output
    assert "Runs:" in output
    assert "headline +" in output
    assert "attribution" in output
    assert "Output:" in output
    assert "Ensemble progress: 1/2" in output


@pytest.mark.fast
def test_risk_section_reports_evaluable_and_unavailable_thresholds() -> None:
    """Threshold output shows both a precise probability and an honest absence."""
    console, stream = _console()

    print_risk_statements(
        console,
        [
            RiskStatement(
                metric="total_employer_plan_cost",
                threshold_value=2_400_000,
                simulation_year=2029,
                exceedance_probability=0.12,
                n_seeds=25,
                is_evaluable=True,
            ),
            RiskStatement(
                metric="missing_metric",
                threshold_value=1,
                is_evaluable=False,
                reason="metric 'missing_metric' is unavailable from these runs",
            ),
        ],
    )

    output = stream.getvalue()
    assert "Risk — thresholds" in output
    assert "12.0% (3/25)" in output
    assert "missing_metric" in output
    assert "not evaluable" in output


@pytest.mark.fast
def test_empty_risk_section_is_explicit() -> None:
    """No threshold configuration is a valid ensemble request, not silence."""
    console, stream = _console()

    print_risk_statements(console, [])

    assert "Risk — thresholds" in stream.getvalue()
    assert "No thresholds configured" in stream.getvalue()


@pytest.mark.fast
def test_attribution_report_is_unranked_caveated_and_names_structural_absences() -> (
    None
):
    """Every displayed attribution finding carries method, sample, and reuse context."""
    console, stream = _console()

    print_attribution_tables(
        console,
        [
            AttributionShare(
                metric="total_employer_plan_cost",
                simulation_year=2029,
                subsystem=Subsystem.TERMINATION,
                variance_share=0.61,
                baseline_variance=10.0,
                frozen_variance=3.9,
                n_seeds=10,
                baselines_reused=10,
                stochastic_status="stochastic",
            ),
            AttributionShare(
                metric="total_employer_plan_cost",
                simulation_year=2029,
                subsystem=Subsystem.HIRING,
                variance_share=0.22,
                baseline_variance=10.0,
                frozen_variance=7.8,
                n_seeds=10,
                baselines_reused=10,
                stochastic_status="stochastic",
            ),
            AttributionShare(
                metric="total_employer_plan_cost",
                simulation_year=2029,
                subsystem=Subsystem.ENROLLMENT,
                n_seeds=10,
                baselines_reused=10,
                stochastic_status="not_stochastic",
            ),
        ],
    )

    output = stream.getvalue()
    unwrapped = " ".join(output.split())
    assert "[EXPERIMENTAL] Conditional variance change" in unwrapped
    assert "termination" in output
    assert "hiring" in output
    assert "not stochastic" in output
    assert "n=10" in output
    assert "10 reused" in output
    # Single-anchor conditional variance is not a decomposition: never ranked,
    # never described as attribution, and always caveated.
    assert "1. termination" not in output
    assert "2. hiring" not in output
    assert "What drives the spread" not in output
    assert "not causal attribution" in unwrapped
    assert "Diagnostic use only" in unwrapped
