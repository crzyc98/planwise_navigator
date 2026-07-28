"""Typed, deliberately small catalog for boundary-focused simulations."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

ROOT = Path(__file__).resolve().parents[2]
CASE_ROOT = ROOT / "tests/fixtures/edge_config"


@dataclass(frozen=True)
class EdgeConfigScenario:
    """Immutable description of one independent regression case."""

    name: str
    config_path: Path
    census_path: Path
    start_year: int
    end_year: int
    boundary: str
    expected_groups: Mapping[str, str]
    assertion_kind: str
    sample_limit: int = 20

    def __post_init__(self) -> None:
        if not self.name or not self.config_path or not self.census_path:
            raise ValueError("scenario name and fixture paths are required")
        if self.end_year < self.start_year:
            raise ValueError("end_year must not precede start_year")
        if not self.expected_groups or any(
            not key or not value for key, value in self.expected_groups.items()
        ):
            raise ValueError("expected_groups must contain named, non-empty groups")
        if not 1 <= self.sample_limit <= 20:
            raise ValueError("sample_limit must be between 1 and 20")


@dataclass(frozen=True)
class ScenarioRun:
    """Completed or failed disposable simulation attempt."""

    scenario: EdgeConfigScenario
    database: Path
    config_identity: str
    error: BaseException | None = None

    @property
    def completed(self) -> bool:
        return self.error is None and self.database.exists()


def _scenario(
    name: str, boundary: str, groups: Mapping[str, str], kind: str
) -> EdgeConfigScenario:
    return EdgeConfigScenario(
        name=name,
        config_path=CASE_ROOT / f"{name}.yaml",
        census_path=CASE_ROOT / f"{name}.csv",
        start_year=2025,
        end_year=2026,
        boundary=boundary,
        expected_groups=groups,
        assertion_kind=kind,
    )


CATALOG = (
    _scenario(
        "broad_auto_enrollment_cutoff",
        "hire date cutoff",
        {"before_cutoff": "outside", "after_cutoff": "inside"},
        "cutoff_enrollment",
    ),
    _scenario(
        "new_hire_eligibility_suppression",
        "new-hire eligibility suppression",
        {"suppressed_new_hire": "suppressed", "eligible_control": "control"},
        "eligibility_suppression",
    ),
    _scenario(
        "tenure_graded_employer_match",
        "completed-service match bands",
        {"short_service": "short", "long_service": "long"},
        "tenure_match",
    ),
    _scenario(
        "auto_escalation_low_cap",
        "annual escalation cap",
        {"below_cap": "below", "at_cap": "equal", "above_cap": "above"},
        "escalation_cap",
    ),
    _scenario(
        "zero_target_growth_rate",
        "zero workforce growth",
        {"retained_workforce": "retained"},
        "zero_growth",
    ),
    _scenario(
        "negative_target_growth_rate",
        "negative workforce growth",
        {"declining_workforce": "declining"},
        "negative_growth",
    ),
    _scenario(
        "custom_new_hire_inputs",
        "custom new-hire age and compensation inputs",
        {"seed_workforce": "seed"},
        "custom_hire_inputs",
    ),
)


def validate_catalog(catalog: tuple[EdgeConfigScenario, ...] = CATALOG) -> None:
    """Keep the matrix small enough for its twenty-minute CI budget.

    Six cases measured 5m17s, so a seventh leaves ample headroom; raise the
    ceiling again only against a fresh measurement, not on principle.
    """
    names = [case.name for case in catalog]
    if not 4 <= len(catalog) <= 7:
        raise ValueError(
            f"edge-config matrix requires four to seven cases, got {len(catalog)}"
        )
    if len(set(names)) != len(names):
        raise ValueError("edge-config matrix case names must be unique")


validate_catalog()
