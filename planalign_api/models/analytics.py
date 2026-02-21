"""Analytics models for DC Plan contribution analysis."""

from typing import Dict, List

from pydantic import BaseModel, Field


class ContributionYearSummary(BaseModel):
    """Contribution summary for a single year."""

    year: int = Field(description="Simulation year")
    total_employee_contributions: float = Field(description="Total employee deferrals")
    total_employer_match: float = Field(description="Total employer match contributions")
    total_employer_core: float = Field(description="Total employer core contributions")
    total_all_contributions: float = Field(description="Total of all contributions")
    participant_count: int = Field(description="Number of enrolled participants")
    # E104: New fields for cost comparison
    average_deferral_rate: float = Field(
        default=0.0, description="Average deferral rate for enrolled participants"
    )
    participation_rate: float = Field(
        default=0.0, description="Participation rate for this year (0-100%)"
    )
    total_employer_cost: float = Field(
        default=0.0, description="Sum of match and core contributions"
    )
    # E013: Employer cost ratio metrics
    total_compensation: float = Field(
        default=0.0, description="Sum of prorated_annual_compensation for all active employees"
    )
    employer_cost_rate: float = Field(
        default=0.0, description="Employer cost as percentage of total compensation"
    )


class DeferralRateBucket(BaseModel):
    """Deferral rate distribution bucket."""

    bucket: str = Field(description="Deferral rate bucket (e.g., '0%', '1%', '10%+')")
    count: int = Field(description="Number of employees in this bucket")
    percentage: float = Field(description="Percentage of enrolled employees")


class DeferralDistributionYear(BaseModel):
    """Deferral rate distribution for a specific simulation year."""

    year: int = Field(description="Simulation year")
    distribution: List[DeferralRateBucket] = Field(
        description="11-bucket deferral rate distribution for this year"
    )


class ParticipationByMethod(BaseModel):
    """Participation breakdown by enrollment method."""

    auto_enrolled: int = Field(description="Auto-enrolled employees")
    voluntary_enrolled: int = Field(description="Voluntarily enrolled employees")
    census_enrolled: int = Field(description="Census/baseline enrolled employees")


class EscalationMetrics(BaseModel):
    """Deferral escalation metrics."""

    employees_with_escalations: int = Field(description="Employees who received escalations")
    avg_escalation_count: float = Field(description="Average number of escalations per employee")
    total_escalation_amount: float = Field(description="Total rate increase from escalations")


class IRSLimitMetrics(BaseModel):
    """IRS contribution limit metrics."""

    employees_at_irs_limit: int = Field(description="Employees who hit IRS 402(g) limit")
    irs_limit_rate: float = Field(description="Percentage of participants at limit")


class DCPlanAnalytics(BaseModel):
    """Complete DC Plan analytics for a scenario."""

    scenario_id: str = Field(description="Scenario identifier")
    scenario_name: str = Field(description="Scenario display name")

    # Participation summary
    total_eligible: int = Field(description="Total eligible employees")
    total_enrolled: int = Field(description="Total enrolled employees")
    participation_rate: float = Field(description="Participation rate (0-100%)")
    participation_by_method: ParticipationByMethod = Field(
        description="Breakdown by enrollment method"
    )

    # Contribution totals by year
    contribution_by_year: List[ContributionYearSummary] = Field(
        description="Year-by-year contribution summary"
    )

    # Grand totals (sum across all years)
    total_employee_contributions: float = Field(
        description="Grand total employee contributions"
    )
    total_employer_match: float = Field(description="Grand total employer match")
    total_employer_core: float = Field(description="Grand total employer core")
    total_all_contributions: float = Field(description="Grand total all contributions")

    # Deferral rate distribution (11 buckets: 0%, 1%, 2%...9%, 10%+)
    deferral_rate_distribution: List[DeferralRateBucket] = Field(
        description="Deferral rate distribution buckets"
    )

    # Per-year deferral rate distributions (E059)
    deferral_distribution_by_year: List[DeferralDistributionYear] = Field(
        default_factory=list,
        description="Per-year deferral rate distributions for all simulation years",
    )

    # Escalation metrics
    escalation_metrics: EscalationMetrics = Field(description="Escalation statistics")

    # IRS limit stats
    irs_limit_metrics: IRSLimitMetrics = Field(description="IRS limit statistics")

    # E104: New fields for cost comparison
    average_deferral_rate: float = Field(
        default=0.0, description="Average deferral rate across all enrolled participants"
    )
    total_employer_cost: float = Field(
        default=0.0, description="Grand total employer cost (match + core)"
    )
    # E013: Employer cost ratio metrics
    total_compensation: float = Field(
        default=0.0, description="Sum of prorated_annual_compensation across all years"
    )
    employer_cost_rate: float = Field(
        default=0.0, description="Aggregate employer cost as percentage of total compensation"
    )


class DCPlanComparisonResponse(BaseModel):
    """Response for comparing DC Plan analytics across scenarios."""

    scenarios: List[str] = Field(description="List of scenario IDs in comparison")
    scenario_names: Dict[str, str] = Field(description="Scenario ID to name mapping")
    analytics: List[DCPlanAnalytics] = Field(
        description="Analytics for each scenario"
    )
