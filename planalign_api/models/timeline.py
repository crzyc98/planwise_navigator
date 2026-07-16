"""Read-only employee timeline API models."""

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field


class TimelineEvent(BaseModel):
    event_id: str
    source: Literal["yearly", "employer_match"]
    event_type: str
    simulation_year: int
    effective_date: date
    event_details: str | None = None
    compensation_amount: float | None = None
    previous_compensation: float | None = None
    deferral_rate: float | None = None
    prev_deferral_rate: float | None = None
    level_id: int | None = None


class YearState(BaseModel):
    simulation_year: int
    employment_status: str | None = None
    detailed_status_code: str | None = None
    current_compensation: float | None = None
    prorated_annual_compensation: float | None = None
    level_id: int | None = None
    current_age: int | None = None
    current_tenure: float | None = None
    eligibility_status: str | None = None
    is_enrolled: bool | None = None
    enrollment_date: date | None = None
    current_deferral_rate: float | None = None
    participation_status: str | None = None
    total_deferral_escalations: int | None = None
    ytd_contributions: float | None = None
    pre_tax_contributions: float | None = None
    roth_contributions: float | None = None
    employer_match_amount: float | None = None
    employer_core_amount: float | None = None
    total_employer_contributions: float | None = None
    irs_limit_reached: bool | None = None


class TimelineYear(BaseModel):
    simulation_year: int
    events: list[TimelineEvent] = Field(default_factory=list)
    state: YearState | None = None


class EmployeeIdentity(BaseModel):
    employee_id: str
    employee_ssn: str | None = None
    employee_birth_date: date | None = None
    employee_hire_date: date | None = None


class EmployeeTimelineResponse(BaseModel):
    workspace_id: str
    scenario_id: str
    employee_id: str
    employee: EmployeeIdentity | None
    available_years: list[int]
    years: list[TimelineYear]
    start_year: int
    years_requested: int


class EmployeeSearchResult(BaseModel):
    employee_id: str
    employment_status: str | None = None
    level_id: int | None = None
    current_compensation: float | None = None
    simulation_year: int


class EmployeeSearchResponse(BaseModel):
    results: list[EmployeeSearchResult]
    total: int
    page: int
    page_size: int
