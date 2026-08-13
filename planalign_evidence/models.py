"""Strict aggregate-only entities for cited evidence packs."""

from __future__ import annotations

import re
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import PurePosixPath
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from planalign_ensemble.models import CANONICAL_METRICS, METRIC_REGISTRY

MetricId = Literal[
    "active_headcount",
    "total_compensation",
    "employer_match_cost",
    "total_employer_plan_cost",
    "participation_rate",
    "avg_deferral_rate",
]
FigureStatus = Literal["defined", "undefined", "suppressed"]
FigureUnit = Literal["count", "currency", "rate", "percent_of_change"]
WarningCode = Literal[
    "run_in_progress",
    "legacy_result",
    "current_config_mismatch",
    "current_seed_mismatch",
    "mixed_generation",
    "incomplete_build",
    "incomplete_provenance",
    "integrity_mismatch",
    "material_residual",
    "residual_dominates",
    "shares_suppressed",
]

# Reconciliation holds at the precision a pack actually reports, not at the
# precision of the float64 aggregates it is derived from. Driver contributions
# arrive as SQL doubles, so a currency decomposition summing to millions carries
# ~1e-10 of representation noise that no correct implementation can remove.
# Requiring exact equality here would make the invariant unsatisfiable on real
# results while still passing on small synthetic fixtures.
RECONCILIATION_QUANTUM: dict[str, Decimal] = {
    "count": Decimal("1"),
    "currency": Decimal("0.01"),
    "rate": Decimal("0.000001"),
}


def reconciliation_quantum(unit: str) -> Decimal:
    """Return the smallest difference that is meaningful for `unit`."""
    return RECONCILIATION_QUANTUM.get(unit, Decimal("0.000001"))


_DECIMAL_PATTERN = re.compile(r"^-?(0|[1-9][0-9]*)(\.[0-9]+)?$")
_WRITE_SQL = re.compile(
    r"\b(ATTACH|COPY|CREATE|INSERT|UPDATE|DELETE|DROP|ALTER|PRAGMA|EXPORT|IMPORT)\b",
    re.IGNORECASE,
)


class StrictModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class Citation(StrictModel):
    result_store: str = Field(min_length=1)
    query_id: Literal["Q1"] = "Q1"
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


class EvidenceFigure(StrictModel):
    value: str | None
    unit: FigureUnit
    status: FigureStatus
    reason: str | None = None
    citation: Citation

    @model_validator(mode="after")
    def _status_matches_value(self) -> "EvidenceFigure":
        if self.status == "defined":
            if self.value is None or self.reason is not None:
                raise ValueError("defined figures require a value and no reason")
            if not _DECIMAL_PATTERN.fullmatch(self.value):
                raise ValueError("value must be a canonical finite decimal string")
            try:
                if not Decimal(self.value).is_finite():
                    raise ValueError("value must be finite")
            except InvalidOperation as exc:
                raise ValueError("value must be a decimal") from exc
        elif self.value is not None or not self.reason:
            raise ValueError("undefined/suppressed figures require only a reason")
        return self


class PopulationEvidence(StrictModel):
    label: str = Field(min_length=1)
    count: EvidenceFigure
    base_count: EvidenceFigure | None = None
    target_count: EvidenceFigure | None = None
    changed_count: EvidenceFigure | None = None


class DriverContribution(StrictModel):
    id: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    label: str = Field(min_length=1)
    description: str = Field(min_length=1)
    contribution: EvidenceFigure
    share_of_change: EvidenceFigure
    population: PopulationEvidence


class Residual(StrictModel):
    contribution: EvidenceFigure
    share_of_change: EvidenceFigure
    material: bool
    largest_contribution: bool


class MetricChange(StrictModel):
    metric: MetricId
    label: str
    base_year: int
    target_year: int
    base_value: EvidenceFigure
    target_value: EvidenceFigure
    total_change: EvidenceFigure
    shares_suppressed_reason: str | None = None

    @model_validator(mode="after")
    def _year_order(self) -> "MetricChange":
        if self.base_year >= self.target_year:
            raise ValueError("base_year must be earlier than target_year")
        return self


class PackWarning(StrictModel):
    code: WarningCode
    severity: Literal["info", "caution", "critical"]
    message: str = Field(min_length=1)


class PackProvenance(StrictModel):
    workspace_id: str | None = None
    scenario_id: str = Field(min_length=1)
    scenario_name: str | None = None
    run_id: str = Field(min_length=1)
    run_timestamp: datetime | None = None
    random_seed: int | None = None
    config_fingerprint: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    result_store: str
    verification_disposition: Literal["fully_verified", "incomplete", "unverifiable"]

    @field_validator("result_store")
    @classmethod
    def _relative_store(cls, value: str) -> str:
        path = PurePosixPath(value)
        if path.is_absolute() or ".." in path.parts or path.name != "simulation.duckdb":
            raise ValueError("result_store must be a contained run-relative locator")
        return value


class EvidencePack(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    provenance: PackProvenance
    change: MetricChange
    drivers: tuple[DriverContribution, ...]
    residual: Residual
    warnings: tuple[PackWarning, ...] = ()
    population_note: str = Field(min_length=1)

    @model_validator(mode="after")
    def _reconcile_and_bind(self) -> "EvidencePack":
        if self.change.metric not in CANONICAL_METRICS:
            raise ValueError("unsupported canonical metric")
        if not 3 <= len(self.drivers) <= 4:
            raise ValueError("canonical metrics require three or four drivers")
        stores = {figure.citation.result_store for figure in self._figures()}
        queries = {figure.citation.query for figure in self._figures()}
        if stores != {self.provenance.result_store} or len(queries) != 1:
            raise ValueError("all figures must bind one query and result store")
        if all(
            item.status == "defined"
            for item in (self.change.total_change, self.residual.contribution)
        ):
            contribution = sum(
                (
                    Decimal(driver.contribution.value or "0")
                    for driver in self.drivers
                    if driver.contribution.status == "defined"
                ),
                Decimal(0),
            )
            contribution += Decimal(self.residual.contribution.value or "0")
            total = Decimal(self.change.total_change.value or "0")
            tolerance = reconciliation_quantum(self.change.total_change.unit)
            if abs(contribution - total) >= tolerance:
                raise ValueError("driver contributions and residual must reconcile")
        expected = tuple(METRIC_REGISTRY[self.change.metric].driver_ids)
        if expected and tuple(driver.id for driver in self.drivers) != expected:
            raise ValueError("driver order does not match canonical registry")
        return self

    def _figures(self) -> tuple[EvidenceFigure, ...]:
        figures = [
            self.change.base_value,
            self.change.target_value,
            self.change.total_change,
            self.residual.contribution,
            self.residual.share_of_change,
        ]
        for driver in self.drivers:
            figures.extend(
                [driver.contribution, driver.share_of_change, driver.population.count]
            )
            figures.extend(
                figure
                for figure in (
                    driver.population.base_count,
                    driver.population.target_count,
                    driver.population.changed_count,
                )
                if figure is not None
            )
        return tuple(figures)


class EvidencePackEnvelope(StrictModel):
    pack: EvidencePack
    text_export: str
    filename: str = Field(pattern=r"^[A-Za-z0-9._-]+\.md$")


__all__ = [
    "Citation",
    "DriverContribution",
    "EvidenceFigure",
    "EvidencePack",
    "EvidencePackEnvelope",
    "MetricChange",
    "PackProvenance",
    "PackWarning",
    "PopulationEvidence",
    "Residual",
]
