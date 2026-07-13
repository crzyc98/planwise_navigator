"""Strict, PII-safe models for archived run provenance evidence."""

from __future__ import annotations

import math
import re
from datetime import datetime, timezone
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_SHA1 = re.compile(r"^[0-9a-f]{40}$")
_SAFE_NAME = re.compile(r"^[A-Za-z0-9_.@+-]+(?:/[A-Za-z0-9_.@+-]+)*$")
_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)


def _safe_text(value: str) -> str:
    if _CONTROL.search(value):
        raise ValueError("control characters are not permitted")
    return value


def _finite_nonnegative(value: float | None) -> float | None:
    if value is not None and not math.isfinite(value):
        raise ValueError("value must be finite")
    return value


def _logical_name(value: str) -> str:
    if not _SAFE_NAME.fullmatch(value) or ".." in value.split("/"):
        raise ValueError("logical name must be a safe relative name")
    return value


def _sha256(value: str) -> str:
    if not _SHA256.fullmatch(value):
        raise ValueError("invalid SHA-256 fingerprint")
    return value


class EvidenceFinding(StrictModel):
    field_path: str
    code: Literal[
        "unavailable",
        "malformed",
        "unbound",
        "identity_conflict",
        "integrity_mismatch",
        "unsafe_metadata",
        "incomplete_capture",
    ]
    reason: str = Field(max_length=300)
    required: bool = True

    _field_safe = field_validator("field_path", "reason")(_safe_text)


class StageCompletion(StrictModel):
    simulation_year: int | None = None
    stage: str
    started_at: datetime | None = None
    completed_at: datetime | None = None
    duration_seconds: float | None = Field(default=None, ge=0)
    outcome: str = "completed"

    @field_validator("duration_seconds")
    @classmethod
    def finite_duration(cls, value: float | None) -> float | None:
        return _finite_nonnegative(value)


class RunIdentityEvidence(StrictModel):
    run_id: UUID
    workspace_id: str | None = None
    scenario_id: str | None = None
    plan_design_id: str | None = None
    status: str
    intended_start_year: int | None = None
    intended_end_year: int | None = None
    completed_years: list[int] = Field(default_factory=list)

    @model_validator(mode="after")
    def valid_years(self) -> "RunIdentityEvidence":
        object.__setattr__(self, "completed_years", sorted(set(self.completed_years)))
        if (
            self.intended_start_year is not None
            and self.intended_end_year is not None
            and self.intended_start_year > self.intended_end_year
        ):
            raise ValueError("start year must not exceed end year")
        return self


class ExecutionTimingEvidence(StrictModel):
    started_at: datetime | None = None
    completed_at: datetime | None = None
    duration_seconds: float | None = Field(default=None, ge=0)
    terminal_stage: str | None = None
    stage_completions: list[StageCompletion] = Field(default_factory=list)

    _finite_duration = field_validator("duration_seconds")(_finite_nonnegative)


class SoftwareEvidence(StrictModel):
    planalign_version: str | None = None
    git_commit_sha: str | None = None
    working_tree_state: Literal["clean", "dirty", "unavailable"] = "unavailable"
    working_tree_fingerprint: str | None = None

    @field_validator("git_commit_sha")
    @classmethod
    def valid_sha(cls, value: str | None) -> str | None:
        if value is not None and not _SHA1.fullmatch(value):
            raise ValueError("invalid Git commit SHA")
        return value

    @field_validator("working_tree_fingerprint")
    @classmethod
    def valid_tree_hash(cls, value: str | None) -> str | None:
        if value is not None and not _SHA256.fullmatch(value):
            raise ValueError("invalid working-tree fingerprint")
        return value

    @model_validator(mode="after")
    def fingerprint_matches_state(self) -> "SoftwareEvidence":
        if self.working_tree_state == "dirty" and self.working_tree_fingerprint is None:
            raise ValueError("dirty working tree requires a fingerprint")
        if (
            self.working_tree_state == "clean"
            and self.working_tree_fingerprint is not None
        ):
            raise ValueError("clean working tree must not have a dirty fingerprint")
        return self


class ConfigurationEvidence(StrictModel):
    effective: dict[str, Any] | None = None
    fingerprint: str | None = None
    fingerprint_method: str | None = None
    redactions: list[str] = Field(default_factory=list)

    @field_validator("fingerprint")
    @classmethod
    def valid_hash(cls, value: str | None) -> str | None:
        if value is not None and not _SHA256.fullmatch(value):
            raise ValueError("invalid SHA-256 fingerprint")
        return value


class InputFingerprint(StrictModel):
    logical_name: str
    sha256: str
    size_bytes: int | None = Field(default=None, ge=0)
    record_count: int | None = Field(default=None, ge=0)
    format: str | None = None

    @field_validator("logical_name")
    @classmethod
    def safe_name(cls, value: str) -> str:
        return _logical_name(value)

    @field_validator("sha256")
    @classmethod
    def valid_hash(cls, value: str) -> str:
        return _sha256(value)


class SeedFingerprint(StrictModel):
    logical_name: str
    sha256: str
    size_bytes: int = Field(ge=0)

    _safe_name = field_validator("logical_name")(_logical_name)
    _valid_hash = field_validator("sha256")(_sha256)


class ArtifactFingerprint(SeedFingerprint):
    pass


class AnnualEventCount(StrictModel):
    simulation_year: int
    event_type: str
    count: int = Field(ge=0)


