"""Strict aggregate-only entities for comparisons of independent scenarios."""

from __future__ import annotations

import re
from decimal import Decimal
from pathlib import PurePosixPath
from typing import Literal

from pydantic import Field, field_validator, model_validator

from planalign_ensemble.models import CANONICAL_METRICS, METRIC_REGISTRY

from .models import (
    FigureStatus,
    FigureUnit,
    MetricId,
    PackProvenance,
    PackWarning,
    StrictModel,
    reconciliation_quantum,
    validate_figure_status,
)

_WRITE_SQL = re.compile(
    r"\b(ATTACH|COPY|CREATE|INSERT|UPDATE|DELETE|DROP|ALTER|PRAGMA|EXPORT|IMPORT)\b",
    re.IGNORECASE,
)

CROSS_DRIVER_IDS: dict[str, tuple[str, ...]] = {
    "active_headcount": ("population_difference",),
    "total_compensation": ("population_effect", "average_value_effect"),
    "employer_match_cost": (
        "compensation_exposure_effect",
        "effective_payout_rate_effect",
    ),
    "total_employer_plan_cost": (
        "employer_match_difference",
        "employer_core_difference",
    ),
    "participation_rate": ("rate_difference",),
    "avg_deferral_rate": ("rate_difference",),
}
assert set(CROSS_DRIVER_IDS) == set(METRIC_REGISTRY)


class CrossCitation(StrictModel):
    result_store: str = Field(min_length=1)
    query_id: Literal["QA", "QB"]
    query: str = Field(min_length=1)
    result_column: str = Field(pattern=r"^[a-z][a-z0-9_]*$")

    @field_validator("result_store")
    @classmethod
    def _relative_store(cls, value: str) -> str:
        path = PurePosixPath(value)
        if path.is_absolute() or ".." in path.parts or path.name != "simulation.duckdb":
            raise ValueError("result_store must be a contained run-relative locator")
        return value

    @field_validator("query")
    @classmethod
    def _read_only_query(cls, value: str) -> str:
        if _WRITE_SQL.search(value) or ";" in value.rstrip().rstrip(";"):
            raise ValueError("citation query must be one read-only statement")
        if not value.lstrip().upper().startswith(("SELECT", "WITH")):
            raise ValueError("citation query must be a SELECT statement")
        return value.rstrip().rstrip(";")


class CrossScenarioFigure(StrictModel):
    value: str | None
    unit: FigureUnit
    status: FigureStatus
    reason: str | None = None
    citations: tuple[CrossCitation, ...]

    @field_validator("citations")
    @classmethod
    def _citation_count(
        cls, value: tuple[CrossCitation, ...]
    ) -> tuple[CrossCitation, ...]:
        if not 1 <= len(value) <= 2:
            raise ValueError("figures require one or two citations")
        return value

    @model_validator(mode="after")
    def _status_matches_value(self) -> "CrossScenarioFigure":
        validate_figure_status(self.status, self.value, self.reason)
        return self


class CrossScenarioPopulationEvidence(StrictModel):
    label: str = Field(min_length=1)
    count_a: CrossScenarioFigure
    count_b: CrossScenarioFigure


class CrossScenarioDriverContribution(StrictModel):
    id: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    label: str = Field(min_length=1)
    description: str = Field(min_length=1)
    contribution: CrossScenarioFigure
    share_of_change: CrossScenarioFigure
    population: CrossScenarioPopulationEvidence
    rate_a: CrossScenarioFigure | None = None
    rate_b: CrossScenarioFigure | None = None

    @model_validator(mode="after")
    def _rates_are_paired(self) -> "CrossScenarioDriverContribution":
        if (self.rate_a is None) != (self.rate_b is None):
            raise ValueError("driver endpoint rates must be provided together")
        return self


class CrossScenarioResidual(StrictModel):
    contribution: CrossScenarioFigure
    share_of_change: CrossScenarioFigure
    material: bool
    largest_contribution: bool


