"""Allowlisted aggregate SQL for canonical evidence-pack metrics."""

from __future__ import annotations

from dataclasses import dataclass

from planalign_ensemble.models import METRIC_REGISTRY


@dataclass(frozen=True)
class DriverDefinition:
    id: str
    label: str
    description: str
    population_label: str


DRIVER_REGISTRY: dict[str, tuple[DriverDefinition, ...]] = {
    "active_headcount": (
        DriverDefinition(
            "new_active_records",
            "New active records",
            "Active records present only in the target year.",
            "target-only active records",
        ),
        DriverDefinition(
            "removed_active_records",
            "Removed active records",
            "Active records present only in the base year.",
            "base-only active records",
        ),
        DriverDefinition(
            "retained_became_active",
            "Retained records becoming active",
            "Retained records whose status became active.",
            "retained inactive-to-active records",
        ),
        DriverDefinition(
            "retained_ceased_active",
            "Retained records ceasing active",
            "Retained records whose status ceased to be active.",
            "retained active-to-inactive records",
        ),
    ),
    "total_compensation": (
        DriverDefinition(
            "entered_population_compensation",
            "Entered population compensation",
            "Target compensation for records entering the snapshot population.",
            "entering records",
        ),
        DriverDefinition(
            "left_population_compensation",
            "Left population compensation",
            "Base compensation removed with records leaving the snapshot population.",
            "leaving records",
        ),
        DriverDefinition(
            "retained_compensation_and_proration",
            "Retained compensation and proration",
            "Compensation, promotion, and partial-year movement for retained records.",
            "retained records",
        ),
    ),
    "employer_match_cost": (
        DriverDefinition(
            "entered_population_cost",
            "Entered population cost",
            "Target match cost for entering records.",
            "entering records",
        ),
        DriverDefinition(
            "left_population_cost",
            "Left population cost",
            "Base match cost removed with leaving records.",
            "leaving records",
        ),
        DriverDefinition(
            "retained_compensation_exposure",
            "Retained compensation exposure",
            "Symmetric compensation-exposure effect among retained records.",
            "retained records",
        ),
        DriverDefinition(
            "retained_effective_match_payout_rate",
            "Retained effective match payout rate",
            "Symmetric change in the realized match-to-compensation rate.",
            "retained records",
        ),
    ),
    "total_employer_plan_cost": (
        DriverDefinition(
            "entered_population_cost",
            "Entered population cost",
            "Target employer contribution cost for entering records.",
            "entering records",
        ),
        DriverDefinition(
            "left_population_cost",
            "Left population cost",
            "Base employer contribution cost removed with leaving records.",
            "leaving records",
        ),
        DriverDefinition(
            "retained_compensation_exposure",
            "Retained compensation exposure",
            "Symmetric compensation-exposure effect among retained records.",
            "retained records",
        ),
        DriverDefinition(
            "retained_effective_plan_payout_rate",
            "Retained effective plan payout rate",
            "Symmetric change in the realized employer-contribution-to-compensation rate.",
            "retained records",
        ),
    ),
    "participation_rate": (
        DriverDefinition(
            "retained_participation_behavior",
            "Retained participation behavior",
            "Participation-status changes among retained records.",
            "retained records",
        ),
        DriverDefinition(
            "entered_population_participation",
            "Entered population participation",
            "Participating values contributed by entering records.",
            "entering records",
        ),
        DriverDefinition(
            "left_population_participation",
            "Left population participation",
            "Participating values removed with leaving records.",
            "leaving records",
        ),
        DriverDefinition(
            "population_reweighting",
            "Population reweighting",
            "Symmetric denominator effect from population-size change.",
            "base-to-target population",
        ),
    ),
    "avg_deferral_rate": (
        DriverDefinition(
            "retained_deferral_behavior",
            "Retained deferral behavior",
            "Deferral-rate changes among retained non-null records.",
            "retained records",
        ),
        DriverDefinition(
            "entered_population_deferral",
            "Entered population deferral",
            "Deferral values contributed by entering records.",
            "entering records",
        ),
        DriverDefinition(
            "left_population_deferral",
            "Left population deferral",
            "Deferral values removed with leaving records.",
            "leaving records",
        ),
        DriverDefinition(
            "population_reweighting",
            "Population reweighting",
            "Symmetric denominator effect from population-size change.",
            "base-to-target population",
        ),
    ),
}


