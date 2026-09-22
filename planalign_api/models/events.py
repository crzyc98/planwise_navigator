"""Read-only event audit explorer API models."""

from datetime import datetime

from pydantic import BaseModel


class EventRecord(BaseModel):
    event_id: str
    event_type: str
    event_category: str | None = None
    event_sequence: int | None = None
    effective_date: datetime
    simulation_year: int
    employee_id: str
    employee_ssn: str | None = None
    employee_age: int | None = None
    employee_tenure: float | None = None
    level_id: int | None = None
    age_band: str | None = None
    tenure_band: str | None = None
    scenario_id: str
    plan_design_id: str
    event_details: str | None = None
    compensation_amount: float | None = None
    previous_compensation: float | None = None
    employee_deferral_rate: float | None = None
    prev_employee_deferral_rate: float | None = None
    event_probability: float | None = None
    parameter_scenario_id: str | None = None
    parameter_source: str | None = None
    data_quality_flag: str | None = None
    created_at: datetime | None = None


class EventListResponse(BaseModel):
    workspace_id: str
    scenario_id: str
    run_id: str | None = None
    database_source: str | None = None
    events: list[EventRecord]
    total: int
    page: int
    page_size: int