class AnnualWorkforceReconciliation(StrictModel):
    simulation_year: int
    opening_workforce: int | None = Field(default=None, ge=0)
    hires: int | None = Field(default=None, ge=0)
    terminations: int | None = Field(default=None, ge=0)
    expected_closing_workforce: int | None = None
    actual_closing_workforce: int | None = Field(default=None, ge=0)
    variance: int | None = None
    opening_source: Literal[
        "baseline", "prior_year_snapshot", "unavailable"
    ] | None = None


class CapturedValidationResult(StrictModel):
    simulation_year: int
    check_name: str
    severity: str
    passed: bool
    affected_record_count: int | None = Field(default=None, ge=0)


class RunProvenanceManifest(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    run_id: UUID
    capture_state: Literal["capturing", "completed", "failed", "cancelled"]
    run_identity: RunIdentityEvidence
    execution_timing: ExecutionTimingEvidence
    software: SoftwareEvidence
    configuration: ConfigurationEvidence
    random_seed: int | None = None
    census_input: InputFingerprint | None = None
    seed_files: list[SeedFingerprint] = Field(default_factory=list)
    event_counts: list[AnnualEventCount] = Field(default_factory=list)
    workforce_reconciliations: list[AnnualWorkforceReconciliation] = Field(
        default_factory=list
    )
    validation_results: list[CapturedValidationResult] = Field(default_factory=list)
    validation_disposition: Literal[
        "passed", "passed_with_warnings", "failed", "incomplete", "unavailable"
    ] = "unavailable"
    completed_stages: list[StageCompletion] = Field(default_factory=list)
    capture_findings: list[EvidenceFinding] = Field(default_factory=list)
    archive_artifacts: list[ArtifactFingerprint] = Field(default_factory=list)
    started_at: datetime
    finalized_at: datetime | None = None

    @model_validator(mode="after")
    def normalize_and_bind(self) -> "RunProvenanceManifest":
        if self.run_id != self.run_identity.run_id:
            raise ValueError("manifest and run identity IDs differ")
        object.__setattr__(
            self,
            "seed_files",
            sorted(self.seed_files, key=lambda item: item.logical_name),
        )
        object.__setattr__(
            self,
            "event_counts",
            sorted(
                self.event_counts,
                key=lambda item: (item.simulation_year, item.event_type),
            ),
        )
        object.__setattr__(
            self,
            "workforce_reconciliations",
            sorted(
                self.workforce_reconciliations, key=lambda item: item.simulation_year
            ),
        )
        object.__setattr__(
            self,
            "validation_results",
            sorted(
                self.validation_results,
                key=lambda item: (
                    item.simulation_year,
                    item.check_name,
                    item.severity,
                    item.passed,
                ),
            ),
        )
        object.__setattr__(
            self,
            "capture_findings",
            sorted(
                self.capture_findings, key=lambda item: (item.field_path, item.code)
            ),
        )
        if self.capture_state != "capturing" and self.finalized_at is None:
            raise ValueError("terminal manifest requires finalized_at")
        duplicate_identity = any(
            (
                len(self.seed_files)
                != len({item.logical_name for item in self.seed_files}),
                len(self.event_counts)
                != len(
                    {
                        (item.simulation_year, item.event_type)
                        for item in self.event_counts
                    }
                ),
                len(self.workforce_reconciliations)
                != len(
                    {item.simulation_year for item in self.workforce_reconciliations}
                ),
                len(self.validation_results)
                != len(
                    {
                        (item.simulation_year, item.check_name, item.severity)
                        for item in self.validation_results
                    }
                ),
                len(self.completed_stages)
                != len(
                    {
                        (item.simulation_year, item.stage)
                        for item in self.completed_stages
                    }
                ),
            )
        )
        if duplicate_identity:
            raise ValueError("provenance evidence lists must contain unique identities")
        return self


class ReportEvidence(StrictModel):
    run: RunIdentityEvidence
    timing: ExecutionTimingEvidence
    software: SoftwareEvidence
    configuration: ConfigurationEvidence
    random_seed: int | None = None
    census_input: InputFingerprint | None = None
    seed_files: list[SeedFingerprint] = Field(default_factory=list)
    event_counts: list[AnnualEventCount] = Field(default_factory=list)
    workforce_reconciliations: list[AnnualWorkforceReconciliation] = Field(
        default_factory=list
    )
    validation_results: list[CapturedValidationResult] = Field(default_factory=list)
    validation_disposition: str


class ReportDigest(StrictModel):
    algorithm: Literal["SHA-256"] = "SHA-256"
    canonicalization: Literal[
        "planalign-provenance-json-v1"
    ] = "planalign-provenance-json-v1"
    value: str

    _valid_hash = field_validator("value")(_sha256)


class ReviewSignOff(StrictModel):
    report_digest: str
    reviewer_name: str | None = None
    decision: str | None = None
    timestamp: datetime | None = None
    comments: str | None = None

    _valid_hash = field_validator("report_digest")(_sha256)


class ProvenanceReport(StrictModel):
    report_schema_version: Literal["1.0"] = "1.0"
    evidence: ReportEvidence
    missing_evidence: list[EvidenceFinding] = Field(default_factory=list)
    verification_disposition: Literal["fully_verified", "incomplete", "unverifiable"]
    digest: ReportDigest
    sign_off: ReviewSignOff


class ProvenanceReportEnvelope(StrictModel):
    report: ProvenanceReport
    audit_sheet: str


def utc_now() -> datetime:
    return datetime.now(timezone.utc)