def build_metric_query(
    metric: str,
    base_year: int,
    target_year: int,
    columns: frozenset[str] | None = None,
) -> str:
    """Return one deterministic, directly executable aggregate statement."""
    if metric not in METRIC_REGISTRY:
        raise ValueError(f"Unsupported canonical metric: {metric}")
    if base_year >= target_year:
        raise ValueError("base_year must be earlier than target_year")
    body = _metric_body(metric)
    available = columns or frozenset(
        {
            "employment_status",
            "prorated_annual_compensation",
            "employer_match_amount",
            "total_employer_contributions",
            "participation_status",
            "current_deferral_rate",
        }
    )
    active = (
        "LOWER(employment_status) = 'active'"
        if "employment_status" in available
        else "NULL::BOOLEAN"
    )
    compensation = _decimal_source("prorated_annual_compensation", available)
    match_cost = _decimal_source("employer_match_amount", available)
    plan_cost = _decimal_source("total_employer_contributions", available)
    participating = (
        "CASE WHEN LOWER(participation_status) = 'participating' THEN CAST(1 AS DECIMAL(38,12)) ELSE CAST(0 AS DECIMAL(38,12)) END"
        if "participation_status" in available
        else "NULL::DECIMAL(38,12)"
    )
    deferral = _decimal_source("current_deferral_rate", available)
    drivers = DRIVER_REGISTRY[metric]
    contribution_columns = ",\n    ".join(
        f"CAST({driver.id} AS DECIMAL(38,12)) AS {driver.id}_contribution"
        for driver in drivers
    )
    population_columns = ",\n    ".join(
        f"CAST({driver.id}_population AS DECIMAL(38,12)) AS {driver.id}_population"
        for driver in drivers
    )
    share_columns = ",\n    ".join(
        f"CAST(CASE WHEN shares_suppressed THEN NULL ELSE 100 * {driver.id} / total_change END AS DECIMAL(38,12)) AS {driver.id}_share"
        for driver in drivers
    )
    named_sum = " + ".join(f"COALESCE({driver.id}, 0)" for driver in drivers)
    return f"""WITH
base AS (
  SELECT
    employee_id,
    {active} AS active,
    {compensation} AS compensation,
    {match_cost} AS match_cost,
    {plan_cost} AS plan_cost,
    {participating} AS participating,
    {deferral} AS deferral
  FROM fct_workforce_snapshot
  WHERE simulation_year = {base_year}
),
target AS (
  SELECT
    employee_id,
    {active} AS active,
    {compensation} AS compensation,
    {match_cost} AS match_cost,
    {plan_cost} AS plan_cost,
    {participating} AS participating,
    {deferral} AS deferral
  FROM fct_workforce_snapshot
  WHERE simulation_year = {target_year}
),
cohorts AS (
  SELECT
    base.employee_id IS NOT NULL AS in_base,
    target.employee_id IS NOT NULL AS in_target,
    base.active AS base_active, target.active AS target_active,
    base.compensation AS base_compensation, target.compensation AS target_compensation,
    base.match_cost AS base_match_cost, target.match_cost AS target_match_cost,
    base.plan_cost AS base_plan_cost, target.plan_cost AS target_plan_cost,
    base.participating AS base_participating, target.participating AS target_participating,
    base.deferral AS base_deferral, target.deferral AS target_deferral
  FROM base FULL OUTER JOIN target USING (employee_id)
),
metric_values AS (
{body}
),
reconciled AS (
  SELECT *,
    target_value - base_value AS total_change,
    (((target_value < 0 AND base_value > 0) OR (target_value > 0 AND base_value < 0)) OR ABS(target_value - base_value) <= share_tolerance) AS shares_suppressed
  FROM metric_values
),
final_values AS (
  SELECT *, total_change - ({named_sum}) AS residual_contribution
  FROM reconciled
)
SELECT
    CAST(base_value AS DECIMAL(38,12)) AS base_value,
    CAST(target_value AS DECIMAL(38,12)) AS target_value,
    CAST(total_change AS DECIMAL(38,12)) AS total_change,
    {contribution_columns},
    {share_columns},
    {population_columns},
    CAST(residual_contribution AS DECIMAL(38,12)) AS residual_contribution,
    CAST(CASE WHEN shares_suppressed THEN NULL ELSE 100 * residual_contribution / total_change END AS DECIMAL(38,12)) AS residual_share
FROM final_values"""


def _decimal_source(column: str, columns: frozenset[str]) -> str:
    if column not in columns:
        return "NULL::DECIMAL(38,12)"
    return f"CAST({column} AS DECIMAL(38,12))"