class ConfigDifference(StrictModel):
    path: str = Field(min_length=1)
    value_a: str | None
    value_b: str | None
    status: Literal["changed", "only_a", "only_b"]


class CrossScenarioMetricChange(StrictModel):
    metric: MetricId
    label: str
    year: int
    scenario_a_id: str = Field(min_length=1)
    scenario_b_id: str = Field(min_length=1)
    value_a: CrossScenarioFigure
    value_b: CrossScenarioFigure
    total_change: CrossScenarioFigure
    population_a: CrossScenarioFigure
    population_b: CrossScenarioFigure
    shares_suppressed_reason: str | None = None

    @model_validator(mode="after")
    def _distinct_scenarios(self) -> "CrossScenarioMetricChange":
        if self.scenario_a_id == self.scenario_b_id:
            raise ValueError("scenario endpoints must be distinct")
        return self


class CrossScenarioEvidencePack(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    provenance_a: PackProvenance
    provenance_b: PackProvenance
    config_differences: tuple[ConfigDifference, ...] = ()
    change: CrossScenarioMetricChange
    drivers: tuple[CrossScenarioDriverContribution, ...]
    residual: CrossScenarioResidual
    warnings: tuple[PackWarning, ...] = ()
    executive_summary: tuple[str, ...] = Field(min_length=1)
    population_note: str = Field(min_length=1)

    @model_validator(mode="after")
    def _reconcile_and_bind(self) -> "CrossScenarioEvidencePack":
        if self.change.metric not in CANONICAL_METRICS:
            raise ValueError("unsupported canonical metric")
        if not 1 <= len(self.drivers) <= 2:
            raise ValueError(
                "canonical cross-scenario metrics require one or two drivers"
            )
        expected = CROSS_DRIVER_IDS[self.change.metric]
        if tuple(driver.id for driver in self.drivers) != expected:
            raise ValueError("driver order does not match cross-scenario registry")
        stores = {
            "QA": self.provenance_a.result_store,
            "QB": self.provenance_b.result_store,
        }
        if any(
            c.result_store != stores[c.query_id]
            for f in self._figures()
            for c in f.citations
        ):
            raise ValueError("figure citation does not match its scenario result store")
        if (
            self.change.total_change.status
            == self.residual.contribution.status
            == "defined"
        ):
            explained = sum(
                (
                    Decimal(d.contribution.value or "0")
                    for d in self.drivers
                    if d.contribution.status == "defined"
                ),
                Decimal(self.residual.contribution.value or "0"),
            )
            total = Decimal(self.change.total_change.value or "0")
            if abs(explained - total) >= reconciliation_quantum(
                self.change.total_change.unit
            ):
                raise ValueError("driver contributions and residual must reconcile")
        return self

    def _figures(self) -> tuple[CrossScenarioFigure, ...]:
        figures = [
            self.change.value_a,
            self.change.value_b,
            self.change.total_change,
            self.change.population_a,
            self.change.population_b,
            self.residual.contribution,
            self.residual.share_of_change,
        ]
        for driver in self.drivers:
            figures.extend(
                (
                    driver.contribution,
                    driver.share_of_change,
                    driver.population.count_a,
                    driver.population.count_b,
                )
            )
            figures.extend(f for f in (driver.rate_a, driver.rate_b) if f is not None)
        return tuple(figures)


class CrossScenarioEvidencePackEnvelope(StrictModel):
    pack: CrossScenarioEvidencePack
    text_export: str
    filename: str = Field(pattern=r"^[A-Za-z0-9._-]+\.md$")


__all__ = [
    "CrossScenarioEvidencePackEnvelope",
    "CROSS_DRIVER_IDS",
    "ConfigDifference",
    "CrossCitation",
    "CrossScenarioDriverContribution",
    "CrossScenarioEvidencePack",
    "CrossScenarioFigure",
    "CrossScenarioMetricChange",
    "CrossScenarioPopulationEvidence",
    "CrossScenarioResidual",
]
