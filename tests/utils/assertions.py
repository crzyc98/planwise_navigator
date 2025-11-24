"""Custom test assertions for Fidelity PlanAlign Engine."""

import pytest
from typing import Dict, Any


def assert_parameter_validity(schema, parameters: Dict[str, Any]) -> Dict[str, Any]:
    """Assert that parameters are valid according to schema."""
    validation_result = schema.validate_parameter_set(parameters)

    if not validation_result["is_valid"]:
        errors = "\n".join(validation_result["errors"])
        pytest.fail(f"Parameter validation failed:\n{errors}")

    return validation_result


def assert_optimization_convergence(result) -> None:
    """Assert that optimization converged successfully."""
    if not result.converged:
        pytest.fail(f"Optimization failed to converge: {result.algorithm_used}")

    if result.objective_value == float("inf"):
        pytest.fail("Optimization returned infinite objective value")

    if not result.optimal_parameters:
        pytest.fail("Optimization returned no optimal parameters")


def assert_performance_acceptable(metrics: Dict[str, float], benchmarks: Dict[str, float]) -> None:
    """Assert that performance metrics are within acceptable bounds."""
    if metrics["execution_time"] > benchmarks.get("max_time", float("inf")):
        pytest.fail(
            f"Execution time {metrics['execution_time']:.2f}s exceeds "
            f"benchmark {benchmarks['max_time']}s"
        )

    if metrics.get("memory_delta", 0) > benchmarks.get("max_memory", float("inf")):
        pytest.fail(
            f"Memory usage {metrics['memory_delta']:.1f}MB exceeds "
            f"benchmark {benchmarks['max_memory']}MB"
        )


def assert_event_valid(event) -> None:
    """Assert that a simulation event is valid."""
    assert hasattr(event, "event_id"), "Event missing event_id"
    assert hasattr(event, "event_type"), "Event missing event_type"
    assert hasattr(event, "employee_id"), "Event missing employee_id"
    assert hasattr(event, "effective_date"), "Event missing effective_date"
    assert hasattr(event, "scenario_id"), "Event missing scenario_id"
    assert hasattr(event, "plan_design_id"), "Event missing plan_design_id"