def _metric_body(metric: str) -> str:
    if metric == "active_headcount":
        return _active_body()
    if metric == "total_compensation":
        return _sum_body("compensation", "compensation_and_proration")
    if metric in {"employer_match_cost", "total_employer_plan_cost"}:
        column = "match_cost" if metric == "employer_match_cost" else "plan_cost"
        rate_id = "match" if metric == "employer_match_cost" else "plan"
        return _cost_body(column, rate_id)
    if metric == "participation_rate":
        return _ratio_body("participating", "participation")
    return _ratio_body("deferral", "deferral", nonnull=True)


def _active_body() -> str:
    return """  SELECT
    CAST(COUNT(*) FILTER (WHERE in_base AND base_active) AS DECIMAL(38,12)) AS base_value,
    CAST(COUNT(*) FILTER (WHERE in_target AND target_active) AS DECIMAL(38,12)) AS target_value,
    CAST(COUNT(*) FILTER (WHERE NOT in_base AND in_target AND target_active) AS DECIMAL(38,12)) AS new_active_records,
    -CAST(COUNT(*) FILTER (WHERE in_base AND NOT in_target AND base_active) AS DECIMAL(38,12)) AS removed_active_records,
    CAST(COUNT(*) FILTER (WHERE in_base AND in_target AND NOT base_active AND target_active) AS DECIMAL(38,12)) AS retained_became_active,
    -CAST(COUNT(*) FILTER (WHERE in_base AND in_target AND base_active AND NOT target_active) AS DECIMAL(38,12)) AS retained_ceased_active,
    CAST(COUNT(*) FILTER (WHERE NOT in_base AND in_target AND target_active) AS DECIMAL(38,12)) AS new_active_records_population,
    CAST(COUNT(*) FILTER (WHERE in_base AND NOT in_target AND base_active) AS DECIMAL(38,12)) AS removed_active_records_population,
    CAST(COUNT(*) FILTER (WHERE in_base AND in_target AND NOT base_active AND target_active) AS DECIMAL(38,12)) AS retained_became_active_population,
    CAST(COUNT(*) FILTER (WHERE in_base AND in_target AND base_active AND NOT target_active) AS DECIMAL(38,12)) AS retained_ceased_active_population,
    CAST(0 AS DECIMAL(38,12)) AS share_tolerance
  FROM cohorts"""


def _sum_body(column: str, suffix: str) -> str:
    return f"""  SELECT
    SUM(base_{column}) FILTER (WHERE in_base) AS base_value,
    SUM(target_{column}) FILTER (WHERE in_target) AS target_value,
    COALESCE(SUM(target_{column}) FILTER (WHERE NOT in_base AND in_target), 0) AS entered_population_{column},
    -COALESCE(SUM(base_{column}) FILTER (WHERE in_base AND NOT in_target), 0) AS left_population_{column},
    COALESCE(SUM(COALESCE(target_{column}, 0) - COALESCE(base_{column}, 0)) FILTER (WHERE in_base AND in_target), 0) AS retained_{suffix},
    CAST(COUNT(*) FILTER (WHERE NOT in_base AND in_target) AS DECIMAL(38,12)) AS entered_population_{column}_population,
    CAST(COUNT(*) FILTER (WHERE in_base AND NOT in_target) AS DECIMAL(38,12)) AS left_population_{column}_population,
    CAST(COUNT(*) FILTER (WHERE in_base AND in_target) AS DECIMAL(38,12)) AS retained_{suffix}_population,
    CAST(0.01 AS DECIMAL(38,12)) AS share_tolerance
  FROM cohorts"""


