"""Deterministic census-enrollment inputs for isolated and scale tests."""

from __future__ import annotations

from typing import Iterator


def census_enrollment_rows(count: int) -> Iterator[tuple[str, str, bool]]:
    """Yield a deterministic census with alternating enrollment status."""
    for index in range(count):
        yield (f"employee-{index:06d}", "2020-01-01", index % 2 == 0)


def enrollment_history_rows(
    count: int, *, scenario_id: str = "default", plan_design_id: str = "default"
) -> Iterator[tuple[str, str, str, str, str, str, int, int, str]]:
    """Yield deterministic prior enrollment facts suitable for set-wise insertion."""
    for index in range(count):
        employee_id = f"employee-{index % 100_000:06d}"
        is_opt_out = index % 11 == 0
        yield (
            f"event-{index:07d}",
            scenario_id,
            plan_design_id,
            employee_id,
            "enrollment_change" if is_opt_out else "enrollment",
            "2025-06-01",
            2025,
            index,
            "Auto-enrollment opt-out" if is_opt_out else "Enrollment",
        )
