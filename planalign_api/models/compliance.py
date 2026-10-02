"""Read-only compliance reporting contracts."""

from typing import Literal

from pydantic import Field

from .base import APIModel
from ..services.compliance_metrics import LimitStatus

MetricName = Literal["402g", "415c", "401a17", "catch_up", "super_catch_up"]


class LimitMeasure(APIModel):
    amount: float | None = None
    limit: float | None = None
    headroom: float | None = None
    excess: float | None = None
    utilization: float | None = None
    status: LimitStatus = "unavailable"


class ComplianceEmployee(APIModel):
    employee_id: str
    plan_design_id: str | None = None
    age: int | None = None
    deferrals: LimitMeasure
    annual_additions: LimitMeasure
    compensation: LimitMeasure
    catch_up_group: Literal["ordinary", "super"] | None = None
    catch_up_capacity: float | None = None
    modeled_catch_up_used: float | None = None
    remaining_catch_up_capacity: float | None = None


class LimitRollup(APIModel):
    below_threshold: int = 0
    near_limit: int = 0
    at_limit: int = 0
    over_limit: int = 0
    unavailable: int = 0
    excess: float = 0.0


class CatchUpRollup(APIModel):
    eligible_count: int = 0
    available_count: int = 0
    utilizing_count: int = 0
    capacity: float = 0.0
    used: float = 0.0
    remaining_capacity: float = 0.0
    utilization: float | None = None


class ComplianceLimits(APIModel):
    year: int
    base_limit: float
    catch_up_limit: float
    super_catch_up_limit: float
    compensation_limit: float
    annual_additions_limit: float
    catch_up_age_threshold: int
    super_catch_up_age_min: int
    super_catch_up_age_max: int
    is_estimated: bool | None = None
    differs_from_current_seed: bool = False


class ComplianceNDTResult(APIModel):
    test_type: Literal["adp", "acp", "415"]
    result: str
    message: str | None = None
    margin: float | None = None


class ComplianceSummary(APIModel):
    scenario_id: str
    scenario_name: str
    year: int
    run_id: str | None = None
    evidence: str
    warning_threshold: float
    limits: ComplianceLimits | None = None
    participant_count: int = 0
    deferrals: LimitRollup
    annual_additions: LimitRollup
    compensation: LimitRollup
    catch_up: CatchUpRollup
    super_catch_up: CatchUpRollup
    ndt: list[ComplianceNDTResult] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class ComplianceResponse(APIModel):
    test_type: Literal["compliance"] = "compliance"
    year: int
    results: list[ComplianceSummary]


class ComplianceEmployeePage(APIModel):
    evidence: str
    total: int
    offset: int
    limit: int
    employees: list[ComplianceEmployee]