def _cost_body(column: str, rate_id: str) -> str:
    return f"""  WITH totals AS (
    SELECT
      SUM(base_{column}) FILTER (WHERE in_base) AS base_value,
      SUM(target_{column}) FILTER (WHERE in_target) AS target_value,
      COALESCE(SUM(target_{column}) FILTER (WHERE NOT in_base AND in_target), 0) AS entered_population_cost,
      -COALESCE(SUM(base_{column}) FILTER (WHERE in_base AND NOT in_target), 0) AS left_population_cost,
      COALESCE(SUM(base_compensation) FILTER (WHERE in_base AND in_target), 0) AS c0,
      COALESCE(SUM(target_compensation) FILTER (WHERE in_base AND in_target), 0) AS c1,
      COALESCE(SUM(base_{column}) FILTER (WHERE in_base AND in_target), 0) AS x0,
      COALESCE(SUM(target_{column}) FILTER (WHERE in_base AND in_target), 0) AS x1,
      COUNT(*) FILTER (WHERE NOT in_base AND in_target) AS entering_count,
      COUNT(*) FILTER (WHERE in_base AND NOT in_target) AS leaving_count,
      COUNT(*) FILTER (WHERE in_base AND in_target) AS retained_count
    FROM cohorts
  )
  SELECT base_value, target_value, entered_population_cost, left_population_cost,
    CASE WHEN c0 = 0 OR c1 = 0 THEN NULL ELSE (c1 - c0) * ((x0 / c0) + (x1 / c1)) / 2 END AS retained_compensation_exposure,
    CASE WHEN c0 = 0 OR c1 = 0 THEN NULL ELSE ((x1 / c1) - (x0 / c0)) * (c0 + c1) / 2 END AS retained_effective_{rate_id}_payout_rate,
    CAST(entering_count AS DECIMAL(38,12)) AS entered_population_cost_population,
    CAST(leaving_count AS DECIMAL(38,12)) AS left_population_cost_population,
    CAST(retained_count AS DECIMAL(38,12)) AS retained_compensation_exposure_population,
    CAST(retained_count AS DECIMAL(38,12)) AS retained_effective_{rate_id}_payout_rate_population,
    CAST(0.01 AS DECIMAL(38,12)) AS share_tolerance
  FROM totals"""


def _ratio_body(column: str, stem: str, *, nonnull: bool = False) -> str:
    base_member = f"in_base AND base_{column} IS NOT NULL" if nonnull else "in_base"
    target_member = (
        f"in_target AND target_{column} IS NOT NULL" if nonnull else "in_target"
    )
    retained = f"({base_member}) AND ({target_member})"
    entered = f"NOT ({base_member}) AND ({target_member})"
    left = f"({base_member}) AND NOT ({target_member})"
    return f"""  WITH totals AS (
    SELECT
      COUNT(*) FILTER (WHERE {base_member}) AS n0,
      COUNT(*) FILTER (WHERE {target_member}) AS n1,
      COALESCE(SUM(base_{column}) FILTER (WHERE {base_member}), 0) AS s0,
      COALESCE(SUM(target_{column}) FILTER (WHERE {target_member}), 0) AS s1,
      COALESCE(SUM(target_{column} - base_{column}) FILTER (WHERE {retained}), 0) AS retained_delta,
      COALESCE(SUM(target_{column}) FILTER (WHERE {entered}), 0) AS entered_sum,
      COALESCE(SUM(base_{column}) FILTER (WHERE {left}), 0) AS left_sum,
      COUNT(*) FILTER (WHERE {retained}) AS retained_count,
      COUNT(*) FILTER (WHERE {entered}) AS entered_count,
      COUNT(*) FILTER (WHERE {left}) AS left_count
    FROM cohorts
  ), factors AS (
    SELECT *, CASE WHEN n0 = 0 OR n1 = 0 THEN NULL ELSE (CAST(1 AS DECIMAL(38,12)) / n0 + CAST(1 AS DECIMAL(38,12)) / n1) / 2 END AS w
    FROM totals
  )
  SELECT
    CASE WHEN n0 = 0 THEN NULL ELSE s0 / n0 END AS base_value,
    CASE WHEN n1 = 0 THEN NULL ELSE s1 / n1 END AS target_value,
    w * retained_delta AS retained_{stem}_behavior,
    w * entered_sum AS entered_population_{stem},
    -w * left_sum AS left_population_{stem},
    CASE WHEN w IS NULL THEN NULL ELSE (s0 + s1) * (CAST(1 AS DECIMAL(38,12)) / n1 - CAST(1 AS DECIMAL(38,12)) / n0) / 2 END AS population_reweighting,
    CAST(retained_count AS DECIMAL(38,12)) AS retained_{stem}_behavior_population,
    CAST(entered_count AS DECIMAL(38,12)) AS entered_population_{stem}_population,
    CAST(left_count AS DECIMAL(38,12)) AS left_population_{stem}_population,
    CAST(n1 AS DECIMAL(38,12)) AS population_reweighting_population,
    CAST(0.000001 AS DECIMAL(38,12)) AS share_tolerance
  FROM factors"""


__all__ = ["DRIVER_REGISTRY", "DriverDefinition", "build_metric_query"]
