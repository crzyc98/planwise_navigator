"""Common diagnostics and targeted result assertions."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping


@dataclass(frozen=True)
class Violation:
    case: str
    boundary: str
    expected: str
    observed: str
    row: Mapping[str, Any]


@dataclass
class TargetedAssertionResult:
    case: str
    boundary: str
    expected: str
    observed: str = ""
    violations: list[Violation] = field(default_factory=list)
    sample_limit: int = 20

    def add(self, observed: str, row: Mapping[str, Any]) -> None:
        self.observed = observed
        if len(self.violations) < self.sample_limit:
            self.violations.append(
                Violation(self.case, self.boundary, self.expected, observed, dict(row))
            )

    @property
    def passed(self) -> bool:
        return not self.violations


def format_result(result: TargetedAssertionResult) -> str:
    samples = [dict(v.row) for v in result.violations[: result.sample_limit]]
    return (
        f"Case: {result.case}\nBoundary: {result.boundary}\n"
        f"Expected: {result.expected}\nObserved: {result.observed or 'none'}\n"
        f"Violation count (sampled): {len(result.violations)}\nSamples: {samples!r}"
    )


def assert_no_violations(result: TargetedAssertionResult) -> None:
    if not result.passed:
        raise AssertionError(format_result(result))


def assert_bounded_samples(rows: Iterable[Mapping[str, Any]], limit: int = 20) -> None:
    if limit < 1 or limit > 20:
        raise ValueError("diagnostic sample limit must be between 1 and 20")
    if len(list(rows)) > limit:
        raise AssertionError("diagnostic sample exceeded configured limit")
