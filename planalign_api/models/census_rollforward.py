"""Census roll-forward: status and jobs (#1078)."""

from datetime import datetime
from typing import Literal, Optional

from pydantic import Field

from .base import APIModel

RollForwardStatus = Literal["queued", "running", "completed", "failed"]


class RollForwardSummary(APIModel):
    """What a finished roll-forward produced."""

    census_year: int = Field(..., description="Year of the original census")
    bridge_year: int = Field(..., description="Year the census was rolled to")
    hires: int = Field(..., description="Hires in the bridge years")
    terminations: int = Field(..., description="Terminations in the bridge years")
    ending_headcount: int = Field(..., description="Employees in the bridge census")
    simulated_employees: int = Field(
        ..., description="Bridge census employees the simulation hired"
    )
    census_path: str = Field(..., description="The saved bridge census")


class RollForwardJob(APIModel):
    """A roll-forward run for one workspace."""

    id: str
    workspace_id: str
    bridge_year: int
    status: RollForwardStatus
    submitted_at: datetime
    completed_at: Optional[datetime] = None
    summary: Optional[RollForwardSummary] = None
    error_message: Optional[str] = None


class CensusStatus(APIModel):
    """Whether the workspace census is behind its simulation start."""

    census_year: Optional[int] = Field(
        None, description="Census year, or null when it can't be read"
    )
    start_year: int = Field(..., description="Workspace simulation start year")
    behind: bool = Field(
        ..., description="The census is more than one year before the start year"
    )
    bridge_year: Optional[int] = Field(
        None, description="The year a roll-forward would reach (start year - 1)"
    )
    active_job: Optional[RollForwardJob] = Field(
        None, description="A roll-forward still queued or running"
    )
